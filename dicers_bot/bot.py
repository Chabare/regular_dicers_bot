import json
import re
from collections import Counter
from datetime import datetime, timedelta
from enum import Enum
from itertools import groupby, zip_longest
from threading import Timer
from typing import Any, List, Optional, Dict, Iterable

import sentry_sdk
from telegram import ParseMode, TelegramError, Update, CallbackQuery, Message
from telegram import User as TUser

from dicers_bot.chat import Chat, User, Keyboard
from dicers_bot.config import Config
from dicers_bot.decorators import admin
from .calendar import Calendar
from .logger import create_logger


def grouper(iterable, n, fillvalue=None):
    """Collect data into fixed-length chunks or blocks"""
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


class SpamType(Enum):
    NONE = 0
    CONSECUTIVE = 1
    DIFFERENT = 2
    SAME = 3


class Bot:
    def __init__(self, updater):
        self.chats: Dict[str, Chat] = {}
        self.updater = updater
        self.state: Dict = {
            "main_id": None
        }
        self.calendar = Calendar()
        self.logger = create_logger("regular_dicers_bot")
        self.config = Config("config.json")

    def show_dice(self, chat_id: str):
        chat = self.chats[chat_id]
        return chat.show_dice()

    def show_dice_keyboards(self):
        for chat_id in self.chats.keys():
            self.hide_attend(chat_id)
            self.show_dice(chat_id)

    def hide_attend(self, chat_id):
        chat: Chat = self.chats[chat_id]
        return chat.hide_attend()

    def save_state(self):
        self.state["chats"] = [chat.serialize() for chat in self.chats.values()]
        with open("state.json", "w+") as f:
            json.dump(self.state, f)

    def register(self, update: Update, send_response: bool = True) -> bool:
        self.logger.info("Register")
        chat_id = update.message.chat_id
        self.logger.info("Register: {}".format(chat_id))

        if chat_id in self.chats.keys():
            self.logger.info("Chat already registered")
            if send_response:
                self.updater.bot.send_message(chat_id=chat_id, text="Why would you register twice, dumbass!")
            return False

        self.logger.info("Chat is being registered")
        try:
            self.chats[chat_id] = Chat(chat_id, self.updater.bot)
            self.save_state()
        except Exception as e:
            sentry_sdk.capture_exception()
            self.logger.error(e)

        if send_response:
            self.logger.info("Chat successfully registered")
            self.updater.bot.send_message(chat_id=chat_id, text="You have been registered.")

        return True

    def unregister(self, update: Update) -> bool:
        chat_id = update.message.chat_id
        try:
            successful_removal = self.chats.pop(chat_id)
            if self.state.get("main_id", "") == chat_id:
                self.state["main_id"] = None
                self.save_state()
        except KeyError:
            successful_removal = False

        if not successful_removal:
            self.updater.bot.send_message(chat_id=chat_id, text="You weren't registered in the first place!")
        else:
            self.updater.bot.send_message(chat_id=chat_id, text="You have been unregistered.")

        return successful_removal

    def register_main(self, update: Update):
        self.logger.info("Register main")
        chat_id = update.message.chat_id
        if not self.state.get("main_id", ""):
            self.logger.debug("main_id is not present")
            _ = self.register(update, False)
            self.state["main_id"] = chat_id
            self.save_state()
            self.updater.bot.send_message(chat_id=chat_id, text="You have been registered as the main chat.")
        else:
            self.logger.debug("main_id is present")
            if chat_id == self.state.get("main_id", ""):
                self.logger.debug("User tries to register a main_chat despite of this chat already being the main chat")
                until_date = timedelta(hours=2)
                self.mute_user(chat_id, self._get_user_from_update(update), until_date=until_date,
                               reason="Tried to register a new main chat")
            else:
                self.logger.debug("User tries to register a main_chat despite of there being an existing one")
                self.updater.bot.send_message(chat_id=chat_id,
                                              text="You can't register as the main chat, since there already is one.")

        self.save_state()

    def _get_user_from_update(self, update: Update) -> Optional[User]:
        user = None
        chat = self.chats.get(update.message.chat_id)
        if chat and update.message:
            if not chat.get_user_by_id(update.message.from_user.id):
                user = User.from_tuser(update.message.from_user)
                chat.add_user(user)

        return user

    def set_user_restriction(self, chat_id: str, user: User, until_date: timedelta, **kwargs):
        timestamp: int = (datetime.now() + until_date).timestamp()
        try:
            result = self.updater.bot.restrict_chat_member(chat_id, user.id, until_date=timestamp,
                                                           **kwargs)
            if not kwargs.get("can_send_messages", False):
                self.updater.bot.send_message(chat_id=chat_id,
                                              text=f"{user.name} has been restricted for {str(until_date)}.")
        except TelegramError as e:
            if e.message == "Can't demote chat creator" and not kwargs.get("can_send_message", False):
                message = "Sadly, user {} couldn't be restricted due to: `{}`. Shame on {}".format(user.name,
                                                                                                   e.message,
                                                                                                   user.name)
                self.logger.info("{}".format(message))
                self.updater.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.MARKDOWN)
            self.logger.error(e)
            result = False

        return result

    def unmute_user(self, chat_id: str, user: User):
        if self.set_user_restriction(chat_id, user, until_date=timedelta(seconds=0), can_send_messages=True):
            user.muted = False
        # We'd need to parse the exception before assigning user.muted differently

    def mute_user(self, chat_id: str, user: User, until_date: timedelta, reason: Optional[str] = None):
        self.logger.info(f"Reason for muting: {reason}")
        if self.set_user_restriction(chat_id, user, until_date=until_date, can_send_messages=False):
            user.muted = True
            # We'd need to parse the exception before assigning user.muted differently

    # noinspection PyUnusedLocal
    @admin
    def remind_users(self, update: Update = None) -> bool:
        # Check that all chat keyboards have been set correctly
        return all([bool(chat.show_attend_keyboard()) for chat in self.chats.values()])

    def handle_attend_callback(self, update: Update):
        callback: CallbackQuery = update.callback_query
        chat_user: TUser = callback.from_user
        user = User.from_tuser(chat_user)
        chat = self.chats[callback.message.chat.id]
        chat.add_user(user)
        chat.set_attend_callback(callback)

        def _mute_user_if_absent():
            chat_id = chat.id
            if user in self.chats[chat_id].current_event.absentees:
                self.mute_user(chat_id, user, timedelta(hours=1))

        attends = callback.data == "attend_True"
        if attends:
            chat.current_event.add_attendee(user)
            self.calendar.create()
            self.unmute_user(chat.id, user)
        else:
            chat.current_event.add_absentee(user)
            try:
                chat.current_event.remove_attendee(user)
                Timer(15 * 60, _mute_user_if_absent).start()
            except Exception as e:
                sentry_sdk.capture_exception()
                self.logger.exception(e)

            if chat.current_keyboard == Keyboard.DICE:
                chat.update_dice_message()

        try:
            self.save_state()
            chat.update_attend_message()
        except Exception as e:
            sentry_sdk.capture_exception()
            self.logger.exception(e)

    def handle_dice_callback(self, update: Update):
        callback: CallbackQuery = update.callback_query
        chat_user: TUser = callback.from_user
        user = User.from_tuser(chat_user)
        chat: Chat = self.chats[callback.message.chat.id]
        chat.set_dice_callback(callback)

        attendees: List[User] = chat.current_event.attendees

        if user.id not in [user.id for user in attendees]:
            self.logger.info("User {} is not in attendees list".format(user.name))
            callback.answer()
            return False
        attendee = [attendee for attendee in attendees if attendee.id == user.id][0]

        data = re.match("dice_(.*)", callback.data).groups()[0]
        if data in map(str, range(1, 7)):
            attendee.set_roll(int(data))
        else:
            attendee.set_jumbo(data == "+1")

        self.save_state()
        chat.update_dice_message()

    def remind_chat(self, update: Update) -> bool:
        self.logger.info("Remind chat")
        try:
            chat_id = update.message.chat_id
            self.logger.info("Remind chat: {}".format(chat_id))
        except AttributeError as e:
            self.logger.info("Attribute error for `update.message.chat_id`: {}".format(e))
            return False

        if not (chat_id in self.chats.keys()):
            self.logger.error("Chat id not known. Chat has to be registered before it can be reminded")
            return False

        self.logger.info("Show attend keyboard for: {}".format(chat_id))
        result = self.chats[chat_id].show_attend_keyboard()
        self.logger.info("Result if showing attend keyboard for {}: {}".format(chat_id, result))

        return bool(result)

    def reset(self, chat_id: str) -> bool:
        self.logger.debug(f"Attempting to reset {chat_id}")
        result = False

        chat = self.chats.get(chat_id)
        if chat:
            result = chat.reset()

            self.save_state()

        return result

    @admin
    def reset_all(self, update: Update):
        self.logger.debug("Attempting to reset all chats")

        success = {}
        for chat in self.chats.values():
            success[chat.id] = chat.reset()

        self.save_state()
        if all(value for _, value in success.items()):
            message = "Reset successfully completed."
        else:
            message = "Reset failed for the following chats:\n{}".format(
                [chat_id for chat_id, suc in success.items() if not suc]
            )
        self.updater.bot.send_message(chat_id=update.message.chat_id, text=message,
                                      disable_notification=True)

    def check_for_spam(self, chat_messages: Dict[Chat, Iterable[Message]]):
        for chat, messages in chat_messages.items():
            user_messages = dict((chat.get_user_by_id(user_id), set(user_messages)) for user_id, user_messages in
                                 groupby(messages, lambda message: message.from_user.id))
            for user, user_messages in user_messages.items():
                user.messages = user_messages
                spam_type = self._check_user_spam(list(user_messages), self.config.get("spam", {}))
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
                    self.logger.warning(spam_type_message)
                    self.mute_user(chat.id, user, timeout, reason=spam_type_message)

    @staticmethod
    def _check_user_spam(user_messages: List[Message], spam_config: Dict[str, int]) -> SpamType:
        """

        :rtype: SpamType
        """
        consecutive_message_limit: int = spam_config.get("consecutive_message_limit", 8)
        consecutive_message_timeframe: int = spam_config.get("consecutive_message_timeframe", 5)
        same_message_limit: int = spam_config.get("same_message_limit", 3)
        same_message_timeframe: int = spam_config.get("same_message_timeframe", 2)
        different_message_limit: int = spam_config.get("different_message_limit", 15)
        different_message_timeframe: int = spam_config.get("different_message_timeframe", 2)

        def is_consecutive(sorted_messages: List[Optional[Message]]):
            if None in sorted_messages:
                return False
            minimum = sorted_messages[0].message_id
            maximum = sorted_messages[-1].message_id

            return sum([message.message_id for message in sorted_messages]) == maximum * (maximum + 1) / 2 - (
                    (minimum - 1) * (minimum / 2))

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
                    return SpamType.SAME

        return SpamType.NONE

    def handle_message(self, update: Update):
        self.logger.info("Handle message: {}".format(update.message.text))
        if update.message.chat_id not in self.chats.keys():
            self.logger.error("Chat {} hasn't been registered.".format(update.message.chat_id))
            self.updater.bot.send_message(chat_id=update.message.chat_id,
                                          text="Please register before performing an action (/register).")
            return
        chat: Chat = self.chats.get(update.message.chat_id)
        chat.add_user(User.from_tuser(update.message.from_user))
        chat.add_message(update.message)

        try:
            self.check_for_spam({chat: chat.messages()})
        except Exception as e:
            sentry_sdk.capture_exception()
            self.logger.exception("{}".format(e))
        else:
            self.logger.info("Handled message")

    def set_state(self, state: Dict[str, Any]):
        self.state = state
        self.state["main_id"] = self.state.get("main_id", "")
        self.chats = {schat["id"]: Chat.deserialize(schat, self.updater.bot) for schat in state.get("chats", [])}

        return True

    def show_attend_keyboards(self):
        for _, chat in self.chats.items():
            chat.show_attend_keyboard()

    def show_users(self, chat_id: str) -> Optional[Message]:
        chat = self.chats.get(chat_id)
        if not chat:
            return None

        message = "\n".join([str(user) for user in chat.users])

        if not message:
            message = "No active users, the user needs to write a message in the chat to be activated (not just a command)"

        return self.updater.bot.send_message(chat_id=chat_id, text=message)
