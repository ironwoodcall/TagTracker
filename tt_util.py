"""TagTracker by Julias Hocking.

Utility functions & constants for TagTracker suite.

Copyright (C) 2023 Julias Hocking

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

import os
import sys
import datetime
import re
import collections
import random
import string


# This is for type hints instead of (eg) int|str
from typing import Union

# from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
from tt_time import VTime
from tt_tag import TagID


def top_level_script() -> str:
    """Return filename of highest-level calling script.

    This is specifically intended to let a module determine
    whether or not it is being called by the tagtracker desktop
    (data entry) script."""

    frame = sys._getframe()
    while frame.f_back:
        frame = frame.f_back
    top = frame.f_globals.get("__file__", None)
    top = top if top else ""
    return top


def squawk(whatever: str = "") -> None:
    """Print whatever with file & linenumber in front of it.

    This is intended for programming errors not prettiness.

    Additional caller info:
        caller_path = f.f_globals['__file__'] (though fails if squawk()
            called from interpreter, as __file__ not in globals at that point)
        caller_file = os.path.basename(caller_path)
    """
    f = sys._getframe(1)  # pylint:disable=protected-access
    caller_module = f.f_globals["__name__"]
    caller_function = f.f_code.co_name
    caller_line_no = f.f_lineno
    print(f"{caller_module}:{caller_function}():{caller_line_no}: {whatever}")


def decomment(string: str) -> str:
    """Remove any part of the string that starts with '#'."""
    r = re.match(r"^([^#]*) *#", string)
    if r:
        return r.group(1)
    return string


def get_date(long: bool = False) -> str:
    """Return current date as string YYYY-MM-DD or a longer str if long=True."""
    # FIXME: superseded by date_str()
    return date_str("today", long_date=long)
    # if long:
    #    return datetime.datetime.today().strftime("%A %B %d (%Y-%m-%d)")
    # return datetime.datetime.today().strftime("%Y-%m-%d")


def date_str(
    maybe_date: str,
    dow_str_len: int = None,
    long_date: bool = False,
    strict: bool = False,
) -> str:
    """Return maybe_date in the form of YYYY-MM-DD (or "").

    Optional flags will return it in a variety of str or int
    formats:
        dow_str_len: if set, returns the date as day of week
            of given length (up to day of week's full length)
        long_date: if True, returns str as a long date
        strict: if set, only accepts exact "YYYY-MM-DD";
            otherwise accepts "now", "today" "tomorrow" and
            "yesterday"; strips whitespace; and accepts
            "" or "/" as separators

    """
    # FIXME: replace get_date() with a call to this
    if not maybe_date or not isinstance(maybe_date, str) or maybe_date.isspace():
        return ""
    thisday = None
    if not strict:
        maybe_date = maybe_date.lower().strip()
        if maybe_date in ["now", "today"]:
            thisday = datetime.datetime.today()
        elif maybe_date == "yesterday":
            thisday = datetime.datetime.today() - datetime.timedelta(1)
        elif maybe_date == "tomorrow":
            thisday = datetime.datetime.today() + datetime.timedelta(1)
        else:
            # Allow YYYYMMDD or YYYY/MM/DD
            r = re.fullmatch(r"(\d\d\d\d)[-/]?(\d\d)[-/]?(\d\d)", maybe_date)
            if not r:
                return ""
            try:
                thisday = datetime.datetime.strptime(
                    f"{r.group(1)}-{r.group(2)}-{r.group(3)}", "%Y-%m-%d"
                )
            except ValueError:
                return ""
    if not thisday:
        try:
            thisday = datetime.datetime.strptime(maybe_date, "%Y-%m-%d")
        except ValueError:
            return ""
    if not thisday:
        return ""
    # Now have thisday (a datetime object), convert to str
    # Format as a day of the week?
    if dow_str_len:
        return thisday.strftime("%A")[0:dow_str_len]
    if long_date:
        return thisday.strftime("%A %B %d (%Y-%m-%d)")
    return thisday.strftime("%Y-%m-%d")


def date_offset(start_date: str, offset: int) -> str:
    """Return a day some number of days before or after a date.

    start_date: is any date string that date_str() will recognize
    offset: is the number of days later(+) or earlier(-)
    Returns:
        YYYY-MM-DD of date which is offset from start_date
        "" if start_date is bad
    """
    start_date = date_str(start_date)
    if not start_date:
        return ""
    offset_day = datetime.datetime.strptime(
        start_date, "%Y-%m-%d"
    ) + datetime.timedelta(offset)
    return offset_day.strftime("%Y-%m-%d")


def dow_int(date_or_dayname: str) -> int:
    """Get ISO day of week from a date or weekday name."""
    date = date_str(date_or_dayname)
    if date:
        d = datetime.datetime.strptime(date, "%Y-%m-%d")
        return int(d.strftime("%u"))
    # Try to match to a dow.
    dow_ints = {
        1: ["m", "mo", "mon", "monday"],
        2: ["tu", "tue", "tues", "tuesday"],
        3: ["w", "we", "wed", "wednesday"],
        4: ["th", "thu", "thurs", "thursday"],
        5: ["f", "fr", "fri", "friday"],
        6: ["sa", "sat", "saturday"],
        7: ["su", "sun", "sunday"],
    }
    for num, name_list in dow_ints.items():
        if str(date_or_dayname).strip().lower() in name_list:
            return num
    return None


def dow_str(iso_dow: int, dow_str_len: int = 0) -> str:
    """Return int ISO day of week as a str of length dow_str_len.

    If dow_len is not specified then returns whole dow name.
    """
    iso_dow = str(iso_dow)
    dow_str_len = dow_str_len if dow_str_len else 99
    d = datetime.datetime.strptime(f"2023-1-{iso_dow}", "%Y-%W-%u")
    return date_str(d.strftime("%Y-%m-%d"), dow_str_len=dow_str_len)


def most_recent_dow(iso_day) -> str:
    """Return most recent date that falls on day of week iso_day."""
    if isinstance(iso_day, str) and iso_day.isdigit():
        iso_day = int(iso_day)
    elif isinstance(iso_day, float):
        iso_day = round(iso_day)
    elif not isinstance(iso_day, int):
        return None

    # Get the current date
    current_date = datetime.date.today()
    # Calculate the difference between the current day of the week and the target ISO day
    day_difference = current_date.isoweekday() - iso_day
    # Calculate the most recent date by subtracting the day difference from the current date
    most_recent_date = current_date - datetime.timedelta(days=day_difference)
    return most_recent_date.strftime("%Y-%m-%d")


def get_time() -> VTime:
    """Return current time as string: HH:MM."""
    # FIXME: get_time() deprecated, use VTime("now") instead
    return VTime(datetime.datetime.today().strftime("%H:%M"))


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
    # FIXME: time_int() deprecated, use VTime() instead
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
) -> VTime:
    """Return maybe_time as HH:MM (or "").

    Input can be int/float (duration or minutes since midnight),
    or a string that *might* be a time in [H]H[:]MM.

    Special case: "now" will return current time if allowed
    by flag "allow_now".

    If default_now is True, then will return current time when input is blank.

    Return is either "" (doesn't look like a valid time) or
    will be HH:MM, always length 5 (i.e. 09:00 not 9:00)
    """
    # FIXME: time_str() deprecated, use VTime() object
    if not maybe_time and default_now:
        return VTime("now")
    if isinstance(maybe_time, float):
        maybe_time = round(maybe_time)
    if isinstance(maybe_time, str):
        if maybe_time.lower() == "now" and allow_now:
            return VTime("now")
        r = re.match(r"^ *([012]*[0-9]):?([0-5][0-9]) *$", maybe_time)
        if not (r):
            return VTime("")
        h = int(r.group(1))
        m = int(r.group(2))
        # Test for an impossible time
        if h > 24 or m > 59 or (h * 60 + m) > 1440:
            return VTime("")
    elif maybe_time is None:
        return VTime("")
    elif not isinstance(maybe_time, int):
        squawk(f"PROGRAM ERROR: called time_str({maybe_time=})")
        return VTime("")
    elif isinstance(maybe_time, int):
        # Test for impossible time.
        if not (0 <= maybe_time <= 1440):
            return VTime("")
        h = maybe_time // 60
        m = maybe_time % 60
    # Return 5-digit time string
    return VTime(f"{h:02d}:{m:02d}")


def pretty_time(atime: Union[int, str, float], trim: bool = False) -> str:
    """Replace lead 0 in HH:MM with blank (or remove, if 'trim' )."""
    # FIXME: pretty_time() deprecated; use VTime().tidy or VTime().short
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

    If must_be_in is not an empty list (or None) then will check whether
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
    # FIXME: parse_tag() is  deprecated, use TagID()
    maybe_tag = maybe_tag.lower()
    # Regular expression for parsing tags
    PARSE_TAG_RE = re.compile(r"^ *([a-z]+)([a-z])0*([0-9]+) *$")
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


def fix_tag(maybe_tag: str, must_be_in: list = None, uppercase: bool = False) -> str:
    """Turn 'str' into a canonical tag name.

    If must_be_in is exists & not an empty list then, will force
    this to only allow tags that are in the list.

    If uppercase then returns the tag in uppercase, default is lowercase.
    """
    # FIXME fix_tag fn is now deprecated, useTagID()
    bits = parse_tag(maybe_tag, must_be_in=must_be_in, uppercase=uppercase)
    return bits[0] if bits else ""


def taglists_by_prefix(unsorted: tuple[TagID]) -> list[list[TagID]]:
    """Get tags sorted into lists by their prefix.

    Return a list of lists of tags, sorted and de-duped. E.g.
        taglists_by_prefix(['wa5','be1','be1', 'wa12','wd15','be1','be10','be9'])
        --> [['be1','be9','be10],['wa5','wa12'],['wd15']]

    Preconditions:
        - tags are either all uppercase or all lowercase
        - all tags are syntactically valid
    """

    # Make a dictionary of all tags keyed by their prefixes
    prefixed_tags = dict(
        zip([tag.prefix for tag in unsorted], [[] for _ in range(0, 100)])
    )
    for tag in unsorted:
        prefixed_tags[tag.prefix].append(tag)
    outerlist = []
    for prefix in sorted(prefixed_tags.keys()):
        outerlist.append(sorted(prefixed_tags[prefix]))
    return outerlist


def tagnums_by_prefix(tags: list[TagID]) -> dict[str, list[int]]:
    """Return a dict of tag prefixes with lists of associated tag numbers."""
    prefixes = {}
    for tag in tags:
        if tag.prefix not in prefixes:
            prefixes[tag.prefix] = []
        prefixes[tag.prefix].append(tag.number)
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


def get_version() -> str:
    """Return system version number from changelog.txt.

    If it looks like a git repo, will also try to include a ref from that.
    """
    version_str = ""
    changelog = "changelog.txt"
    if os.path.exists(changelog):
        # Read startup header from changelog.
        with open(changelog, "r", encoding="utf-8") as f:
            for line in f:
                r = re.match(r"^ *([0-9]+\.[0-9\.]+\.[0-9]+): *$", line)
                if r:
                    version_str = r.group(1)
                    break

    # Git ref
    git_head = os.path.join(".git", "HEAD")
    if not os.path.exists(git_head):
        return version_str
    # .git/HEAD points to the file that contains the version
    with open(git_head, "r", encoding="utf-8") as f:
        ref_path = ""
        for line in f:
            r = re.match(r"^ref: *(refs.*)", line)
            if r:
                ref_path = r.group(1)
        if not ref_path:
            return version_str
    ref_full_path = os.path.join(".git", ref_path)
    if not os.path.exists(ref_full_path):
        return version_str
    git_str = ""
    with open(ref_full_path, "r", encoding="utf-8") as f:
        for line in f:
            if line:
                git_str = line.strip()[:7]
                break
    # get just the feature portion of the git ref_path
    r = re.match(r"^refs/heads/(.*)", ref_path)
    if r:
        git_str = f"{git_str} {r.group(1)}"
    # Full version string now
    version_str = f"{version_str} ({git_str})"
    return version_str


def OLD_plural(count: int) -> str:
    """Get an "s" if count indicates one is needed."""
    if isinstance(count, (int, float)) and count == 1:
        return ""
    else:
        return "s"


def untaint(tainted: str) -> str:
    """Remove any suspicious characters from a possibly tainted string."""
    return "".join(c for c in tainted if c.isprintable())


def plural(count: int, singluar_form: str, plural_form: str = "") -> str:
    """Choose correct singlur/pliral form of a word."""
    if count == 1:
        return singluar_form
    plural_form = plural_form if plural_form else f"{singluar_form}s"
    return plural_form


def line_splitter(
    input_string, width: int = 80, print_handler=None, print_handler_args=None
) -> list[str]:
    """Split and maybe print input_string to a given width.

    print_handler is an optional print handler function (e.g. print,iprint,squawk)
        if None, then no printing takes place
    print_handler_args is a dict of named arguments for print_handler
        (e.g. {"num_indents":2})
    Returns a list of strings of width width or less.

    Thanks ChatGPT for the basic code and especially for the tricky syntax
    forwarding optional args to the print hander.
    """
    # If no print handler args just make an empty dict.
    print_handler_args = print_handler_args if print_handler_args else {}

    lines = []
    while len(input_string) > width:
        last_space_index = input_string.rfind(" ", 0, width + 1)

        if last_space_index == -1:
            last_space_index = width

        line = input_string[:last_space_index]
        lines.append(line)

        if print_handler:
            print_handler(line, **print_handler_args)

        input_string = input_string[last_space_index + 1 :]

    lines.append(input_string)

    if print_handler:
        print_handler(input_string, **print_handler_args)

    return lines

def calculate_visit_frequencies(
    durations_list: list, category_width: int = 30
) -> collections.Counter:
    durations = []
    for d in durations_list:
        if isinstance(d, int):
            durations.append(d)
        else:
            durations.append(VTime(d).num)
    durations = [d for d in durations if isinstance(d, int)]

    # Make a new list of the durations, categorized
    categorized = [(d // category_width) * category_width for d in durations]

    # Count how many are in each category
    return collections.Counter(categorized)


def calculate_visit_modes(
    durations_list: list, category_width: int = 30
) -> tuple[list[VTime], int]:
    """Calculate the mode(s) for the list of durations.

    The elements in durations can be VTime, str, or int,
    as long as they all evaluate to a VTime.

    For purposes of determining mode, times within one
    block of time of length category_width are
    considered identical.  Defaulit 30 (1/2 hour)

    Returns a list of sorted VTimes().tidy of all the centre times of
    the modes and the number of times it/they occurred.
    """
    freq_list = calculate_visit_frequencies(durations_list,category_width)
    mosts = freq_list.most_common()
    occurences = mosts[0][1]
    modes_numeric = sorted(
        [element for element, count in mosts if count == occurences]
    )
    modes_list = [f"{VTime(x+category_width/2).tidy}" for x in modes_numeric]
    # modes_list = []
    # modes_list = [x.tidy for x in modes_list]

    return modes_list, occurences

def random_string(length):
    """Create a random alphaetic string of a given length."""
    return "".join(random.choice(string.ascii_letters) for _ in range(length))

