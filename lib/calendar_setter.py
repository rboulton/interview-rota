

class CalendarSetter(object):
    def __init__(self, service):
        self.service = service

    def add_event(self, calendar_summary, event_data):
        event = self.service.events().insert(
            calendarId=self.service.calendar_id(calendar_summary),
            sendNotifications=True,
            body=event_data,
        ).execute()
        print 'Event created: {}'.format(
            event.get('htmlLink'),
        )
