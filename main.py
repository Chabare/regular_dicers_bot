import threading

import schedule
import telegram
from telegram.ext import CommandHandler, Updater


class Bot:
    custom_keyboard_attend = [["Dabei"], ["Nicht dabei"]]

    def __init__(self, updater):
        self.updater = updater
        self.user_ids = set()
        self.attend_markup = telegram.ReplyKeyboardMarkup(self.custom_keyboard_attend)

    def register(self, update):
        try:
            user = update.message.chat_id
            original_length = len(self.user_ids)
            self.user_ids.add(user)

            with open("users.json", "w+") as f:
                json.dump(list(self.user_ids), f)

            if len(self.user_ids) == original_length:
                self.updater.bot.send_message(chat_id=user, text="Why would you register twice, dumbass!")
            else:
                self.updater.bot.send_message(chat_id=user, text="You have been registered.")
        except Exception as e:
            print(e)

    def remind_users(self):
        for user in self.user_ids:
            self.updater.bot.send_message(chat_id=user, text="Wer ist dabei?", reply_markup=self.attend_markup)


def run_scheduler(bot):
    schedule.every().monday.at("14:00").do(bot.remind_users)
    while bot.updater is not None:
        schedule.run_pending()

    run_scheduler(bot)


def start(token: str):
    updater = Updater(token=token)
    bot = Bot(updater)

    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("register", lambda _, u: bot.register(u)))
    dispatcher.add_handler(CommandHandler("remind", lambda b, u: bot.remind_users()))

    with open("users.json") as f:
        bot.user_ids = set(json.load(f))

    t = threading.Thread(target=run_scheduler, args=[bot])
    t.start()

    print("Running")
    updater.start_polling()


if __name__ == "__main__":
    import json

    with open("secrets.json") as f:
        token = json.load(f)['token']

    try:
        start(token)
    except Exception as e:
        print(e)
