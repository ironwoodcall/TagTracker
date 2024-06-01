"""A tag as it is (or can be) used.

This likely has overlap with the (unused?) RealTag class
so cleanup is likely required..

Copyright (c) 2024 Todd Glover & Julias Hocking

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.


"""

from tt_tag import TagID
from tt_time import VTime
from tt_bikevisit import BikeVisit
from tt_constants import REGULAR, OVERSIZE, UNKNOWN


class BikeTagError(Exception):
    """Custom exception class for BikeTag errors."""

    pass


class BikeTag:
    """A bike tag that is used or can be used or can't be used because it's retired.

    This assures that only one tag for any given tagid is created.

    """

    IN_USE = "IN_USE"
    DONE = "DONE"
    UNUSED = "UNUSED"
    RETIRED = "RETIRED"

    # all_biketags: dict[str, "BikeTag"] = {}

    def __new__(cls, tagid: TagID, bike_type: str = UNKNOWN):
        # if tagid in cls.all_biketags:
        #     return cls.all_biketags[tagid]
        instance = super(BikeTag, cls).__new__(cls)
        return instance

    def __init__(self, tagid: TagID, bike_type: str = UNKNOWN):
        # if tagid in BikeTag.all_biketags:
        #     return
        self.tagid = tagid
        self.status = self.UNUSED
        self.visits: list[BikeVisit] = []
        self.bike_type = bike_type
        if self.bike_type not in (REGULAR, OVERSIZE, UNKNOWN):
            raise BikeTagError(f"Unknown bike type '{bike_type}' for {tagid}")
        # BikeTag.all_biketags[tagid] = self

    # Lower-level methods

    def start_visit(self, time: VTime):
        visit = BikeVisit(self.tagid, time)
        self.visits.append(visit)
        self.status = self.IN_USE

    def finish_visit(self, time: VTime):
        if self.visits:
            latest_visit = self.latest_visit()
            latest_visit.time_out = time
            self.status = self.DONE

    def latest_visit(self) -> BikeVisit:
        """Return latest of the biketag's visit, if any."""
        if self.visits:
            return self.visits[-1]
        return None

    def previous_check_out(self) -> VTime:
        """Get the check-out time from the next-to-last
        visit.  If no visit, return "00:00".
        """
        if len(self.visits) > 1:
            return self.visits[-2].time_out
        else:
            return VTime(0)

    # Higher-level command-fulfillment methods

    def check_in(self, bike_time: VTime):
        """Check bike(s) in.

        Can check in at the given time if:
            - is DONE or UNUSED
            - is not earlier that prior check-out

        """
        if self.status not in {self.DONE, self.UNUSED}:
            raise BikeTagError(f"Tag {self.tagid} is already checked in or is retired.")
        if self.status == self.DONE and bike_time <= self.latest_visit().time_out:
            raise BikeTagError(
                f"Check-in at {bike_time.short} for tag {self.tagid} "
                "must be later than prior check-out."
            )
        self.start_visit(bike_time)

    def check_out(self, time: VTime):
        if self.status == self.IN_USE:
            self.finish_visit(time)

    def edit_in(self, bike_time: VTime):
        """Apply bike_time check in to the most recent time for this tag."""
        # No visit underway -- make a new visit.
        if self.status in {self.UNUSED, self.RETIRED}:
            raise BikeTagError(f"Tag {self.tagid} has no check-in to edit.")
        elif self.status in [self.IN_USE, self.DONE]:
            latest_visit = self.latest_visit()
            if bike_time < self.previous_check_out():
                raise BikeTagError(
                    f"Proposed check-in of {bike_time.short} for tag {self.tagid} "
                    "is earlier than prior check-out."
                )
            # Ok to edit the time_in
            latest_visit.time_in = bike_time
        else:
            raise BikeTagError(
                f"Invalid state '{self.status}' for edit_in of '{self.tagid}'."
            )

    def edit_out(self, time: VTime):
        if self.status == self.DONE:
            v = self.latest_visit()
            if v.time_in >= time:
                raise BikeTagError(
                    f"Tag {self.tagid}: Checkout time {time} must be later than check-in time {v.time_in}."
                )
            v.time_out = time
        elif self.status == self.IN_USE:
            v = self.latest_visit()
            if v.time_in >= time:
                raise BikeTagError(
                    f"Check-out time {time} for {self.tagid} must be later than check-in time {v.time_in}."
                )
            self.finish_visit(time)
        else:
            raise BikeTagError("Invalid state for edit_out")

    def delete_in(self):
        if self.status == self.IN_USE:
            if self.visits:
                self.visits.pop()
                self.status = self.DONE if self.visits else self.UNUSED
            else:
                raise BikeTagError(f"Tag {self.tagid} has no visits to delete.")
        else:
            raise BikeTagError(f"Bike {self.tagid} is not currently checked in.")

    def delete_out(self):
        if self.status == self.DONE:
            v = self.latest_visit()
            v.time_out = None
            self.status = self.IN_USE
        else:
            raise BikeTagError("Invalid state for delete_out")

    def status_as_at(self, as_of_when: str = ""):
        """Return the status as of a particular time."""
        # Return RETIRED status if the current status is RETIRED
        if self.status == self.RETIRED:
            return self.RETIRED

        # Return UNUSED if there are no visits or the first visit is after the given time
        if not self.visits or self.visits[0].time_in > as_of_when:
            return self.UNUSED

        # Iterate through to see if this is IN_USE
        for visit in self.visits:
            if (
                visit.time_in < as_of_when
                and visit.time_out
                and as_of_when < visit.time_out
            ):
                return self.IN_USE
            if visit.time_in < as_of_when and not visit.time_out:
                return self.IN_USE
        # Not in use, so must be DONE
        return self.DONE

    def lint_check(self) -> list[str]:
        """Check the BikeTag for errors. Return any errors as a list."""

        errors = []

        # Absent or bad tagid.
        if self.tagid != TagID(self.tagid):
            errors.append(f"Missing or bad tagid for BikeTag '{self.tagid}'")
        # Inconsistencies between visits and BikeTag status.
        if self.status in {self.UNUSED, self.RETIRED}:
            if self.visits:
                errors.append(
                    f"BikeTag {self.tagid} has visits but status is {self.status}."
                )
        elif self.status in {self.IN_USE, self.DONE}:
            if self.visits:
                if self.latest_visit().time_out:
                    if self.status == self.IN_USE:
                        errors.append(
                            f"BikeTag {self.tagid} is IN_USE but has a finished last visit."
                        )
                elif self.status == self.DONE:
                    errors.append(
                        f"BikeTag {self.tagid} is DONE but has an unfinished last visit."
                    )
            else:
                errors.append(
                    f"BikeTag {self.tagid} is {self.status} but has no visits."
                )
        else:
            errors.append(
                f"BikeTag {self.tagid} has unrecognized status {self.status}."
            )

        # Check all visits for time discrepencies..
        # This does *not* check that a visit's time overlaps another.
        last_visit_num = len(self.visits)  # NB: *Not* the visits[] index
        for i, visit in enumerate(self.visits, start=1):
            whatvisit = f"Visit {self.tagid}:{i}"
            if not visit.time_in:
                errors.append(f"{whatvisit} has no check-in time.")
                continue
            if visit.time_out:
                if visit.time_in >= visit.time_out:
                    errors.append(
                        f"{whatvisit} has a check-in time same or later than its check-out."
                    )
            elif i != last_visit_num:
                errors.append(
                    f"{whatvisit} has no checkout time but is not the "
                    f"last of tag's {len(self.visits)} visits."
                )

        # Check for overlapping visits.
        for i in range(len(self.visits) - 1):
            current_out = self.visits[i].time_out
            next_in = self.visits[i + 1].time_in
            if current_out > next_in:
                errors.append(f"Visits {self.tagid}:{i+1} and :{i+2} overlap.")

        return errors

        # # Iterate over visits to determine the status at the given time
        # for i, visit in enumerate(self.visits):
        #     if visit.time_in <= as_of_when:
        #         # If there's no time_out, the status is IN_USE
        #         if not visit.time_out:
        #             return self.IN_USE

        #         # If time_out is after or equal to as_of_when, check further conditions
        #         if visit.time_out >= as_of_when:
        #             # If it's the last visit, the status is DONE
        #             if i == len(self.visits) - 1:
        #                 return self.DONE

        #             # If the next visit's time_in is after as_of_when, the status is DONE
        #             if as_of_when < self.visits[i + 1].time_in:
        #                 return self.DONE

        # # If no conditions match, return the default status (assuming IN_USE as default)
        # return self.IN_USE
