import datetime
import json
import logging
import re
from typing import List, Optional, Set, Dict, Union

from telegram import Bot as TBot
from telegram import Chat as TChat
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup, Update, CallbackQuery
from telegram import User as TUser
from telegram.error import BadRequest

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
    admin_user_id = "139656428"

    def __init__(self, updater):
        self.chats: Dict[str, Chat] = {}
        self.updater = updater
        self.user_ids = set()
        self.state = {
            "main_id": None,
            "attendees": []
        }
        self.calendar = Calendar()
        self.logger = create_logger("regular_dicers_bot")

    def show_dice(self, update):
        chat_id = update.message.chat_id
        self.chats[chat_id].show_dice()

    def save_state(self):
        with open("state.json", "w+") as f:
            json.dump(self.state, f)

    def register(self, update, send_success=True):
        try:
            user = update.message.chat_id
            original_length = len(self.user_ids)
            self.user_ids.add(user)

            with open("users.json", "w+") as f:
                json.dump(list(self.user_ids), f)

            if send_success:
                if len(self.user_ids) == original_length:
                    self.updater.bot.send_message(chat_id=user, text="Why would you register twice, dumbass!")
                else:
                    self.updater.bot.send_message(chat_id=user, text="You have been registered.")
            return True
        except Exception as e:
            return False

    def unregister(self, update):
        try:
            user = update.message.chat_id
            original_length = len(self.user_ids)
            try:
                self.user_ids.remove(user)
                if self.state["main_id"] == user:
                    self.state["main_id"] = None
                    self.save_state()
            except KeyError:
                return

            with open("users.json", "w+") as f:
                json.dump(list(self.user_ids), f)

            if len(self.user_ids) == original_length:
                self.updater.bot.send_message(chat_id=user, text="You weren't registered in the first place!")
            else:
                self.updater.bot.send_message(chat_id=user, text="You have been unregistered.")
            return True
        except Exception as e:
            self.logger.error(repr(e))
            return False

    def register_main(self, update):
        user = update.message.chat_id
        if user == self.admin_user_id:
            registered = self.register(update, False)
            if registered:
                user = update.message.chat_id
                self.state["main_id"] = user
                self.save_state()
                self.updater.bot.send_message(chat_id=user, text="You have been registered as the main chat.")

    def remind_users(self, update=None):
        # Check for admin user
        if update and update.message.chat_id != self.admin_user_id:
            self.logger.error("{} tried to use /remind_all".format(update.message.chat_id))
            self.updater.bot.send_message(chat_id=update.message.chat_id, text="Fuck you")
        else:
            for user in self.user_ids:
                self.updater.bot.send_message(chat_id=user, text=self.build_message(user),
                                              reply_markup=self.attend_markup)

    def handle_attend_callback(self, update: Update):
        try:
            callback: CallbackQuery = update.callback_query
            user: TUser = callback.from_user
            chat_id = callback.message.chat.id
            attendees = dict()
            try:
                all_attendees = self.state["attendees"]["current"]
            except KeyError:
                all_attendees = dict()
                self.state["attendees"]["current"] = all_attendees

            try:
                attendees = all_attendees[str(chat_id)]
            except KeyError:
                pass

            all_attendees[str(chat_id)] = attendees

            data = callback.data
            attends = data == "attend_True"
            attendees[str(user.id)] = {
                "attends": attends,
                "name": user.first_name,
                "roll": -1,
                "jumbo": False
            }
            self.save_state()

            try:
                callback.edit_message_text(text=self.build_message(chat_id), reply_markup=self.attend_markup)
                self.updater.bot.unpin_chat_message(chat_id=chat_id)
                self.updater.bot.pin_chat_message(chat_id=chat_id, message_id=data['message_id'],
                                                  disable_notification=True)
            except BadRequest:
                # Message is unchanged
                pass

            if chat_id == self.state["main_id"] and self.positive_attendees(chat_id):
                self.calendar.create()

            callback.answer()
        except Exception as e:
            self.logger.error(repr(e))

    def handle_dice_callback(self, update: Update):
        try:
            callback: CallbackQuery = update.callback_query
            chat_id = callback.message.chat.id
            data = re.match("dice_(.*)", callback.data).groups()[0]
            user: TUser = callback.from_user
            if user.first_name not in [user["name"] for user in self.positive_attendees(chat_id)]:
                callback.edit_message_text(text=self.build_dice_roll_message(chat_id), reply_markup=self.dice_markup)
                callback.answer()
                return

            if not (str(chat_id) in self.state["attendees"]["current"]):
                self.state["attendees"]["current"][str(chat_id)] = {}
            if not (str(user.id) in self.state["attendees"]["current"][str(chat_id)]):
                self.state["attendees"]["current"][str(chat_id)][str(user.id)] = {}

            if data == "-1":
                self.state["attendees"]["current"][str(chat_id)][str(user.id)]["jumbo"] = False
            elif data == "+1":
                self.state["attendees"]["current"][str(chat_id)][str(user.id)]["jumbo"] = True
            else:
                self.state["attendees"]["current"][str(chat_id)][str(user.id)]["roll"] = int(data)

            self.save_state()

            try:
                callback.edit_message_text(text=self.build_dice_roll_message(chat_id), reply_markup=self.dice_markup)
            except BadRequest:
                pass
            callback.answer()
        except Exception as e:
            print("asd: {}".format(e))
            self.logger.error(repr(e))

    def positive_attendees(self, chat_id):
        attendees: dict = self.state["attendees"]["current"][str(chat_id)]
        return list(map(lambda user: user, filter(lambda user: user["attends"], attendees.values())))

    def build_dice_roll_message(self, chat_id: str) -> str:
        base_message = "Was hast du gewürfelt?"
        try:
            users = self.positive_attendees(chat_id)
            if not users:
                raise KeyError()
            return base_message + " Bisher: " + ", ".join(
                ["{} ({}{})".format(user["name"], user["roll"], "+1" if user["jumbo"] else "") for user in users if
                 user["roll"] != -1])
        except KeyError:
            return base_message

    def build_message(self, chat_id) -> str:
        try:
            users = self.positive_attendees(chat_id)
            if not users:
                raise KeyError()
            return "Wer ist dabei? Bisher: " + ", ".join(
                ["{}".format(user["name"]) for user in users])
        except KeyError:
            return "Wer ist dabei?"

    def remind_user(self, update):
        try:
            chat_id = update.message.chat_id
            data = self.updater.bot.send_message(chat_id=chat_id, text=self.build_message(chat_id),
                                                 reply_markup=self.attend_markup)
            self.updater.bot.pin_chat_message(chat_id=chat_id, message_id=data['message_id'], disable_notification=True)
        except Exception as e:
            self.logger.error(repr(e))

    def reset_attendees(self):
        for _, chat in self.chats.items():
            chat.close_current_event()

        self.save_state()


class User(TUser):
    pass


class Event:
    def __init__(self):
        self.logger = create_logger("event_{}".format(self.timestamp))
        self.logger.info("Create event")
        self.timestamp = self._next_monday()
        self.attendees: Set[User] = {}
        self.logger.info("Created event for {}".format(self.timestamp))

    def add_attendee(self, user: User):
        self.logger.info("Add {} to event".format(user))
        self.attendees.add(user)

    def remove_attendee(self, user: User):
        self.logger.info("Remove {} from event".format(user))
        self.attendees.remove(user)

    def update_attendee(self, user: User):
        self.logger.info("Update {} for event".format(user))
        self.attendees.update(user)

    def serialize(self) -> Dict[str, Union[int, Set[User]]]:
        self.logger.info("Serialize event")
        return {
            "timestamp": self.timestamp,
            "attendees": self.attendees
        }

    def _next_monday(self):
        self.logger.info("Calculate _next_monday")
        today = datetime.datetime.today()
        weekday = 0

        d = datetime.date(today.year, today.month, today.day)
        days_ahead = weekday - d.weekday()

        next_monday = d + datetime.timedelta(days_ahead)
        self.logger.info("Next monday is on: {}".format(next_monday))
        return next_monday


class Chat(TChat):
    events: List[Event] = []
    pinned_message_id: Optional[int] = None
    current_event: Optional[Event]
    attend_message_id: int
    price_message_id: int

    def __init__(self, id: str, bot: TBot, telegram_chat: TChat):
        self.logger = create_logger("chat_{}".format(id))
        self.logger.info("Create chat")
        self.id: str = id
        self._internal: TChat = telegram_chat
        self.bot: TBot = bot
        self.logger.info("Created chat")

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
            event = Event()

        self.current_event = event

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
        if not self.attend_message_id or not self.current_event:
            self.logger.info("Failed to update attend message: attend_message_id: {} | self.current_event".format(
                self.attend_message_id,
                self.current_event.serialize()
            ))
            raise Exception  # TODO

        message = self._build_price_message()
        self.logger.info("Edit message ({})".format(message))
        result = self.bot.edit_message_text(chat_id=self.id, message_id=self.price_message_id, text=message)

        self.logger.info("edit_message_text returned: {}".format(result))
        return result

    def _build_attend_message(self):
        self.logger.info("Build attend message")
        message = "Wer ist dabei?"
        attendees = self.current_event.attendees

        if attendees:
            self.logger.info("attend message has attendees")
            message += " Bisher: " + ", ".join([user["name"] for user in attendees])

        return message

    def update_price_message(self):
        self.logger.info("Update price message")
        if not self.price_message_id or not self.current_event:
            self.logger.info("Failed to update price message: price_message_id: {} | self.current_event".format(
                self.price_message_id,
                self.current_event.serialize()
            ))
            raise Exception  # TODO

        message = self._build_attend_message()
        self.logger.info("Edit message ({})".format(message))
        result = self.bot.edit_message_text(chat_id=self.id, message_id=self.price_message_id, text=message)

        self.logger.info("edit_message_text returned: {}".format(result))
        return result

    def _build_price_message(self):
        self.logger.info("Build price message")
        message = "Was hast du gewürfelt?"
        attendees = self.current_event.attendees

        if attendees:
            self.logger.info("price message has attendees")
            return message + " Bisher: " + ", ".join(
                ["{} ({}{})".format(attendee["name"], attendee["roll"], "+1" if attendee["jumbo"] else "") for attendee
                 in attendees if
                 attendee["roll"] != -1])

        return message

    def _send_message(self, **kwargs):
        self.logger.info(
            "Send message with: {}".format(" | ".join(["{}: {}".format(key, val) for key, val in kwargs.items()]))
        )
        result = self.bot.send_message(chat_id=self.id, **kwargs)

        self.logger.info("Result of sending message: {}".format(result))
        return result

    def show_dice(self):
        self.logger.info("Showing dice")
        result = self._send_message(text=self._build_price_message(), reply_markup=self.get_dice_keyboard())

        self.logger.info("Result of showing dice: {}".format(result))
        return result
