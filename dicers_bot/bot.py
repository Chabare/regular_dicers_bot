import json
import re
from telegram import ReplyKeyboardMarkup
from telegram import ReplyKeyboardRemove

from .calendar import Calendar


class Bot:
    custom_keyboard_attend = [["Dabei"], ["Nicht dabei"]]
    offset = 0
    admin_user_id = "139656428"

    def __init__(self, updater):
        self.updater = updater
        self.user_ids = set()
        self.state = {
            "main_id": None
        }
        self.attend_markup = ReplyKeyboardMarkup(self.custom_keyboard_attend, one_time_keyboard=True)
        self.calendar = Calendar()

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
            print(e)
            return False

    def register_main(self, update):
        user = update.message.chat_id
        if user == self.admin_user_id:
            registered = self.register(update, False)
            if registered:
                user = update.message.chat_id
                self.state["main_id"] = user
                with open("state.json", "w+") as f:
                    json.dump(self.state, f)
                self.updater.bot.send_message(chat_id=user, text="You have been registered as the main chat.")

    def remind_users(self, update=None):
        # Check for admin user
        if update and update.message.chat_id != self.admin_user_id:
            print("{} tried to use /remind_all".format(update.message.chat_id))
            self.updater.bot.send_message(chat_id=update.message.chat_id, text="Fuck you")
        else:
            for user in self.user_ids:
                self.updater.bot.send_message(chat_id=user, text="Wer ist dabei?", reply_markup=self.attend_markup)

    def check_participation_message(self, update):
        positive_messages = ["^dabei$", "👍", r"^ja\b", "👌", r"^yes\b", r"^\+1?"]
        negative_messages = ["^nicht dabei$", "👎", r"^no\b", r"^nein\b", "^-1?", "^nope\b"]
        for positive_message in positive_messages:
            if re.match(positive_message, update.message.text.lower()):
                if update.message.chat_id == self.state["main_id"]:
                    self.calendar.create()
                update.message.reply_text("🍹❤️", quote=True, reply_markup=ReplyKeyboardRemove(True))
        for negative_message in negative_messages:
            if re.match(negative_message, update.message.text.lower()):
                update.message.reply_text("Shame on you", quote=True, reply_markup=ReplyKeyboardRemove(True))

    def remind_user(self, update):
        self.updater.bot.send_message(chat_id=update.message.chat_id, text="Wer ist dabei?", reply_markup=self.attend_markup)

    def remove_keyboard(self, update=None):
        if update:
            self.updater.bot.send_message(chat_id=update.message.chat_id, text="", reply_markup=ReplyKeyboardRemove(True))
        else:
            for user in self.user_ids:
                self.updater.bot.send_message(chat_id=user, text="", reply_markup=ReplyKeyboardRemove(True))
