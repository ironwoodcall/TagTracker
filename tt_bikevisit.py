"""A visit of a tag on a day

Copyright (c) 2024 Todd Glover & Julias Hocking

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.


"""

from tt_tag import TagID
from tt_time import VTime


class BikeVisit:
    # Class attributes
    all_visits = {}
    _last_seq = 0

    def __init__(self, tagid, time_in="now"):
        # Auto-generate a unique seq number
        self.seq = BikeVisit._last_seq
        BikeVisit._last_seq += 1
        self.time_in = VTime(time_in)
        self.time_out = VTime("")
        self.tagid = TagID(tagid)
        # Add the new instance to the all_visits dict
        BikeVisit.all_visits[self.seq] = self

    def delete_visit(self):
        if self.seq in BikeVisit.all_visits:
            del BikeVisit.all_visits[self.seq]

    def duration(self, as_of_when: VTime | str = "now") -> int:
        # Return duration (in minutes) of visit
        as_of_when = VTime(as_of_when)
        dur = min(as_of_when.num, self.time_out.num)
        dur = dur if dur >= 0 else 0
        return dur
