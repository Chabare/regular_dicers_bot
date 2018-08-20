import threading

import schedule
from telegram.ext import CommandHandler, Updater

users = set()
updater = None


def register(bot, update):
    global users

    try:
        user = update.message.chat_id
        original_length = len(users)
        users.add(user)

        with open("users.json", "w+") as f:
            json.dump(list(users), f)

        if len(users) == original_length:
            bot.send_message(chat_id=user, text="Why would you register twice, dumbass!")
        else:
            bot.send_message(chat_id=user, text="You have been registered.")
    except Exception as e:
        print(e)


def remind_users():
    global users
    global updater

    for user in users:
        updater.bot.send_message(chat_id=user, text="Wer ist dabei?")


def run_scheduler():
    global updater

    schedule.every().monday.at("16:00").do(remind_users)
    while updater is not None:
        schedule.run_pending()

    run_scheduler()


def start(token: str):
    global updater
    global users
    updater = Updater(token=token)

    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("register", register))

    with open("users.json") as f:
        users = set(json.load(f))

    t = threading.Thread(target=run_scheduler)
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
