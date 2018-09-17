import threading

import schedule
from dicers_bot import Bot
from telegram.ext import CommandHandler, MessageHandler, Updater


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
    updater.idle()


if __name__ == "__main__":
    import json

    with open("secrets.json") as f:
        token = json.load(f)['token']

    try:
        start(token)
    except Exception as e:
        print(e)
