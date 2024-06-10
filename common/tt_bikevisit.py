"""A visit of a tag on a day

Copyright (c) 2024 Todd Glover & Julias Hocking

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.


"""

from common.tt_tag import TagID
from common.tt_time import VTime


class BikeVisit:
    # Class attributes
    # all_visits = {}
    _last_seq = 0

    def __init__(self, tagid, time_in="now",time_out=None):
        # Auto-generate a unique seq number
        self.seq = BikeVisit._last_seq
        BikeVisit._last_seq += 1
        self.time_in = VTime(time_in)
        self.time_out = VTime(time_out) or VTime("")
        self.tagid = TagID(tagid)
        # Add the new instance to the all_visits dict
        # BikeVisit.all_visits[self.seq] = self

    # def delete_visit(self):
    #     if self.seq in BikeVisit.all_visits:
    #         del BikeVisit.all_visits[self.seq]

    def duration(self, as_of_when:str = "now") -> int:
        """Return the duration of the visit, in minutes as of "as_of_when".

        If the visit has not started by "as_pf_when", returns None.
        """
        # Return duration (in minutes) of visit
        as_of_when = VTime(as_of_when or "now")
        if self.time_in > as_of_when:
            return None

        end = min(as_of_when, self.time_out) if self.time_out else as_of_when

        dur = end.num - self.time_in.num
        dur = dur if dur >= 0 else 0
        return dur
