"""VTime str object represents time as HH:MM.

Typically used for time since midnight but can also
represent duration (<=24 hours)

Attributes:
    {self}  canonical time string "HH:MM" since midnight
    tidy    pretty version of itself (e.g. " 6:30" instead of "06:30")
    short   shortened pretty version (e.g. "6:30" instead of "06:30")
    num     integer minutes since midnight
    original    string representation of whatever was passed in

Invocation:
    string as HMM, HHMM, HH:MM, H:MM; or
    int/float as minutes since midnight (or of duration); or
    the keyword "now", which sets it to the current locale time

Invalid input results in a blank VTime object.

Copyright (C) 2023-2024 Todd Glover & Julias Hocking

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""

import re
from datetime import datetime, timedelta


# An alias at the end of this module determines which version of VTime is invoked


class HMS_VTime(str):
    """THis is a first cut at a drop-in replacement for VTime that uses
    granularity in seconds not minutes.  When trying it out, the
    frequency distribution graphs did not work.  Don't know what else
    might not work.

    If this is implemented, then it would require changes in TrackerDay load/save
    functions (JSON files would need to preserve the second granularity) and
    the db loader, and the database structure.

    A careful review of code looking for places that assume a particular length
    or a particular level of matching to (eg) "24:00" would be needed as well.
    """

    # FIXME: VTime() object with seconds-precision... needs work
    # Hour/Minute time pattern accepts time with or without colon
    _TIME_PATTERN_HM = re.compile(r"^(\d+):?(\d{2})$")
    # HMS time pattern is [H]H:MM:SS - always with colons
    _TIME_PATTERN_HMS = re.compile(r"^(\d+):(\d{2}):(\d{2})$")

    def __new__(cls, maybe_time: str = "", allow_large=False):
        time_str, time_seconds, time_dt, time_full = cls._convert_time(
            maybe_time, allow_large
        )
        this = super().__new__(cls, time_str)
        this.num_seconds = time_seconds
        this.num = time_seconds // 60 if time_seconds is not None else None
        this.time_dt = time_dt
        this.tidy = (
            time_str.replace("0", " ", 1) if time_str.startswith("0") else time_str
        )
        this.short = time_str[1:] if time_str.startswith("0") else time_str
        this.original = str(maybe_time).strip()
        this.full = time_full
        return this

    @classmethod
    def _convert_time(
        cls, maybe_time, allow_large=False
    ) -> tuple[str, int, datetime, str]:
        if isinstance(maybe_time, (int, float)):
            maybe_time = (
                round(maybe_time * 60)
                if isinstance(maybe_time, float)
                else maybe_time * 60
            )
            if maybe_time < 0 or (not allow_large and maybe_time >= 86400):
                return "", None, None, ""
            time_dt = datetime.combine(
                datetime.today(), datetime.min.time()
            ) + timedelta(seconds=maybe_time)
            time_full = time_dt.strftime("%H:%M:%S")
            return cls._int_to_time(maybe_time // 60), maybe_time, time_dt, time_full

        elif isinstance(maybe_time, str):
            maybe_time = maybe_time.strip()
            if maybe_time.lower().startswith("now"):
                match = re.match(r"^now\s*([+-]\d+)?$", maybe_time, re.IGNORECASE)
                if match:
                    minutes_offset = int(match.group(1)) if match.group(1) else 0
                    now = datetime.now() + timedelta(minutes=minutes_offset)
                    hours, minutes, seconds = now.hour, now.minute, now.second
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                    time_full = now.strftime("%H:%M:%S")
                    return f"{hours:02}:{minutes:02}", total_seconds, now, time_full

            match = cls._TIME_PATTERN_HM.match(maybe_time)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                if hours > 24 and not allow_large or minutes > 59:
                    return "", None, None, ""
                total_seconds = hours * 3600 + minutes * 60
                time_dt = datetime.combine(
                    datetime.today(), datetime.min.time()
                ) + timedelta(seconds=total_seconds)
                time_full = time_dt.strftime("%H:%M:%S")
                return f"{hours:02}:{minutes:02}", total_seconds, time_dt, time_full
        return "", None, None, ""

    def __init__(
        self, maybe_time: str = "", allow_large=False
    ):  # pylint: disable=unused-argument
        """This is here only so that IDE will know the structure of a HMS_VTime."""
        if False:  # pylint: disable=using-constant-test
            self.num_seconds: int = None
            self.num: int = None
            self.short: str = None
            self.tidy: str = None
            self.original: str = None
            self.time_dt: datetime = None
            self.full: str = None

    @staticmethod
    def _int_to_time(int_time) -> str:
        hours = int_time // 60
        minutes = int_time % 60
        return f"{hours:02}:{minutes:02}"

    @property
    def time_in_seconds(self) -> int:
        """Return the time represented in seconds since midnight."""
        return self.num_seconds

    @property
    def datetime(self) -> datetime:
        """Return the internal datetime representation."""
        return self.time_dt

    @property
    def full(self) -> str:
        """Return the time represented as HH:MM:SS."""
        return self._full

    @full.setter
    def full(self, value: str):
        self._full = value

    def __eq__(self, other) -> bool:
        """Define equality to mean represent same time in HH:MM:SS format."""
        return bool(self.full == HMS_VTime(other).full)

    def __lt__(self, other) -> bool:
        return bool(self.full < HMS_VTime(other).full)

    def __gt__(self, other) -> bool:
        return bool(self.full > HMS_VTime(other).full)

    def __le__(self, other) -> bool:
        return bool(self.full <= HMS_VTime(other).full)

    def __ge__(self, other) -> bool:
        return bool(self.full >= HMS_VTime(other).full)

    def __ne__(self, other) -> bool:
        return bool(self.full != HMS_VTime(other).full)

    def __hash__(self):
        """Make hash int for the object."""
        return hash(self.full)

    # The purpose of the NULL class property is to enable comparisons like
    #   if time_out != VTime.NULL
    # rather than comparing to ""
    NULL = None

    @classmethod
    def set_null_value(cls, value):
        cls.NULL = value


HMS_VTime.set_null_value(HMS_VTime("null"))


class HM_VTime(str):
    # Precompile regex pattern for valid formats with optional colon
    _TIME_PATTERN_HM = re.compile(r"^(\d+):?(\d{2})$")

    def __new__(cls, maybe_time: str = "", allow_large=False):
        time_str, time_int = cls._convert_time(maybe_time, allow_large)
        this = super().__new__(cls, time_str)
        this.num = time_int
        this.tidy = (
            time_str.replace("0", " ", 1) if time_str.startswith("0") else time_str
        )
        this.short = time_str[1:] if time_str.startswith("0") else time_str
        this.original = str(maybe_time).strip()
        return this

    @classmethod
    def _convert_time(cls, maybe_time, allow_large=False) -> tuple[str, int]:
        if isinstance(maybe_time, (int, float)):
            # See if in range.
            maybe_time = (
                round(maybe_time) if isinstance(maybe_time, float) else maybe_time
            )
            if maybe_time < 0 or (not allow_large and maybe_time >= 1440):
                return ("", None)
            return cls._int_to_time(maybe_time), maybe_time

        elif isinstance(maybe_time, str):
            maybe_time = maybe_time.strip()
            # Special case: "now" means use current time
            if maybe_time.lower() == "now":
                now = datetime.now()
                hours, minutes = now.hour, now.minute
                return f"{hours:02}:{minutes:02}", hours * 60 + minutes
            # Pattern match for HH:MM
            match = cls._TIME_PATTERN_HM.match(maybe_time)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
            else:
                return "", None
            if hours > 24 and not allow_large or minutes > 59:
                return "", None
            return f"{hours:02}:{minutes:02}", hours * 60 + minutes
        return "", None

    def __init__(
        self, maybe_time: str = "", allow_large=False
    ):  # pylint:disable=unused-argument
        """This is here only so that IDE will know the structure of a VTime."""
        if False:  # pylint: disable=using-constant-test
            self.num: int = None
            self.short: str = None
            self.tidy: str = None
            self.original: str = None

    @staticmethod
    def _int_to_time(int_time) -> str:
        hours = int_time // 60
        minutes = int_time % 60
        return f"{hours:02}:{minutes:02}"

    # Comparisons are between str representations of itself and other
    def __eq__(self, other) -> bool:
        """Define equality to mean represent same tag name."""
        return bool(str(self) == str(HM_VTime(other)))

    def __lt__(self, other) -> bool:
        return bool(str(self) < str(HM_VTime(other)))

    def __gt__(self, other) -> bool:
        return bool(str(self) > str(HM_VTime(other)))

    def __le__(self, other) -> bool:
        return bool(str(self) <= str(HM_VTime(other)))

    def __ge__(self, other) -> bool:
        return bool(str(self) >= str(HM_VTime(other)))

    def __ne__(self, other) -> bool:
        return bool(str(self) != str(HM_VTime(other)))

    def __hash__(self):
        """Make hash int for the object.

        Not a simple object so not hashable (ie not usable as a dict key)
        so must provide own hash method that can be used as a dict key.
        For these, just hash the tag's string value. Case folding
        not necessary since it will never contain alpha characters.
        """
        return hash(str(self))


VTime = HM_VTime
