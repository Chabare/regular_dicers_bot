from __future__ import annotations

from enum import Enum
from typing import Optional, Set, List, Dict, Any, Callable

from telegram import Bot as TBot, Update
from telegram import Chat as TChat
from telegram import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, TelegramError
from telegram.error import BadRequest

from .decorators import group
from .event import Event
from .logger import create_logger
from .user import User


class Keyboard(Enum):
    NONE = 0
    ATTEND = 1
    DICE = 2


class ChatType(Enum):
    UNDEFINED = ""
    PRIVATE = TChat.PRIVATE
    GROUP = TChat.GROUP
    SUPERGROUP = TChat.SUPERGROUP

    def __eq__(self, other) -> bool:
        if not isinstance(other, str):
            if isinstance(other, ChatType):
                return self.value == other.value
            else:
                return False

        return self.value == other


class Chat:
    def __init__(self, _id: str, bot: TBot):
        self.logger = create_logger("chat_{}".format(_id))
        self.logger.debug("Create chat")
        self.events: List[Event] = []
        self.pinned_message_id: Optional[int] = None
        self.current_event: Optional[Event] = None
        self.attend_callback: Optional[CallbackQuery] = None
        self.dice_callback: Optional[CallbackQuery] = None
        self.current_keyboard = Keyboard.NONE
        self.id: str = _id
        self.bot: TBot = bot
        self.start_event()
        self.users: Set[User] = set()
        self.title = None
        self.type = ChatType.UNDEFINED
        self.spam_detection = True

    def get_user_by_id(self, _id: int) -> Optional[User]:
        result = next(filter(lambda user: user.id == _id, self.users), None)

        return result

    def serialize(self) -> Dict[str, Any]:
        serialized_event = None
        if self.current_event:
            serialized_event = self.current_event.serialize()

        serialized = {
            "id": self.id,
            "current_event": serialized_event,
            "pinned_message_id": self.pinned_message_id,
            "events": [event.serialize() for event in self.events],
            "users": [user.serialize() for user in self.users],
            "title": self.title,
            "spam_detection": self.spam_detection
        }

        return serialized

    def add_user(self, user: User):
        self.users.add(user)

    @classmethod
    def deserialize(cls, json_object: Dict, bot: TBot) -> Chat:
        chat = Chat(
            json_object["id"],
            bot
        )
        chat.pinned_message_id = json_object.get("pinned_message_id")
        chat.current_event = Event.deserialize(json_object.get("current_event"))
        chat.events = [Event.deserialize(event_json_object) for event_json_object in json_object.get("events", [])]
        chat.users = {User.deserialize(user_json_object) for user_json_object in json_object.get("users", [])}
        chat.title = json_object.get("title", None)
        chat.spam_detection = json_object.get("spam_detection", True)

        return chat

    @group
    def pin_message(self, message_id: int, disable_notifications: bool = True, unpin: bool = False) -> bool:
        if unpin:
            self.logger.debug("Force unpin before pinning")
            self.unpin_message()

        successful_pin = False
        try:
            successful_pin = self.bot.pin_chat_message(chat_id=self.id,
                                                       message_id=message_id,
                                                       disable_notification=disable_notifications)
        except TelegramError as e:
            self.logger.error(f"Couldn't pin message due to error: {e}")

        if successful_pin:
            self.pinned_message_id = message_id
            self.logger.debug("Successfully pinned message: {}".format(message_id))
            return True
        else:
            self.logger.warning("Pinning message failed")

        return successful_pin

    @group
    def unpin_message(self) -> bool:
        successful_unpin = False
        try:
            successful_unpin = self.bot.unpin_chat_message(chat_id=self.id)
        except TelegramError as e:
            self.logger.error(f"Couldn't unpin message due to error: {e}")

        if successful_unpin:
            self.logger.info("Successfully unpinned message")
            self.pinned_message_id = None
        else:
            self.logger.info("Failed to unpin message")

        return successful_unpin

    def close_current_event(self) -> None:
        self.logger.info("Close current event")
        if self.current_event:
            self.events.append(self.current_event)
        self.current_event = None

    def start_event(self, event: Optional[Event] = None) -> None:
        self.logger.info("Start event")
        if not event:
            self.logger.info("No event given, create one")
            event = Event()

        self.current_event = event
        self.logger.info("Started event")

    def get_attend_keyboard(self) -> InlineKeyboardMarkup:
        self.logger.info("Get attend keyboard")
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(
                text="Dabei",
                callback_data="attend_True"),
            InlineKeyboardButton(
                text="Nicht dabei",
                callback_data="attend_False")
        ]])

    def get_dice_keyboard(self) -> InlineKeyboardMarkup:
        self.logger.info("Get dice keyboard")
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(
                text=str(i),
                callback_data="dice_{}".format(str(i))) for i in range(1, 4)
        ], [
            InlineKeyboardButton(
                text=str(i),
                callback_data="dice_{}".format(str(i))) for i in range(4, 7)
        ], [
            InlineKeyboardButton(
                text="Normal",
                callback_data="dice_-1"),
            InlineKeyboardButton(
                text="Jumbo",
                callback_data="dice_+1")
        ], [
            InlineKeyboardButton(
                text="Alkoholfrei",
                callback_data="dice_non-alcoholic"),
            InlineKeyboardButton(
                text="Vernünftig",
                callback_data="dice_alcoholic")
        ]])

    def update_attend_message(self) -> None:
        self.logger.info("Update attend message")
        if not self.attend_callback:
            self.logger.info("Failed to update attend message (no attend_callback)")
            return

        if not self.current_event:
            self.logger.debug("No current event, emptying old attend message.")
            try:
                self.attend_callback.edit_message_reply_markup(reply_markup=None)
                self.attend_callback.answer()
                self.attend_callback = None
            except BadRequest:
                self.logger.warning("Could not use attend_callback", exc_info=True)
            return

        message = self._build_attend_message()
        self.logger.info("Edit message (%s)", message)

        try:
            result: Message = self.attend_callback.edit_message_text(text=message,
                                                                     reply_markup=self.get_attend_keyboard())
            self.logger.info("edit_message_text returned: %s", result)
        except BadRequest:
            # This will happen if the message didn't change
            self.logger.debug("edit_message_text failed", exc_info=True)

        self.logger.info("Answer attend callback")
        self.attend_callback.answer()

    def _build_attend_message(self) -> str:
        self.logger.info("Build attend message for event: %s", self.current_event)
        message = "Wer ist dabei?" + "\nBisher: "
        attendees = self.current_event.attendees
        absentees = self.current_event.absentees
        not_voted = self.users.difference(attendees.union(absentees))

        condition: Callable[[Any], bool] = lambda _: True
        sind_die_kurzen_dabei: bool = len([user for user in attendees if user.name in ["nadine", "tashina"]]) == 2

        if sind_die_kurzen_dabei:
            condition: Callable[[str], bool] = lambda username: username not in ["nadine", "tashina"]

        user_string = ", ".join(sorted([user.name for user in attendees if condition(user.name)]))

        if sind_die_kurzen_dabei:
            user_string += " #dieKurzenSindDabei"

        if user_string:
            if len(attendees) == len(self.users):
                message += "Alle 🎉"
            else:
                message += user_string
        else:
            message += "Niemand :("
        if absentees:
            self.logger.debug("attend message has absentees")
            message += "\nNicht dabei: " + ", ".join([user.name for user in absentees])
        else:
            self.logger.debug("No absentees for event")

        if not_voted:
            self.logger.debug("there are people who have not yet voted")
            message += "\nincoming warnings: " + ", ".join([user.name for user in not_voted])
        else:
            self.logger.debug("everyone has voted")

        self.logger.info("Successfully built the attend message: %s", message)
        return message

    def update_dice_message(self) -> None:
        self.logger.info("Update price message")
        if not self.dice_callback:
            self.logger.info("Failed to update price message: no dice_callback")
            self.logger.info("Raise exception")
            return None

        if not self.current_event:
            self.logger.debug("No current event, emptying old dice message.")
            try:
                self.dice_callback.edit_message_reply_markup(reply_markup=None)
                self.dice_callback.answer()
                self.dice_callback = None
            except BadRequest:
                self.logger.warning("Could not use dice_callback", exc_info=True)

            return None

        message = self._build_dice_message()
        self.logger.info("Edit message (%s)", message)

        try:
            result = self.dice_callback.edit_message_text(text=message, reply_markup=self.get_dice_keyboard())
            self.logger.info("edit_message_text returned: %s", result)
        except BadRequest:
            # This will happen if the message didn't change
            self.logger.debug("edit_message_text failed", exc_info=True)

        self.logger.info("Answer dice callback")

        self.dice_callback.answer()

    def _build_dice_message(self) -> str:
        self.logger.info("Build price message")
        message = "Was hast du gewürfelt?\n"
        attendees = [attendee for attendee in self.current_event.attendees if attendee.roll != -1]

        if attendees:
            self.logger.info("price message has attendees")
            attendees = sorted(attendees, key=lambda user: user.name.lower())
            message += ", ".join(
                ["{} ({}{}{})".format(attendee.name, attendee.roll, "+1" if attendee.jumbo else "",
                                      "" if attendee.alcoholic else " 💔") for attendee in
                 attendees])

            rolls = [(attendee.roll + 1 if attendee.jumbo else attendee.roll + 0) for attendee in attendees if
                     attendee.roll != -1]
            message += "\nΣ: {}€ + {}€ Trinkgeld".format(sum(rolls), len(rolls))

        return message

    def _send_message(self, **kwargs) -> Message:
        """
        Alias for `self.bot.send_message(chat_id=self.id, [...])`
        :param kwargs: Dict[str, Any] Passed to bot.send_message
        :raises: TelegramError Raises TelegramError if the message couldn't be sent
        :return:
        """
        message = " | ".join(["{}: {}".format(key, val) for key, val in kwargs.items()])
        self.logger.info(f"Send message with: {message}")

        result = self.bot.send_message(chat_id=self.id, **kwargs)

        self.logger.info("Result of sending message: {}".format(result))
        return result

    def show_dice(self) -> Optional[Message]:
        if not self.current_event:
            self.logger.info("No `current_event`, abort `show_dice`.")
            self._send_message(text="There is no event right now, unable to provide a dice.")

            return None

        self.logger.info("Showing dice")
        result = self._send_message(text=self._build_dice_message(), reply_markup=self.get_dice_keyboard())
        if result:
            self.current_keyboard = Keyboard.DICE
            self.logger.info("Successfully shown dice: {}".format(result))
            self.logger.info("Assigning internal id and pin message: {}".format(result))
            self.pin_message(result.message_id, unpin=True)
        else:
            self.logger.info("Failed to send dice message: {}".format(result))

        return result

    def show_attend_keyboard(self) -> Message:
        """
        :raises: TelegramError Raises TelegramError if the message couldn't be sent
        :return: Message Attend keyboard message
        """
        self.logger.info("Show attend keyboard")

        # Start an event if none exists
        self.start_event(self.current_event)

        message = self._build_attend_message()
        result = self._send_message(text=message, reply_markup=self.get_attend_keyboard())

        if result:
            self.current_keyboard = Keyboard.ATTEND
            self.logger.info("Successfully shown attend: {}".format(result))
            self.logger.info("Assigning internal id and pin message: {}".format(result))
            self.pin_message(result.message_id)
        else:
            self.logger.info("Failed to send attend message: {}".format(result))

        return result

    @group
    def administrators(self) -> Set[User]:
        """
        Lists all administrators in this chat.
        Skips administrators who are not in `self.users`.
        This doesn't work in private chats, since there are no admins in a private chat

        :return: Administrators in this chat Set[User]
        """
        administrators: Set[User] = set()

        try:
            chat_administrators = self.bot.get_chat_administrators(chat_id=self.id)
        except TelegramError:
            return administrators

        for admin in chat_administrators:
            try:
                user = next(filter(lambda user: user.id == admin.user.id, self.users))
                administrators.add(user)
            except StopIteration:
                pass

        return administrators

    def set_attend_callback(self, callback: CallbackQuery) -> None:
        self.logger.info("Set attend callback")
        self.attend_callback = callback

    def set_dice_callback(self, callback: CallbackQuery) -> None:
        self.logger.info("Set dice callback")
        self.dice_callback = callback

    def hide_attend(self) -> bool:
        self.logger.info("Hide attend keyboard")
        result = True

        try:
            self.attend_callback.edit_message_text(text=self._build_attend_message())
            self.unpin_message()
        except (TelegramError, AttributeError) as e:
            self.logger.error(e)
            result = False

        return result

    def add_message(self, update: Update) -> None:
        user = self.get_user_by_id(update.effective_user.id)

        user.messages.add(update.effective_message)

    def messages(self) -> List[Message]:
        messages = []
        for user in self.users:
            messages.extend(user.messages)

        return messages

    def reset(self) -> None:
        self.close_current_event()
        self.update_attend_message()
        self.update_dice_message()
        self.unpin_message()
        self.current_keyboard = Keyboard.NONE
        for user in self.users:
            user.roll = -1
            user.jumbo = False
            user.muted = False

    def __repr__(self) -> str:
        return f"<{self.id} | {self.title}>"
