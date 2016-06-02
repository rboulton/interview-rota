from bank_holidays import BankHolidays
from calendar_fetcher import CalendarCache, Event
import datetime
import os
import pytz


utc = pytz.timezone("UTC")
local_time = pytz.timezone("Europe/London")
interview_placeholder_description = """
Keep this slot free for interviews.  These may be arranged at short notice.

Please accept this invitation as soon as possible.  If you cannot make this
appointment, you must find someone to swap with.
""".strip()

appointment_calendar_name = "Dev & Web Ops Recruitment"


class Slot(object):
    def __init__(self, date, time, length, new):
        start_localtz = local_time.localize(datetime.datetime(
            year = date.year,
            month = date.month,
            day = date.day,
            hour = int(time[:2]),
            minute = int(time[3:]),
        ))
        self.start = utc.normalize(start_localtz)
        self.end = self.start + datetime.timedelta(minutes = length)
        self.new = new
        self.event = None

    def __repr__(self):
        return "{} to {} {} {}".format(self.start, self.end, "new" if self.new else "old", self.event)


class SlotGenerator(object):
    def __init__(self, calendar_fetcher, date_min, min_new_slot_date, date_max, cache_dir):
        self.calendar_fetcher = calendar_fetcher
        self.date_min = date_min
        self.min_new_slot_date = min_new_slot_date
        self.date_max = date_max
        self.bank_holidays = BankHolidays(cache_dir).dates()

    def generate(self):
        self.booked = self.calendar_fetcher.get(appointment_calendar_name)

        for date in self._generate_dates():
            new = (date >= self.min_new_slot_date)
            yield self.associate_event(Slot(date, "10:15", 150, new))
            yield self.associate_event(Slot(date, "14:15", 150, new))

    def associate_event(self, slot):
        for event in self.booked.events:
            if not "interview" in event.summary.lower():
                continue
            if event.intersects_with(slot.start, slot.end):
                slot.event = event

        if slot.new and slot.event is None:
            slot.event = self.make_placeholder_event(slot)
        return slot

    def make_placeholder_event(self, slot):
        event = Event({
            "start": {"dateTime": slot.start.isoformat()},
            "end": {"dateTime": slot.end.isoformat()},
            "summary": "Interview placeholder",
            "description": interview_placeholder_description,
        }, False)
        event.optional = False
        return event

    def _generate_dates(self):
        date = self.date_min
        while date <= self.date_max:
            if (
                date.weekday() not in (5, 6) and
                date not in self.bank_holidays
            ):
                yield date
            date = date + datetime.timedelta(days=1)


def fetch_slots(creds, cache_dir):
    today = datetime.date.today()
    date_min = today - datetime.timedelta(days=28)
    date_max = today + datetime.timedelta(days=28)
    min_new_slot_date = today + datetime.timedelta(days=10)

    calendar_fetcher = CalendarCache(
        creds, date_min, date_max, os.path.join(cache_dir, "calendars")
    )

    return list(SlotGenerator(
        calendar_fetcher, date_min, min_new_slot_date, date_max,
        os.path.join(cache_dir, "slots"),
    ).generate())
