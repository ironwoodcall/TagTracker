"""This file has experiments.

    Possible evolution of the TrackerDay class to include TagsConfig object
    RealTag & some variants
"""


#pylint:disable=pointless-string-statement
"""TrackerDay and TagsConfig (& such)

Why would I be doing this?
1) So that can read a config file into a TagsConfig object
    without expecting the transactions or valet-opening stuff
2) So that valet hours can be a mutable (passed by reference)
    object - meaning that can do something like
        read datafile into trackerday obj td
        if today is today:
            read tags.cfg stuff into conf pzipart of td
        RETIRED_TAGS = td.retired
        (etc)
        ALL_TAGS = (this is one-time, ALL_TAGS is read-only)
            ==> this could be a frozen set!


Current TrackerDay:
        TrackerDay      tagtracker.py       type    tags.cfg
        date            VALET_DATE          str
        opening_time    VALET_OPENS         str
        closing_time    VALET_CLOSES        str
        bikes_in        check_ins           dict
        bikes_out       check_outs          dict
        regular         NORMAL_TAGS         list        *
        oversize        OVERSIZE_TAGS       list        *
        retired         RETIRED_TAGS        list        *
        colour_letters  COLOUR_LETTERS      dict        *
        all_tags()      ALL_TAGS            list       (*)

New TrackerDay:
    VOpen class.
        Data class; 3 members:
            .opening_time
            .closing_time
            .date
        Why?  tagtracker proper can make its globals
        point to elements in a TagTracker object;
        these can then get updated without the globals
        statment, and will then (by regerence) update the
        TrakerDay object.
        So: no more pack* and unpack* required.
    TagsConfig class
        Data class.  Members:
            regular
            oversize
            retired
            colour_letters
            all_tags <-- only needs updating when the lists change
                so prob do something funny with @property for
                the lists, and a 'dirty' flag
    TrackerDay class.
        Mostly data class.
        Might inherit from TagsConfig and ValetOpen
            TagsConfig
            ValetOpen
            bikes_in
            bikes_out
            tag() - might return a Visit() object


"""
class ValetOpen():
    def __init__(self) -> None:
        self.date = ""
        self.opening_time = ""
        self.closing_time = ""

class TagsConfig():
    def __init__(self) -> None:
        self.regular = []
        self.oversize = []
        self.all_tags = []
        self.colour_letters = {}
        self._tester = ['starter']
    @property
    def tester(self):
        return self._tester
    @tester.setter
    def tester(self,val):
        print(f"adding {val} to _tester {self._tester}")
        self._tester.append(val)

class TrackerDay(TagsConfig,ValetOpen):
    def  __init__(self) -> None:
        TagsConfig.__init__(self)
        ValetOpen.__init__(self)
        self.bikes_in = {'wa1':'07:53'}

    def xx__init__(self) -> None:
        super().__init__()
        self.date = "2023-06-15"
        print("TrackerDay init")



"""This is a semi-experimental RealTag class


    A TagID is the name of a tag; it might be a correct tag name or not.
    It is a type of string, and its representation is canonical
    tag representation (e.g. "wa1").  TagIDs with identical representation
    are considered equal, even though the 'original' attribute
    might not be the same.

    A RealTag (AnyTag?) is a theoretical tag, which may or may not
    exist (e.g. "qz8597" doesn't exist) but which does have a valid
    tagid.  Its attributes identify whether it is assigned to a category
    (retired, oversize, regular) and (???) possibly some state
    (Available, In_Use, Returned)

    A KnownTag is an AnyTag that is identified in the TagsConfig,
    suggesting that it is either available for use or is retired.
    Is a KnownTag a different kind of object than AnyTag, or is it
    just a set of AnyTags?  Prob a set, since
    known_tags = [t for t in <list of any_tags> if t.tagtype].

    A TagsConfig is the _full set of tags context for a particular day.
    It aggregates lists of oversize, regular and retired tags,
    plus a colours dictionary.  (NB a TrackerDay is a TagsConfig plus
    lists of check_ins and check_outs)

    A Stay is a use of a tag at a time.  It knows the checkin and (maybe)
    checkout time, length of time.  A Stay is always and only built on
    a known AnyTag.


    How I might expect to use them:
        - seeing if an input token (or file token) is a tagid
        - seeing if tags are the same
        - initializing known tags from config file
        - looking up status of a (known) tag
        - checking a bike in (this might be creation of a Stay)
        - checking a bike out
        - printing a bike's tag in various reports
        - saving transaction info
        - analysing in
            - visits; durations
            - audit (bikes here, not-here)
            - blocks aggregations (Block)
            - count of bikes on hand, count of transactinos
            - Event





"""

from tt_globals import *
import tt_util as ut
import tt_trackerday as td
from tt_tag import TagID


class RealTag:
    """A deployed or deployable tag (but including retired tags)

    Attributes:
        assigned: None, RETIRED, OVERSIZE, REGULAR
        status: None, AVAILABLE, IN_USE, RETURNED


    """

    _everyTag = {}  # dict[str(TagID),RealTag]

    def __new__(cls, maybe_tag: str = "", tag_type: str = UNKNOWN):
        the_tag = TagID(maybe_tag)
        if not the_tag:
            return None
        if the_tag in cls._everyTag:
            return cls._everyTag[the_tag]
        instance = super().__new__(cls)
        ##print(f"{type(super())=}; {super()=}, {type(instance)=}")
        instance.tag = the_tag
        cls._everyTag[the_tag] = instance
        return instance

    def __init__(self, tag_string="", tag_type: str = UNKNOWN):
        # self.tag = TagID(tag_string)
        assert tag_type in [
            UNKNOWN,
            REGULAR,
            OVERSIZE,
            RETIRED,
        ], f"Unknown tag_type {tag_type} in RealTag.__init__()"
        if False:
            self.tag = ""
        self.tagtype = tag_type
        self.time_in = ""  # HH:MM
        self.time_out = ""  # HH:MM
        self.duration = 0  # minutes
        self.still_here = None  # True or False

    @property
    def duration(self) -> int:
        if not self.time_in:
            return None
        if self.time_out:
            end_time = self.time_out
        else:
            # No time out.  Need to fabricate a latest time.
            # Use the earliest of latest event, current time, closing time
            latest_event = max(
                ["00:00"]   # This just so there will never be an empty list
                + [rt.time_in for rt in RealTag._everyTag if rt.time_in]
                + [rt.time_out for rt in RealTag._everyTag if rt.time_out]
            )
            end_time = min(ut.get_time(), latest_event)
        return max(ut.time_int(end_time) - ut.time_int(self.time_in), 1)

    @classmethod
    def retired_tags(cls) -> list:
        return [x.tag for x in cls._everyTag.values() if x._tagtype == RETIRED]

    @classmethod
    def oversize_tags(cls) -> list:
        return [x.tag for x in cls._everyTag.values() if x._tagtype == OVERSIZE]

    @classmethod
    def regular_tags(cls) -> list:
        return [x.tag for x in cls._everyTag.values() if x._tagtype == REGULAR]

    @classmethod
    def active_tags(cls) -> list:
        return [
            x.tag for x in cls._everyTag.values() if x._tagtype in [OVERSIZE, REGULAR]
        ]

    @classmethod
    def known_tags(cls) -> list:
        return [x.tag for x in cls._everyTag.values() if x._tagtype != UNKNOWN]


Stay = RealTag


class anotherStay(RealTag):
    """A Stay is a RealTag that is being used."""

    def __new__(cls, tag: RealTag):
        instance = super().__new__(cls)
        if not isinstance(tag, RealTag):
            return None
        return instance

    def __init__(self, tag: RealTag) -> None:
        self.tag = tag
        self.time_in = ""  # HH:MM
        self.time_out = ""  # HH:MM
        self.duration = 0  # minutes
        self.type = None  # REGULAR, OVERSIZE
        self.still_here = None  # True or False


class oldStay(RealTag):
    """Just a data structure to keep track of bike visits."""

    def __new__(cls, tag: str, check_in: str):
        instance = super().__new__(cls, tag)
        if not instance:
            return None
        t = TagID(tag)
        if not t:
            return None
        instance.tag = t
        return instance

    def __init__(self, tag: str, check_in: str) -> None:
        super().__init__(tag)
        """Initialize blank."""
        # self.tag = tag  # canonical
        self.time_in = ""  # HH:MM
        self.time_out = ""  # HH:MM
        self.duration = 0  # minutes
        self.type = None  # REGULAR, OVERSIZE
        self.still_here = None  # True or False

    def __bool__(self) -> bool:
        return bool(self.time_in)


if __name__ == "main":
    some_str = input()
    RETIRED_TAGS = []
    OVERSIZE_TAGS = []
    REGULAR_TAGS = []

    if not TagID(some_str).valid:
        print("error")
    t = TagID(some_str)
    if not t:
        print(f"{t.original} is no good")

    # initializing from file
    tagtype = REGULAR
    for token in ["asd", "bc1", "bc2"]:  # items_from_file:
        rt = RealTag(token)
        if not rt:
            print(f"{token} is not a tag")
        rt.tagtype = tagtype

    # initializing from TagsConfig lists
    # (Assumes TagsConfig lists are valid tags)
    for tag in RETIRED_TAGS:
        RealTag(tag).tagtype = RETIRED
    for tag in [t for t in REGULAR_TAGS if t not in RETIRED_TAGS]:
        RealTag(tag).tagtype = REGULAR
    for tag in [t for t in OVERSIZE if t not in RETIRED_TAGS]:
        RealTag(tag).tagtype = OVERSIZE

    # Check a bike in
    import tt_util as ut

    Stay(RealTag(some_str)).time_in = ut.get_time()
