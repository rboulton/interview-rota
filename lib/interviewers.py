"""Get information about interviewers

"""

import csv
import datetime
import os
from calendar_fetcher import CalendarCache


# Count an interview which happens as this many times as much work as just
# reserving the slot.
work_of_interview = 3


def to_bool(value):
    return value.lower().strip().startswith("y")


class Interviewer(object):
    def __init__(self, fields):
        self.name = fields.get("name")
        self.email = fields.get("email")
        self.can_chair = to_bool(fields.get("can_chair"))
        self.technical = to_bool(fields.get("technical"))
        self.can_do_frontend_test = to_bool(fields.get("can_do_frontend_test"))
        self.senior_developer = to_bool(fields.get("senior_developer"))
        self.gender = fields.get("gender").lower().strip()
        self.use_rate = float(fields.get("use_rate", "1"))
        self.team = fields.get("team")
        self.calendar = None
        self.recent_interview_slots = 0
        self.recent_interviews = 0
        self.newly_assigned_interviews = 0

    def recent_work(self):
        return (
            self.recent_interview_slots +
            self.recent_interviews * work_of_interview
        )

    def planned_work(self):
        return self.newly_assigned_interviews

    def work(self):
        return self.recent_work() + self.planned_work()

    def __repr__(self):
        return "<Interviewer(%r, %r)>" % (self.name, self.team)


class Interviewers(object):
    def __init__(self, people):
        self._people = dict(
            (person.email, person)
            for person in people
        )

    def __len__(self):
        return len(self._people)

    def __iter__(self):
        for _, person in sorted(self._people.items()):
            yield person

    def emails(self):
        return self._people.keys()

    @staticmethod
    def from_csv(csv_file):
        people = []
        with open(csv_file, "rb") as fobj:
            for row in csv.DictReader(fobj):
                people.append(Interviewer(row))
        return Interviewers(people)

    def by_email(self, email):
        return self._people[email]


def fetch_interviewers(creds, cache_dir):
    csv_file = os.environ["INTERVIEWERS_CSV"]

    interviewers = Interviewers.from_csv(csv_file)

    today = datetime.date.today()
    date_min = today - datetime.timedelta(days=28)
    date_max = today + datetime.timedelta(days=28)

    calendar_fetcher = CalendarCache(
        creds, date_min, date_max, os.path.join(cache_dir, "calendars")
    )

    for interviewer in interviewers:
        interviewer.calendar = calendar_fetcher.get(interviewer.email)
    return interviewers
