import json
from telegram import InlineKeyboardMarkup, Update, CallbackQuery, User
from telegram import InlineKeyboardButton
from telegram.error import BadRequest

from .calendar import Calendar


class Bot:
    custom_keyboard_attend = [[
        InlineKeyboardButton(
            text="Dabei",
            callback_data="True"),
        InlineKeyboardButton(
            text="Nicht dabei",
            callback_data="False")
    ]]
    offset = 0
    admin_user_id = "139656428"

    def __init__(self, updater):
        self.updater = updater
        self.user_ids = set()
        self.state = {
            "main_id": None,
            "attendees": dict()
        }
        self.attend_markup = InlineKeyboardMarkup(self.custom_keyboard_attend)
        self.calendar = Calendar()

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
            print(e)
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
            print(e)
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
            print("{} tried to use /remind_all".format(update.message.chat_id))
            self.updater.bot.send_message(chat_id=update.message.chat_id, text="Fuck you")
        else:
            for user in self.user_ids:
                self.updater.bot.send_message(chat_id=user, text=self.build_message(user), reply_markup=self.attend_markup)

    def handle_callback(self, update: Update):
        try:
            callback: CallbackQuery = update.callback_query
            user: User = callback.from_user
            chat_id = callback.message.chat.id
            attendees = dict()
            try:
                all_attendees = self.state["attendees"]
            except KeyError:
                all_attendees = dict()
                self.state["attendees"] = all_attendees

            try:
                attendees = all_attendees[str(chat_id)]
            except KeyError:
                pass

            all_attendees[str(chat_id)] = attendees

            data = callback.data
            attends = data == "True"
            attendees[str(user.id)] = {
                "attends": attends,
                "name": user.first_name
            }
            self.save_state()

            try:
                callback.edit_message_text(text=self.build_message(chat_id), reply_markup=self.attend_markup)
            except BadRequest:
                # Message is unchanged
                pass

            if chat_id == self.state["main_id"] and self.positive_attendees(chat_id):
                self.calendar.create()

            callback.answer()
        except Exception as e:
            print(e)

    def positive_attendees(self, chat_id):
        attendees: dict = self.state["attendees"][str(chat_id)]
        return list(map(lambda user: user["name"], filter(lambda user: user["attends"], attendees.values())))

    def build_message(self, chat_id) -> str:
        try:
            first_names = self.positive_attendees(chat_id)
            if not first_names:
                raise KeyError()
            return "Wer ist dabei? Bisher: " + ", ".join(first_names)
        except KeyError:
            return "Wer ist dabei?"

    def remind_user(self, update):
        try:
            chat_id = update.message.chat_id
            self.updater.bot.send_message(chat_id=chat_id, text=self.build_message(chat_id), reply_markup=self.attend_markup)
        except Exception as e:
            print(e)

    def reset_attendees(self):
        self.state["attendees"] = dict()
        self.save_state()
