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

    def __init__(self, tagid, time_in="now", time_out=None):
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

    def duration(
        self, as_of_when: str = "now", is_close_of_business: bool = False
    ) -> int:
        """Return the duration of the visit, in minutes as of "as_of_when".

        If is_close_of_business then always returns a positive integer;
        else if the visit has not started by "as_of_when", returns None.

        There is an oddball edge case for is close_of_business case where
        time_in is later than as_of_when and there is no time_out; in this
        case duration is arbitrarily set to 30 minutes.
        """
        DURATION_EDGECASE_BUFFER = 30

        # Return duration (in minutes) of visit
        as_of_when = VTime(as_of_when or "now")

        if is_close_of_business:
            end = self.time_out or max(
                as_of_when,
                VTime(self.time_in.num + DURATION_EDGECASE_BUFFER),
            )

        else:
            if self.time_out:
                end = min(self.time_out, as_of_when)
            else:
                end = None if self.time_in > as_of_when else as_of_when

        dur = end.num - self.time_in.num
        dur = dur if dur >= 0 else 0
        return dur
