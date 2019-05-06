from __future__ import annotations

from datetime import datetime, timedelta
from typing import Set, Dict, Any, Optional

from dicers_bot.chat import User
from .logger import create_logger


class Event:
    def __init__(self):
        self.date_format = "%d.%m.%Y"
        self.timestamp = self._next_monday()
        self.logger = create_logger("event_{}".format(self.timestamp))
        self.logger.info("Create event")
        self.attendees: Set[User] = set()
        self.absentees: Set = set()
        self.logger.info("Created event for {}".format(self.timestamp))

    def add_absentee(self, user) -> None:
        self.logger.info("Add absentee {} to event".format(user))

        self.absentees.add(user)

    def remove_absentee(self, user) -> None:
        self.logger.info("Remove absentee {} from event".format(user))
        self.absentees.remove(user)
        self.add_attendee(user)

    def add_attendee(self, user: User) -> None:
        self.logger.info("Add {} to event".format(user))
        try:
            self.remove_absentee(user)
        except KeyError:
            self.logger.info("User was not in absentees: {}".format(user))
        self.attendees.add(user)

    def remove_attendee(self, user) -> None:
        self.logger.info("Remove {} from event".format(user))
        self.attendees.remove(user)

    def serialize(self) -> Dict[str, Any]:
        self.logger.info("Serialize event")
        serialized = {
            "timestamp": self.timestamp.strftime(self.date_format),
            "attendees": [attendee.serialize() for attendee in self.attendees],
            "absentees": [absentee.serialize() for absentee in self.absentees]
        }
        self.logger.info("Serialized event")  # .format(serialized))
        return serialized

    @classmethod
    def deserialize(cls, json_object: Dict) -> Optional[Event]:
        if not json_object:
            return None

        event = Event()
        event.timestamp = datetime.strptime(json_object.get("timestamp"), event.date_format)
        event.attendees = set([User.deserialize(attendee) for attendee in json_object.get("attendees", [])])
        event.absentees = set([User.deserialize(absentee) for absentee in json_object.get("absentees", [])])

        return event

    @staticmethod
    def _next_monday() -> datetime:
        today = datetime.today()
        weekday = 0

        d = datetime.strptime("{} {} {}".format(today.year, today.month, today.day), "%Y %m %d")
        days_ahead = weekday - d.weekday()

        next_monday = d + timedelta(days_ahead)
        return next_monday
