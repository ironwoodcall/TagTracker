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

class VTime(str):
    # Precompile regex pattern for valid formats with optional colon
    TIME_PATTERN = re.compile(r'^(\d+):?(\d{2})$')

    def __new__(cls, maybe_time:str="", allow_large=False):
        time_str,time_int = cls._convert_time(maybe_time, allow_large)
        this = super().__new__(cls, time_str)
        this.num = time_int
        this.tidy = time_str.replace('0', ' ', 1) if time_str.startswith('0') else time_str
        this.short = time_str[1:] if time_str.startswith('0') else time_str
        this.original = str(maybe_time).strip()
        return this

    @classmethod
    def _convert_time(cls,maybe_time, allow_large=False) -> tuple[str,int]:
        if isinstance(maybe_time,(int,float)):
            # See if in range.
            maybe_time = round(maybe_time) if isinstance(maybe_time,float) else maybe_time
            if maybe_time < 0 or (not allow_large and maybe_time >= 1440):
                return ('',None)
            return cls._int_to_time(maybe_time),maybe_time

        elif isinstance(maybe_time, str):
            maybe_time = maybe_time.strip()
            # Special case: "now" means use current time
            if maybe_time.lower() == "now":
                now = datetime.now()
                hours, minutes = now.hour, now.minute
                return f'{hours:02}:{minutes:02}', hours * 60 + minutes
            # Pattern match for HH:MM
            match = cls.TIME_PATTERN.match(maybe_time)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
            else:
                return '',None
            if hours > 24 and not allow_large or minutes > 59:
                return '',None
            return f'{hours:02}:{minutes:02}', hours*60+minutes
        return '',None

    def __init__(self, maybe_time:str="", allow_large=False): #pylint:disable=unused-argument
        """This is here only so that IDE will know the structure of a VTime."""
        if False: # pylint: disable=using-constant-test
            self.num:int = None
            self.short:str = None
            self.tidy:str = None
            self.original:str = None

    @staticmethod
    def _int_to_time(int_time) -> str:
        hours = int_time // 60
        minutes = int_time % 60
        return f'{hours:02}:{minutes:02}'

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
        For these, just hash the tag's string value. Case folding
        not necessary since it will never contain alpha characters.
        """
        return hash(str(self))

