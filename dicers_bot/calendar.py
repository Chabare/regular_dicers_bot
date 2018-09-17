from datetime import datetime

from oauth2client import file, client, tools
from googleapiclient.discovery import build
from httplib2 import Http


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
    event = base_event

    def __init__(self, filename: str = "credentials.json"):
        store = file.Storage(filename)
        credentials = store.get()
        if not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(filename, SCOPES)
            flow.user_agent = "regular_dicers_bot"
            credentials = tools.run_flow(flow, store)
        self.service = build("calendar", "v3", http=credentials.authorize(Http()))

    def create(self):
        self.fill_base_event()
        gevent = self.service.events().insert(calendarId="43httl0ouo48t260oqturfrs84@group.calendar.google.com",
                                              body=self.event).execute()

        return gevent.get("htmlLink")

    @staticmethod
    def get_start_time():
        today = datetime.today()
        start = today.replace(hour=21, minute=0, second=0, microsecond=0)

        return start

    @staticmethod
    def get_end_time():
        today = datetime.today()
        end = today.replace(hour=23, minute=30, second=0, microsecond=0)

        return end

    def fill_base_event(self):
        date_format = "%Y-%m-%dT%H:%M:%S"
        self.event["start"]["dateTime"] = self.get_start_time().strftime(date_format)
        self.event["end"]["dateTime"] = self.get_end_time().strftime(date_format)
