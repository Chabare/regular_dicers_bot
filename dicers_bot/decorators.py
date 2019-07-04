from __future__ import annotations

import inspect
from datetime import timedelta

from telegram import Update
from telegram.ext import CallbackContext

from . import bot
from . import chat
from . import logger
from . import user


class Command:
    def __init__(self, chat_admin: bool = False, main_admin: bool = False):
        self.chat_admin = chat_admin
        self.main_admin = main_admin

    @staticmethod
    def _add_chat(clazz, update: Update, context: CallbackContext) -> chat.Chat:
        new_chat = clazz.chats.get(update.effective_chat.id)
        if not new_chat:
            new_chat = chat.Chat(update.effective_chat.id, clazz.updater.bot)
            clazz.chats[new_chat.id] = new_chat

        context.chat_data["chat"] = new_chat

        new_chat.title = update.effective_chat.title
        new_chat.type = update.effective_chat.type

        return new_chat

    @staticmethod
    def _add_user(update: Update, context: CallbackContext) -> user.User:
        return User.from_tuser(update.effective_user)

    def __call__(self, func):
        def wrapped_f(*args, **kwargs):
            exception = None
            log = logger.create_logger(f"command_{func.__name__}")
            log.debug("Start")

            signature = inspect.signature(func)
            arguments = signature.bind(*args, **kwargs).arguments

            clazz: bot.Bot = arguments.get("self")
            update: Update = arguments.get("update")
            context: CallbackContext = arguments.get("context")
            execution_message: str = f"Executing {func.__name__}"
            finished_execution_message: str = f"Finished executing {func.__name__}"

            if not update:
                log.debug("Execute function due to coming directly from the bot.")

                log.debug(execution_message)
                result = func(*args, **kwargs)
                log.debug(finished_execution_message)

                return result

            chat = context.chat_data.get("chat")
            if not chat:
                chat = self._add_chat(clazz, update, context)
            chat.type = update.effective_chat.type

            if not clazz.chats.get(chat.id):
                clazz.chats[chat.id] = chat

            user = chat.get_user_by_id(update.effective_user.id)
            if not user:
                user = self._add_user(update, context)

            chat.add_user(user)
            context.user_data["user"] = user

            if self.main_admin:
                if chat.id == clazz.state.get("main_id"):
                    log.debug("Execute function due to coming from the main_chat")
                else:
                    message = f"Chat {chat} is not allowed to perform this action."
                    log.warning(message)
                    clazz.mute_user(chat_id=chat.id, user=user, until_date=timedelta(minutes=15), reason=message)
                    exception = PermissionError()

            if self.chat_admin:
                if chat.type == chat.ChatType.PRIVATE:
                    log.debug("Execute function due to coming from a private chat")
                elif user in chat.administrators():
                    log.debug("User is a chat admin and therefore allowed to perform this action, executing")
                else:
                    log.error("User isn't a chat_admin and is not allowed to perform this action.")
                    exception = PermissionError()

            if update.effective_message:
                chat.add_message(update)  # Needs user in chat

            log.debug(execution_message)
            try:
                if exception:
                    raise exception

                result = func(*args, **kwargs)
                log.debug(finished_execution_message)
                return result
            except PermissionError:
                if update.effective_message:
                    update.effective_message.reply_text("You're not allowed to perform this action.")
            except Exception as e:
                # Log for debugging purposes
                log.error(str(e), exc_info=True)

                raise e
            finally:
                clazz.save_state()
                log.debug("End")

        return wrapped_f


def group(function):
    def wrapper(clz: chat.Chat, *args, **kwargs):
        log = logger.create_logger(f"group_wrapper_{function.__name__}")
        log.debug("Start")
        if not (hasattr(clz, "type") and (isinstance(clz.type, str) or isinstance(clz.type, chat.ChatType))):
            message = "group decorator can only be used on a class which has a `type` attribute of type `str` or `chat.ChatType`."
            log.error(message)
            raise TypeError(message)

        if clz.type == chat.ChatType.PRIVATE:
            log.debug("Not executing group function in private chat.")
            return False

        log.debug("Execute function")
        return function(clz, *args, **kwargs)

    return wrapper
