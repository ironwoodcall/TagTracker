"""This is the RealTag class

Copyright (c) 2023-2024 Julias Hocking & Todd Glover

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.

    A TagID is the name of a tag; it might be a correct tag name or not.
    It is a type of string, and its representation is canonical
    tag representation (e.g. "wa1").  TagIDs with identical representation
    are considered equal, even though the 'original' attribute
    might not be the same.

    A RealTag (AnyTag?) is a TagID about which something might be known
    from the tags config info. Its attributes identify whether its type
    (OVERSIZE, REGULAR) and its config-based state (RETIRED, USABLE).

"""

import tt_constants as k
from tt_tag import TagID
from tt_time import VTime
from tt_trackerday import TrackerDay


class RealTag:
    """A tag with attributes that reflect info in the Tags Config (only).

    Arguments:
        tag_string: a string that may or may not represent a valid TagID
        config: a TrackerDay with (presumably) tags config info in it.
            Only the tags config portion of the TrackerDay is used
            (.retired, .oversize, .regular sets of TagIDs)

    Attributes:
        tagid: a TagID (or "" if given a string that does not look like a tagid)
        type: None, OVERSIZE, REGULAR
        state: None, USABLE, RETIRED

    """

    def __init__(self, tag_string: k.MaybeTag = "", config: TrackerDay = None):
        self.type = None
        self.state = None
        self.tag = TagID(tag_string)
        if not self.tag or not config:
            self.tag = ""
            return
        assert isinstance(
            config, TrackerDay
        ), f"bad config in call to RealTag({tag_string})"
        if self.tag in config.regular:
            self.type = k.REGULAR
        elif self.tag in config.oversize:
            self.type = k.OVERSIZE
        if self.tag in config.retired:
            self.state = k.RETIRED
        elif self.tag in (config.oversize | config.regular):
            self.state = k.USABLE


class Stay(RealTag):
    """A tag's use and condition at a particular time.

    Arguments:
        tag_string: a string that may or may not represent a valid TagID
        config: a TrackerDay with (presumably) tags config info in it.
            Only the tags config portion of the TrackerDay is used
            (.retired, .oversize, .regular sets of TagIDs)

    Attributes:
        tagid: a TagID (or "" if given a string that does not look like a tagid)
        type: None, OVERSIZE, REGULAR
        state: None, USABLE, BIKE_IN, BIKE_OUT, RETIRED
    """

    def __init__(
        self,
        tag_string: k.MaybeTag = "",
        day: TrackerDay = None,
        as_of_when: k.MaybeTime = "now",
    ):
        """Create a Stay (ie a tag with activity)"""
        super().__init__(tag_string, day)
        as_of_when = VTime(as_of_when)
        self.as_of_when = as_of_when
        self.time_in = VTime("")
        self.time_out = VTime("")
        self.duration = 0
        if not self.tag or not day:
            return
        if self.tag in day.bikes_out and day.bikes_out[self.tag] <= self.as_of_when:
            # Bike came and went before as_of_when
            self.state = k.BIKE_OUT
            self.time_out = day.bikes_out[self.tag]
            self.time_in = day.bikes_in[self.tag]
            self.duration = min(as_of_when.num, self.time_out.num) - self.time_in.num
        elif self.tag in day.bikes_in and day.bikes_in[self.tag] <= self.as_of_when:
            # Bike came in before as_of_when
            self.state = k.BIKE_IN
            self.time_in = day.bikes_in[self.tag]
            self.duration = as_of_when.num - self.time_in.num

    @property
    def still_here(self):
        """Get whether a tag bike is currently onsite."""
        return self.state == k.BIKE_IN

    @staticmethod
    def dump_visits(visits: dict["Stay"]) -> None:
        """Dump whole visits dictionary."""
        print("\nvisits\n")
        for v in visits.values():
            print(v.dump())

    @staticmethod
    def calc_stays(
        day: TrackerDay, as_of_when: k.MaybeTime = "now"
    ) -> dict[TagID, "Stay"]:
        """Create a dict of stays keyed by tag as of as_of_when.

        If as_of_when is not given, then this will use the current time.

        If there are bikes that are not checked out, then this will
        consider their check-out time to be:
            earlier of:
                current time
                closing time if there is one, else time of latest event of the day.
        """
        as_of_when = VTime(as_of_when)

        # If a bike isn't checked out or its checkout is after the requested
        # time, then use as_of_when as its checkout time?
        stays = {}
        for tag, time_in in day.bikes_in.items():
            if time_in > as_of_when:
                continue
            this_stay = Stay(tag, day, as_of_when=as_of_when)
            stays[tag] = this_stay
        return stays
