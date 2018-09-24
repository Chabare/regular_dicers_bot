import datetime
import os
import threading

import schedule
from telegram.ext import CommandHandler, MessageHandler, Updater

from dicers_bot import Bot


def run_scheduler(bot):
    schedule.every().monday.at("14:00").do(bot.remind_users)
    while bot.updater is not None:
        schedule.run_pending()

    run_scheduler(bot)


def start(token: str):
    updater = Updater(token=token)
    bot = Bot(updater)

    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("register", lambda _, update: bot.register(update)))
    dispatcher.add_handler(CommandHandler("remind_all", lambda _, update: bot.remind_users(update)))
    dispatcher.add_handler(CommandHandler("remind_me", lambda _, update: bot.remind_user(update)))
    dispatcher.add_handler(CommandHandler("status", lambda b, update: b.send_message(chat_id=update.message.chat_id,
                                                                                     text="[{}]".format(
                                                                                         update.message.chat_id))))
    dispatcher.add_handler(CommandHandler("server_time", lambda b, u: b.send_message(chat_id=u.message.chat_id,
                                                                                     text=datetime.datetime.now().strftime(
                                                                                         "%d-%m-%Y %H-%m-%S"))))
    dispatcher.add_handler(CommandHandler("version", lambda b, u: b.send_message(chat_id=u.message.chat_id,
                                                                                     text="{{VERSION}}")))
    dispatcher.add_handler(MessageHandler("", callback=lambda _, update: bot.check_participation_message(update)))

    user_file = "users.json"
    if os.path.exists(user_file):
        with open(user_file) as f:
            bot.user_ids = set(json.load(f))
    else:
        bot.user_ids = []

    t = threading.Thread(target=run_scheduler, args=[bot])
    t.start()

    print("Running")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    import json

    with open("secrets.json") as f:
        token = json.load(f)['token']

    try:
        start(token)
    except Exception as e:
        print(e)
