import itertools
import json
import re
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta
from enum import Enum
from itertools import zip_longest
from threading import Timer
from typing import Any, List, Optional, Dict, Iterable, Set, Tuple, Sequence

import sentry_sdk
from telegram import ParseMode, TelegramError, Update, CallbackQuery, Message, ChatPermissions, InputTextMessageContent, \
    InlineQueryResultArticle
from telegram.error import BadRequest
from telegram.ext import CallbackContext, Updater

from . import partyamt
from .calendar import Calendar
from .chat import Chat, ChatType, User, Keyboard
from .cocktails import get_cocktails
from .config import Config
from .decorators import Command
from .event import Event
from .insult import Insult
from .logger import create_logger


def grouper(iterable, n, fillvalue=None) -> Iterable[Tuple[Any, Any]]:
    """Collect data into fixed-length chunks or blocks"""
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


class SpamType(Enum):
    NONE = 0
    CONSECUTIVE = 1
    DIFFERENT = 2
    SAME = 3


class Bot:
    def __init__(self, updater: Updater):
        self.chats: Dict[str, Chat] = {}
        self.updater = updater
        self.state: Dict[str, Any] = {
            "main_id": None
        }
        self.calendar = Calendar()
        self.logger = create_logger("regular_dicers_bot")
        self.config = Config("config.json")

    @Command()
    def show_dice(self, update: Update, context: CallbackContext) -> Optional[Message]:
        chat: Chat = context.chat_data["chat"]
        return chat.show_dice()

    @Command(main_admin=True)
    def show_dice_keyboards(self, update: Optional[Update], context: Optional[CallbackContext]) -> None:
        for chat_id in self.chats.keys():
            self.hide_attend(chat_id)
            if context:
                self.show_dice(update, context)
            elif chat_id in self.chats:
                self.chats.get(chat_id).show_dice()
            else:
                self.logger.warning(
                    f"Can't show keyboard for {chat_id}, `context` is `None` and `chat_id` is not in `self.chats`.")

    def hide_attend(self, chat_id: str) -> bool:
        chat: Chat = self.chats[chat_id]
        return chat.hide_attend()

    def save_state(self) -> None:
        self.state["chats"] = [chat.serialize() for chat in self.chats.values()]
        with open("state.json", "w+") as f:
            json.dump(self.state, f)

    @Command(chat_admin=True)
    def delete_chat(self, update: Update, context: CallbackContext) -> None:
        chat: Chat = context.chat_data["chat"]

        if chat.id in self.chats:
            self.logger.info(f"Deleting chat ({chat}) from state.")
            del self.chats[chat.id]
            del context.chat_data["chat"]

    @Command()
    def register_main(self, update: Update, context: CallbackContext) -> Message:
        self.logger.info("Register main")
        chat: Chat = context.chat_data["chat"]
        user: User = context.user_data["user"]

        if not self.state.get("main_id", ""):
            self.logger.debug("main_id is not present")
            self.state["main_id"] = chat.id
            message = "You have been registered as the main chat."
            self.logger.info(f"Main chat ({chat.id}) has been registered")
        else:
            self.logger.debug("main_id is present")
            if chat.id == self.state.get("main_id", ""):
                self.logger.debug("User tries to register a main_chat despite of this chat already being the main chat")
                until_date = timedelta(hours=2)
                self.mute_user(chat.id, user, until_date=until_date,
                               reason="Tried to register this chat (which is the main chat) as the main chat")
                message = "You are the main chat already."
            else:
                self.logger.debug("User tries to register a main_chat despite of there being an existing one")
                message = "You can't register as the main chat, since there already is one."

        return update.effective_message.reply_text(text=message)

    @Command(main_admin=True)
    def unregister_main(self, update: Update, context: CallbackContext) -> Message:
        self.logger.info("Unregistering main chat")
        self.state["main_id"] = None

        return update.effective_message.reply_text(text="You've been unregistered as the main chat")

    def set_user_restriction(self, chat_id: str, user: User, until_date: timedelta, permissions: ChatPermissions,
                             reason: str = None) -> bool:
        timestamp: int = int((datetime.now() + until_date).timestamp())
        try:
            result: bool = self.updater.bot.restrict_chat_member(chat_id, user.id, permissions, until_date=timestamp)
            if not permissions.can_send_messages:
                datestring: str = str(until_date).rsplit(".")[0]  # str(timedelta) -> [D day[s], ][H]H:MM:SS[.UUUUUU]
                message = f"{user.name} has been restricted for {datestring}."
                if reason:
                    message += f"\nReason: {reason}"
                self.updater.bot.send_message(chat_id=chat_id,
                                              text=message, disable_notification=True)
        except TelegramError as e:
            if e.message == "Can't demote chat creator" and not permissions.can_send_messages:
                message = "Sadly, user {} couldn't be restricted due to: `{}`. Shame on {}".format(user.name,
                                                                                                   e.message,
                                                                                                   user.name)
                self.logger.debug("{}".format(message))
                self.updater.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.MARKDOWN)
            self.logger.error(e)
            result = False

        return result

    def unmute_user(self, chat_id: str, user: User) -> bool:
        result = False
        permissions = ChatPermissions(can_send_messages=True, can_send_media_messages=True,
                                      can_send_other_messages=True, can_add_web_page_previews=True)

        try:
            # if self.updater.bot.promote_chat_member(chat_id, user.id, can_post_messages=True):
            if self.set_user_restriction(chat_id, user, timedelta(minutes=0), permissions):
                user.muted = False
                result = True
            else:
                self.logger.error("Failed to unmute user")
        except TelegramError:
            self.logger.error("Error while promoting chat member", exc_info=True)

        return result

    def mute_user(self, chat_id: str, user: User, until_date: timedelta, reason: Optional[str] = None) -> bool:
        if user.muted:
            return True

        permissions = ChatPermissions(can_send_messages=False)
        result = False
        self.logger.info(f"Reason for muting: {reason}")
        if self.set_user_restriction(chat_id, user, until_date=until_date, reason=reason, permissions=permissions):
            user.muted = True
            result = True

            # We'd need to parse the exception before assigning user.muted differently
            def _set_user_unmute():
                user.muted = False

            self.logger.info(f"Set timer for {until_date.total_seconds()}s to set user mute state to `False`")
            Timer(until_date.total_seconds(), _set_user_unmute).start()

        return result

    # noinspection PyUnusedLocal
    @Command(main_admin=True)
    def remind_users(self, update: Optional[Update], context: Optional[CallbackContext]) -> bool:
        result = True
        for chat in self.chats.values():
            try:
                if not chat.show_attend_keyboard():
                    result = False
            except TelegramError:
                self.logger.error(f"Failed to reset chat {chat}", exc_info=True)
                result = False

        return result

    @Command()
    def handle_attend_callback(self, update: Update, context: CallbackContext) -> bool:
        callback: CallbackQuery = update.callback_query
        chat: Chat = context.chat_data["chat"]
        user = context.user_data["user"]

        chat.set_attend_callback(callback)

        user_has_voted_already = (user in chat.current_event.attendees) or (user in chat.current_event.absentees)

        def _mute_user_if_absent() -> None:
            if user in chat.current_event.absentees:
                insult = Insult.random().text
                if "{username}" in insult:
                    insult = insult.replace("{username}", user.name)

                time_to_mute: timedelta = datetime.now().replace(hour=21, minute=0, second=0) - datetime.now()

                if time_to_mute.days >= 0:
                    self.mute_user(chat.id, user, time_to_mute, reason=insult)

        attendees = chat.current_event.attendees

        attends = callback.data == "attend_True"
        if attends:
            chat.current_event.add_attendee(user)

            if chat.current_event.remote_created:
                self.calendar.create()
                partyamt.add_event()
                chat.current_event.remote_created = True

            self.unmute_user(chat.id, user)
        else:
            if user in attendees and user.roll != -1:
                self.logger.debug(f"User {user.name} with roll tried to unattend.")
                message = f"You ({user.name}) can't unattend after adding your roll."
                self.send_message(chat_id=chat.id, text=message)

                return False

            chat.current_event.add_absentee(user)
            try:
                self.logger.info("Give user time to explain himself (15m), mute him afterwards.")
                Timer(15 * 60, _mute_user_if_absent).start()
                chat.current_event.remove_attendee(user)
            except KeyError as e:
                sentry_sdk.capture_exception()
                self.logger.exception(e, exc_info=True)

            if chat.current_keyboard == Keyboard.DICE:
                chat.update_dice_message()

        try:
            chat.update_attend_message()
        except Exception as e:
            sentry_sdk.capture_exception()
            self.logger.exception(e, exc_info=True)

        if not user_has_voted_already:
            vote_count: int = len(chat.current_event.attendees) + len(chat.current_event.absentees)
            if len(chat.users) == vote_count and vote_count > 1:
                self.send_message(chat_id=chat.id, text="Alle haben abgestimmt.")
            else:
                self.logger.debug(f"Not everyone has voted yet ({vote_count} < {len(chat.users)})"
                                  f" or only one user present ({len(chat.users) == 1})")
        else:
            self.logger.debug(f"{user.name} has already voted")

        return True

    @Command()
    def handle_dice_callback(self, update: Update, context: CallbackContext) -> None:
        callback: CallbackQuery = update.callback_query
        chat: Chat = context.chat_data["chat"]
        user = chat.get_user_by_id(update.effective_user.id)

        chat.set_dice_callback(callback)

        attendees: Set[User] = chat.current_event.attendees

        if user.id not in [user.id for user in attendees]:
            self.logger.debug("User {} is not in attendees list".format(user.name))
            message = f"You ({user.name}) are not attending this event, you can't roll a dice yet."

            if not user.muted:
                self.send_message(chat_id=chat.id, text=message)
                self.mute_user(chat.id, user, timedelta(hours=1), reason="I fucking told you")

            callback.answer()
            return

        attendee = [attendee for attendee in attendees if attendee.id == user.id][0]

        data = re.match("dice_(.*)", callback.data).groups()[0]
        if data in map(str, range(1, 7)):
            attendee.set_roll(int(data))
        elif "alcoholic" in data:
            attendee.set_alcoholic("alcoholic" == data)
        else:
            attendee.set_jumbo(data == "+1")

        chat.update_dice_message()

    @Command()
    def remind_chat(self, update: Update, context: CallbackContext) -> bool:
        chat: Chat = context.chat_data["chat"]
        args: str = " ".join(context.args)

        self.logger.debug(f"Remind chat: {chat.id}")

        self.logger.info("Show attend keyboard for: {}".format(chat.id))

        result = self.chats[chat.id].show_attend_keyboard(args)

        self.logger.debug("Result if showing attend keyboard for {}: {}".format(chat.id, result))

        return bool(result)

    @Command(chat_admin=True)
    def reset(self, update: Update, context: CallbackContext) -> bool:
        chat = context.chat_data["chat"]
        self.logger.debug(f"Attempting to reset {chat.id}")
        message = "Reset has been performed successfully."
        result = True

        try:
            chat.reset()
            for user in chat.users:
                self.unmute_user(chat.id, user)
        except TelegramError:
            self.logger.warning(f"Could not reset for chat {chat.id}", exc_info=True)
            message = "Could not perform reset."
            result = False

        update.effective_message.reply_text(text=message)

        return result

    @Command(main_admin=True)
    def reset_all(self, update: Optional[Update], context: Optional[CallbackContext]) -> bool:
        self.logger.debug("Attempting to reset all chats")

        success = {}
        for chat in self.chats.values():
            message = "Reset has been performed successfully."
            try:
                chat.reset()
                success[chat.id] = True
            except TelegramError:
                success[chat.id] = False
                self.logger.warning(f"Could not reset for chat {chat.id}", exc_info=True)
                message = "Could not perform reset."

            if update:
                update.effective_message.reply_text(text=message)

        result = True
        if all(value for _, value in success.items()):
            message = "Success"
        else:
            message = "Failure for the following chats:\n{}".format(
                [chat_id for chat_id, suc in success.items() if not suc]
            )
            result = False

        if update:
            update.effective_message.reply_text(text=message, disable_notification=True)

        return result

    def check_for_spam(self, user: User, chat: Chat) -> SpamType:
        user_chat_messages = [message for message in user.messages if message.chat_id == chat.id]

        try:
            spam_type = self._check_user_spam(user_chat_messages, self.config.get("spam", {}))
        except IndexError:
            spam_type = SpamType.NONE

        spam_type_message = ""
        timeout = timedelta(seconds=30)
        if spam_type == SpamType.CONSECUTIVE:
            spam_type_message = "User has been muted due to being the only one sending messages (repeatedly)"
            timeout = timedelta(minutes=30)
        elif spam_type == SpamType.DIFFERENT:
            spam_type_message = f"User ({user}) has been muted for sending different messages in a short time"
            timeout = timedelta(hours=1)
        elif spam_type == SpamType.SAME:
            spam_type_message = f"User ({user}) is spamming the same message over and over again"
            timeout = timedelta(hours=2)
        else:
            self.logger.debug("User ({}) is not spamming".format(user))

        if spam_type_message:
            if not user.spamming:
                user.spamming = True
                self.logger.warning(spam_type_message)
                self.mute_user(chat.id, user, timeout, reason=spam_type_message)
        else:
            user.spamming = False

        return spam_type

    @staticmethod
    def _check_user_spam(user_messages: List[Message], spam_config: Dict[str, int]) -> SpamType:
        """

        :rtype: SpamType
        """
        logger = create_logger("_check_user_spam")

        consecutive_message_limit: int = spam_config.get("consecutive_message_limit", 8)
        consecutive_message_timeframe: int = spam_config.get("consecutive_message_timeframe", 5)
        same_message_limit: int = spam_config.get("same_message_limit", 3)
        same_message_timeframe: int = spam_config.get("same_message_timeframe", 2)
        different_message_limit: int = spam_config.get("different_message_limit", 15)
        different_message_timeframe: int = spam_config.get("different_message_timeframe", 2)
        check_timeframe: int = spam_config.get("check_timeframe", 60)

        user_messages = [message for message in user_messages if
                         ((datetime.now() - message.date).seconds * 60) <= check_timeframe]

        def is_consecutive(sorted_messages: Sequence[Optional[Message]]) -> bool:
            if None in sorted_messages:
                return False
            minimum = sorted_messages[0].message_id
            maximum = sorted_messages[-1].message_id

            return bool(sum([message.message_id for message in sorted_messages]) == maximum * (maximum + 1) / 2 - (
                    (minimum - 1) * (minimum / 2)))

        first = user_messages[0].date
        last = user_messages[-1].date
        if len(user_messages) > different_message_limit and last - first < timedelta(hours=different_message_timeframe):
            return SpamType.DIFFERENT

        groups = grouper(user_messages, consecutive_message_limit)
        for message_group in groups:
            if is_consecutive(message_group):
                first = message_group[0].date
                last = message_group[-1].date
                if last - first < timedelta(minutes=consecutive_message_timeframe):
                    return SpamType.CONSECUTIVE

        same_text_messages = Counter([message.text for message in user_messages])
        for message_text, count in same_text_messages.items():
            if count > same_message_limit:
                messages = list(filter(lambda m: m.text == message_text, user_messages))
                first = messages[0].date
                last = messages[-1].date
                if last - first < timedelta(hours=same_message_timeframe):
                    logger.debug("SpamType.SAME {}(x{})".format(message_text, count))
                    return SpamType.SAME

        return SpamType.NONE

    @Command()
    def handle_message(self, update: Update, context: CallbackContext) -> None:
        self.logger.info("Handle message: {}".format(update.effective_message.text))
        chat: Chat = context.chat_data["chat"]
        user: User = chat.get_user_by_id(update.effective_user.id)

        try:
            if chat.spam_detection:
                self.check_for_spam(user, chat)
        except Exception as e:
            sentry_sdk.capture_exception()
            self.logger.exception(e, exc_info=True)
        else:
            self.logger.debug("Handled message")

    @Command()
    def handle_left_chat_member(self, update: Update, context: CallbackContext) -> None:
        chat: Chat = context.chat_data["chat"]

        if update.effective_message.left_chat_member.id != self.updater.bot.id:
            try:
                user: User = [user for user in chat.users if user.id == update.effective_message.left_chat_member.id][0]
            except IndexError:
                self.logger.error("Couldn't find user in chat")
            else:
                chat.users.remove(user)
                update.effective_message.reply_text("Bye bye birdie")

    def set_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.state["main_id"] = self.state.get("main_id", "")
        self.chats = {schat["id"]: Chat.deserialize(schat, self.updater.bot) for schat in state.get("chats", [])}

    def send_message(self, *args, **kwargs) -> Message:
        return self.updater.bot.send_message(*args, **kwargs)

    @Command()
    def show_users(self, update: Update, context: CallbackContext) -> Optional[Message]:
        chat: Chat = context.chat_data["chat"]

        message = ""
        events: List[Event] = chat.events
        if chat.current_event:
            events += [chat.current_event]

        sorted_users: List[User] = sorted(chat.users, key=lambda _user: _user.name)
        for user in sorted_users:
            attendance_count = 0
            for event in events:
                if user in event.attendees:
                    attendance_count += 1

            message += f"\n{str(user)} ({attendance_count}/{len(chat.events)})"

        if not message:
            message = "No active users. Users need to write a message in the chat to be recognized (not just a command)"

        return self.send_message(chat_id=chat.id, text=message)

    @Command()
    def new_member(self, update: Update, context: CallbackContext) -> None:
        chat = context.chat_data["chat"]

        self.logger.info(f"New member(s) have joined this chat")

        for member in update.effective_message.new_chat_members:
            if member.id != self.updater.bot.id:
                chat.users.add(User.from_tuser(member))
                message = f"Welcome, fellow alcoholic [{member.first_name}](tg://user?id={member.id})"
                update.effective_message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    @Command(chat_admin=True)
    def enable_spam_detection(self, update: Update, context: CallbackContext) -> Message:
        chat = context.chat_data["chat"]
        chat.spam_detection = True
        self.logger.debug("Enabled spam detection")

        return update.message.reply_text("Spam detection has been enabled")

    @Command(chat_admin=True)
    def disable_spam_detection(self, update: Update, context: CallbackContext) -> Message:
        chat = context.chat_data["chat"]
        chat.spam_detection = False
        self.logger.debug("Disabled spam detection")

        return update.message.reply_text("Spam detection has been disabled")

    @Command()
    def status(self, update: Update, context: CallbackContext) -> Message:
        return update.effective_message.reply_text(text=f"{context.chat_data['chat']}")

    @Command()
    def version(self, update: Update, context: CallbackContext) -> Message:
        return update.effective_message.reply_text("{{VERSION}}")

    @Command()
    def server_time(self, update: Update, context: CallbackContext) -> Message:
        time = datetime.now().strftime("%d-%m-%Y %H-%M-%S")
        return update.effective_message.reply_text(time)

    @Command()
    def price_stats(self, update: Update, context: CallbackContext) -> Message:
        chat: Chat = context.chat_data["chat"]
        message = ""

        events: List[Event] = chat.events
        if chat.current_event:
            events += [chat.current_event]

        total_attendance = 0
        total_price = 0
        totals: Dict[User, Tuple[int, float, float]] = dict()
        for user in chat.users:
            total = 0
            attended = 0

            for event in user.get_attended_events(events):
                event_user: User = [euser for euser in event.attendees if euser == user][0]

                if event_user.roll > 0:
                    total += event_user.roll
                    total += 1 if event_user.jumbo else 0
                    attended += 1

            if attended == 0:
                continue

            average = total / attended
            totals[user] = (attended, total, average)
            total_attendance += attended
            total_price += total

        sorted_users = sorted(totals.items(), key=lambda item: item[1][2])
        for user, at_tuple in sorted_users:
            attended: int = at_tuple[0]
            total: float = at_tuple[1]
            average: float = at_tuple[2]
            message += f"\n{user.name}: `{total}`€/`{attended}` = `{average:.2f}`€"

        if total_attendance == 0:
            message = "There are no stats yet."
        else:
            message += f"\nTotal: `{total_price}`€/`{total_attendance}` = `{total_price / total_attendance:.2f}`€"

        return update.effective_message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    @Command()
    def get_data(self, update: Update, context: CallbackContext) -> Message:
        chat: Chat = context.chat_data["chat"]
        data = [_chat for _chat in self.state.get("chats", []) if _chat.get("id") == chat.id]

        if data:
            with tempfile.TemporaryFile() as temp:
                temp.write(json.dumps(data[0]).encode("utf-8"))
                temp.seek(0)
                return self.updater.bot.send_document(chat_id=chat.id, document=temp, filename=f"{chat.title}.json")
        else:
            return update.effective_message.reply_text("Couldn't find any data for this chat.")

    @Command()
    def add_insult(self, update: Update, context: CallbackContext) -> Message:
        text = " ".join(context.args)

        self.logger.debug(f"Add insult ({text}) from {context.user_data['user'].name}")
        if text and Insult.add(text):
            self.logger.debug("Insult added successfully")
            message = update.effective_message.reply_text("Successfully added new insult")
        else:
            self.logger.debug("Insult was not added")
            insult = Insult.random().text
            if "{username}" in insult:
                insult = insult.replace("{username}", update.effective_user.first_name)
            message = update.effective_message.reply_text(f"Not a new insult\n{insult}")

        return message

    @Command(chat_admin=True)
    def mute(self, update: Update, context: CallbackContext):
        if not context.args:
            message = "Please provide a user and an optional timeout (`/mute <user> [<timeout in minutes>] [<reason>]`)"
            self.logger.warning("No arguments have been provided, don't execute `mute`.")
            return self.updater.bot.send_message(chat_id=update.message.chat_id, text=message,
                                                 parse_mode=ParseMode.MARKDOWN)

        username = context.args[0]
        minutes = 15
        reason = " ".join(context.args[2:])

        try:
            minutes = int(context.args[1])
        except (IndexError, ValueError):
            sentry_sdk.capture_exception()
            self.logger.error("Exception while getting time string from mute command", exc_info=True)

        mute_time = timedelta(minutes=minutes)
        chat = context.chat_data["chat"]

        try:
            user = next(filter(lambda x: x.name == username, chat.users))
        except StopIteration:
            sentry_sdk.capture_exception()
            self.logger.warn(f"Couldn't find user {username} in users for chat {update.message.chat_id}", exc_info=True)
            update.effective_message.reply_text(f"Can't mute {username} (not found in current chat).")
        else:
            self.mute_user(update.message.chat_id, user, until_date=mute_time, reason=reason)

    @Command(chat_admin=True)
    def unmute(self, update: Update, context: CallbackContext):
        if not context.args:
            message = "You have to provide a user which should be unmuted."
            self.logger.warning("No arguments have been provided, don't execute `unmute`.")
            return update.effective_message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

        username: str = context.args[0].strip()
        chat: Chat = context.chat_data["chat"]

        # @all is an unusable username
        if username == "@all":
            for user in chat.users:
                try:
                    self.unmute_user(chat.id, user)
                except BadRequest:
                    self.logger.error(f"Failed to unmute user ({user})")

            return

        try:
            user = next(filter(lambda x: x.name.lower() == username.lower(), chat.users))
        except StopIteration:
            sentry_sdk.capture_exception()
            self.logger.warn(f"Couldn't find user {username} in users for chat {update.message.chat_id}", exc_info=True)
            update.effective_message.reply_text(f"Can't unmute {username} (not found in current chat).")
        else:
            if self.unmute_user(chat.id, user):
                update.effective_message.reply_text(f"Successfully unmuted {username}.")
            else:
                update.effective_message.reply_text(f"Failed to unmute {username}.")

    @Command()
    def set_cocktail(self, update: Update, context: CallbackContext):
        chat: Chat = context.chat_data["chat"]
        user: User = context.user_data["user"]

        if not chat.current_event:
            self.logger.debug("Someone tried `set_cocktail` outside of an active event")
            if not self.mute_user(chat.id, user, timedelta(minutes=15), reason="You can only set a cocktail during an active event"):
                return update.effective_message.reply_text("You can only set a cocktail during an active event")

        if not context.args:
            message = "You have to provide a cocktail name."
            self.logger.warning("No arguments have been provided, don't execute `set_cocktail`.")
            
            if not self.mute_user(chat.id, user, timedelta(hours=1), message + " #itoldyouso"):
                return update.effective_message.reply_text(f"[idiot](tg://user?id={user.id}) couldn't be muted", parse_mode=ParseMode.MARKDOWN)
            return

        argument = " ".join(context.args[:]).strip()
        cocktails = get_cocktails()

        try:
            drink_id = int(argument)
            drink_name = [cocktail.name for cocktail in cocktails if cocktail.id == drink_id][0]
        except (ValueError, IndexError):
            drink_name: str = argument
            if drink_name.lower() not in [cocktail.name.lower() for cocktail in cocktails]:
                return update.effective_message.reply_text(f"{argument} was not found in the list of cocktails")

        try:
            event_user: User = [event_user for event_user in chat.current_event.attendees if event_user.id == user.id][0]
        except IndexError:
            self.logger.debug("Couldn't find user in current event attendees")
            if not self.mute_user(chat.id, user, timedelta(minutes=15), "Tried to set a cocktail despite being absent."):
                return update.effective_message.reply_text("You can't set a cocktail while being absent")

    @Command()
    def list_insults(self, update: Update, context: CallbackContext):
        message = "\n".join([f"`{insult.text}`" for insult in Insult.read_all()])

        if not message:
            message = "There are no insults yet"

        update.effective_message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    @Command()
    def jesus(self, update: Update, context: CallbackContext):
        chat: Chat = context.chat_data["chat"]

        self.updater.bot.send_photo(chat.id, "https://lh3.googleusercontent.com/MoijEYIHHzGPbQ8qotmF0zLOIroLpgcaKTQ2--j-reu8Mc1NsTiPVB3S28oAFWo04LzwFb55TDTRSWsfR83a31NyMuS-9amZGt3qUmP9vswCFLQReKuP0G0z3m4ZijZSm_6_JEz_ix9t77vtd6qOZe5vkPObO8u8BgzOwrlKvmomOr7jmDuc3rapJdUOY5zZCp5pSf-58ZsoviBw5fliMy8N4QNPrygv6274dqBJVk4Fs-xjBhqmxGOApk9igv9H-J4wx-DDLsGMwSl-T4uORbdISUUMIOsZffw8TifSMsPkSMGb9GN720FJYgFyGr1tkwdC_YiuInYfs1Za30EBVWLkE2Mw9O4smX60_DDWp6RQlWCfx1qOlLWa1gP0dZZ4_5VCRxfbXH0zL-m4I0hPxtmJtBKcHQt1kn68jaXlHUlpUgl2MHvyamz4TWQUGOD1It-aShK6twXsQ-CQ-KxIs5Rc_fEQapVV5zqHouE4jVZdUoPdrHg0TAkeZV7kJItFn8uq8s51gjz3hoawwQVf6tmI4cyK_h5a1RAQFJtLl3kNBMvHmXbNOFr1wF8ei5eIqKFPK6Za5k-5qQCSubxQvwBD4Bb4wmYKeHlGmfakSV8Q7d9083ecbYcCVeqFZP_IZE_IKrWJphlfcOSGzfTznWERRqv1dAcBY8iyu7U7cSDIi53gayT-2jk=w1007-h1342-no")

    @Command()
    def handle_unknown_command(self, update: Update, context: CallbackContext):
        user: User = context.user_data["user"]
        chat: Chat = context.chat_data["chat"]

        reason = "This is not a valid command fuckwit."
        self.mute_user(chat_id=chat.id, user=user, until_date=timedelta(minutes=15), reason=reason)

    def kick_user(self, chat: Chat, user: User):
        return self.updater.bot.kick_chat_member(chat_id=chat.id, user_id=user.id)

    @Command(chat_admin=True)
    def kick(self, update: Update, context: CallbackContext):
        chat: Chat = context.chat_data["chat"]

        if not context.args:
            message = "Please provide a user and an optional reason(`/kick <user> [<reason>]`)"
            self.logger.warning("No arguments have been provided, don't execute `kick`.")
            return update.message.reply_text(text=message, parse_mode=ParseMode.MARKDOWN)

        username = context.args[0]
        reason = " ".join(context.args[1:])

        try:
            user: User = next(filter(lambda x: x.name == username, chat.users))
        except StopIteration:
            sentry_sdk.capture_exception()
            self.logger.warning(f"Couldn't find user {username} in users for chat {update.message.chat_id}",
                                exc_info=True)
            update.effective_message.reply_text(f"Can't kick {username} (not found in current chat).")
        else:
            try:
                result = self.kick_user(chat, user)
            except TelegramError as e:
                message = f"Couldn't remove {user.name} from chat due to error ({e})"
                self.logger.error(message)
                update.message.reply_text(message)
            else:
                if result:
                    message = f"{user.name} was kicked from chat"
                    message += f" due to {reason}." if reason else "."
                    self.logger.debug(message)
                    chat.users.remove(user)
                    update.message.reply_text(message)
                else:
                    message = f"{user.name} couldn't be kicked from chat"
                    self.logger.warning(message)
                    update.effective_message.reply_text(message)

    @Command()
    def list_cocktails(self, update: Update, context: CallbackContext):
        chat: Chat = context.chat_data["chat"]
        user: User = context.user_data["user"]

        if chat.type != ChatType.PRIVATE and chat.id != -1001204520396:
            self.logger.debug(f"{user.name} tried list_cocktails in a group chat")

            message = "This is only intended for private chats."
            if not self.mute_user(chat.id, user, until_date=timedelta(minutes=15), reason=message):
                update.effective_message.reply_text(message)

            return None

        messages = []
        for category, cocktails in itertools.groupby(get_cocktails(), key=lambda x: x.category):
            cocktails: List[str] = [f"({cocktail.id}) {str(cocktail)}" for cocktail in cocktails]

            split_messages: List[List[str]] = _split_messages([f"*{category}*\n{'‾' * len(category) * 2}"] + cocktails)
            for m in split_messages:
                messages.append("\n".join(m))

        if not messages:
            messages = ["Cocktails couldn't be fetched"]

        first = True
        for message in messages:
            self.send_message(chat_id=chat.id, text=message, parse_mode=ParseMode.MARKDOWN, disable_notification=first)
            first = False
            time.sleep(0.5)

    # @Command()
    def handle_inline_query(self, update: Update, context: CallbackContext):
        query = update.inline_query.query
        cocktails = get_cocktails()

        results = [
            InlineQueryResultArticle(
                id=cocktail.id,
                title=cocktail.name,
                input_message_content=InputTextMessageContent(
                    f"/set_cocktail {cocktail.name}"
                )
            )
            for cocktail in cocktails
            if query.lower() in cocktail.name.lower()
        ]

        update.inline_query.answer(results)


def _split_messages(lines):
    message_length = 1024
    messages = []
    current_length = 0
    current_message = 0
    for line in lines:
        if len(messages) <= current_message:
            messages.append([])

        line_length = len(line)
        if current_length + line_length < message_length:
            current_length += line_length
            messages[current_message].append(line)
        else:
            current_length = 0
            current_message += 1

    return messages
