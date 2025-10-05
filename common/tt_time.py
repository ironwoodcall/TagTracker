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
from datetime import datetime


# An alias at the end of this module determines which version of VTime is invoked


class HMS_VTime(str):
    """Variant of VTime that tracks seconds precision."""

    def __new__(cls, maybe_time: str = "", allow_large: bool = False):
        time_str, full_str, total_seconds = cls._convert_time(maybe_time, allow_large)
        this = super().__new__(cls, time_str)
        this.hms = full_str
        seconds_value = None if total_seconds is None else total_seconds
        # Minutes are truncated not rounded from seconds. Can use // since will never be negative.
        minutes_value = None if total_seconds is None else total_seconds // 60
        this.as_seconds = seconds_value
        this.as_minutes = minutes_value
        this.num = minutes_value  # Backwards compat alias
        this.tidy = (
            time_str.replace("0", " ", 1) if time_str.startswith("0") else time_str
        )
        this.short = time_str[1:] if time_str.startswith("0") else time_str
        this.original = str(maybe_time).strip()
        return this

    def __init__(
        self, maybe_time: str = "", allow_large: bool = False
    ):  # pylint:disable=unused-argument
        if False:  # pylint: disable=using-constant-test
            self.hms: str = None
            self.as_seconds: int = None
            self.as_minutes: float = None
            self.num: float = None
            self.short: str = None
            self.tidy: str = None
            self.original: str = None

    @classmethod
    def _convert_time(
        cls, maybe_time, allow_large: bool = False
    ) -> tuple[str, str, int | None]:
        if isinstance(maybe_time, HMS_VTime):
            return str(maybe_time), maybe_time.hms, maybe_time.as_seconds

        if isinstance(maybe_time, (int, float)):
            if isinstance(maybe_time, float):
                total_seconds = int(round(maybe_time * 60))
            else:
                total_seconds = int(maybe_time) * 60
            if total_seconds < 0 or (not allow_large and total_seconds > 86400):
                return "", "", None
            return cls._seconds_to_strings(total_seconds)

        if isinstance(maybe_time, str):
            maybe_time = maybe_time.strip()
            if not maybe_time:
                return "", "", None
            if maybe_time.lower() == "now":
                now = datetime.now()
                total_seconds = now.hour * 3600 + now.minute * 60 + now.second
                return cls._seconds_to_strings(total_seconds)

            hours = minutes = seconds = None

            if ":" in maybe_time:
                parts = maybe_time.split(":")
                if len(parts) == 2:
                    hours_str, minutes_str = parts
                    seconds_str = "00"
                elif len(parts) == 3:
                    hours_str, minutes_str, seconds_str = parts
                else:
                    return "", "", None

                if not (
                    hours_str.isdigit()
                    and minutes_str.isdigit()
                    and seconds_str.isdigit()
                ):
                    return "", "", None
                if len(minutes_str) != 2 or len(seconds_str) != 2:
                    return "", "", None
                hours = int(hours_str)
                minutes = int(minutes_str)
                seconds = int(seconds_str)
            elif maybe_time.isdigit() and len(maybe_time) >= 3:
                hours = int(maybe_time[:-2])
                minutes = int(maybe_time[-2:])
                seconds = 0
            else:
                return "", "", None

            if minutes > 59 or seconds > 59:
                return "", "", None
            if not allow_large:
                if hours > 24 or (hours == 24 and (minutes or seconds)):
                    return "", "", None

            total_seconds = hours * 3600 + minutes * 60 + seconds
            if total_seconds < 0:
                return "", "", None
            if not allow_large and total_seconds > 86400:
                return "", "", None

            return cls._seconds_to_strings(total_seconds)

        return "", "", None

    @staticmethod
    def _seconds_to_strings(total_seconds: int | None) -> tuple[str, str, int | None]:
        if total_seconds is None:
            return "", "", None
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return (
            f"{hours:02}:{minutes:02}",
            f"{hours:02}:{minutes:02}:{seconds:02}",
            total_seconds,
        )

    def __eq__(self, other) -> bool:
        other_time = self._coerce_to_vtime(other)
        self_seconds = self.as_seconds
        other_seconds = other_time.as_seconds
        if self_seconds is None and other_seconds is None:
            return True
        return self_seconds == other_seconds

    def __lt__(self, other) -> bool:
        other_time = self._coerce_to_vtime(other)
        self_seconds = self.as_seconds
        other_seconds = other_time.as_seconds
        if self_seconds is None:
            return other_seconds is not None
        if other_seconds is None:
            return False
        return self_seconds < other_seconds

    def __gt__(self, other) -> bool:
        other_time = self._coerce_to_vtime(other)
        self_seconds = self.as_seconds
        other_seconds = other_time.as_seconds
        if other_seconds is None:
            return self_seconds is not None
        if self_seconds is None:
            return False
        return self_seconds > other_seconds

    def __le__(self, other) -> bool:
        other_time = self._coerce_to_vtime(other)
        self_seconds = self.as_seconds
        other_seconds = other_time.as_seconds
        if self_seconds is None and other_seconds is None:
            return True
        if self_seconds is None:
            return True
        if other_seconds is None:
            return False
        return self_seconds <= other_seconds

    def __ge__(self, other) -> bool:
        other_time = self._coerce_to_vtime(other)
        self_seconds = self.as_seconds
        other_seconds = other_time.as_seconds
        if self_seconds is None and other_seconds is None:
            return True
        if self_seconds is None:
            return False
        if other_seconds is None:
            return True
        return self_seconds >= other_seconds

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.as_seconds)

    @staticmethod
    def _coerce_to_vtime(value):
        return value if isinstance(value, HMS_VTime) else HMS_VTime(value)



# class HM_VTime(str):
#     # Precompile regex pattern for valid formats with optional colon
#     _TIME_PATTERN_HM = re.compile(r"^(\d+):?(\d{2})$")

#     def __new__(cls, maybe_time: str = "", allow_large=False):
#         time_str, time_int = cls._convert_time(maybe_time, allow_large)
#         this = super().__new__(cls, time_str)
#         this.num = time_int
#         this.tidy = (
#             time_str.replace("0", " ", 1) if time_str.startswith("0") else time_str
#         )
#         this.short = time_str[1:] if time_str.startswith("0") else time_str
#         this.original = str(maybe_time).strip()
#         return this

#     @classmethod
#     def _convert_time(cls, maybe_time, allow_large=False) -> tuple[str, int]:
#         if isinstance(maybe_time, (int, float)):
#             # See if in range.
#             maybe_time = (
#                 round(maybe_time) if isinstance(maybe_time, float) else maybe_time
#             )
#             if maybe_time < 0 or (not allow_large and maybe_time >= 1440):
#                 return ("", None)
#             return cls._int_to_time(maybe_time), maybe_time

#         elif isinstance(maybe_time, str):
#             maybe_time = maybe_time.strip()
#             # Special case: "now" means use current time
#             if maybe_time.lower() == "now":
#                 now = datetime.now()
#                 hours, minutes = now.hour, now.minute
#                 return f"{hours:02}:{minutes:02}", hours * 60 + minutes
#             # Pattern match for HH:MM
#             match = cls._TIME_PATTERN_HM.match(maybe_time)
#             if match:
#                 hours = int(match.group(1))
#                 minutes = int(match.group(2))
#             else:
#                 return "", None
#             if hours > 24 and not allow_large or minutes > 59:
#                 return "", None
#             return f"{hours:02}:{minutes:02}", hours * 60 + minutes
#         return "", None

#     def __init__(
#         self, maybe_time: str = "", allow_large=False
#     ):  # pylint:disable=unused-argument
#         """This is here only so that IDE will know the structure of a VTime."""
#         if False:  # pylint: disable=using-constant-test
#             self.num: int = None
#             self.short: str = None
#             self.tidy: str = None
#             self.original: str = None

#     @staticmethod
#     def _int_to_time(int_time) -> str:
#         hours = int_time // 60
#         minutes = int_time % 60
#         return f"{hours:02}:{minutes:02}"

#     # Comparisons are between str representations of itself and other
#     def __eq__(self, other) -> bool:
#         """Define equality to mean represent same tag name."""
#         return bool(str(self) == str(HM_VTime(other)))

#     def __lt__(self, other) -> bool:
#         return bool(str(self) < str(HM_VTime(other)))

#     def __gt__(self, other) -> bool:
#         return bool(str(self) > str(HM_VTime(other)))

#     def __le__(self, other) -> bool:
#         return bool(str(self) <= str(HM_VTime(other)))

#     def __ge__(self, other) -> bool:
#         return bool(str(self) >= str(HM_VTime(other)))

#     def __ne__(self, other) -> bool:
#         return bool(str(self) != str(HM_VTime(other)))

#     def __hash__(self):
#         """Make hash int for the object.

#         Not a simple object so not hashable (ie not usable as a dict key)
#         so must provide own hash method that can be used as a dict key.
#         For these, just hash the tag's string value. Case folding
#         not necessary since it will never contain alpha characters.
#         """
#         return hash(str(self))


VTime = HMS_VTime
