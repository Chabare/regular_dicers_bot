from __future__ import annotations

from typing import Any, Dict, Optional, Set, Iterator, List

from telegram import Message
from telegram import User as TUser

from .event import Event


class User:
    def __init__(self, name: str, _id: int, chat_user: Optional[TUser] = None):
        self.name = name
        self.roll = -1
        self.jumbo = False
        self.alcoholic = True
        self.id = _id
        self._internal = chat_user
        self.muted = False
        self.messages: Set[Message] = set()
        self.spamming = False
        self.drink = None

    def set_roll(self, roll: int) -> None:
        self.roll = roll

    def set_jumbo(self, jumbo: bool) -> None:
        self.jumbo = jumbo

    def set_alcoholic(self, alcoholic: bool) -> None:
        self.alcoholic = alcoholic

    # def __getattr__(self, item):
    #     return getattr(self.internal, item)

    def __eq__(self, other) -> bool:
        if not isinstance(other, User):
            return False

        return other.id == self.id

    def __hash__(self) -> int:
        return self.name.__hash__()

    def __str__(self) -> str:
        """
        <Name | Roll (jumbo) | muted>
        """
        roll = str(self.roll) if self.roll != -1 else "no roll"
        jumbo = " (+1)" if self.jumbo else ""
        muted = "muted" if self.muted else "not muted"

        roll += jumbo
        return f"<{' | '.join([self.name, roll, muted])}>"

    @classmethod
    def from_tuser(cls, chat_user: TUser) -> User:
        user = User(chat_user.first_name, chat_user.id, chat_user)

        return user

    @classmethod
    def deserialize(cls, json: Dict[str, Any]) -> User:
        user = User(json.get("name"), json.get("id"))
        user.muted = json.get("muted", False)
        user.roll = int(json.get("roll", -1))
        user.jumbo = bool(json.get("jumbo", False))
        user.alcoholic = bool(json.get("alcoholic", True))
        user.drink = json.get("drink_name", None)

        return user

    def serialize(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "roll": self.roll,
            "jumbo": self.jumbo,
            "muted": self.muted,
            "id": self.id,
            "alcoholic": self.alcoholic,
            "drink_name": self.drink
        }

    def get_attended_events(self, events: List[Event]) -> Iterator[Event]:
        for event in events:
            if self in event.attendees:
                yield event

    def markdown_mention(self) -> str:
        return f"[{self.name}](tg://user?id={self.id})"
