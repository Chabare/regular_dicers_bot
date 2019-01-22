from typing import Any, Dict, Optional, Set

from telegram import Message
from telegram import User as TUser


class User:
    def __init__(self, name: str, _id: int, chat_user: Optional[TUser] = None):
        self.name = name
        self.roll = -1
        self.jumbo = False
        self.id = _id
        self._internal = chat_user
        self.muted = False
        self.messages: Set[Message] = set()

    def set_roll(self, roll: int) -> None:
        self.roll = roll

    def set_jumbo(self, jumbo: bool) -> None:
        self.jumbo = jumbo

    # def __getattr__(self, item):
    #     return getattr(self.internal, item)

    def __eq__(self, other):
        if not isinstance(other, User):
            return False

        return other.name == self.name

    def __hash__(self):
        return self.name.__hash__()

    def __str__(self) -> str:
        return "{} ({}{})".format(self.name, self.roll, "+1" if self.jumbo else "")

    @classmethod
    def from_tuser(cls, chat_user: TUser):
        user = User(chat_user.name, chat_user.id, chat_user)

        return user

    @classmethod
    def deserialize(cls, json: Dict[str, Any]):
        user = User(json.get("name"), json.get("id"))
        user.muted = json.get("muted", False)

        return user

    def serialize(self):
        return {
            "name": self.name,
            "roll": self.roll,
            "jumbo": self.jumbo,
            "muted": self.muted,
            "id": self.id
        }
