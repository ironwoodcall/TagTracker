"""This is the RealTag class


    A TagID is the name of a tag; it might be a correct tag name or not.
    It is a type of string, and its representation is canonical
    tag representation (e.g. "wa1").  TagIDs with identical representation
    are considered equal, even though the 'original' attribute
    might not be the same.

    A RealTag (AnyTag?) is a TagID about which something might be known
    from the tags config info. Its attributes identify whether its type
    (OVERSIZE, REGULAR) and its config-based state (RETIRED, USABLE).

"""

from tt_globals import *
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

    def __init__(self, tag_string: str = "", config: TrackerDay = None):
        self.type = None
        self.state = None
        self.tagid = TagID(tag_string)
        if not self.tagid or not config:
            self.tagid = ""
            return
        assert isinstance(
            config, TrackerDay
        ), f"bad config in call to RealTag({tag_string})"
        if self.tagid in config.regular:
            self.type = REGULAR
        elif self.tagid in config.oversize:
            self.type = OVERSIZE
        if self.tagid in config.retired:
            self.state = RETIRED
        elif self.tagid in (config.oversize | config.regular):
            self.state = USABLE


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
        tag_string: str = "",
        day: TrackerDay = None,
        as_of_when: VTime = "now",
    ):
        """Create a Stay (ie a tag with activity)"""
        super().__init__(tag_string, day)
        as_of_when = VTime(as_of_when)
        self.as_of_when = as_of_when
        self.time_in = VTime("")
        self.time_out = VTime("")
        self.duration = None
        if not self.tagid or not day:
            return
        if self.tagid in day.bikes_out and day.bikes_out[self.tagid] <= self.as_of_when:
            self.state = BIKE_OUT
            self.time_out = day.bikes_out[self.tagid]
            self.time_in = day.bikes_in[self.tagid]
            self.duration = min(as_of_when.num,self.time_out.num) - self.time_in.num
        elif self.tagid in day.bikes_in and day.bikes_in[self.tagid] <= self.as_of_when:
            self.state = BIKE_IN
            self.time_in = day.bikes_in[self.tagid]
            self.duration = as_of_when.num - self.time_in.num

        @property
        def still_here(self):
            """Get whether a tag bike is currently in the valet."""
            return self.state == BIKE_IN
