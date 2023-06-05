"""TagTracker by Julias Hocking.

Utility functions & constants for TagTracker suite.

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

import os
import datetime
import re
from typing import Union  # This is for type hints instead of (eg) int|str
from inspect import currentframe, getframeinfo

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import


def squawk(whatever="") -> None:
    """Print whatever with file & linenumber in front of it.

    This is intended for programming errors not prettiness.
    """
    cf = currentframe()
    filename = os.path.basename(getframeinfo(cf).filename)
    lineno = cf.f_back.f_lineno
    print(f"{filename}:{lineno}: {whatever}")


def get_date(long: bool = False) -> str:
    """Return current date as string YYYY-MM-DD or a longer str if long=True."""
    if long:
        return datetime.datetime.today().strftime("%A %B %d (%Y-%m-%d)")
    return datetime.datetime.today().strftime("%Y-%m-%d")


def long_date(date: str) -> str:
    """Convert YYYY-MM-DD to a long statement of the date."""
    return datetime.datetime.fromisoformat(date).strftime("%A %B %d (%Y-%m-%d)")


def date_str(maybe_date: str) -> str:
    """Return maybe_date in the form of YYYY-MM-DD (or "")."""
    if not maybe_date:
        return ""
    r = DATE_FULL_RE.match(maybe_date)
    if not (r):
        return ""
    y = int(r.group(1))
    m = int(r.group(2))
    d = int(r.group(3))
    # Test for an impossible date
    if y > 2100 or m < 1 or m > 12 or d < 1 or d > 31:
        return ""
    return f"{y:04d}-{m:02d}-{d:02d}"


def get_time() -> Time:
    """Return current time as string: HH:MM."""
    return datetime.datetime.today().strftime("%H:%M")


def time_int(maybe_time: Union[str, int, float, None]) -> Union[int, None]:
    """Return maybe_time (str or int) to number of minutes since midnight or "".

        Input can be int (minutes since midnight) or a string
    that might be a time in HH:MM.

    Return is either None (doesn't look like a valid time) or
    will be an integer between 0 and 1440.

    Warning: edge case: if given "00:00" or 0, this will return 0,
    which can test as False in a boolean argument.  In cases where 0
    might be a legitimate time, test for the type of the return or
    test whether "is None".
    """
    if isinstance(maybe_time, float):
        maybe_time = round(maybe_time)
    if isinstance(maybe_time, str):
        r = re.match(r"^ *([012]*[0-9]):?([0-5][0-9]) *$", maybe_time)
        if not (r):
            return None
        h = int(r.group(1))
        m = int(r.group(2))
        # Test for an impossible time
        if h > 24 or m > 59 or (h * 60 + m) > 1440:
            return None
        return h * 60 + m
    if isinstance(maybe_time, int):
        # Test for impossible time.
        if not (0 <= maybe_time <= 1440):
            return None
        return maybe_time
    if maybe_time is None:
        return None
    # Not an int, not a str, not None.
    squawk(f"PROGRAM ERROR: called time_int({maybe_time=})")
    return None


def time_str(
    maybe_time: Union[int, str, float, None],
    allow_now: bool = False,
    default_now: bool = False,
) -> Time:
    """Return maybe_time as HH:MM (or "").

    Input can be int/float (duration or minutes since midnight),
    or a string that *might* be a time in [H]H[:]MM.

    Special case: "now" will return current time if allowed
    by flag "allow_now".

    If default_now is True, then will return current time when input is blank.

    Return is either "" (doesn't look like a valid time) or
    will be HH:MM, always length 5 (i.e. 09:00 not 9:00)
    """
    if not maybe_time and default_now:
        return get_time()
    if isinstance(maybe_time, float):
        maybe_time = round(maybe_time)
    if isinstance(maybe_time, str):
        if maybe_time.lower() == "now" and allow_now:
            return get_time()
        r = re.match(r"^ *([012]*[0-9]):?([0-5][0-9]) *$", maybe_time)
        if not (r):
            return ""
        h = int(r.group(1))
        m = int(r.group(2))
        # Test for an impossible time
        if h > 24 or m > 59 or (h * 60 + m) > 1440:
            return ""
    elif maybe_time is None:
        return ""
    elif not isinstance(maybe_time, int):
        squawk(f"PROGRAM ERROR: called time_str({maybe_time=})")
        return ""
    elif isinstance(maybe_time, int):
        # Test for impossible time.
        if not (0 <= maybe_time <= 1440):
            return ""
        h = maybe_time // 60
        m = maybe_time % 60
    # Return 5-digit time string
    return f"{h:02d}:{m:02d}"


def pretty_time(atime: Union[int, str, float], trim: bool = False) -> str:
    """Replace lead 0 in HH:MM with blank (or remove, if 'trim' )."""
    atime = time_str(atime)
    if not atime:
        return ""
    replace_with = "" if trim else " "
    if atime[0] == "0":
        atime = f"{replace_with}{atime[1:]}"
    return atime


def parse_tag(maybe_tag: str, must_be_in=None, uppercase: bool = False) -> list[str]:
    """Test maybe_tag as a tag, return it as tag and bits.

    Tests maybe_tag by breaking it down into its constituent parts.
    If looks like a valid tagname, returns a list of
        [tag_id, colour, tag_letter, tag_number]
    If tag is not valid, then the return list is empty []

    If must_be_in is notan empty list (or None) then will check whether
    this tag is in the list passed in, and if
    not in the list, will return an empty list.

    If uppercase, this will return the tag & its bits in uppercase;
    otherwise in lowercase.

    Canonical tag id is a concatenation of
        tag_colour: 1+ lc letters representing the tag's colour,
                as defined in COLOUR_LETTERS
        tag_letter: 1 lc letter, the first character on the tag
        tag_number: a sequence number, without lead zeroes.
    """
    maybe_tag = maybe_tag.lower()
    r = PARSE_TAG_RE.match(maybe_tag)
    if not bool(r):
        return []

    tag_colour = r.group(1)
    tag_letter = r.group(2)
    tag_colour = tag_colour.upper() if uppercase else tag_colour
    tag_letter = tag_letter.upper() if uppercase else tag_letter
    tag_number = r.group(3)
    tag_id = f"{tag_colour}{tag_letter}{tag_number}"

    if must_be_in and tag_id not in must_be_in:
        return []

    return [tag_id, tag_colour, tag_letter, tag_number]


def fix_tag(maybe_tag: str, must_be_in: list = None, uppercase: bool = False) -> Tag:
    """Turn 'str' into a canonical tag name.

    If must_be_in is exists & not an empty list then, will force
    this to only allow tags that are in the list.

    If uppercase then returns the tag in uppercase, default is lowercase.
    """
    bits = parse_tag(maybe_tag, must_be_in=must_be_in, uppercase=uppercase)
    return bits[0] if bits else ""


def sort_tags(unsorted: list[Tag]) -> list[Tag]:
    """Sorts a list of tags (smart eg about wa12 > wa7).

    Precondition is that tags are all either uppercase or lowercase.
    """
    if re.search(r"[A-Z]", unsorted):
        uppercase = True
    elif re.search(r"[a-z]", unsorted):
        uppercase = False
    else:
        squawk(f"error call to sort_tags(), list is mixed case: '{unsorted=}'")
        uppercase = True

    newlist = []
    for tag in unsorted:
        bits = parse_tag(tag,uppercase=uppercase)
        newlist.append(f"{bits[1]}{bits[2]}{int(bits[3]):04d}")
    newlist.sort()
    newlist = [fix_tag(t, uppercase=uppercase) for t in newlist]
    return newlist


def tags_by_prefix(tags: list[Tag]) -> dict[str, list[Tag]]:
    """Return a dict of tag prefixes with lists of associated tag numbers."""
    prefixes = {}
    for tag in tags:
        # pylint: disable=unbalanced-tuple-unpacking
        (t_colour, t_letter, t_number) = parse_tag(tag,uppercase=False)[1:4]
        # pylint: disable=unbalanced-tuple-unpacking
        prefix = f"{t_colour}{t_letter}"
        if prefix not in prefixes:
            prefixes[prefix] = []
        prefixes[prefix].append(int(t_number))
    for numbers in prefixes.values():
        numbers.sort()
    return prefixes


def splitline(inp: str) -> list[str]:
    """Split input on commas & whitespace into list of non-blank strs."""
    # Start by splitting on commas
    tokens = inp.split(",")
    # Split on whitespace.  This makes a list of lists.
    tokens = [item.split() for item in tokens]
    # Flatten the list of lists into a single list.
    tokens = [item for sublist in tokens for item in sublist]
    # Reject any blank members of the list.
    tokens = [x for x in tokens if x]
    return tokens


def build_colour_dict(file: str) -> TagDict:
    """Create dictionary of colour names and abbreviations.

    Reads them from file; if file does not exist, creates it.
    """
    # Create empty file if does not exist.
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            header = (
                "Enter each first letter(s) of a tag name corresponding to "
                "a tag colour separated by whitespace on their own line, "
                "eg 'b black' etc"
            )
            f.writelines(header)
            return {}
    # Read from existing file
    with open(file, "r", encoding="utf-8") as f:
        lines = f.readlines()[1:]  # ignore header text
    colours = {}
    for line in lines:
        if len(line.rstrip().split()) == 2:
            abbrev = line.rstrip().split()[0]
            colour = line.rstrip().split()[1]
            colours[abbrev] = colour  # add to dictionary
    return colours


def get_version() -> str:
    """Return system version number."""
    changelog = "changelog.txt"
    if not os.path.exists(changelog):
        return "?"

    # Read startup header from changelog.
    with open(changelog, "r", encoding="utf-8") as f:
        for line in f:
            r = re.match(r"^ *([0-9]+\.[0-9]+\.[0-9]+): *$", line)
            if r:
                return r.group(1)
    return ""

def plural(count:int) -> str:
    """Get an "s" if count indicates one is needed."""
    if isinstance(count,(int,float)) and count == 1:
        return ""
    else:
        return "s"