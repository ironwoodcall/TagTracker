"""TagTracker by Julias Hocking.

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
import sys
import time
from datetime import datetime
import re
import pathlib
import statistics
from typing import Union    # This is for type hints instead of (eg) int|str
import TrackerConfig as cfg

def get_date() -> str:
    """Return current date as string: YYYY-MM-DD."""
    return datetime.today().strftime("%Y-%m-%d")

def get_time() -> str:
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
    print(text_style(f"PROGRAM ERROR: called time_int({maybe_time=})",
            style=cfg.ERROR_STYLE))
    return None

def time_str(maybe_time:Union[int,str,float,None]) -> str:
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
        print(text_style(f"PROGRAM ERROR: called time_str({maybe_time=})",
                style=cfg.ERROR_STYLE))
        return ""
    elif isinstance(maybe_time,int):
        # Test for impossible time.
        if not (0 <= maybe_time <= 1440):
            return ""
        h = maybe_time // 60
        m = maybe_time % 60
    # Return 5-digit time string
    return f"{h:02d}:{m:02d}"

def pretty_time(time:Union[int,str,float], trim:bool=False ) -> str:
    """Replace lead 0 in HH:MM with blank (or remove, if 'trim' )."""
    time = time_str(time)
    if not time:
        return ""
    replace_with = "" if trim else " "
    if time[0] == "0":
        time = f"{replace_with}{time[1:]}"
    return time

def parse_tag(maybe_tag:str, must_be_available=False) -> list[str]:
    """Test maybe_tag as a tag, return it as tag and bits.

    Tests maybe_tag by breaking it down into its constituent parts.
    If looks like a valid tagname, returns a list of
        [tag_id, colour, tag_letter, tag_number]
    If tag is not valid, then the return list is empty []

    If must_be_available flag is True then will check whether this
    tag is in the list of all available tags (all_tags), and if
    not in the list, will return the empty list.

    Canonical tag id is a concatenation of
        tag_colour: 1+ lc letters representing the tag's colour,
                as defined in cfg.colour_letters
        tag_letter: 1 lc letter, the first character on the tag
        tag_number: a sequence number, without lead zeroes.
    """
    maybe_tag = maybe_tag.lower()
    r = cfg.PARSE_TAG_RE.match(maybe_tag)
    if not bool(r):
        return []

    tag_colour = r.group(1)
    tag_letter = r.group(2)
    tag_number = r.group(3)
    tag_id = f"{tag_colour}{tag_letter}{tag_number}"

    if must_be_available and tag_id not in cfg.all_tags:
        return []

    return [tag_id,tag_colour,tag_letter,tag_number]

def fix_tag(maybe_tag:str, **kwargs) -> str:
    """Turn 'str' into a canonical tag name.

    Keyword must_be_available, if set True, will force
    this to only allow tags that are set as usable in config files.
    """
    bits = parse_tag(maybe_tag,
            must_be_available=kwargs.get("must_be_available"))
    return bits[0] if bits else ""

def sort_tags( unsorted:list[str]) -> list[str]:
    """Sorts a list of tags (smart eg about wa12 > wa7)."""
    newlist = []
    for tag in unsorted:
        bits = parse_tag(tag,must_be_available=False)
        newlist.append(f"{bits[1]}{bits[2]}{int(bits[3]):04d}")
    newlist.sort()
    newlist = [fix_tag(t) for t in newlist]
    return newlist

def text_style(text:str, style=None) -> str:
    """Return text with style 'style' applied."""
    if not cfg.USE_COLOUR:
        return text
    if not style:
        style = cfg.NORMAL_STYLE
    if style not in cfg.STYLE:
        iprint(f"*** PROGRAM ERROR: Unknown style '{style}' ***",
               style=cfg.ERROR_STYLE)
        return "!!!???"
    return f"{cfg.STYLE[style]}{text}{cfg.STYLE[cfg.RESET_STYLE]}"

def iprint(text:str="", num_indents:int=1, style=None,end="\n") -> None:
    """Print the text, indented num_indents times.

    Recognizes the 'end=' keyword for the print() statement.
    """
    if style:
        text = text_style(text,style=style)
    print(f"{cfg.INDENT * num_indents}{text}",end=end)

def future_warning(when:str="") -> None:
    """Give a reminder that requested report time is in the future.

    If called with when same as current time or in the past, does nothing.
    """
    if when:
        rightnow = get_time()
        if rightnow >= when:
            return
        msg = ("(Reporting a time "
                f"{pretty_time(time_int(when)-time_int(rightnow),trim=True)}"
                "h later than now)")
    else:
        msg = "(Reporting a time in the future)"
    iprint(msg,style=cfg.HIGHLIGHT_STYLE)

def earliest_event() -> str:
    """Return the earliest event of the day as HH:MM (or "" if none)."""
        # Find earliest and latest block of the day
    all_events = list(check_ins.keys()) + list(check_outs.keys())
    if not all_events:
        return ""
    return min(all_events)

def latest_event( as_of_when:Union[str,int,None]=None ) -> str:
    """Return the latest event of the day at or before as_of_when.

    If no events in the time period, return "".
    If as_of_when is blank or None, then this will use the whole day.
    FIXME: check that this is the right choice. Would it be better to
    go only up to the current moment?
    """
    if not as_of_when:
        as_of_when = "24:00"
    else:
        as_of_when = time_str(as_of_when)
        if not (as_of_when):
            return ""

    events = [x for x in
            (list(check_ins.values()) + list(check_outs.values()))
            if x <= as_of_when]
    # Anything?
    if not events:
        return ""
    # Find earliest and latest block of the day
    latest = max(events)
    return latest

def read_tags() -> bool:
    """Fetch tag data from file.

    Read data from a pre-existing log file, if one exists
    check for .txt file for today's date in folder called 'logs'
    e.g. "logs/2023-04-20.txt"
    if exists, read for ins and outs
    if none exists, who cares -- one will get made.
    """
    logfilename = LOG_FILEPATH
    pathlib.Path("logs").mkdir(exist_ok = True) # make logs folder if missing
    if not os.path.exists(logfilename):
        iprint('No existing log for today found. Creating new log.',
               style=cfg.SUBTITLE_STYLE)
        return True
    iprint(f"Loading data from existing log file {logfilename}...",
           style=cfg.SUBTITLE_STYLE)
    errors = 0  # How many errors found reading logfile?
    section = None
    with open(logfilename, 'r') as f:
        for line_num, line in enumerate(f, start=1):
            # ignore blank or # comment lines
            line = re.sub(r"\s*#.*","", line)
            line = line.strip()
            if not line:
                continue
            # Look for section headers
            if (re.match(r"^Bikes checked in.*:",line)):
                section = cfg.BIKE_IN
                continue
            elif (re.match(r"^Bikes checked out.*:", line)):
                section = cfg.BIKE_OUT
                continue
            # Look for headers for oversize & regular bikes, ignore them.
            elif (re.match(r"^Regular-bike tags.*:",line)):
                section = cfg.IGNORE
                continue
            elif (re.match(r"^Oversize-bike tags.*:",line)):
                section = cfg.IGNORE
                continue
            # Can do nothing unless we know what section we're in
            if section is None:
                iprint(f"weirdness in line {line_num} of {logfilename}",
                       style=cfg.ERROR_STYLE)
                errors += 1
                continue
            if section == cfg.IGNORE:
                # Things to ignore
                continue
            # Break into putative tag and text, looking for errors
            cells = line.split(',')
            if len(cells) != 2:
                iprint(f"Bad line in file {logfilename} line {line_num}",
                       style=cfg.ERROR_STYLE)
                errors += 1
                continue
            this_tag = fix_tag(cells[0],must_be_available=False)
            if not (this_tag):
                iprint("String does not appear to ba a tag (file"
                        f" {logfilename} line {line_num})",
                        style=cfg.ERROR_STYLE)
                errors += 1
                continue
            if this_tag not in cfg.all_tags:
                iprint(f"Tag '{this_tag}' not in use (file"
                        f" {logfilename} line {line_num})",
                        style=cfg.ERROR_STYLE)
                errors += 1
                continue
            this_time = time_str(cells[1])
            if not (this_time):
                iprint("Time value poorly formed in file"
                        f" {logfilename} line {line_num}",
                        style=cfg.ERROR_STYLE)
                errors += 1
                continue
            # Maybe add to check_ins or check_outs structures.
            if section == cfg.BIKE_IN:
                # Maybe add to check_in structure
                if this_tag in check_ins:
                    iprint(f"Duplicate {this_tag} check-in found at "
                            f"line {line_num}",
                            style=cfg.ERROR_STYLE)
                    errors += 1
                    continue
                if this_tag in check_outs and check_outs[this_tag] < this_time:
                    iprint(f"Tag {this_tag} check out before check-in"
                            f" in file {logfilename}",
                            style=cfg.ERROR_STYLE)
                    errors += 1
                    continue
                check_ins[this_tag] = this_time
            elif section == cfg.BIKE_OUT:
                if this_tag in check_outs:
                    iprint(f"Duplicate {this_tag} check-out found at "
                            f"line {line_num}",
                            style=cfg.ERROR_STYLE)
                    errors += 1
                    continue
                if this_tag in check_ins and check_ins[this_tag] > this_time:
                    iprint(f"Tag {this_tag} check out before check-in"
                            f" in file {logfilename}",
                            style=cfg.ERROR_STYLE)
                    errors += 1
                    continue
                check_outs[this_tag] = this_time
            else:
                iprint("PROGRAM ERROR: should not reach this code spot 876246",
                       style=cfg.ERROR_STYLE)
                errors += 1
                continue

    if errors:
        iprint(f"Found {errors} errors in logfile {logfilename}",
               style=cfg.ERROR_STYLE)
    else:
        iprint('Existing log for today successfully loaded',
               style=cfg.SUBTITLE_STYLE)
    return not bool(errors)

def rotate_log() -> None:
    """Rename the current log to <itself>.bak."""
    backuppath = f"{LOG_FILEPATH}.bak"
    if os.path.exists(backuppath):
        os.unlink(backuppath)
    if os.path.exists(LOG_FILEPATH):
        os.rename(LOG_FILEPATH,backuppath)
    return None

def write_tags() -> None:
    """Write current data to today's log file."""
    lines = []
    lines.append("# TagTracker logfile (data file) created on "
            f"{get_date()} {get_time()}")
    lines.append("Bikes checked in / tags out:")
    for tag, time in check_ins.items(): # for each bike checked in
        lines.append(f"{tag},{time}") # add a line "tag,time"
    lines.append("Bikes checked out / tags in:")
    for tag,time in check_outs.items(): # for each  checked
        lines.append(f"{tag},{time}") # add a line "tag,time"
    # Also write tag info of which bikes are oversize, which are regular.
    # This is for logfile aggregator.
    lines.append( "# The following sections are for logfile aggregator")
    lines.append("Regular-bike tags:")
    for tag in cfg.normal_tags:
        lines.append(tag)
    lines.append("Oversize-bike tags:")
    for tag in cfg.oversize_tags:
        lines.append(tag)
    lines.append(f"# Normal end of file")
    # Write the data to the file.
    with open(LOG_FILEPATH, 'w') as f: # write stored lines to file
        for line in lines:
            f.write(line)
            f.write("\n")

class Visit():
    def __init__(self, tag:str) -> None:
        self.tag = tag      # canonical
        self.time_in = ""   # HH:MM
        self.time_out = ""  # HH:MM
        self.duration = 0   # minutes
        self.type = None    # cfg.REGULAR, cfg.OVERSIZE
        self.still_here = None  # True or False

def calc_visits( as_of_when:Union[int,str]=None ) -> dict[str:Visit]:
    """Create a dict of visits keyed by tag as of as_of_when.

    If as_of_when is not given, then this will choose the latest
    check-out time of the day as its time.

    As a special case, this will also accept the word "now" to
    mean the current time.
    """
    if isinstance(as_of_when,str) and as_of_when.lower() == "now":
        as_of_when = get_time()
    elif as_of_when is None:
        # Set as_of_when to be the time of the latest checkout of the day.
        if check_ins:
            as_of_when = min(list(check_ins.values()))
        else:
            as_of_when = get_time()
    as_of_when = time_str(as_of_when)
    visits = {}
    for tag,time_in in check_ins.items():
        if time_in > as_of_when:
            continue
        this_visit = Visit(tag)
        this_visit.time_in = time_in
        if tag in check_outs and check_outs[tag] <= as_of_when:
            this_visit.time_out = check_outs[tag]
            this_visit.still_here = False
        else:
            this_visit.time_out = as_of_when
            this_visit.still_here = False
        this_visit.duration = max(1,
                (time_int(this_visit.time_out) -
                time_int(this_visit.time_in)))
        if tag in cfg.normal_tags:
            this_visit.type = cfg.REGULAR
        else:
            this_visit.type = cfg.OVERSIZE
        visits[tag] = this_visit
    return visits

class Event():
    """What happened at each discrete time of day (that something happened)."""

    def __init__(self, time:str ) -> None:
        self.num_here_total = None  # will be int
        self.num_here_regular = None
        self.num_here_oversize = None
        self.bikes_in = []   # List of canonical tag ids.
        self.bikes_out = []
        self.num_ins = 0     # This is just len(self.bikes_in).
        self.num_outs = 0    # This is just len(self.bikes_out).

def calc_events(as_of_when:Union[int,str]=None ) -> dict[str:Event]:
    """Create a dict of events keyed by HH:MM time.

    If as_of_when is not given, then this will choose the latest
    check-out time of the day as its time.

    As a special case, this will also accept the word "now" to
    mean the current time.
    """
    if isinstance(as_of_when,str) and as_of_when.lower() == "now":
        as_of_when = get_time()
    elif as_of_when is None:
        # Set as_of_when to be the time of the latest checkout of the day.
        if check_ins:
            as_of_when = min(list(check_ins.values()))
        else:
            as_of_when = get_time()
    as_of_when = time_str(as_of_when)
    # First pass, create all the Events and list their tags in & out.
    events = {}
    for tag,time in check_ins.items():
        if time > as_of_when:
            continue
        if time not in events:
            events[time] = Event(time)
        events[time].bikes_in.append(tag)
    for tag,time in check_outs.items():
        if time > as_of_when:
            continue
        if time not in events:
            events[time] = Event(time)
        events[time].bikes_out.append(tag)
    # Second pass, calculate other attributes of Events.
    num_regular = 0     # Running balance of regular & oversize bikes.
    num_oversize = 0
    for time in sorted(events.keys()):
        vx = events[time]
        vx.num_ins = len(vx.bikes_in)
        vx.num_outs = len(vx.bikes_out)
        # How many regular & oversize bikes have we added or lost?
        diff_normal = (
            len([x for x in vx.bikes_in if x in cfg.normal_tags]) -
            len([x for x in vx.bikes_out if x in cfg.normal_tags]))
        diff_oversize = (
            len([x for x in vx.bikes_in if x in cfg.oversize_tags]) -
            len([x for x in vx.bikes_out if x in cfg.oversize_tags]))
        num_regular += diff_normal
        num_oversize += diff_oversize
        vx.num_here_regular = num_regular
        vx.num_here_oversize = num_oversize
        vx.num_here_total = num_regular + num_oversize
        vx.num_ins = len(vx.bikes_in)
        vx.num_outs = len(vx.bikes_out)
    return events

def bike_check_ins_report( as_of_when:str ) -> None:
    """Print the check-ins count part of the summary statistics.

    as_of_when is HH:MM time, assumed to be a correct time.
    """
    # Find the subset of check-ins at or before our cutoff time.
    these_check_ins = {}
    for tag,time in check_ins.items():
        if time <= as_of_when:
            these_check_ins[tag] = time
    # Summary stats
    num_still_here = len(set(these_check_ins.keys()) -
        set([x for x in check_outs if check_outs[x] <= as_of_when]))
    num_bikes_ttl = len(these_check_ins)
    these_checkins_am = [x for x in these_check_ins if these_check_ins[x] < "12:00"]
    num_bikes_am = len(these_checkins_am)
    num_bikes_regular = len(
            [x for x in these_check_ins if x in cfg.normal_tags])
    num_bikes_oversize = len(
            [x for x in these_check_ins if x in cfg.oversize_tags])

    print()
    iprint("Bike check-ins",style=cfg.SUBTITLE_STYLE)
    iprint(f"Total bikes in:   {num_bikes_ttl:4d}")
    iprint(f"AM bikes in:      {num_bikes_am:4d}")
    iprint(f"PM bikes in:      {(num_bikes_ttl - num_bikes_am):4d}")
    iprint(f"Regular in:       {num_bikes_regular:4d}")
    iprint(f"Oversize in:      {num_bikes_oversize:4d}")
    iprint(f"Bikes still here: {num_still_here:4d}")

def visit_lengths_by_category_report(visits:dict) -> None:
    """Report number of visits in different length categories."""

    def one_range(lower:float=None, upper:float=None) -> None:
        """Calculate and print visits in range lower:upper.

        If lower is missing, uses anything below upper
        If upper is missing, uses anything above lower
        """
        noun = cfg.VISIT_NOUN.title()
        if not lower and not upper:
            iprint(f"PROGRAM ERROR: called one_range(lower='{lower}',"
                   f"upper='{upper}')",style=cfg.ERROR_STYLE)
            return None
        if not lower:
            header = f"{noun}s < {upper:3.1f}h:"
            lower = 0
        elif not upper:
            header = f"{noun}s >= {lower:3.1f}h:"
            upper = 999
        else:
            header = f"{noun}s {lower:3.1f}-{upper:3.1f}h:"
        # Count visits in this time range.
        num = 0
        for v in visits.values():
            if v.duration >= lower*60 and v.duration < upper*60:
                num += 1
        iprint(f"{header:18s}{num:4d}")

    print()
    iprint(f"Number of {cfg.VISIT_NOUN.lower()}s by duration",
           style=cfg.SUBTITLE_STYLE)
    prev_boundary = None
    for boundary in cfg.VISIT_CATEGORIES:
        one_range(lower=prev_boundary,upper=boundary)
        prev_boundary = boundary
    one_range(lower=prev_boundary,upper=None)

def visit_statistics_report(visits:dict) -> None:
    """Max, min, mean, median, mode of visits."""
    noun = cfg.VISIT_NOUN.lower()

    def one_line( key:str, value:str ) -> None:
        """Print one line."""
        iprint(f"{key:17s}{value}", style=cfg.NORMAL_STYLE)

    def visits_mode(durations_list:list[int]) -> None:
        """Prints the mode info."""
        # Find the mode value(s), with visit durations rounded
        # to nearest ROUND_TO_NEAREST time.

        rounded = [round(x/cfg.MODE_ROUND_TO_NEAREST)*cfg.MODE_ROUND_TO_NEAREST
                for x in durations_list]
        modes_str = ",".join([pretty_time(x) for x in statistics.multimode( rounded )])
        modes_str = (f"{modes_str}  (times "
                f"rounded to {cfg.MODE_ROUND_TO_NEAREST} minutes)")
        one_line(f"Mode {cfg.VISIT_NOUN}:", modes_str)

    # Make a dict of stay-lengths with list tags (for longest/shortest).
    duration_tags = {}
    for tag,v in visits.items():
        dur = v.duration
        if dur not in duration_tags:
            duration_tags[dur] = []
        duration_tags[dur].append(tag)
    if not duration_tags:
        return  # No durations
    print()
    iprint(f"{cfg.VISIT_NOUN.title()} length statistics",
           style=cfg.SUBTITLE_STYLE)
    longest = max(list(duration_tags.keys()))
    long_tags = ",".join(duration_tags[longest])
    one_line(f"Longest {noun}:", f"{pretty_time((longest))}  (tag(s): {long_tags})")
    shortest = min(list(duration_tags.keys()))
    short_tags = ",".join(duration_tags[shortest])
    one_line(f"Shortest {noun}:", f"{pretty_time((shortest))}  (tag(s): {short_tags})")
    # Make a list of stay-lengths (for mean, median, mode)
    durations_list = [x.duration for x in visits.values()]
    one_line( f"Mean {noun}:", pretty_time(statistics.mean(durations_list)))
    one_line( f"Median {noun}:", pretty_time(statistics.median(list(duration_tags.keys()))))
    visits_mode(durations_list)


def highwater_report(events:dict) -> None:
    """Make a highwater table as at as_of_when"""
    # High-water mark for bikes in valet at any one time
    def one_line( header:str, events:dict, time:str, highlight_field:int ) -> None:
        """Print one line for highwater_report."""
        values = [events[time].num_here_regular,
                  events[time].num_here_oversize,
                  events[time].num_here_total]
        line = f"{header:15s}"
        for num,val in enumerate(values):
            bit = f"{val:3d}"
            if num == highlight_field:
                bit = text_style(bit,style=cfg.HIGHLIGHT_STYLE)
            line = f"{line}   {bit}"
        iprint(f"{line}    {time}")
    # Table header
    print()
    iprint("Most bikes at valet at any one time", style=cfg.SUBTITLE_STYLE)
    if not events:
        iprint("(No bikes)")
        return
    # Find maximum bikes on hand for the categories
    max_regular_num = max([x.num_here_regular for x in events.values()])
    max_oversize_num = max([x.num_here_oversize for x in events.values()])
    max_total_num = max([x.num_here_total for x in events.values()])
    max_regular_time = None
    max_oversize_time = None
    max_total_time = None
    # Find the first time at which these took place
    for time in sorted(events.keys()):
        if (events[time].num_here_regular >= max_regular_num
                and not max_regular_time):
            max_regular_time = time
        if (events[time].num_here_oversize >= max_oversize_num
                and not max_oversize_time):
            max_oversize_time = time
        if (events[time].num_here_total >= max_total_num
                and not max_total_time):
            max_total_time = time
    iprint("                 Reglr OvrSz Total WhenAchieved")
    one_line("Most regular:", events, max_regular_time, 0)
    one_line("Most oversize:", events, max_oversize_time, 1)
    one_line("Most combined:", events, max_total_time, 2)

def busy_report(events:dict[str:Event], as_of_when) -> None:
    """Report the busiest time(s) of day."""
    def one_line(rank:int, num_events:int, times:list[str]) -> None:
        """Format and print one line of busyness report."""
        iprint(f"{rank:2d}     {num_events:3d}      ",end="")
        for time_num,start_time in enumerate(sorted(times),start=1):
            end_time=time_str(time_int(start_time)+cfg.BLOCK_DURATION)
            print(f"{pretty_time(start_time,trim=True)}-"
                  f"{pretty_time(end_time,trim=True)}", end="")
            if time_num < len(times):
                print(", ",end="")
        print()

    # Make an empty dict of busyness of timeblocks.
    blocks = dict(zip(
        Block.timeblock_list(as_of_when),
        [0 for _ in range(0,100)]))
    # Count actions in each timeblock
    for time, ev in events.items():
        start = Block.block_start(time) # Which block?
        blocks[start] = ev.num_ins + ev.num_outs
    # Make a dict of busynesses with list of timeblocks for each.
    busy_times = {}
    for time, activity in blocks.items():
        if activity not in busy_times:
            busy_times[activity] = []
        busy_times[activity].append(time)
    # Report the results.
    print()
    iprint("Busiest times of day",style=cfg.SUBTITLE_STYLE)
    iprint("Rank  Ins&Outs  When")
    for rank, activity in enumerate(sorted(busy_times.keys(),reverse=True), start=1):
        if rank > cfg.BUSIEST_RANKS:
            break
        one_line(rank, activity, busy_times[activity])

def qstack_report( visits:dict[str:Visit] ) -> None:
    """Report whether visits are more queue-like or more stack-like."""
    # Make a list of tuples: start_time, end_time for all visits.
    visit_times = list(zip( [vis.time_in for vis in visits.values()],
        [vis.time_out for vis in visits.values()]))
    ##print(text_style(f"DEBUG:{list(visit_times)=}",style=cfg.WARNING_STYLE))
    queueish = 0
    stackish = 0
    neutralish = 0
    visit_compares = 0

    for (time_in,time_out) in visit_times:
        earlier_visits = [(tin,tout) for (tin,tout) in visit_times
                if tin < time_in and tout > time_in]
        visit_compares += len(earlier_visits)
        for earlier_out in [v[1] for v in earlier_visits]:
            if earlier_out < time_out:
                queueish += 1
            elif earlier_out > time_out:
                stackish += 1
            else:
                neutralish += 1

    print("")
    iprint(f"Were today's {cfg.VISIT_NOUN.lower()}s "
           "more queue-like or stack-like?", style=cfg.SUBTITLE_STYLE)
    if not queueish and not stackish:
        iprint("Unable to determine.")
        return
    queue_proportion = queueish / (queueish + stackish + neutralish)
    stack_proportion = stackish / (queueish + stackish + neutralish)
    iprint(f"Based on {visit_compares} compares of {len(visits)} "
           f"{cfg.VISIT_NOUN.lower()}s, today's {cfg.VISIT_NOUN.lower()}s are:")
    iprint(f"{round(queue_proportion*100):3d}% queue-like (overlapping)",num_indents=2)
    iprint(f"{round(stack_proportion*100):3d}% stack-like (nested)",num_indents=2)
    iprint(f"{round((1 - stack_proportion - queue_proportion)*100):3d}% neither",num_indents=2)

def day_end_report( args:list ) -> None:
    """Reports summary statistics about visits, up to the given time.

    If not time given, calculates as of latest checkin/out of the day.
    """
    rightnow = get_time()
    as_of_when = (args + [None])[0]
    if not as_of_when:
        as_of_when = rightnow
    else:
        as_of_when = time_str(as_of_when)
        if not (as_of_when):
            iprint(f"Unrecognized time passed to visits summary ({args[0]})",
                style=cfg.WARNING_STYLE)
            return
    print()
    iprint(f"Summary statistics as at {as_of_when}",style=cfg.TITLE_STYLE)
    if as_of_when > rightnow:
        future_warning(as_of_when)
    if not latest_event(as_of_when):
        iprint(f"No bikes checked in by {as_of_when}",
               style=cfg.SUBTITLE_STYLE)
        return
    # Bikes in, in various categories.
    bike_check_ins_report(as_of_when)
    # Stats that use visits (stays)
    visits = calc_visits(as_of_when)
    visit_lengths_by_category_report(visits)
    visit_statistics_report(visits)

def more_stats_report( args:list ) -> None:
    """Reports more summary statistics about visits, up to the given time.

    If not time given, calculates as of latest checkin/out of the day.
    """
    rightnow = get_time()
    as_of_when = (args + [None])[0]
    if not as_of_when:
        as_of_when = rightnow
    else:
        as_of_when = time_str(as_of_when)
        if not (as_of_when):
            iprint(f"Unrecognized time passed to visits summary ({args[0]})",
                style=cfg.WARNING_STYLE)
            return
    print()
    iprint(f"More summary statistics as at {as_of_when}",style=cfg.TITLE_STYLE)
    if as_of_when > rightnow:
        future_warning(as_of_when)
    if not latest_event(as_of_when):
        iprint(f"No bikes checked in by {as_of_when}",
               style=cfg.SUBTITLE_STYLE)
        return
    # Stats that use visits (stays)
    visits = calc_visits(as_of_when)
    # Dict of time (events)
    events = calc_events(as_of_when)
    highwater_report( events )
    # Busiest times of day
    busy_report(events,as_of_when)
    # Queue-like vs stack-like
    qstack_report(visits)

def find_tag_durations(include_bikes_on_hand=True) -> dict[str,int]:
    """Make dict of tags with their stay duration in minutes.

    If include_bikes_on_hand, this will include checked in
    but not returned out.  If False, only bikes returned out.
    """
    timenow = time_int(get_time())
    tag_durations = {}
    for tag,in_str in check_ins.items():
        in_minutes = time_int(in_str)
        if tag in check_outs:
            out_minutes = time_int(check_outs[tag])
            tag_durations[tag] = out_minutes-in_minutes
        elif include_bikes_on_hand:
            tag_durations[tag] = timenow - in_minutes
    # Any bike stays that are zero minutes, arbitrarily call one minute.
    for tag,duration in tag_durations.items():
        if duration < 1:
            tag_durations[tag] = 1
    return tag_durations

def delete_entry(args:list[str]) -> None:
    """Perform tag entry deletion dialogue."""
    (target,which_to_del,confirm) = (args + [None,None,None])[:3]
    if target:
        target = fix_tag(target,must_be_available=False)
    if not target:
        target = False
    del_syntax_message = text_style("Syntax: d <tag> <both or check-out only"
            " (b/o)> <optional pre-confirm (y)>",style=cfg.SUBPROMPT_STYLE)
    if not(target in [False] + cfg.all_tags or which_to_del in [False,'b','o']
           or confirm in [False, 'y']):
        iprint(del_syntax_message) # remind of syntax if invalid input
        return None # interrupt
    if not target: # get target if unspecified
        iprint("Which tag's entry would you like to remove? "
               f"(tag name) {cfg.CURSOR}",
               style=cfg.SUBPROMPT_STYLE,end="")
        target = input().lower()
    checked_in = target in check_ins
    checked_out = target in check_outs
    if not checked_in and not checked_out:
        iprint(f"'{target}' isn't in today's records (delete cancelled)",
               style=cfg.WARNING_STYLE)
    elif checked_out: # both events recorded
        time_in_temp = check_ins[target]
        time_out_temp = check_outs[target]
        if not which_to_del: # ask which to del if not specified
            iprint(f"This tag has both a check-in ({time_in_temp}) and "
                   f"a check-out ({time_out_temp}) recorded.",
                   style=cfg.SUBPROMPT_STYLE)
            iprint("Do you want to delete (b)oth events, "
                   "for just the check-(o)ut?  (b/o) {cfg.CURSOR}",
                   style=cfg.SUBPROMPT_STYLE,end="")
            which_to_del = input().lower()
        if which_to_del == 'b':
            if confirm == 'y': # pre-confirmation
                sure = True
            else:
                iprint("Are you sure you want to delete both events "
                       f"for {target}? (y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                sure = input().lower() == 'y'
            if sure:
                check_ins.pop(target)
                check_outs.pop(target)
                iprint(f"Deleted {target} from today's records "
                       f"(was in at {time_in_temp}, out at {time_out_temp})",
                       style=cfg.ANSWER_STYLE)
            else:
                iprint("Delete cancelled",style=cfg.WARNING_STYLE)

        elif which_to_del == 'o': # selected to delete
            if confirm == 'y':
                sure = True
            else:
                iprint("Are you sure you want to delete the "
                       f"check-out record for {target}? (y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="" )
                sure = input().lower() == 'y'

            if sure:
                time_temp = check_outs[target]
                check_outs.pop(target)
                iprint(f"Deleted today's {time_temp} check-out for {target}",
                       style=cfg.ANSWER_STYLE)
            else:
                iprint("Delete cancelled",style=cfg.WARNING_STYLE)
        else:
            iprint("Delete cancelled",style=cfg.WARNING_STYLE)
    else: # checked in only
        time_in_temp = check_ins[target]
        if which_to_del in ['b', False]:
            if confirm == 'y':
                sure = True
            else: # check
                iprint("This tag has only a check-in recorded. "
                       f"Are you sure you want to delete it? (y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                sure = input().lower() == 'y'
            if sure:
                time_temp = check_ins[target]
                check_ins.pop(target)
                iprint(f"Deleted {time_temp} check-in for {target}",
                       style=cfg.ANSWER_STYLE)
            else:
                iprint("Delete cancelled",style=cfg.WARNING_STYLE)
        else:#  which_to_del == 'o':
            iprint(f"{target} has only a check-in ({time_in_temp}) recorded; "
                   "can't delete a nonexistent check-out",
                   style=cfg.WARNING_STYLE)

def query_tag(args:list[str]) -> None:
    """Query the check in/out times of a specific tag."""
    target = (args + [None])[0]
    if not target: # only do dialog if no target passed
        iprint(f"Which tag would you like to query? (tag name) {cfg.CURSOR}",
               style=cfg.SUBPROMPT_STYLE, end="")
        target = input().lower()
    fixed_target = fix_tag(target,must_be_available=True)
    print()
    if not fixed_target:
        iprint(f"Tag {target} is not available (retired, does not exist, etc)",
               style=cfg.WARNING_STYLE)
        return
    elif fixed_target not in check_ins:
        iprint(f"Tag '{fixed_target}' not used yet today",
               style=cfg.WARNING_STYLE)
        return
    iprint(f"{check_ins[fixed_target]}  {fixed_target} checked  IN",
           style=cfg.ANSWER_STYLE)
    if fixed_target in check_outs:
        iprint(f"{check_outs[fixed_target]}  {fixed_target} returned OUT",
               style=cfg.ANSWER_STYLE)
    else:
        iprint(f"(now)  {target} still at valet", style=cfg.ANSWER_STYLE)

def prompt_for_time(inp = False) -> bool or str:
    """Prompt for a time input if needed.

    Helper for edit_entry(); if no time passed in, get a valid
    24h time input from the user and return an HH:MM string.
    """
    if not inp:
        iprint("What is the correct time for this event? "
               f"(HHMM or 'now') {cfg.CURSOR}",
               style=cfg.SUBPROMPT_STYLE, end="")
        #iprint("Use 24-hour format, or 'now' to use "
        #       f"the current time ({get_time()}) ",end="")
        inp = input()
    if inp.lower() == 'now':
        return get_time()
    hhmm = time_str(inp)
    if not hhmm:
        return False
    return hhmm

def edit_entry(args:list[str]):
    """Perform Dialog to correct a tag's check in/out time."""
    (target, in_or_out, new_time) = (args + [None,None,None])[:3]

    edit_syntax_message = text_style("Syntax: e <bike's tag> <in or out (i/o)> "
            "<new time or 'now'>",cfg.WARNING_STYLE)
    if not target:
        iprint(f"Which bike's record do you want to edit? (tag ID) {cfg.CURSOR}",
               style=cfg.SUBPROMPT_STYLE, end="")
        target = input().lower()
    elif not target in cfg.all_tags:
        iprint(edit_syntax_message)
        return False
    if target in cfg.all_tags:
        if target in check_ins:
            if not in_or_out:
                iprint("Do you want to change this bike's "
                       f"check-(i)n or check-(o)ut time? (i/o) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                in_or_out = input().lower()
                if not in_or_out in ['i','o']:
                    iprint(f"'{in_or_out}' needs to be 'i' or 'o' "
                           "(edit cancelled)", style=cfg.WARNING_STYLE)
                    return False
            if not in_or_out in ['i','o']:
                iprint(edit_syntax_message)
            else:
                new_time = prompt_for_time(new_time)
                if not new_time:
                    iprint('Invalid time entered (edit cancelled)',
                           style=cfg.WARNING_STYLE)
                elif in_or_out == 'i':
                    if (target in check_outs and
                            (time_int(new_time) >
                            time_int(check_outs[target]))):
                        iprint("Can't set a check-IN later than a check-OUT;",
                               style=cfg.WARNING_STYLE)
                        iprint(f"{target} was returned OUT at {check_outs[target]}",
                               style=cfg.WARNING_STYLE)
                    else:
                        iprint(f"Check-IN time for {target} "
                               f"set to {new_time}",style=cfg.ANSWER_STYLE)
                        check_ins[target] = new_time
                elif in_or_out == 'o':
                    if (time_int(new_time) <
                            time_int(check_ins[target])):
                        # don't check a tag out earlier than it checked in
                        iprint("Can't set a check-OUT earlier than check-IN;",
                               style=cfg.WARNING_STYLE)
                        iprint(f"{target} was checked IN at {check_ins[target]}",
                               style=cfg.WARNING_STYLE)
                    else:
                        iprint(f"Check-OUT time for {target} "
                               f"set to {new_time}",
                               style=cfg.ANSWER_STYLE)
                        check_outs[target] = new_time
        else:
            iprint(f"{target} isn't in today's records (edit cancelled)",
                   style=cfg.WARNING_STYLE)
    else:
        iprint(f"'{target}' isn't a valid tag (edit cancelled)",
               style=cfg.WARNING_STYLE)

def tags_by_prefix(tags_dict:dict) -> dict:
    """Return a dict of tag prefixes with lists of associated tag numbers."""
    prefixes = {}
    for tag in tags_dict:
        #(prefix,t_number) = cfg.PARSE_TAG_PREFIX_RE.match(tag).groups()
        (t_colour,t_letter,t_number) = parse_tag(tag,must_be_available=False)[1:4]
        prefix = f"{t_colour}{t_letter}"
        if prefix not in prefixes:
            prefixes[prefix] = []
        prefixes[prefix].append(int(t_number))
    for numbers in prefixes.values():
        numbers.sort()
    return prefixes

class Block():
    """Class to help with reporting.

    Each instance is a timeblock of duration cfg.BLOCK_DURATION.
    """

    def __init__(self, start_time:Union[str,int]) -> None:
        """Initialize. Assumes that start_time is valid."""
        if isinstance(start_time,str):
            self.start = time_str(start_time)
        else:
            self.start = time_str(start_time)
        self.ins_list = []      # Tags of bikes that came in.
        self.outs_list = []     # Tags of bikes returned out.
        self.num_ins = 0        # Number of bikes that came in.
        self.num_outs = 0       # Number of bikes that went out.
        self.here_list = []     # Tags of bikes in valet at end of block.
        self.num_here = 0       # Number of bikes in valet at end of block.

    @staticmethod
    def block_start(time:Union[int,str], as_number:bool=False) -> Union[str,int]:
        """Return the start time of the block that contains time 'time'.

        'time' can be minutes since midnight or HHMM.
        Returns HHMM unless as_number is True, in which case returns int.
        """
        # Get time in minutes
        time = time_int(time) if isinstance(time,str) else time
        # which block of time does it fall in?
        block_start_min = (time // cfg.BLOCK_DURATION) * cfg.BLOCK_DURATION
        if as_number:
            return block_start_min
        return time_str(block_start_min)

    @staticmethod
    def block_end(time:Union[int,str], as_number:bool=False) -> Union[str,int]:
        """Return the last minute of the timeblock that contains time 'time'.

        'time' can be minutes since midnight or HHMM.
        Returns HHMM unless as_number is True, in which case returns int.
        """
        # Get block start
        start = Block.block_start(time, as_number=True)
        # Calculate block end
        end = start + cfg.BLOCK_DURATION - 1
        # Return as minutes or HHMM
        if as_number:
            return end
        return time_str(end)

    @staticmethod
    def timeblock_list( as_of_when:str=None ) -> list[str]:
        """Build a list of timeblocks from beg of day until as_of_when.

        Latest block of the day will be the latest timeblock that
        had any transactions at or before as_of_when.
        """
        as_of_when = as_of_when if as_of_when else get_time()
        # Make list of transactions <= as_of_when
        transx = [x for x in
                (list(check_ins.values()) + list(check_outs.values()))
                if x <= as_of_when]
        # Anything?
        if not transx:
            return []
        # Find earliest and latest block of the day
        min_block_min = Block.block_start(min(transx), as_number=True)
        max_block_min = Block.block_start(max(transx), as_number=True)
        # Create list of timeblocks for the the whole day.
        timeblocks = []
        for t in range(min_block_min, max_block_min+cfg.BLOCK_DURATION,
                cfg.BLOCK_DURATION):
            timeblocks.append(time_str(t))
        return timeblocks

    @staticmethod
    def calc_blocks(as_of_when:str=None) -> dict:
        """Create a dictionary of Blocks {start:Block} for whole day."""
        as_of_when = as_of_when if as_of_when else "18:00"
        # Create dict with all the bloctimes as keys (None as values)
        blocktimes = Block.timeblock_list(as_of_when=as_of_when)
        if not blocktimes:
            return {}
        blocks = {}
        for t in Block.timeblock_list(as_of_when=as_of_when):
            blocks[t] = Block(t)
        latest_time = Block.block_end(t,as_number=False)
        for tag, time in check_ins.items():
            if time > latest_time:
                continue
            bstart = Block.block_start(time)
            blocks[bstart].ins_list += [tag]
        for tag, time in check_outs.items():
            if time > latest_time:
                continue
            bstart = Block.block_start(time)
            blocks[bstart].outs_list += [tag]
        here_set = set()
        for btime,blk in blocks.items():
            blk.num_ins = len(blk.ins_list)
            blk.num_outs = len(blk.outs_list)
            here_set = (here_set | set(blk.ins_list)) - set(blk.outs_list)
            blk.here_list = here_set
            blk.num_here = len(here_set)
        return blocks

def lookback(args:list[str]) -> None:
    """Display a look back at recent activity.

    Args are both optional, start_time and end_time.
    If end_time is missing, runs to current time.
    If start_time is missing, starts one hour before end_time.
    """
    def format_one( time:str, tag:str, check_in:bool) -> str:
        """Format one line of output."""
        in_tag = tag if check_in else ""
        out_tag = "" if check_in else tag
        #inout = "bike IN" if check_in else "returned OUT"
        return f"{time}   {in_tag:<5s} {out_tag:<5s}"

    (start_time, end_time) = (args + [None,None])[:2]
    if not end_time:
        end_time = get_time()
    if not start_time:
        start_time = time_str(time_int(end_time)-60)
    start_time = time_str(start_time)
    end_time = time_str(end_time)
    if not start_time or not end_time or start_time > end_time:
        iprint("Can not make sense of the given start/end times",
               style=cfg.WARNING_STYLE)
        return
    # Collect any bike-in/bike-out events that are in the time period.
    events = []
    for tag, time in check_ins.items():
        if start_time <= time <= end_time:
            events.append( format_one(time, tag, True))
    for tag, time in check_outs.items():
        if start_time <= time <= end_time:
            events.append( format_one(time, tag, False))
    # Print
    iprint()
    iprint(f"Log of events from {start_time} to {end_time}:",
            style=cfg.TITLE_STYLE)
    print()
    iprint("Time  BikeIn BikeOut",style=cfg.SUBTITLE_STYLE)
    for line in sorted(events):
        iprint(line)

def dataform_report(args:list[str]) -> None:
    """Print days activity in timeblocks.

    This is to match the (paper/google) data tracking sheets.
    Single args are both optional, end_time.
    If end_time is missing, runs to current time.
    If start_time is missing, starts one hour before end_time.
    """
    end_time = (args + [None])[0]
    if not end_time:
        end_time = get_time()
    end_time = time_str(end_time)
    if not ():
        print()
        iprint(f"Unrecognized time {args[0]}",style=cfg.WARNING_STYLE)
        return

    print()
    iprint(f"Tracking form data from start of day until {end_time}",
           style=cfg.TITLE_STYLE)
    all_blocks = Block.calc_blocks(end_time)
    if not all_blocks:
        earliest = min(list(check_ins.values()) + list(check_outs.values()))
        iprint(f"No bikes came in before {end_time} "
               f"(earliest came in at {earliest})",
               style=cfg.HIGHLIGHT_STYLE)
        return
    for which in [cfg.BIKE_IN,cfg.BIKE_OUT]:
        titlebit = "checked IN" if which == cfg.BIKE_IN else "returned OUT"
        title = f"Bikes {titlebit}:"
        print()
        iprint(title, style=cfg.SUBTITLE_STYLE)
        iprint("-" * len(title), style=cfg.SUBTITLE_STYLE)
        for start,block in all_blocks.items():
            inouts = (block.ins_list if which == cfg.BIKE_IN
                    else block.outs_list)
            endtime = time_str(time_int(start)+cfg.BLOCK_DURATION)
            iprint(f"{start}-{endtime}  {' '.join(sort_tags(inouts))}")

def audit_report(args:list[str]) -> None:
    """Create & display audit report as at a particular time.

    On entry: as_of_when_args is a list that can optionally
    have a first element that's a time at which to make this for.

    This is smart about any checkouts that are alter than as_of_when.
    If as_of_when is missing, then counts as of current time.
    (This is replacement for existing show_audit function.)
    Reads:
        check_ins
        check_outs
        cfg.colour_letters
        cfg.normal_tags
        cfg.oversize_tags
    """
    # FIXME: this is long and could get broken up with helper functions
    rightnow = get_time()
    as_of_when = (args + [rightnow])[0]

    # What time will this audit report reflect?
    as_of_when = time_str(as_of_when)
    if not as_of_when:
        iprint(f"Unrecognized time passed to audit ({args[0]})",
               style=cfg.WARNING_STYLE)
        return False

    # Get rid of any check-ins or -outs later than the requested time.
    # (Yes I know there's a slicker way to do this but this is nice and clear.)
    check_ins_to_now = {}
    for (tag,ctime) in check_ins.items():
        if ctime <= as_of_when:
            check_ins_to_now[tag] = ctime
    check_outs_to_now = {}
    for (tag,ctime) in check_outs.items():
        if ctime <= as_of_when:
            check_outs_to_now[tag] = ctime
    bikes_on_hand = {}
    for (tag,ctime) in check_ins_to_now.items():
        if tag not in check_outs_to_now:
            bikes_on_hand[tag] = ctime

    num_bikes_on_hand = len(bikes_on_hand)
    normal_in = 0
    normal_out = 0
    oversize_in = 0
    oversize_out = 0

    # This assumes that any tag not a normal tag is an oversize tag
    for tag in check_ins_to_now:
        if tag in cfg.normal_tags:
            normal_in += 1
            if tag in check_outs_to_now:
                normal_out += 1
        else:
            oversize_in += 1
            if tag in check_outs_to_now:
                oversize_out += 1
    # Sums
    sum_in = normal_in + oversize_in
    sum_out = normal_out + oversize_out
    sum_total = sum_in - sum_out
    # Tags broken down by prefix (for tags matrix)
    prefixes_on_hand = tags_by_prefix(bikes_on_hand)
    prefixes_returned_out = tags_by_prefix(check_outs_to_now)
    returns_by_colour = {}
    for prefix,numbers in prefixes_returned_out.items():
        colour_code = prefix[:-1]   # prefix without the tag_letter
        if colour_code not in returns_by_colour:
            returns_by_colour[colour_code] = len(numbers)
        else:
            returns_by_colour[colour_code] += len(numbers)

    # Audit report header.
    print()

    iprint(f"Audit report as at {as_of_when}", style=cfg.TITLE_STYLE)
    future_warning(as_of_when)

    # Audit summary section.
    print()
    iprint("Summary             Regular Oversize Total",
           style=cfg.SUBTITLE_STYLE)
    iprint(f"Bikes checked in:     {normal_in:4d}    {oversize_in:4d}"
           f"    {sum_in:4d}")
    iprint(f"Bikes returned out:   {normal_out:4d}    {oversize_out:4d}"
           f"    {sum_out:4d}")
    iprint(f"Bikes in valet:       {(normal_in-normal_out):4d}"
           f"    {(oversize_in-oversize_out):4d}    {sum_total:4d}")
    if (sum_total != num_bikes_on_hand):
        iprint("** Totals mismatch, expected total "
               f"{num_bikes_on_hand} != {sum_total} **",
               style=cfg.ERROR_STYLE)

    # Tags matrixes
    no_item_str = "  "  # what to show when there's no tag
    print()
    # Bikes returned out -- tags matrix.
    iprint(f"Bikes still in valet at {as_of_when}:",style=cfg.SUBTITLE_STYLE)
    for prefix in sorted(prefixes_on_hand.keys()):
        numbers = prefixes_on_hand[prefix]
        line = f"{prefix.upper():3>} "
        for i in range(0,max(numbers)+1):
            s = f"{i:02d}" if i in numbers else no_item_str
            line = f"{line} {s}"
        iprint(line)
    if not prefixes_on_hand:
        iprint("-no bikes-")
    print()

    # Bikes returned out -- tags matrix.
    bikes_out_title = "Bikes returned out ("
    for colour_code in sorted(returns_by_colour.keys()):
        num = returns_by_colour[colour_code]
        bikes_out_title = (f"{bikes_out_title}{num} "
                f"{cfg.colour_letters[colour_code].title()}, ")
    bikes_out_title = f"{bikes_out_title}{sum_out} Total)"
    iprint(bikes_out_title,style=cfg.SUBTITLE_STYLE)
    for prefix in sorted(prefixes_returned_out.keys()):
        numbers = prefixes_returned_out[prefix]
        line = f"{prefix.upper():3>} "
        for i in range(0,max(numbers)+1):
            s = f"{i:02d}" if i in numbers else no_item_str
            line = f"{line} {s}"
        iprint(line)
    if not prefixes_returned_out:
        iprint("-no bikes-")

    return

def tag_check(tag:str) -> None:
    """Check a tag in or out.

    This processes a prompt that's just a tag ID.
    """
    if tag in cfg.retired_tags: # if retired print specific retirement message
        iprint(f"{tag} is retired", style=cfg.WARNING_STYLE)
    else: # must not be retired so handle as normal
        if tag in check_ins:
            if tag in check_outs:# if tag has checked in & out
                query_tag([tag])
                iprint(f"Overwrite {check_outs[tag]} check-out with "
                       f"current time ({get_time()})? "
                       f"(y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                sure = input() == 'y'
                if sure:
                    edit_entry([tag, 'o', get_time()])
                else:
                    iprint("Cancelled",style=cfg.WARNING_STYLE)
            else:# checked in only
                now_mins = time_int(get_time())
                check_in_mins = time_int(check_ins[tag])
                time_diff_mins = now_mins - check_in_mins
                if time_diff_mins < cfg.CHECK_OUT_CONFIRM_TIME: # if < 1/2 hr
                    iprint("This bike checked in at "
                           f"{check_ins[tag]} ({time_diff_mins} mins ago)",
                           style=cfg.SUBPROMPT_STYLE)
                    iprint("Do you want to check it out? "
                           f"(Y/n) {cfg.CURSOR}",
                           style=cfg.SUBPROMPT_STYLE, end="")
                    sure = input().lower() in ['', 'y']
                else: # don't check for long stays
                    sure = True
                if sure:
                    check_outs[tag] = get_time()# check it out
                    iprint(f"{tag} returned OUT",style=cfg.ANSWER_STYLE)
                else:
                    iprint("Cancelled return bike out",style=cfg.WARNING_STYLE)
        else:# if string is in neither dict
            check_ins[tag] = get_time()# check it in
            iprint(f"{tag} checked IN",style=cfg.ANSWER_STYLE)

def parse_command(user_input:str) -> list[str]:
    """Parse user's input into list of [tag] or [command, command args].

    Returns [] if not a recognized tag or command.
    """
    user_input = user_input.lower().strip()
    if not (user_input):
        return []
    # Special case - if user input starts with '/' or '?' add a space.
    if user_input[0] in ["/","?"]:
        user_input = user_input[0] + " " + user_input[1:]
    # Split to list, test to see if tag.
    input_tokens = user_input.split()
    command = fix_tag(input_tokens[0], must_be_available=True)
    if command:
        return [command]    # A tag
    # See if it is a recognized command.
    # cfg.command_aliases is dict of lists of aliases keyed by
    # canonical command name (e.g. {"edit":["ed","e","edi"], etc})
    command = None
    for c, aliases in cfg.COMMANDS.items():
        if input_tokens[0] in aliases:
            command = c
            break
    # Is this an unrecognized command?
    if not command:
        return [cfg.CMD_UNKNOWN]
    # We have a recognized command, return it with its args.
    input_tokens[0] = command
    return input_tokens

def main():
    """Run main program loop and dispatcher."""
    done = False
    while not done:
        user_str = input(text_style(f"\nBike tag or command {cfg.CURSOR}",cfg.PROMPT_STYLE))
        tokens = parse_command(user_str)
        if not tokens:
            continue        # No input, ignore
        (cmd, *args) = tokens
        # Dispatcher
        data_dirty = False
        if cmd == cfg.CMD_EDIT:
            edit_entry(args)
            data_dirty = True
        elif cmd == cfg.CMD_AUDIT:
            audit_report(args)
        elif cmd == cfg.CMD_DELETE:
            delete_entry(args)
            data_dirty = True
        elif cmd == cfg.CMD_EDIT:
            edit_entry(args)
            data_dirty = True
        elif cmd == cfg.CMD_EXIT:
            done = True
        elif cmd == cfg.CMD_BLOCK:
            dataform_report(args)
        elif cmd == cfg.CMD_HELP:
            print(cfg.help_message)
        elif cmd == cfg.CMD_LOOKBACK:
            lookback(args)
        elif cmd == cfg.CMD_QUERY:
            query_tag(args)
        elif cmd == cfg.CMD_STATS:
            day_end_report(args)
        elif cmd == cfg.CMD_MORE_STATS:
            more_stats_report(args)
        elif cmd == cfg.CMD_UNKNOWN:
            print()
            iprint("Unrecognized tag or command, enter 'h' for help",
                    style=cfg.WARNING_STYLE)
        else:
            # This is a tag
            tag_check(cmd)
            data_dirty = True
        # Save if anything has changed
        if data_dirty:
            rotate_log()
            write_tags()
            data_dirty = False

def error_exit() -> None:
    """If an error has occurred, give a message and shut down.

    Any specific info about the error should already have been printed."""
    print()
    iprint("Closing in 30 seconds",style=cfg.ERROR_STYLE)
    time.sleep(30)
    exit()

def datafile_name() -> str:
    """Return the name of the data file (logfile) to read/write."""

    if len(sys.argv) <= 1:
        # Use default filename
        return f"logs/{cfg.LOG_BASENAME}{DATE}.log"

    # Custom logfile name or location
    file = sys.argv[1]
    # File there?
    if not os.path.exists(file):
        iprint(f"Error: File {file} not found",style=cfg.ERROR_STYLE)
        error_exit()

    # This is the custom logfile & it exists
    return file

# STARTUP
if not cfg.SETUP_PROBLEM: # no issue flagged while reading config

    # These are the master dictionaries for tag status.
    #   key = canonical tag id (e.g. "wf4")
    #   value = ISO8601 event time (e.g. "08:43" as str)
    check_ins = {}
    check_outs = {}

    print()
    print(text_style(f"TagTracker {cfg.VERSION} by Julias Hocking",
            style=cfg.ANSWER_STYLE))
    print()
    DATE = get_date()
    LOG_FILEPATH = datafile_name()

    if read_tags(): # only run main() if tags read successfully
        main()
    else: # if read_tags() problem
        error_exit()
else:
    error_exit()
#==========================================

