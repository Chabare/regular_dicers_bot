import datetime
import json
import logging
import re
from typing import List, Optional, Set, Dict, Union

from telegram import Bot as TBot
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup, Update, CallbackQuery, Message
from telegram import User as TUser

from .calendar import Calendar


def create_logger(name: str, level: int = logging.DEBUG):
    import sys
    logger = logging.Logger(name)
    ch = logging.StreamHandler(sys.stdout)

    formatting = "[{}] %(levelname)s\t%(module)s.%(funcName)s\tLine=%(lineno)d | %(message)s".format(name)
    formatter = logging.Formatter(formatting)
    ch.setFormatter(formatter)

    logger.addHandler(ch)
    logger.setLevel(level)

    return logger


class Bot:
    offset = 0

    def __init__(self, updater):
        self.chats: Dict[str, Chat] = {}
        self.updater = updater
        self.user_ids = set()
        self.state: Dict[str, Union[Dict[str, Chat], Optional[str]]] = {
            "main_id": None
        }
        self.calendar = Calendar()
        self.logger = create_logger("regular_dicers_bot")

    def show_dice(self, chat_id: str):
        print(chat_id)
        chat = self.chats[chat_id]
        print(chat)
        return chat.show_dice()

    def show_dices(self):
        for chat_id in self.chats.keys():
            self.show_dice(chat_id)

    def save_state(self):
        return
        self.state["chats"] = self.chats  # TODO: Serialize values
        with open("state.json", "w+") as f:
            json.dump(self.state, f)

    def register(self, update: Update, send_success: bool = True) -> bool:
        self.logger.info("Register")
        chat_id = update.message.chat_id
        self.logger.info("Register: {}".format(chat_id))

        if chat_id in self.chats.keys():
            self.logger.info("Chat already registered")
            self.updater.bot.send_message(chat_id=chat_id, text="Why would you register twice, dumbass!")
            return False

        self.logger.info("Chat is being registered")
        try:
            self.chats[chat_id] = Chat(chat_id, self.updater.bot)
            self.save_state()
        except Exception as e:
            print("Exception: {}".format(e))

        if send_success:
            self.logger.info("Chat successfully registered")
            self.updater.bot.send_message(chat_id=chat_id, text="You have been registered.")
        else:
            self.logger.info("Failed to register chat")

        return True

    def unregister(self, update: Update) -> bool:
        chat_id = update.message.chat_id
        try:
            successful_removal = self.chats.pop(chat_id)
            if self.state["main_id"] == chat_id:
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
        chat_id = update.message.chat_id
        if not self.state["main_id"]:
            registered = self.register(update, False)
            if registered:
                self.state["main_id"] = chat_id
                self.save_state()
                self.updater.bot.send_message(chat_id=chat_id, text="You have been registered as the main chat.")

    def remind_users(self, update: Update = None) -> bool:
        if update:
            chat_id = update.message.chat_id
            if chat_id != self.state["main_id"]:
                self.updater.bot.send_message(chat_id=update.message.chat_id, text="Fuck you")
                return False

        # Check that all chat keyboards have been set correctly
        return all([bool(chat.show_attend_keyboard()) for chat in self.chats.values()])

    def handle_attend_callback(self, update: Update):
        callback: CallbackQuery = update.callback_query
        chat_user: TUser = callback.from_user
        user = User.from_tuser(chat_user)
        chat = self.chats[callback.message.chat.id]
        chat.set_attend_callback(callback)

        attends = callback.data == "attend_True"
        try:
            if attends:
                chat.current_event.add_attendee(user)
            else:
                chat.current_event.add_absentee(user)
        except Exception as e:
            print("Exception: {}".format(e))

        self.save_state()
        chat.update_attend_message()

    def handle_dice_callback(self, update: Update):
        callback: CallbackQuery = update.callback_query
        chat_user: TUser = callback.from_user
        chat: Chat = self.chats[callback.message.chat.id]
        chat.set_dice_callback(callback)

        attendees: List[User] = chat.current_event.attendees

        if chat_user.name not in [user.name for user in attendees]:
            self.logger.info("User {} is not in attendees list".format(chat_user.name))
            return False

        data = re.match("dice_(.*)", callback.data).groups()[0]
        if data in map(str, range(1, 7)):
            [user for user in attendees if user.name == chat_user.name][0].set_roll(int(data))
        else:
            [user for user in attendees if user.name == chat_user.name][0].set_jumbo(data == "+1")

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

    def reset(self):
        for _, chat in self.chats.items():
            chat.close_current_event()
            chat.unpin_message()

        self.save_state()


class User:
    def __init__(self, name: str):
        self.name = name
        self.roll = -1
        self.jumbo = False

    def set_roll(self, roll: int) -> None:
        self.roll = roll

    def set_jumbo(self, jumbo: bool) -> None:
        self.jumbo = jumbo

    def __eq__(self, other):
        if not isinstance(other, User):
            return False

        return other.name == self.name

    def __hash__(self):
        return self.name.__hash__()

    def __str__(self) -> str:
        return "{} ({}{})".format(self.name, self.roll, "+1" if self.jumbo else "")

    @classmethod
    def from_tuser(cls, chat_user):
        return User(chat_user.name)  # TODO


class Event:
    def __init__(self):
        self.timestamp = self._next_monday()
        self.logger = create_logger("event_{}".format(self.timestamp))
        self.logger.info("Create event")
        self.attendees: Set[User] = set()
        self.absentees: Set[User] = set()
        self.logger.info("Created event for {}".format(self.timestamp))

    def add_absentee(self, user: User):
        self.logger.info("Add absentee {} to event".format(user))
        try:
            self.remove_attendee(user)
        except KeyError:
            self.logger.info("User was not in attendees: {}".format(user))

        return self.absentees.add(user)

    def remove_absentee(self, user: User):
        self.logger.info("Remove absentee {} from event".format(user))
        self.absentees.remove(user)
        self.add_attendee(user)

    def add_attendee(self, user: User):
        self.logger.info("Add {} to event".format(user))
        try:
            self.remove_absentee(user)
        except KeyError:
            self.logger.info("User was not in absentees: {}".format(user))
        self.attendees.add(user)

    def remove_attendee(self, user: User):
        self.logger.info("Remove {} from event".format(user))
        self.attendees.remove(user)
        self.add_absentee(user)

    def serialize(self) -> Dict[str, Union[int, Set[User]]]:
        self.logger.info("Serialize event")
        return {
            "timestamp": self.timestamp,
            "attendees": self.attendees
        }

    @staticmethod
    def _next_monday():
        # self.logger.info("Calculate _next_monday")
        today = datetime.datetime.today()
        weekday = 0

        d = datetime.date(today.year, today.month, today.day)
        days_ahead = weekday - d.weekday()

        next_monday = d + datetime.timedelta(days_ahead)
        # self.logger.info("Next monday is on: {}".format(next_monday))
        return next_monday


class Chat:
    events: List[Event] = []
    pinned_message_id: Optional[int]
    current_event: Optional[Event]
    attend_callback: CallbackQuery
    dice_callback: CallbackQuery

    def __init__(self, id: str, bot: TBot):
        self.logger = create_logger("chat_{}".format(id))
        self.logger.info("Create chat")
        self.id: str = id
        self.bot: TBot = bot
        self.logger.info("Created chat")
        self.start_event()

    def serialize(self):
        self.logger.info("Serialize event")
        return {
            "id": id,
            "current_event": self.current_event,
            "pinned_message_id": self.pinned_message_id
        }

    def pin_message(self, message_id: int, disable_notifications: bool = True, unpin: bool = False) -> bool:
        self.logger.info("Pin message")
        if unpin:
            self.logger.info("Force unpin before pinning")
            self.unpin_message()

        if not self.pinned_message_id and self.bot.pin_chat_message(chat_id=self.id,
                                                                    message_id=message_id,
                                                                    disable_notification=disable_notifications):
            self.pinned_message_id = message_id
            self.logger.info("Successfully pinned message: {}".format(message_id))
            return True

        self.logger.info("Pinning message failed")
        return False

    def unpin_message(self):
        self.logger.info("Unpin message")
        if self.bot.unpin_chat_message(chat_id=self.id):
            self.logger.info("Successfully unpinned message")
            self.pinned_message_id = None
            return True

        self.logger.info("Failed to unpin message")
        return False

    def close_current_event(self):
        self.logger.info("Close current event")
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
        self.logger.info("Edit message ({})".format(message))
        result = self.attend_callback.edit_message_text(text=message, reply_markup=self.get_attend_keyboard())
        self.logger.info("Answer attend callback")
        self.attend_callback.answer()

        self.logger.info("edit_message_text returned: {}".format(result))
        return result

    def _build_attend_message(self):
        self.logger.info("Build attend message for event: {}".format(self.current_event))
        message = "Wer ist dabei?"
        attendees = self.current_event.attendees
        absentees = self.current_event.absentees

        if attendees:
            self.logger.info("attend message has attendees")
            message += " Bisher: " + ", ".join([user.name for user in attendees])
        else:
            self.logger.info("No attendees for event")
        if absentees:
            self.logger.info("attend message has absentees")
            message += " | Nicht dabei: " + ", ".join([user.name for user in absentees])
        else:
            self.logger.info("No absentees for event")

        self.logger.info("Successfully built the attend message: {}".format(message))
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
        self.logger.info("Edit message ({})".format(message))
        result = self.dice_callback.edit_message_text(text=message, reply_markup=self.get_dice_keyboard())
        self.logger.info("Answer dice callback")
        self.dice_callback.answer()

        self.logger.info("edit_message_text returned: {}".format(result))
        return result

    def _build_dice_message(self):
        self.logger.info("Build price message")
        message = "Was hast du gewürfelt?"
        attendees = [attendee for attendee in self.current_event.attendees if attendee.roll != -1]

        if attendees:
            self.logger.info("price message has attendees")
            return message + " Bisher: " + ", ".join(map(str, attendees))

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
            self.logger.info("Successfully shown dice: {}".format(result))
            self.logger.info("Assigning internal id and pin message: {}".format(result))
            self.pin_message(result.message_id, unpin=True)
        else:
            self.logger.info("Failed to send dice message: {}".format(result))

        return result

    def show_attend_keyboard(self) -> Message:
        self.logger.info("Show attend keyboard")
        message = self._build_attend_message()
        result = self._send_message(text=message, reply_markup=self.get_attend_keyboard())
        if result:
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
