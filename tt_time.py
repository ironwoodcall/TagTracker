"""VTime (Valet Time) str object represents tie as HH:MM.

Typically used for time since midnight but can also
represent duration (<=24 hours)

Attributes:
    {self}  canonical time string "HH:MM" since midnight
    pretty  pretty version of itself (e.g. " 6:30" instead of "06:30")
    short   shortened pretty version (e.g. "6:30" instead of "06:30")
    num     integer minutes since midnight
    original    string representation of whatever was passed in

Invocation:
    string as HMM, HHMM, HH:MM, H:MM; or
    int/float as minutes since midnight; or
    the keyword "now"
        return datetime.datetime.today().strftime("%H:%M")
"""
import re
import datetime


class VTime(str):
    @staticmethod
    def _time_int(maybe_time: str) -> int:
        """Convert known-good string representation of time to int (or None)."""
        r = re.match(r"^ *([012]*[0-9]):?([0-5][0-9]) *$", maybe_time)
        if not (r):
            return None
        h = int(r.group(1))
        m = int(r.group(2))
        as_int = h * 60 + m
        # Test for an impossible time
        if h > 24 or m > 59 or as_int > 1440:
            return None
        return as_int

    @staticmethod
    def _find_time(maybe_time) -> str:
        """Get tuple (str,int) representation of maybe_time."""
        if isinstance(maybe_time, float):
            maybe_time = round(maybe_time)
        if isinstance(maybe_time, int):
            if 0 <= maybe_time <= 60 * 24:
                h = maybe_time // 60
                m = maybe_time % 60
                return (f"{h:02d}:{m:02d}", maybe_time)
            else:
                return ("", None)
        if not isinstance(maybe_time, str):
            return ("", None)
        if maybe_time.strip().lower() == "now":
            timenow = datetime.datetime.today().strftime("%H:%M")
            return (timenow, VTime._time_int(timenow))
        # Candidate might be some kind of HHMM
        as_int = VTime._time_int(maybe_time)
        if as_int is None:
            return ("", None)
        return VTime._find_time(as_int)

    def __new__(cls, maybe_time=""):
        """Create a Valet Time string with its 'self' as canonical time."""
        (self_string, self_int) = cls._find_time(maybe_time)
        instance = super().__new__(cls, self_string)
        instance.num = self_int
        instance.original = str(maybe_time)
        return instance

    def __init__(self, maybe_time=""):  # pylint:disable=unused-argument
        # str.__init__()
        # On entry, {self} is "" or a valid HH:MM time
        if False:  # pylint:disable=using-constant-test
            self.original = ""
            self.num = 0
        if self and (self[0] == "0"):
            self.tidy = f" {self[1:]}"
            self.short = self[1:]
        else:
            self.tidy = self
            self.short = self

    # Comparisons are between str representations of itself and other
    def __eq__(self, other) -> bool:
        """Define equality to mean represent same tag name."""
        return bool(str(self) == str(VTime(other)))

    def __lt__(self, other) -> bool:
        return bool(str(self) < str(VTime(other)))

    def __gt__(self, other) -> bool:
        return bool(str(self) > str(VTime(other)))

    def __le__(self, other) -> bool:
        return bool(str(self) <= str(VTime(other)))

    def __ge__(self, other) -> bool:
        return bool(str(self) >= str(VTime(other)))

    def __ne__(self, other) -> bool:
        return bool(str(self) != str(VTime(other)))

    def __hash__(self):
        """Make hash int for the object.

        Not a simple object so not hashable (ie not usable as a dict key)
        so must provide own hash method that can be used as a dict key.
        For these, just hash the tag's string value (always lowercase!!!)
        """
        return hash(str(self))
