from apiclient import discovery
import datetime
import dateutil.parser
import httplib2
import json
import os
import pytz
import re

wfh_events = re.compile(r'\b((wfh)|(working from home)|(2nd line))\b')
unavailable_events = re.compile(r'\b((leave)|(al)|(holiday)|(ooi)|(out of office)|(off work))\b')
preferred_events = re.compile(r'preferred interview slot')


class Event(object):
    def __init__(self, data, is_saved, calendar_id=None):
        self.is_saved = is_saved
        self.start = self.parse_date_or_time(data["start"], is_start=True)
        self.end = self.parse_date_or_time(data["end"], is_start=False)
        self.summary = data.get("summary", "")
        self.description = data.get("description", "")
        self.attendees = self.group_attendees(data, calendar_id)
        self.busy = data.get("transparency", "") != "transparent"
        invitation = self.owner_invitation(data)
        if invitation is None:
            self.response_status = ""
            self.optional = True
        else:
            self.response_status = invitation.get("responseStatus", "")
            self.optional = invitation.get("optional", False)

    def intersects_with(self, start, end):
        if end < self.start:
            return False
        if start > self.end:
            return False
        return True

    def potential_attendees(self):
        return (
            self.attendees.get('accepted', []) +
            self.attendees.get('tentative', []) +
            self.attendees.get('needsAction', [])
        )

    @staticmethod
    def owner_invitation(data):
        invitation = [
            attendee for attendee in data.get("attendees", [])
            if attendee.get("self")
        ]
        if len(invitation) == 0:
            return None
        return invitation[0]

    @staticmethod
    def parse_date_or_time(data, is_start):
        if "dateTime" in data:
            return Event.parse_iso_datetime(data["dateTime"], is_start=is_start)
        return Event.parse_iso_datetime(data["date"], is_start=is_start)

    @staticmethod
    def parse_iso_datetime(iso_date_string, is_start):
        if is_start:
            default = datetime.datetime(
                year=2000, month=1, day=1,
                hour=0, minute=0, tzinfo=pytz.utc,
            )
        else:
            default = datetime.datetime(
                year=2000, month=1, day=1,
                hour=0, minute=0, tzinfo=pytz.utc,
            )

        return pytz.utc.normalize(
            dateutil.parser.parse(
                iso_date_string, default=default
        ))

    @staticmethod
    def group_attendees(data, calendar_id):
        attendees = data.get("attendees", [])
        if len(attendees) == 0:
            return {
                "accepted": [calendar_id],
            }
        result = {}
        for attendee in attendees:
            if attendee.get("optional", False):
                continue
            if attendee.get("resource", False):
                continue
            result.setdefault(
                attendee["responseStatus"], []
            ).append(attendee["email"])
        return result

    def __repr__(self):
        return u"Event({} to {}: {} {} {} optional={} busy={})".format(
            self.start,
            self.end,
            repr(self.summary),
            self.attendees,
            self.response_status,
            self.optional,
            self.busy,
        ).encode('utf8')


class Calendar(object):
    def __init__(self, calendar_summary, events):
        self.calendar_summary = calendar_summary
        self.events = sorted(events, key=lambda e: e.start)

    def intersecting_events(self, start, end):
        return [
            event
            for event in self.events
            if event.intersects_with(start, end)
        ]

    def conflict_level(self, start, end):
        """Return a level indicating the amount of conflict for a slot.

        Returns 0 for no conflict, and a very high value for someone who is on
        leave or out of the office.

        Returns None if the time isn't available at all for the person (eg, on
        holiday).

        """
        events = self.intersecting_events(start, end)
        max_attendees = 0
        is_preferred = False
        for event in events:
            if preferred_events.search(event.summary.lower()):
                is_preferred = True
                continue
            if wfh_events.search(event.summary.lower()):
                return None
            if not event.busy:
                continue
            if unavailable_events.search(event.summary.lower()):
                return None
            if event.response_status != "accepted":
                continue
            max_attendees = max(max_attendees,
                len(event.attendees.get("accepted", [])))
        if is_preferred:
            return 0
        elif max_attendees == 0:
            return 1
        elif max_attendees == 1:
            return 2
        elif max_attendees == 2:
            return 5
        else:
            return 10


class CalendarService(object):
    def __init__(self, creds):
        self.creds = creds
        self._service = None
        self._calendars = None

    def service(self):
        if self._service is None:
            http = self.creds.authorize(httplib2.Http())
            self._service = discovery.build('calendar', 'v3', http=http)
        return self._service

    def calendar_id(self, calendar_summary):
        if self._calendars is None:
            self._fetch_list_of_calendars()
        return self._calendars.get(calendar_summary, calendar_summary)

    def events(self):
        return self.service().events()

    def _fetch_list_of_calendars(self):
        self._calendars = dict(self._iter_calendars())

    def _iter_calendars(self):
        page_token = None
        while True:
            results = self.service().calendarList().list(pageToken=page_token).execute()
            for result in results['items']:
                yield (result['summary'], result['id'])
            page_token = results.get('nextPageToken')
            if page_token is None:
                break


class CalendarFetcher(object):
    def __init__(self, service, date_min_formatted, date_max_formatted):
        self.service = service
        self.date_min_formatted = date_min_formatted
        self.date_max_formatted = date_max_formatted
        
    def fetch_events(self, calendar_summary):
        print("Fetching calendar for %s" % (calendar_summary, ))
        return list(self._iter_events(self.service.calendar_id(calendar_summary)))

    def _iter_events(self, calendar_id):
        page_token = None
        while True:
            results = self.service.events().list(
                pageToken=page_token,
                calendarId=calendar_id,
                orderBy="startTime",
                singleEvents=True,
                timeMin=self.date_min_formatted,
                timeMax=self.date_max_formatted,
                timeZone="UTC",
            ).execute()
            for event in results['items']:
                yield event
            page_token = results.get('nextPageToken')
            if page_token is None:
                break


class CalendarCache(object):
    def __init__(self, calendar_service, date_min, date_max, cache_dir):
        self.calendar_service = calendar_service
        self.date_min_formatted = date_min.isoformat() + "T00:00:00Z"
        self.date_max_formatted = date_max.isoformat() + "T00:00:00Z"
        self.cache_dir = cache_dir
        self.calendar_fetcher = CalendarFetcher(
            calendar_service,
            self.date_min_formatted,
            self.date_max_formatted,
        )

        if not os.path.isdir(cache_dir):
            os.makedirs(cache_dir)

    def get(self, calendar_summary):
        calendar_id = self.calendar_service.calendar_id(calendar_summary)
        return Calendar(
            calendar_summary,
            [
                Event(event, True, calendar_id)
                for event in self._fetch_events(calendar_summary)
            ],
        )

    def _fetch_events(self, calendar_summary):
        slug = re.sub("[^a-z0-9]", "_", calendar_summary.lower())
        path = os.path.join(self.cache_dir, slug)
        if os.path.exists(path + ".json"):
            with open(path + ".json", "rb") as fobj:
                data = json.load(fobj)
                if (
                    data["date_min"] == self.date_min_formatted and
                    data["date_max"] == self.date_max_formatted
                ):
                    return data["data"]

        result = self.calendar_fetcher.fetch_events(calendar_summary)
        with open(path + ".tmp", "wb") as fobj:
            json.dump({
                "date_min": self.date_min_formatted,
                "date_max": self.date_max_formatted,
                "data": result,
            }, fobj)
        os.rename(path + ".tmp", path + ".json")
        return result
