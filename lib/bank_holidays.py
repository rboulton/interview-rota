import datetime
import json
import os
import requests
import time


class BankHolidays(object):
    def __init__(self, cache_dir):
        self._dates = []
        self.cache_dir = cache_dir

    def dates(self):
        data = self._fetch()
        dates = []
        for event in data["events"]:
            date_str = event["date"]
            dates.append(datetime.datetime(
                int(date_str[0:4]),
                int(date_str[5:7]),
                int(date_str[8:10]),
            ))
        dates.sort()
        return dates

    def _fetch(self):
        if not os.path.isdir(self.cache_dir):
            os.makedirs(self.cache_dir)
        holidays_file = os.path.join(self.cache_dir, "holidays")

        if (
            os.path.isfile(holidays_file + ".json") and
            time.time() - os.stat(holidays_file + ".json").st_mtime < 86400
        ):
            with open(holidays_file + ".json") as fobj:
                return json.load(fobj)
        data = requests.get("https://www.gov.uk/bank-holidays/england-and-wales.json").content
        with open(holidays_file + ".json", "wb") as fobj:
            fobj.write(data)
        return json.loads(data)
