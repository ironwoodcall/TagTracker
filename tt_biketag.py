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
from tt_constants import REGULAR,OVERSIZE,UNKNOWN


class BikeTagError(Exception):
    """Custom exception class for BikeTag errors."""

    pass


class BikeTag:
    """A bike tag that is used or can be used or can't be used because it's retired.

    This assures that only one tag for any given tagid is created.

    """

    IN_USE = "_in_"
    DONE = "_done"
    UNUSED = "_unused_"
    RETIRED = "_retired_"

    # all_biketags: dict[str, "BikeTag"] = {}

    def __new__(cls, tagid: TagID, bike_type: str=UNKNOWN):
        # if tagid in cls.all_biketags:
        #     return cls.all_biketags[tagid]
        instance = super(BikeTag, cls).__new__(cls)
        return instance

    def __init__(self, tagid: TagID, bike_type: str=UNKNOWN):
        # if tagid in BikeTag.all_biketags:
        #     return
        self.tagid = tagid
        self.status = self.UNUSED
        self.visits: list[BikeVisit] = []
        self.bike_type = bike_type
        if self.bike_type not in (REGULAR,OVERSIZE,UNKNOWN):
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

    # Higher-level command-fulfillment methods

    def check_in(self, time: VTime):
        self.edit_in(time)

    def check_out(self, time: VTime):
        if self.status == self.IN_USE:
            self.finish_visit(time)

    def edit_in(self, time: VTime):
        if self.status == self.UNUSED:
            self.start_visit(time)
            self.status = self.IN_USE
        elif self.status in [self.IN_USE, self.DONE] and len(self.visits) == 1:
            latest_visit = self.latest_visit()
            latest_visit.time_in = time
        else:
            raise BikeTagError("Invalid state for edit_in")

    def edit_out(self, time: VTime):
        if self.status == self.DONE:
            v = self.latest_visit()
            if v.time_in >= time:
                raise BikeTagError("time_in must be less than time")
            v.time_out = time
        elif self.status == self.IN_USE:
            v = self.latest_visit()
            if v.time_in >= time:
                raise BikeTagError("time_in must be less than time")
            self.finish_visit(time)
        else:
            raise BikeTagError("Invalid state for edit_out")

    def delete_in(self):
        if self.status == self.IN_USE:
            if self.visits:
                self.visits.pop()
            else:
                raise BikeTagError("No visits to delete")
        else:
            raise BikeTagError("Invalid state for delete_in")

    def delete_out(self):
        if self.status == self.DONE:
            v = self.latest_visit()
            v.time_out = None
            self.status = self.IN_USE
        else:
            raise BikeTagError("Invalid state for delete_out")
