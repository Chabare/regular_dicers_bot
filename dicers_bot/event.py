from datetime import datetime, timedelta
from typing import Set, Dict

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

    def add_absentee(self, user):
        self.logger.info("Add absentee {} to event".format(user))

        return self.absentees.add(user)

    def remove_absentee(self, user):
        self.logger.info("Remove absentee {} from event".format(user))
        self.absentees.remove(user)
        self.add_attendee(user)

    def add_attendee(self, user: User):
        self.logger.info("Add {} to event".format(user))
        try:
            self.remove_absentee(user)
        except KeyError:
            self.logger.info("User was not in absentees: {}".format(user))
        self.attendees.add(user)

    def remove_attendee(self, user):
        self.logger.info("Remove {} from event".format(user))
        self.attendees.remove(user)

    def serialize(self) -> Dict:
        self.logger.info("Serialize event")
        serialized = {
            "timestamp": self.timestamp.strftime(self.date_format),
            "attendees": [attendee.serialize() for attendee in self.attendees]
        }
        self.logger.info("Serialized event: {}".format(serialized))
        return serialized

    @classmethod
    def deserialize(cls, json_object: Dict):
        event = Event()
        event.timestamp = datetime.strptime(json_object["timestamp"], event.date_format)
        event.attendees = set([User.deserialize(attendee) for attendee in json_object["attendees"]])

        return event

    @staticmethod
    def _next_monday():
        today = datetime.today()
        weekday = 0

        d = datetime.strptime("{} {} {}".format(today.year, today.month, today.day), "%Y %m %d")
        days_ahead = weekday - d.weekday()

        next_monday = d + timedelta(days_ahead)
        return next_monday