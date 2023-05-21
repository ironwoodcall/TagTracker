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
##import sys
##import time
from datetime import datetime
import re
##import pathlib
##import statistics
from typing import Union    # This is for type hints instead of (eg) int|str
from inspect import currentframe, getframeinfo

Tag = str
Time = str
TagDict = dict[Tag,Time]

# Constants to use as dictionary keys.
# E.g. rather than something[this_time]["tag"] = "whatever",
# could instead be something[this_time][TAG_KEY] = "whatever"
# The values of these constants aren't important as long as they're unique.
# By using these rather than string values, the lint checker in the
# editor can pick up missing or misspelled items, as can Python itself.
TAG = "tag"
BIKE_IN = "bike_in"
BIKE_OUT = "bike_out"
INOUT = "inout"
REGULAR = "regular"
OVERSIZE = "oversize"
TOTAL = "total"
COUNT = "count"
TIME = "time"
IGNORE = "ignore"

def squawk(whatever="") -> None:
    """Print whatever with file & linenumber in front of it.

    This is intended for programming errors not prettiness.
    """
    cf = currentframe()
    filename = os.path.basename(getframeinfo(cf).filename)
    lineno = cf.f_back.f_lineno
    print(f"{filename}:{lineno}: {whatever}")

def get_date() -> str:
    """Return current date as string: YYYY-MM-DD."""
    return datetime.today().strftime("%Y-%m-%d")

def get_time() -> Time:
    """Return current time as string: HH:MM."""
    return datetime.today().strftime("%H:%M")

def time_int(maybe_time:Union[str,int,float,None]) -> Union[int,None]:
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
    if isinstance(maybe_time,float):
        maybe_time = round(maybe_time)
    if isinstance(maybe_time,str):
        r = re.match(r"^ *([012]*[0-9]):?([0-5][0-9]) *$", maybe_time)
        if not (r):
            return None
        h = int(r.group(1))
        m = int(r.group(2))
        # Test for an impossible time
        if h > 24 or m > 59 or (h * 60 + m) > 1440:
            return None
        return h * 60 + m
    if isinstance(maybe_time,int):
        # Test for impossible time.
        if not (0 <= maybe_time <= 1440):
            return None
        return maybe_time
    if maybe_time is None:
        return None
    # Not an int, not a str, not None.
    squawk(f"PROGRAM ERROR: called time_int({maybe_time=})")
    return None

def time_str(maybe_time:Union[int,str,float,None]) -> Time:
    """Return inp (wich is str or int) to HH:MM, or "".

    Input can be int (minutes since midnight) or a string
    that might be a time in HH:MM.

    Return is either "" (doesn't look like a valid time) or
    will be HH:MM, always length 5 (i.e. 09:00 not 9:00)
    """
    if isinstance(maybe_time,float):
        maybe_time = round(maybe_time)
    if isinstance(maybe_time,str):
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
    elif not isinstance(maybe_time,int):
        squawk(f"PROGRAM ERROR: called time_str({maybe_time=})")
        return ""
    elif isinstance(maybe_time,int):
        # Test for impossible time.
        if not (0 <= maybe_time <= 1440):
            return ""
        h = maybe_time // 60
        m = maybe_time % 60
    # Return 5-digit time string
    return f"{h:02d}:{m:02d}"

def pretty_time(atime:Union[int,str,float], trim:bool=False ) -> str:
    """Replace lead 0 in HH:MM with blank (or remove, if 'trim' )."""
    atime = time_str(atime)
    if not atime:
        return ""
    replace_with = "" if trim else " "
    if atime[0] == "0":
        atime = f"{replace_with}{atime[1:]}"
    return atime

def write_datafile(file:str,
        opening_time:Time, closing_time:Time,
        bikes_in:TagDict, bikes_out:TagDict,
        normal:list, oversize:list,
        header_lines:list=None) -> None:
    """Write current data to today's data file."""
    lines = []
    if header_lines:
        lines = header_lines
    else:
        lines.append("# TagTracker datafile (data file) created on "
                f"{get_date()} {get_time()}")
    # Valet opening & closing hours
    if opening_time:
        lines.append(f"Valet opens: {opening_time}")
    if closing_time:
        lines.append(f"Valet closes: {closing_time}")

    lines.append("Bikes checked in / tags out:")
    for tag, atime in bikes_in.items(): # for each bike checked in
        lines.append(f"{tag},{atime}") # add a line "tag,time"
    lines.append("Bikes checked out / tags in:")
    for tag,atime in bikes_out.items(): # for each  checked
        lines.append(f"{tag},{atime}") # add a line "tag,time"
    # Also write tag info of which bikes are oversize, which are regular.
    # This is for datafile aggregator.
    lines.append( "# The following sections are for datafile aggregator")
    lines.append("Regular-bike tags:")
    for tag in normal:
        lines.append(tag)
    lines.append("Oversize-bike tags:")
    for tag in oversize:
        lines.append(tag)
    lines.append("# Normal end of file")
    # Write the data to the file.
    with open(file, 'w',encoding='utf-8') as f: # write stored lines to file
        for line in lines:
            f.write(line)
            f.write("\n")

# assemble list of normal tags
def build_tags_config(filename:str) -> list[Tag]:
    """Build a tag list from a file.

    Constructs a list of each allowable tag in a given category
    (normal, oversize, retired, etc) by reading its category.cfg file.
    """
    tags = []
    if not os.path.exists(filename): # make new tags config file if needed
        with open(filename, 'w',encoding='utf-8') as f:
            header = ("# Enter lines of whitespace-separated tags, "
                    "eg 'wa0 wa1 wa2 wa3'\n")
            f.writelines(header)
    with open(filename, 'r',encoding='utf-8') as f: # open and read
        lines = f.readlines()
    line_counter = 0 # init line counter to 0
    for line in lines:
        line_counter += 1 # increment for current line
        if not line[0] == '#': # for each non-comment line
            # (blank lines do nothing here anyway)
            line_words = line.rstrip().split() # split into each tag name
            for word in line_words: # check line for nonconforming tag names
                if not PARSE_TAG_RE.match(word):
                    print(f'Invalid tag "{word}" found '
                          f'in {filename} on line {line_counter}')
                    return [] # stop loading
            tags += line_words # add all tags in that line to this tag type
    return tags

def build_colour_dict(file:str) -> TagDict:
    """Create dictionary of colour names and abbreviations.

    Reads them from file; if file does not exist, creates it.
    """
    # Create empty file if does not exist.
    if not os.path.exists(file):
        with open(file, 'w',
                encoding='utf-8') as f:
            header = ("Enter each first letter(s) of a tag name corresponding to "
                    "a tag colour separated by whitespace on their own line, "
                    "eg 'b black' etc")
            f.writelines(header)
            return {}
    # Read from existing file
    with open(file, 'r', encoding='utf-8') as f:
        lines = f.readlines()[1:] # ignore header text
    colours = {}
    for line in lines:
        if len(line.rstrip().split()) == 2:
            abbrev = line.rstrip().split()[0]
            colour = line.rstrip().split()[1]
            colours[abbrev] = colour # add to dictionary
    return colours

def get_version() -> str:
    """Return system version number."""
    changelog = "changelog.txt"
    if not os.path.exists(changelog):
        return "?"

    # Read startup header from changelog.
    with open(changelog, 'r',encoding='utf-8') as f:
        for line in f:
            r = re.match(r"^ *([0-9]+\.[0-9]+\.[0-9]+): *$", line)
            if r:
                return r.group(1)
    return ""

# Regular expression for parsing tags -- here & in main program.
PARSE_TAG_RE = re.compile(r"^ *([a-z]+)([a-z])0*([0-9]+) *$")


