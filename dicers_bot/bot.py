import json
import logging
import re
import time

from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup, Update, CallbackQuery, User
from telegram.error import BadRequest

from .calendar import Calendar


class Bot:
    custom_keyboard_attend = [[
        InlineKeyboardButton(
            text="Dabei",
            callback_data="attend_True"),
        InlineKeyboardButton(
            text="Nicht dabei",
            callback_data="attend_False")
    ]]
    custom_keyboard_dice_roll = [[
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
    ]]
    offset = 0
    admin_user_id = "139656428"

    def __init__(self, updater):
        self.updater = updater
        self.user_ids = set()
        self.state = {
            "main_id": None,
            "attendees": {
                "current": {},
                "history": {}
            }
        }
        self.attend_markup = InlineKeyboardMarkup(self.custom_keyboard_attend)
        self.dice_markup = InlineKeyboardMarkup(self.custom_keyboard_dice_roll)
        self.calendar = Calendar()
        self.logger = self.create_logger()

    def show_dice(self, update):
        chat_id = update.message.chat_id
        self.updater.bot.send_message(chat_id=chat_id, text=self.build_dice_roll_message(chat_id),
                                      reply_markup=self.dice_markup)

    def create_logger(self, level: int = logging.DEBUG):
        import sys
        logger = logging.Logger("regular_dicers_bot")
        ch = logging.StreamHandler(sys.stdout)

        formatting = "[regular_dicers_bot] %(levelname)s\t%(module)s.%(funcName)s\tLine=%(lineno)d | %(message)s"
        formatter = logging.Formatter(formatting)
        ch.setFormatter(formatter)

        logger.addHandler(ch)
        logger.setLevel(level)

        return logger

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
            self.logger.error(e)
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
            user: User = callback.from_user
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
            self.logger.error(e)

    def handle_dice_callback(self, update: Update):
        try:
            callback: CallbackQuery = update.callback_query
            chat_id = callback.message.chat.id
            data = re.match("dice_(.*)", callback.data).groups()[0]
            user: User = callback.from_user
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
            self.logger.error(e)

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
            self.logger.error(e)

    def reset_attendees(self):
        self.logger.error("reset")
        self.state["attendees"]["history"][int(time.time())] = self.state["attendees"]["current"]
        self.state["attendees"]["current"] = dict()

        self.save_state()
