"""Allocate people to interview slots.

Takes into account:

 - slots which don't conflict in calendars
 - the number of people involved in conflicts
 - slots which are marked as "preferred interview slot" in calendars
 - number of interview slots that interviewers have been invited to in the last
   month
 - number of interviews which interviewers were involved in in the last month
 - spread of skills that interviewers have
 - ensuring that all interviews have two technical people, and at least one
   person of each gender

"""

from collections import Counter
from datetime import timedelta
import math
# from pprint import pprint


class SlotAssignment(object):
    def __init__(self, slot, interviewers):
        """

        :param slot: The Slot object that people are being assigned to.

        """
        self.slot = slot
        self._interviewers = interviewers
        self._assigned = self._already_assigned(slot.event, interviewers)
        self._possible_emails = {}
        self.costs = {}

    def __repr__(self):
        return "<SlotAssignment({}, {}, viable={}, cost={}, has_chair={}, can_be_frontend={}, has_two_tech={}, gender_diverse={})>".format(
            self.slot.start,
            self.assigned,
            self.viable,
            self.cost,
            self.has_chair,
            self.can_be_frontend,
            self.has_two_tech,
            self.gender_diverse,
        )

    @property
    def assigned(self):
        return tuple(self._assigned)

    def possible(self, level):
        return self._possible_emails.get(level, [])

    def assign(self, email):
        assert email in reduce(lambda x, y: x + y, self._possible_emails.values(), [])
        try:
            interviewer = self._interviewers.by_email(email)
        except KeyError:
            print "Unknown email to assign to interview"
        else:
            self._assigned.append(interviewer)
        self.remove_from_possible(email)

    def add_to_possible(self, conflict_level, email):
        self.remove_from_possible(email)
        self._possible_emails.setdefault(conflict_level, []).append(email)

    def remove_from_possible(self, email):
        for values in self._possible_emails.values():
            try:
                values.remove(email)
            except ValueError:
                pass

    @staticmethod
    def _already_assigned(event, interviewers):
        if event is None:
            return [] 

        attendees = []
        emails = event.potential_attendees()
        for email in emails:
            try:
                interviewer = interviewers.by_email(email)
            except KeyError:
                print "Unknown invitee of recent interview: ", email
                continue
            attendees.append(interviewer)
        return attendees

    @property
    def viable(self):
        """Return True if the assignment is sufficient to run an interview.

        """
        return (
            len(self._assigned) == 3 and
            self.has_chair and
            self.has_two_tech and
            self.gender_diverse
        )

    @property
    def has_chair(self):
        return any(person.can_chair for person in self._assigned)

    @property
    def can_be_frontend(self):
        return any(person.can_do_frontend_test for person in self._assigned)

    @property
    def has_two_tech(self):
        return len(filter(lambda person: person.technical, self._assigned)) >= 2

    @property
    def gender_diverse(self):
        genders = Counter()
        for person in self._assigned:
            genders[person.gender] += 1
        return len(genders) >= 2

    @property
    def has_women(self):
        genders = Counter()
        for person in self._assigned:
            genders[person.gender] += 1
        return genders['f'] > 0

    @property
    def has_man(self):
        genders = Counter()
        for person in self._assigned:
            genders[person.gender] += 1
        return genders['m'] > 0

    @property
    def cost(self):
        """Determine the cost of this assignment.

        This only takes into account this interview, not things like overusing
        a single person.
        
        """
        return sum(
            self.costs[person.email]
            for person in self.assigned
        )


class SlotAssignments(object):
    def __init__(self, assignments):
        self.assignments = dict(
            (assignment.slot.start, assignment)
            for assignment in assignments
        )

    def __iter__(self):
        for _, assignment in sorted(self.assignments.items()):
            yield assignment

    def __len__(self):
        return len(self.assignments)

    def assign(self, slot_start, email):
        self.assignments[slot_start].assign(email)

    def drop(self, assignment):
        del self.assignments[assignment.slot.start]

    def new_assignments(self):
        return self.new_where(lambda assignment: assignment.slot.new)

    def new_where(self, check):
        return SlotAssignments(
            assignment
            for (_, assignment) in sorted(self.assignments.items())
            if assignment.slot.new and check(assignment)
        )


class PossibleAssignments(object):
    def __init__(self, assignments):
        self.slots = dict(
            (assignment.slot.start, [])
            for assignment in assignments
        )
        self.options_for_person = Counter()

    def assignments_possible(self):
        """Return True iff some assignments are possible"""
        return any(
            len(emails) > 0
            for emails in self.slots.values()
        )

    def add(self, start, email):
        if start in self.slots:
            self.slots[start].append(email)
            self.options_for_person[email] += 1

    def people_busiest_first(self):
        return map(
            lambda x: x[0],
            sorted(
                self.options_for_person.items(),
                key = lambda x: (x[1], x[0])
            )
        )

    def busiest_slot_possible(self, email):
        busyness = {}
        for start, emails in self.slots.items():
            if email in emails:
                busyness[start] = len(emails)
        slots = sorted(busyness.items(), key = lambda x: x[1])
        if len(slots) > 0:
            return slots[0][0]
        return None

    def assigned(self, start, email):
        """Record that someone is assigned to a slot at a time.

        Removes them from the list of possible people to assign to this or
        nearby slots.

        """

        for slot_start, emails in self.slots.items():
            if abs(start - slot_start) < timedelta(hours=23):
                try:
                    emails.remove(email)
                    self.options_for_person[email] -= 1
                except ValueError:
                    pass

    def drop_slot(self, start):
        """Drop a slot from the list of possible slots.

        Used when someone has newly been assigned to a slot.

        """
        if start in self.slots:
            for old_email in self.slots[start]:
                self.options_for_person[old_email] -= 1
            del self.slots[start]


class Allocator(object):
    def __init__(self, slots, interviewers):
        # All our interviewers
        self.interviewers = interviewers

        # All the slots for interviews since a month ago, and until a month in
        # the future.
        self.slots = slots

        # Who is assigned to each slot
        self.assignments = SlotAssignments(
            SlotAssignment(slot, self.interviewers)
            for slot in self.slots
        )

    def allocate(self):
        self.count_recent_interviews()
        self.conflicts_by_email, self.conflict_levels = self.calc_conflict_levels(
            self.interviewers,
            self.assignments
        )

        self.allocate_chairs()
        self.allocate_gender()
        self.allocate_frontend()
        self.allocate_technical()
        self.allocate_three_people()

        self.update_assignment_events()

    def update_assignment_events(self):
        for interviewer in self.interviewers:
            # print interviewer.email, interviewer.newly_assigned_interviews
            interviewer.newly_assigned_interviews = 0

        for assignment in self.assignments.new_assignments():
            assignment.slot.event.attendees = {"needsAction": [
                email
                for email in assignment.assigned
            ]}
            for interviewer in assignment.assigned:
                interviewer.newly_assigned_interviews += 1

        # print
        # for interviewer in self.interviewers:
        #    print interviewer.email, interviewer.newly_assigned_interviews

    def allocate_chairs(self):
        """Allocate chairs to slots

        Will update self.assignments to store the allocated chair in them.

        May fail to allocate to some of the slots, in which case it will drop them.

        """
        print "Assigning chairs"
        people = filter(lambda x: x.can_chair, self.interviewers)
        check = lambda assignment: not assignment.has_chair
        self.assign_people(check, people)
        self.drop_slots(check, "chair")
        # pprint([assignment for assignment in self.assignments.new_assignments()])

    def allocate_gender(self):
        """Allocate people of opposite gender to slots which have one gender
        
        Will update the supplied assignments to store the allocated person in them.

        May fail to allocate to some of the slots, in which case it will drop them.

        """
        print "Assigning opposite gender"
        people = filter(lambda x: x.gender == 'f', self.interviewers)
        check = lambda assignment: not assignment.has_women
        self.assign_people(check, people)
        self.drop_slots(check, "woman")
        # pprint([assignment for assignment in self.assignments.new_assignments()])

        people = filter(lambda x: x.gender == 'm', self.interviewers)
        check = lambda assignment: not assignment.has_man
        self.assign_people(check, people)
        self.drop_slots(check, "man")
        # pprint([assignment for assignment in self.assignments.new_assignments()])

    def allocate_frontend(self):
        """Allocate people who can run the frontend test to some of the slots

        (We don't have enough people trained to cover all the slots.)
        
        Will update the supplied assignments to store the allocated person in them.

        May fail to allocate to some of the slots, in which case it will drop them.

        """
        print "Assigning frontend interviewers"
        people = filter(lambda x: x.can_do_frontend_test, self.interviewers)
        check = lambda assignment: not assignment.can_be_frontend
        self.assign_people(check, people, 0.5)
        # pprint([assignment for assignment in self.assignments.new_assignments()])

    def allocate_technical(self):
        """Allocate at least two technical people to the slots
        
        Will update the supplied assignments to store the allocated person in them.

        May fail to allocate to some of the slots, in which case it will drop them.

        """
        print "Assigning technical people"
        people = filter(lambda x: x.technical, self.interviewers)
        check = lambda assignment: not assignment.has_two_tech
        while True:
            if not self.assign_people(check, people):
                break
        # pprint([assignment for assignment in self.assignments.new_assignments()])
        self.drop_slots(check, "two technical people")

    def allocate_three_people(self):
        """Allocate three people to the slots
        
        Will update the supplied assignments to store the allocated person in them.

        May fail to allocate to some of the slots, in which case it will drop them.

        """
        print "Assigning full panel"
        people = self.interviewers
        check = lambda assignment: len(assignment.assigned) < 3
        while True:
            if not self.assign_people(check, people):
                break
        # pprint([assignment for assignment in self.assignments.new_assignments()])
        self.drop_slots(check, "three people")

    def drop_slots(self, check, description):
        """Drop any slots which match the check
        
        """
        for assignment in self.assignments.new_where(check):
            print "Unable to allocate {} to interview at {}".format(
                description,
                assignment.slot.start
            )
            self.assignments.drop(assignment)

    def assign_people(self, check, people, rate_to_fill=1.0):
        assignments_made = set()
        assignments_to_fill = self.assignments.new_where(check)
        total_number_of_new_assignments = len(self.assignments.new_assignments())
        number_to_fill = (
            int(math.ceil(total_number_of_new_assignments * rate_to_fill))
            - (total_number_of_new_assignments - len(assignments_to_fill))
        )

        work_share = self.calc_work_share(len(assignments_to_fill), people)

        people_emails = set(person.email for person in people)

        # print "Initial assignments"
        # pprint([assignment for assignment in assignments_to_fill])

        # Try and allocate people at each level of conflict with existing
        # meetings, only moving to the next level once there are no more
        # possible assignments.
        for conflict_level in self.conflict_levels:
            self.update_assignment_events()

            print "At conflict level {}".format(conflict_level)
            possible_at_level = PossibleAssignments(assignments_to_fill.new_where(
                lambda a: a.slot.start not in assignments_made
            ))

            # Record possible assignments at this level.
            for assignment in assignments_to_fill:
                for email in assignment.possible(conflict_level):
                    if work_share.get(email, 0) > 0:
                        possible_at_level.add(assignment.slot.start, email)
            # print "Possible:"; pprint(possible_at_level.slots)

            # Mark assignments too close to existing ones for a person as not
            # possible
            for assignment in self.assignments:
                for person in assignment.assigned:
                    if person.email in people_emails:
                        # print "Already: {} {}".format(assignment.slot.start, person.email)
                        possible_at_level.assigned(
                            assignment.slot.start,
                            person.email,
                        )

            # print "Possible slots:"; pprint(possible_at_level.slots)

            # Try and assign slots for people in turn, starting with the
            # busiest ones first.
            changed = True
            while changed:
                changed = False
                # print possible_at_level.people_busiest_first()
                for email in possible_at_level.people_busiest_first():
                    work = work_share.get(email, 0)
                    if work > 0:
                        slot_start = possible_at_level.busiest_slot_possible(email)
                        if slot_start is not None:
                            print(
                                "Assigning {} to slot {} at conflict level {}".format(
                                    email, slot_start, conflict_level
                                )
                            )
                            possible_at_level.assigned(slot_start, email)
                            possible_at_level.drop_slot(slot_start)
                            assignments_to_fill.assign(slot_start, email)
                            work_share[email] -= 1
                            changed = True
                            assignments_made.add(slot_start)
                            number_to_fill -= 1
                            # print "Possible slots:"; pprint(possible_at_level.slots)
                            # print "Work Share:"
                            # pprint(work_share)
                            # print

                            if number_to_fill <= 0:
                                return len(assignments_made) != 0
        return len(assignments_made) != 0

    @staticmethod
    def calc_work_share(slots_to_assign, interviewers):
        """Calculate the number of interviews to assign to each person.

        """
        # Calculate total amount of work to be done (in units of "interview
        # slot reservations").
        work_done = sum(
            interviewer.recent_work() + interviewer.planned_work()
            for interviewer in interviewers
        )
        # print "Work done"
        # for interviewer in interviewers:
        #     print("{} recent={} planned={}".format(
        #         interviewer.email, interviewer.recent_work(), interviewer.planned_work()
        #     ))

        # Share the work out to aim to get everyone doing an equal share
        average_work = float(work_done + slots_to_assign) / len(interviewers)
        work_share = dict(
            (interviewer.email, (average_work - interviewer.work()) * interviewer.use_rate)
            for interviewer in interviewers
        )
        # print "Raw work share"
        # for email, share in sorted(work_share.items()):
        #     print("{} {}".format(email, share))

        # print "Work Share unnormalised:"
        # pprint(work_share)
        # print sum(work_share.values()), slots_to_assign
        # print

        # Adjust to take account of people who had already done more work than
        # we're requiring of them.
        for rounding_point in range(-9, 1):
            rounded_work_share = Allocator.normalised_work_share(
                slots_to_assign, work_share, rounding_point * 0.1
            )
            if sum(rounded_work_share.values()) >= slots_to_assign:
                break
        work_share = rounded_work_share

        print "Work Share:"
        for email, share in sorted(work_share.items()):
            print(" {} {}".format(email, share))
        print sum(work_share.values()), slots_to_assign
        print

        return work_share

    @staticmethod
    def normalised_work_share(slots_to_assign, work_share, rounding_point):
        multiplier = float(slots_to_assign) / sum(work_share.values())
        work_share = dict(
            (email, max(0, int(math.ceil(work * multiplier + rounding_point))))
            for (email, work) in work_share.items()
        )
        work_share = dict(
            (email, share)
            for (email, share) in work_share.items()
            if share > 0
        )
        return work_share


    @staticmethod
    def calc_conflict_levels(interviewers, assignments):
        conflicts_by_email = Counter()
        conflict_levels = set()
        for assignment in assignments.new_assignments():
            costs = {}
            for interviewer in interviewers:
                conflict_level = interviewer.calendar.conflict_level(
                    assignment.slot.start, assignment.slot.end)
                if conflict_level is None:
                    continue
                conflict_levels.add(conflict_level)
                assignment.add_to_possible(conflict_level, interviewer.email)
                costs[interviewer.email] = conflict_level
                conflicts_by_email[interviewer.email] += conflict_level
            assignment.costs = costs
        return dict(conflicts_by_email), sorted(conflict_levels)

    def display_interviewer_stats(self):
        print "Name, recent interviewer, recent interview slots"
        for interviewer in self.interviewers:
            print interviewer.name, interviewer.recent_interviews, interviewer.recent_interview_slots

    def count_recent_interviews(self):
        """Count the number of recent interviews done.

        Store the counts in the Interviewer objects.

        """
        for slot in self.slots:
            if slot.new or slot.event is None:
                continue
            for attendee in slot.event.attendees.get("accepted", []):
                try:
                    interviewer = self.interviewers.by_email(attendee)
                except KeyError:
                    print "Unknown attendee of recent interview: ", attendee
                    continue
                interviewer.recent_interview_slots += 1
                if not slot.event.summary.lower().startswith("Interview placeholder"):
                    interviewer.recent_interviews += 1
