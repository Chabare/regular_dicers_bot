from enum import Enum
from typing import Optional, Set, List, Dict

from telegram import Bot as TBot
from telegram import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, TelegramError
from telegram.error import BadRequest

from dicers_bot.user import User
from .event import Event
from .logger import create_logger


class Keyboard(Enum):
    NONE = 0
    ATTEND = 1
    DICE = 2


class Chat:
    def __init__(self, _id: str, bot: TBot):
        self.events: List[Event] = []
        self.pinned_message_id: Optional[int] = None
        self.current_event: Optional[Event] = None
        self.attend_callback: Optional[CallbackQuery] = None
        self.dice_callback: Optional[CallbackQuery] = None
        self.current_keyboard = Keyboard.NONE
        self.logger = create_logger("chat_{}".format(_id))
        self.logger.info("Create chat")
        self.id: str = _id
        self.bot: TBot = bot
        self.logger.info("Created chat")
        self.start_event()
        self.logger.info("Initialize empty user set")
        self.users: Set[User] = set()

    def get_user_by_id(self, _id: int) -> Optional[User]:
        result = next(filter(lambda user: user.id == _id, self.users), None)

        return result

    def serialize(self):
        self.logger.info("Serialize chat")
        serialized = {
            "id": self.id,
            "current_event": self.current_event.serialize() if self.current_event else None,
            "pinned_message_id": self.pinned_message_id,
            "events": [event.serialize() for event in self.events]
        }
        self.logger.info("Serialized chat: {}".format(serialized))

        return serialized

    def add_user(self, user: User):
        self.users.add(user)

    @classmethod
    def deserialize(cls, json_object: Dict, bot: TBot):
        chat = Chat(
            json_object["id"],
            bot
        )
        chat.pinned_message_id = json_object["pinned_message_id"]
        chat.current_event = Event.deserialize(json_object["current_event"])
        chat.events = [Event.deserialize(event_json_object) for event_json_object in json_object["events"]]

        return chat

    def pin_message(self, message_id: int, disable_notifications: bool = True, unpin: bool = False) -> bool:
        self.logger.info("Pin message")
        if unpin:
            self.logger.info("Force unpin before pinning")
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
            self.logger.info("Successfully pinned message: {}".format(message_id))
            return True

        self.logger.info("Pinning message failed")
        return False

    def unpin_message(self):
        self.logger.info("Unpin message")

        successful_unpin = False
        try:
            successful_unpin = self.bot.unpin_chat_message(chat_id=self.id)
        except TelegramError as e:
            self.logger.error(f"Couldn't unpin message due to error: {e}")

        if successful_unpin:
            self.logger.info("Successfully unpinned message")
            self.pinned_message_id = None
            return True

        self.logger.info("Failed to unpin message")
        return False

    def close_current_event(self):
        self.logger.info("Close current event")
        if self.current_event:
            self.events.append(self.current_event)
        self.current_event = None

    def start_event(self, event: Optional[Event] = None):
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
        ]])

    def update_attend_message(self):
        self.logger.info("Update attend message")
        if not self.attend_callback or not self.current_event:
            self.logger.info("Failed to update attend message: attend_callback: {} | self.current_event".format(
                self.attend_callback,
                self.current_event.serialize()
            ))
            raise Exception  # TODO

        message = self._build_attend_message()
        self.logger.info("Edit message (%s)", message)

        try:
            result = self.attend_callback.edit_message_text(text=message, reply_markup=self.get_attend_keyboard())
            self.logger.info("edit_message_text returned: %s", result)
        except BadRequest:
            # This will happen if the message didn't change
            self.logger.debug("edit_message_text failed", exc_info=True)

        self.logger.info("Answer attend callback")
        self.attend_callback.answer()

    def _build_attend_message(self):
        self.logger.info("Build attend message for event: %s", self.current_event)
        message = "Wer ist dabei?"
        attendees = self.current_event.attendees
        absentees = self.current_event.absentees

        if attendees:
            self.logger.info("attend message has attendees")
            message += "\nBisher: " + ", ".join([user.name for user in attendees])
        else:
            self.logger.info("No attendees for event")
        if absentees:
            self.logger.info("attend message has absentees")
            message += "\nNicht dabei: " + ", ".join([user.name for user in absentees])
        else:
            self.logger.info("No absentees for event")

        self.logger.info("Successfully built the attend message: %s", message)
        return message

    def update_dice_message(self):
        self.logger.info("Update price message")
        if not self.dice_callback or not self.current_event:
            self.logger.info("Failed to update price message: dice_callback: {} | self.current_event".format(
                self.dice_callback,
                self.current_event.serialize()
            ))
            self.logger.info("Raise exception")
            raise Exception  # TODO

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

    def _build_dice_message(self):
        self.logger.info("Build price message")
        message = "Was hast du gewürfelt?\n"
        attendees = [attendee for attendee in self.current_event.attendees if attendee.roll != -1]

        if attendees:
            self.logger.info("price message has attendees")
            message += ", ".join(
                ["{} ({}{})".format(attendee.name, attendee.roll, "+1" if attendee.jumbo else "") for attendee in
                 attendees])

            rolls = [(attendee.roll + 1 if attendee.jumbo else attendee.roll + 0) for attendee in attendees if
                     attendee.roll != -1]
            message += "\nΣ: {}€ + {}€ Trinkgeld".format(sum(rolls), len(rolls))

        return message

    def _send_message(self, **kwargs):
        self.logger.info(
            "Send message with: {}".format(" | ".join(["{}: {}".format(key, val) for key, val in kwargs.items()]))
        )
        result = self.bot.send_message(chat_id=self.id, **kwargs)

        self.logger.info("Result of sending message: {}".format(result))
        return result

    def show_dice(self) -> Message:
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

    def set_attend_callback(self, callback: CallbackQuery):
        self.logger.info("Set attend callback")
        self.attend_callback = callback

    def set_dice_callback(self, callback: CallbackQuery):
        self.logger.info("Set dice callback")
        self.dice_callback = callback

    def hide_attend(self):
        self.logger.info("Hide attend keyboard")
        try:
            self.attend_callback.edit_message_text(text=self._build_attend_message())
            self.unpin_message()
        except TelegramError as e:
            self.logger.error(e)

    def add_message(self, message: Message):
        user = self.get_user_by_id(message.from_user.id)

        return user.messages.add(message)

    def messages(self) -> List[Message]:
        messages = []
        for user in self.users:
            messages.extend(user.messages)

        return messages
