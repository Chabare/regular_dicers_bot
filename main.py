import datetime
import os
import threading
import time

import schedule
from telegram.ext import CommandHandler, Updater, CallbackQueryHandler

from dicers_bot import Bot


def run_scheduler(bot):
    schedule.every().monday.at("14:00").do(bot.remind_users)
    schedule.every().tuesday.at("00:00").do(bot.reset_attendees)
    schedule.every().monday.at("20:10").do(bot.show_dice)
    while True:
        schedule.run_pending()
        time.sleep(5)


def start(token: str):
    updater = Updater(token=token)
    bot = Bot(updater)

    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("register", lambda _, update: bot.register(update)))
    dispatcher.add_handler(CommandHandler("unregister", lambda _, update: bot.unregister(update)))
    dispatcher.add_handler(CommandHandler("register_main", lambda _, update: bot.register_main(update)))
    dispatcher.add_handler(CommandHandler("remind_all", lambda _, update: bot.remind_users(update)))
    dispatcher.add_handler(CommandHandler("remind_me", lambda _, update: bot.remind_user(update)))
    dispatcher.add_handler(CommandHandler("show_dice", lambda _, update: bot.show_dice(update)))
    dispatcher.add_handler(CommandHandler("reset", lambda b, _: bot.reset_attendees()))
    dispatcher.add_handler(CommandHandler("status", lambda b, update: b.send_message(chat_id=update.message.chat_id,
                                                                                     text="[{}]".format(
                                                                                         update.message.chat_id))))
    dispatcher.add_handler(CommandHandler("server_time", lambda b, u: b.send_message(chat_id=u.message.chat_id,
                                                                                     text=datetime.datetime.now().strftime(
                                                                                         "%d-%m-%Y %H-%M-%S"))))
    dispatcher.add_handler(CommandHandler("version", lambda b, u: b.send_message(chat_id=u.message.chat_id,
                                                                                 text="{{VERSION}}")))
    dispatcher.add_handler(
        CallbackQueryHandler(lambda _, u: bot.handle_attend_callback(u), pattern="attend_(.*)"))
    dispatcher.add_handler(
        CallbackQueryHandler(lambda _, u: bot.handle_dice_callback(u), pattern="dice_(.*)"))

    user_file = "users.json"
    if os.path.exists(user_file):
        with open(user_file) as f:
            bot.user_ids = set(json.load(f))
    else:
        bot.user_ids = set()

    state_file = "state.json"
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = dict(json.load(f))
        bot.state = state

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
