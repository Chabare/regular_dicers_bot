from datetime import datetime

from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools

from .logger import create_logger

SCOPES = "https://www.googleapis.com/auth/calendar"
base_event = {
    "summary": "Würfeln",
    "location": "Kasinostr. 5, 64293 Darmstadt",
    "description": "",
    "start": {
        "dateTime": "...",
        "timeZone": "Europe/Berlin"
    },
    "end": {
        "dateTime": "...",
        "timeZone": "Europe/Berlin"
    },
}


class Calendar:
    def __init__(self, filename: str = "credentials.json"):
        self.event = base_event
        self.last_event = None
        self.logger = create_logger("calendar")

        # noinspection PyBroadException
        try:
            credentials = self._load_credentials(filename)
            self.service = build("calendar", "v3", http=credentials.authorize(Http()))
            self.logger.debug("Calendar initialized.")
        except Exception as e:
            self.logger.warning("Calendar module is disabled. Reason: %s", str(e))
            self.service = None

    def create(self) -> None:
        service = self.service
        if not service:
            return None

        if datetime.today().weekday() != 0:
            print("Not monday ({})".format(datetime.today().weekday()))
            return None
        self.fill_base_event()

        if self.last_event and self.event["start"]["dateTime"] == self.last_event["start"]["dateTime"]:
            print("Event already exists(now | last): {} == {}".format(
                self.event["start"]["dateTime"],
                self.last_event["start"]["dateTime"])
            )
            return None

        gevent = service.events().insert(calendarId="43httl0ouo48t260oqturfrs84@group.calendar.google.com",
                                         body=self.event).execute()
        self.last_event = self.event
        self.event = base_event

        gevent.get("htmlLink")

    @staticmethod
    def _load_credentials(filename) -> client.Credentials:
        store = file.Storage(filename)

        try:
            credentials = store.get()
        except KeyError:
            credentials = None

        if not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(filename, SCOPES)
            flow.user_agent = "regular_dicers_bot"
            return tools.run_flow(flow, store)

        return credentials

    @staticmethod
    def _get_start_time() -> datetime:
        today = datetime.today()
        start = today.replace(hour=21, minute=0, second=0, microsecond=0)

        return start

    @staticmethod
    def _get_end_time() -> datetime:
        today = datetime.today()
        end = today.replace(hour=23, minute=30, second=0, microsecond=0)

        return end

    def fill_base_event(self) -> None:
        date_format = "%Y-%m-%dT%H:%M:%S"
        self.event["start"]["dateTime"] = self._get_start_time().strftime(date_format)
        self.event["end"]["dateTime"] = self._get_end_time().strftime(date_format)
