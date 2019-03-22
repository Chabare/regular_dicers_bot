import functools


def admin(func):
    """
    The function needs to have a keyword parameter named `update` or have the update as the first parameter after self.
    The admin key is determined by `self.state.get("main_id")`.

    The admin decorator executes the given function if:
    - the `update` argument is `None`
    - the chat_id from update (`update.message.chat_id`) matches the main chat id (`Bot.state["main_id"]`)
    - `main_id` is `None`

    Examples:
    @admin
    def require_admin(self, *, update: Update):
        [...]

    @admin
    def require_admin_2(self, update: Update):
        [...]

    :param func: Func] -> Any
    :return:
    """
    @functools.wraps(func)
    def admin_wrapper(*args, **kwargs):
        admin_key = args[0].state.get("main_id")

        try:
            update = kwargs.get("update") or args[1]
        except IndexError:
            update = None

        if not update or getattr(update, "message", None):
            if not update or update.message.chat_id == admin_key:
                return func(*args, **kwargs)
            else:
                raise PermissionError("You're not authorized to perform this action")

    return admin_wrapper
