import os
import threading
import time
from datetime import datetime

import schedule
import sentry_sdk
from pytz import timezone
from telegram import TelegramError
from telegram.ext import CommandHandler, Updater, CallbackQueryHandler, MessageHandler, Filters

from dicers_bot import Bot, create_logger


def run_scheduler(bot: Bot):
    logger = create_logger("run_scheduler")
    logger.debug("Start run_scheduler")
    default_timezone = timezone("Europe/Berlin")
    today: datetime = datetime.today()
    additional_reset_time: str = default_timezone.localize(today.replace(hour=13, minute=0)).strftime("%H:%M")
    attend_time: str = default_timezone.localize(today.replace(hour=14, minute=0)).strftime("%H:%M")
    dice_time: str = default_timezone.localize(today.replace(hour=20, minute=30)).strftime("%H:%M")
    reset_time: str = default_timezone.localize(today.replace(hour=0, minute=0)).strftime("%H:%M")

    logger.info("Set schedule")

    schedule.every().monday.at(additional_reset_time).do(bot.reset)
    schedule.every().monday.at(attend_time).do(bot.show_attend_keyboards)
    schedule.every().monday.at(dice_time).do(bot.show_dice_keyboards)
    schedule.every().tuesday.at(reset_time).do(bot.reset)

    logger.info("Run schedule")
    while True:
        schedule.run_pending()
        time.sleep(5)


def handle_telegram_error(error: TelegramError):
    create_logger("handle_telegram_error").error(error)


def start(bot_token: str):
    updater = Updater(token=bot_token)
    bot = Bot(updater)

    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("register", lambda _, update: bot.register(update)))
    dispatcher.add_handler(CommandHandler("unregister", lambda _, update: bot.unregister(update)))
    dispatcher.add_handler(CommandHandler("register_main", lambda _, update: bot.register_main(update)))
    dispatcher.add_handler(CommandHandler("remind_all", lambda _, update: bot.remind_users(update)))
    dispatcher.add_handler(CommandHandler("remind_me", lambda _, update: bot.remind_chat(update)))
    dispatcher.add_handler(CommandHandler("show_dice", lambda _, update: bot.show_dice(update.message.chat_id)))
    dispatcher.add_handler(CommandHandler("reset", lambda b, _: bot.reset()))
    dispatcher.add_handler(CommandHandler("status", lambda b, update: b.send_message(chat_id=update.message.chat_id,
                                                                                     text="[{}]".format(
                                                                                         update.message.chat_id))))
    dispatcher.add_handler(CommandHandler("server_time", lambda b, u: b.send_message(chat_id=u.message.chat_id,
                                                                                     text=datetime.now().strftime(
                                                                                         "%d-%m-%Y %H-%M-%S"))))
    dispatcher.add_handler(CommandHandler("version", lambda b, u: b.send_message(chat_id=u.message.chat_id,
                                                                                 text="{{VERSION}}")))
    dispatcher.add_handler(
        CallbackQueryHandler(lambda _, u: bot.handle_attend_callback(u), pattern="attend_(.*)"))
    dispatcher.add_handler(
        CallbackQueryHandler(lambda _, u: bot.handle_dice_callback(u), pattern="dice_(.*)"))
    dispatcher.add_handler(
        MessageHandler(Filters.text, lambda _, update: bot.handle_message(update)))
    dispatcher.add_error_handler(
        lambda _bot, _update, error: handle_telegram_error(error)
    )

    state_file = "state.json"
    if os.path.exists(state_file):
        with open(state_file) as file:
            try:
                state = json.load(file)
            except json.decoder.JSONDecodeError as e:
                create_logger("state.json").warning(f"Unable to load previous state: {e}")
                state = {"main_id": None}

        bot.set_state(state)

    create_logger("thread").info("Start scheduler thread")
    t = threading.Thread(target=run_scheduler, args=[bot])
    t.start()

    print("Running")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    import json

    with open("secrets.json") as f:
        content = json.load(f)
        token = content['token']
        try:
            sentry_dsn = content['sentry_dsn']
        except KeyError:
            sentry_dsn = None

    sentry_sdk.init(sentry_dsn)

    # noinspection PyBroadException
    try:
        start(token)
    except Exception:
        sentry_sdk.capture_exception()
