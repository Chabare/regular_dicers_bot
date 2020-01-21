import os
import sys
import threading
from datetime import datetime

import sentry_sdk
from telegram import TelegramError
from telegram.ext import CommandHandler, Updater, CallbackQueryHandler, MessageHandler, Filters, InlineQueryHandler

from dicers_bot import Bot, create_logger


def schedule_jobs(bot: Bot, updater: Updater):
    logger = create_logger("schedule jobs")
    logger.debug("Start")
    today: datetime = datetime.today()
    additional_reset_time = today.replace(hour=13, minute=30)
    attend_time = today.replace(hour=14, minute=0)
    dice_time = today.replace(hour=21, minute=0)
    reset_time = today.replace(hour=0, minute=0)

    logger.info("Set schedule")

    monday = (0,)
    tuesday = (1,)
    updater.job_queue.run_daily(callback=lambda _: bot.reset_all(None, None), time=additional_reset_time, days=monday)
    updater.job_queue.run_daily(callback=lambda _: bot.remind_users(None, None), time=attend_time, days=monday)
    updater.job_queue.run_daily(callback=lambda _: bot.show_dice_keyboards(None, None), time=dice_time, days=monday)
    updater.job_queue.run_daily(callback=lambda _: bot.reset_all(None, None), time=reset_time, days=tuesday)

    logger.info("Updated job_queue")


def handle_telegram_error(error: TelegramError):
    create_logger("handle_telegram_error").error(error)


def start(bot_token: str):
    logger = create_logger("start")
    logger.debug("Start bot")

    updater = Updater(token=bot_token, use_context=True)
    bot = Bot(updater)

    dispatcher = updater.dispatcher

    logger.debug("Register command handlers")
    # CommandHandler
    dispatcher.add_handler(CommandHandler("register_main", bot.register_main))
    dispatcher.add_handler(CommandHandler("remind_me", bot.remind_chat))
    dispatcher.add_handler(CommandHandler("show_dice", bot.show_dice))
    dispatcher.add_handler(CommandHandler("users", bot.show_users))
    dispatcher.add_handler(CommandHandler("price_stats", bot.price_stats))
    dispatcher.add_handler(CommandHandler("set_cocktail", bot.set_cocktail))
    dispatcher.add_handler(CommandHandler("add_insult", bot.add_insult, pass_args=True))
    dispatcher.add_handler(CommandHandler("list_insults", bot.list_insults))
    dispatcher.add_handler(CommandHandler("jesus", bot.jesus))
    dispatcher.add_handler(CommandHandler("list_cocktails", bot.list_cocktails))

    # chat_admin
    dispatcher.add_handler(CommandHandler("reset", bot.reset))
    dispatcher.add_handler(CommandHandler("delete_chat", bot.delete_chat))
    dispatcher.add_handler(CommandHandler("enable_spam_detection", bot.enable_spam_detection))
    dispatcher.add_handler(CommandHandler("disable_spam_detection", bot.disable_spam_detection))
    dispatcher.add_handler(CommandHandler("get_data", bot.get_data))
    dispatcher.add_handler(CommandHandler("mute", bot.mute, pass_args=True))
    dispatcher.add_handler(CommandHandler("unmute", bot.unmute, pass_args=True))
    dispatcher.add_handler(CommandHandler("kick", bot.kick, pass_args=True))

    # main_admin
    dispatcher.add_handler(CommandHandler("remind_all", bot.remind_users))
    dispatcher.add_handler(CommandHandler("reset_all", bot.reset_all))
    dispatcher.add_handler(CommandHandler("unregister_main", bot.unregister_main))

    # Debugging
    dispatcher.add_handler(CommandHandler("status", bot.status))
    dispatcher.add_handler(CommandHandler("server_time", bot.server_time))
    dispatcher.add_handler(CommandHandler("version", bot.version))

    # CallbackQueryHandler
    dispatcher.add_handler(CallbackQueryHandler(bot.handle_attend_callback, pattern="attend_(.*)"))
    dispatcher.add_handler(CallbackQueryHandler(bot.handle_dice_callback, pattern="dice_(.*)"))

    # InlineQueryHandler
    dispatcher.add_handler(InlineQueryHandler(bot.handle_inline_query))

    # MessageHandler
    dispatcher.add_handler(MessageHandler(Filters.command, bot.handle_unknown_command))
    dispatcher.add_handler(
        MessageHandler(Filters.text, bot.handle_message))
    dispatcher.add_handler(
        MessageHandler(Filters.status_update.left_chat_member, bot.handle_left_chat_member))
    dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, bot.new_member))

    # ErrorHandler
    dispatcher.add_error_handler(
        lambda _bot, _update, error: handle_telegram_error(error)
    )

    state_file = "state.json"
    logger.debug(f"Read state from {state_file}")
    if os.path.exists(state_file):
        with open(state_file) as file:
            try:
                state = json.load(file)
            except json.decoder.JSONDecodeError as e:
                logger.warning(f"Unable to load previous state: {e}")
                state = {"main_id": None}

        bot.set_state(state)

    schedule_jobs(bot, updater)

    try:
        if sys.argv[1] == "--testrun":
            logger.info("Scheduling exit in 5 seconds")

            def _exit():
                logger.info("Exiting")
                updater.stop()
                updater.is_idle = False

            timer = threading.Timer(5, _exit)
            timer.setDaemon(True)
            timer.start()
    except IndexError:
        pass

    logger.info("Running")
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
    except Exception as e:
        sentry_sdk.capture_exception()
        create_logger("__main__").error(e)
        sys.exit(1)
