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
from datetime import datetime
import re
from typing import Union    # This is for type hints instead of (eg) int|str
from inspect import currentframe, getframeinfo

# Type aliases only to improve readability and IDE linting
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

def date_str(maybe_date:str) -> str:
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
    """Return maybe_time as HH:MM (or "").

    Input can be int/float (duration or minutes since midnight),
    or a string that *might* be a time in [H]H[:]MM.

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

def parse_tag(maybe_tag:str, must_be_in=None, uppercase:bool=False) -> list[str]:
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

    return [tag_id,tag_colour,tag_letter,tag_number]

def fix_tag(maybe_tag:str, must_be_in:list=None,uppercase:bool=False) -> Tag:
    """Turn 'str' into a canonical tag name.

    If must_be_in is exists & not an empty list then, will force
    this to only allow tags that are in the list.

    If uppercase then returns the tag in uppercase, else lowercase.
    """
    bits = parse_tag(maybe_tag, must_be_in=must_be_in,uppercase=uppercase)
    return bits[0] if bits else ""

def sort_tags( unsorted:list[Tag]) -> list[Tag]:
    """Sorts a list of tags (smart eg about wa12 > wa7)."""
    newlist = []
    for tag in unsorted:
        bits = parse_tag(tag)
        newlist.append(f"{bits[1]}{bits[2]}{int(bits[3]):04d}")
    newlist.sort()
    newlist = [fix_tag(t) for t in newlist]
    return newlist

def tags_by_prefix(tags:list[Tag]) -> dict[str,list[Tag]]:
    """Return a dict of tag prefixes with lists of associated tag numbers."""
    prefixes = {}
    for tag in tags:
        # pylint: disable=unbalanced-tuple-unpacking
        (t_colour,t_letter,t_number) = (parse_tag(tag)[1:4])
        # pylint: disable=unbalanced-tuple-unpacking
        prefix = f"{t_colour}{t_letter}"
        if prefix not in prefixes:
            prefixes[prefix] = []
        prefixes[prefix].append(int(t_number))
    for numbers in prefixes.values():
        numbers.sort()
    return prefixes

class TrackerDay():
    """One day's worth of tracker info."""

    def __init__(self) -> None:
        """Initialize blank."""
        self.date = ""
        self.opening_time = ""
        self.closing_time = ""
        self.bikes_in = {}
        self.bikes_out = {}
        self.regular = []
        self.oversize = []

def rotate_log(filename:str) -> None:
    """Rename the current logfile to <itself>.bak."""
    backuppath = f"{filename}.bak"
    if os.path.exists(backuppath):
        os.unlink(backuppath)
    if os.path.exists(filename):
        os.rename(filename,backuppath)
    return None

def read_datafile(filename:str, err_msgs:list[str],
            usable_tags:list[Tag]=None) -> TrackerDay:
    """Fetch tag data from file into a TrackerDay object.

    Read data from a pre-existing data file, returns the info in a
    TrackerDay object.  If no file, TrackerDay will be mostly blank.

    err_msgs is the (presumably empty) list, to which any error messages
    will be appended.  If no messages are added, then it means this
    ran without error.

    usable_tags is a list of tags that can be used; if a tag is not in the
    list then it's an error.  If usable_tags is empty or None then no
    checking takes place.

    """
    def data_read_error(text:str, message_list:list[str],
                errs:int=0, fname:str="", fline:int=None) -> int:
        """Print a datafile read error, increments error counter.

        This returns the incremented error counter.  Ugh.
        Also, if this is the first error (errors_before is None or 0)
        then this makes an initial print() on the assumptino that the
        immediately preceding print() statement had end="".
        """
        text = f" {text}"
        if fline:
            text = f"{fline}:{text}"
        if fname:
            text = f"{fname}:{text}"
        message_list.append(text)
        return errs + 1

    data = TrackerDay()
    errors = 0  # How many errors found reading datafile?
    section = None
    with open(filename, 'r',encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            # ignore blank or # comment lines
            line = re.sub(r"\s*#.*","", line)
            line = line.strip()
            if not line:
                continue
            # Look for section headers
            if (re.match(r"^Bikes checked in.*:",line)):
                section = BIKE_IN
                continue
            elif (re.match(r"^Bikes checked out.*:", line)):
                section = BIKE_OUT
                continue
            # Look for headers for oversize & regular bikes, ignore them.
            elif (re.match(r"^Regular-bike tags.*:",line)):
                section = IGNORE
                continue
            elif (re.match(r"^Oversize-bike tags.*:",line)):
                section = IGNORE
                continue
            elif (re.match(r"^Valet date:",line)):
                # Read the logfile's date
                section = IGNORE
                r = re.match(r"Valet date: *(.+)",line)
                maybedate = date_str(r.group(1))
                if not maybedate:
                    errors = data_read_error("Unable to read valet date",
                        err_msgs, errs=errors,
                        fname=filename, fline=line_num)
                    continue
                data.date = maybedate
                continue
            elif (re.match(r"^Valet (opens|closes):",line)):
                # This is either an open or a close time (probably)
                section = IGNORE
                r = re.match(r"Valet (opens|closes): *(.+)",line)
                maybetime = time_str(r.group(2))
                if not maybetime:
                    errors = data_read_error(
                        "Unable to read valet open/close time", err_msgs,
                        errs=errors, fname=filename, fline=line_num)
                    continue
                if r.group(1) == "opens":
                    data.opening_time = maybetime
                else:
                    data.closing_time = maybetime
                continue
            # Can do nothing unless we know what section we're in
            if section is None:
                errors = data_read_error(
                        "Unexpected unintelligibility in line", err_msgs,
                        errs=errors, fname=filename, fline=line_num)
                continue
            if section == IGNORE:
                # Things to ignore
                continue
            # Break into putative tag and text, looking for errors
            cells = line.split(',')
            if len(cells) != 2:
                errors = data_read_error("Bad line in file", err_msgs,
                        errs=errors, fname=filename, fline=line_num)
                continue
            this_tag = fix_tag(cells[0])
            if not (this_tag):
                errors = data_read_error("String does not appear to be a tag",
                        err_msgs, errs=errors,
                        fname=filename, fline=line_num)
                continue
            if usable_tags and this_tag not in usable_tags:
                errors = data_read_error(f"Tag '{this_tag}' not in use",
                        err_msgs, errs=errors,
                        fname=filename, fline=line_num)
                continue
            this_time = time_str(cells[1])
            if not (this_time):
                errors = data_read_error(
                        "Poorly formed time value", err_msgs,
                        errs=errors, fname=filename, fline=line_num)
                continue
            # Maybe add to data.bikes_in or data.bikes_out structures.
            if section == BIKE_IN:
                # Maybe add to check_in structure
                if this_tag in data.bikes_in:
                    errors = data_read_error(
                            f"Duplicate {this_tag} check-in", err_msgs,
                            errs=errors, fname=filename, fline=line_num)
                    continue
                if (this_tag in data.bikes_out and
                        data.bikes_out[this_tag] < this_time):
                    errors = data_read_error(
                            f"Tag {this_tag} check out before check-in",
                            err_msgs, errs=errors,
                            fname=filename, fline=line_num)
                    continue
                data.bikes_in[this_tag] = this_time
            elif section == BIKE_OUT:
                if this_tag in data.bikes_out:
                    errors = data_read_error(
                            f"Duplicate {this_tag} check-out", err_msgs,
                            errs=errors, fname=filename, fline=line_num)
                    continue
                if this_tag not in data.bikes_in:
                    errors = data_read_error(
                            f"Tag {this_tag} checked out but not in",
                            err_msgs, errs=errors,
                            fname=filename, fline=line_num)
                    continue
                if (this_tag in data.bikes_in
                        and data.bikes_in[this_tag] > this_time):
                    errors = data_read_error(
                            f"Tag {this_tag} check out before check-in",
                            err_msgs, errs=errors,
                            fname=filename, fline=line_num)
                    continue
                data.bikes_out[this_tag] = this_time
            else:
                squawk("PROGRAM ERROR: should not reach this code spot")
                errors += 1
                continue
    if errors:
        err_msgs.append(f"Found {errors} errors in datafile {filename}")
    # Return today's working data.
    return data

def write_datafile(filename:str, data:TrackerDay, header_lines:list=None
            ) -> None:
    """Write current data to today's data file."""
    lines = []
    if header_lines:
        lines = header_lines
    else:
        lines.append("# TagTracker datafile (data file) created on "
                f"{get_date()} {get_time()}")
    # Valet data, opening & closing hours
    if data.date:
        lines.append(f"Valet date: {data.date}")
    if data.opening_time:
        lines.append(f"Valet opens: {data.opening_time}")
    if data.closing_time:
        lines.append(f"Valet closes: {data.closing_time}")

    lines.append("Bikes checked in / tags out:")
    for tag, atime in data.bikes_in.items(): # for each bike checked in
        lines.append(f"{tag.lower()},{atime}") # add a line "tag,time"
    lines.append("Bikes checked out / tags in:")
    for tag,atime in data.bikes_out.items(): # for each  checked
        lines.append(f"{tag.lower()},{atime}") # add a line "tag,time"
    # Also write tag info of which bikes are oversize, which are regular.
    # This is for datafile aggregator.
    lines.append( "# The following sections are for datafile aggregator")
    lines.append("Regular-bike tags:")
    for tag in data.regular:
        lines.append(tag.lower())
    lines.append("Oversize-bike tags:")
    for tag in data.oversize:
        lines.append(tag.lower())
    lines.append("# Normal end of file")
    # Write the data to the file.
    with open(filename, 'w',encoding='utf-8') as f: # write stored lines to file
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
                if not PARSE_TAG_RE.match(word.lower()):
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
# Date re checks for date that might be in another string
_DATE_RE = r"(2[0-9][0-9][0-9])[/-]([01]?[0-9])[/-]([0123]?[0-9])"
# Match a date within another string
DATE_PART_RE = re.compile(r"(\b|[^a-zA-Z0-9])" + _DATE_RE + r"\b")
# Match a date as the whole string
DATE_FULL_RE = re.compile(r"^ *" + _DATE_RE + " *$")

