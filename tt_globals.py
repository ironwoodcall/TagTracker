"""TagTracker by Julias Hocking.

Global constants for use through most or all the TagTracker modules.
These are meant to be wildcard-imported.

Copyright (C) 2023 Julias Hocking

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

# Type aliases only to improve readability and IDE linting
Tag = str
Time = str

from tt_tag import TagID
from tt_time import VTime


# Constants to use as dictionary keys.
# E.g. rather than something[this_time]["tag"] = "whatever",
# could instead be something[this_time][TAG_KEY] = "whatever"
# The values of these constants aren't important as long as they're unique.
# By using these rather than string values, the lint checker in the
# editor can pick up missing or misspelled items, as can Python itself.
# These all have a non-ASCII chr (→) at the beginning to make it unlikely
# that their values would ever get typed or otherwise be non-unique

TAG = chr(0x2192) + "tag"
BIKE_IN = chr(0x2192) + "bike_in"
BIKE_OUT = chr(0x2192) + "bike_out"
INOUT = chr(0x2192) + "inout"
REGULAR = chr(0x2192) + "regular"
OVERSIZE = chr(0x2192) + "oversize"
MIXED = chr(0x2192) + "mixed"
RETIRED = chr(0x2192) + "retired"
TOTAL = chr(0x2192) + "total"
COUNT = chr(0x2192) + "count"
TIME = chr(0x2192) + "time"
IGNORE = chr(0x2192) + "ignore"
COLOURS = chr(0x2192) + "colours"
BADVALUE = chr(0x2192) + "badvalue"
UPPERCASE = chr(0x2192) + "uppercase"
LOWERCASE = chr(0x2192) + "lowercase"
UNKNOWN = chr(0x2192) + "unknown"
ON = chr(0x2192) + "on"
OFF = chr(0x2192) + "off"

# Here's how I really want to do it, but then pylint won't know they're defined
# for keyword in [
#    "TAG", "TIME",
#    "BIKE_IN","BIKE_OUT","INOUT",
#    "REGULAR","OVERSIZE","RETIRED",
#    "TOTAL","COUNT",
#    "IGNORE",
#    "COLOURS",
#    "BADVALUE",
#    "UPPERCASE","LOWERCASE",
#   "UNKNOWN",
#    "ON","OFF"
# ]:
#   globals()[keyword] = chr(0x2192) + keyword.lower()


# Regular expression for parsing tags -- here & in main program.
PARSE_TAG_RE = re.compile(r"^ *([a-z]+)([a-z])0*([0-9]+) *$")
# Date re checks for date that might be in another string
_DATE_RE = r"(2[0-9][0-9][0-9])[/-]([01]?[0-9])[/-]([0123]?[0-9])"
# Match a date within another string
DATE_PART_RE = re.compile(r"(\b|[^a-zA-Z0-9])" + _DATE_RE + r"\b")
# Match a date as the whole string
DATE_FULL_RE = re.compile(r"^ *" + _DATE_RE + " *$")
