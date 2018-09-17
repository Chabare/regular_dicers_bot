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
    dispatcher.add_handler(CommandHandler("register", lambda _, update: bot.register(update)))
    dispatcher.add_handler(CommandHandler("remind_all", lambda _, update: bot.remind_users(update)))
    dispatcher.add_handler(CommandHandler("remind_me", lambda _, update: bot.remind_user(update)))
    dispatcher.add_handler(CommandHandler("status", lambda b, update: b.send_message(chat_id=update.message.chat_id, text="[{}]".format(update.message.chat_id))))
    dispatcher.add_handler(MessageHandler("", callback=lambda _, update: bot.check_participation_message(update)))

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
