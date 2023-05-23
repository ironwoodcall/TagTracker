"""TagTracker by Julias Hocking.

This is the data entry module for the TagTracker suite.
Its configuration file is tagtracker_config.py.

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
import pathlib
import statistics
from typing import Union    # This is for type hints instead of (eg) int|str

import tracker_util as ut
import tagtracker_config as cfg

# Initialize valet open/close globals
VALET_OPENS = ""
VALET_CLOSES = ""
VALET_DATE=""

def simplified_taglist(tags:Union[list[ut.Tag],str]) -> str:
    """Make a simplified str of tag names from a list of tags.

    E.g. "wa1,2,3,4,9 wb1,9,10 be4"
    The tags list can be a string separated by whitespace or comma.
    or it can be a list of tags.
    """
    if isinstance(tags,str):
        # Break the tags down into a list.  First split comma.
        tags = tags.split(",")
        # Split on whitespace.  This makes a list of lists.
        tags = [item.split() for item in tags]
        # Flatten the list of lists into a single list.
        tags = [item for sublist in tags for item in sublist]
    # Make dict of [prefix]:list of tag_numbers_as_int
    tag_prefixes = ut.tags_by_prefix(tags)
    simplified_list = []
    for prefix in sorted(tag_prefixes.keys()):
        # A list of the tag numbers for this prefix
        simplified_list.append(f"{prefix}" +
                (",".join([str(num) for num in sorted(tag_prefixes[prefix])])))
    # Return all of these joined together
    simple_str = " ".join(simplified_list)
    simple_str = simple_str.upper() if UC_TAGS else simple_str.lower()
    return simple_str

def num_bikes_at_valet( as_of_when:Union[ut.Time,int]=None ) -> int:
    """Return count of bikes at the valet as of as_of_when."""
    as_of_when = ut.time_str(as_of_when)
    if not as_of_when:
        as_of_when = ut.get_time()
    # Count bikes that came in & by the given time, and the diff
    num_in = len([t for t in check_ins.values() if t <= as_of_when])
    num_out = len([t for t in check_outs.values() if t <= as_of_when])
    return max(0, num_in - num_out)

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

def future_warning(when:ut.Time="") -> None:
    """Give a reminder that requested report time is in the future.

    If called with when same as current time or in the past, does nothing.
    """
    if when:
        rightnow = ut.get_time()
        if rightnow >= when:
            return
        msg = ("(Reporting a time "
                f"{ut.pretty_time(ut.time_int(when)-ut.time_int(rightnow),trim=True)}"
                "h later than now)")
    else:
        msg = "(Reporting a time in the future)"
    iprint(msg,style=cfg.HIGHLIGHT_STYLE)

def valet_logo():
    """Print a cute bike valet logo using unicode."""
    UL = chr(0x256d)
    VR = chr(0x2502)
    HR = chr(0x2500)
    UR = chr(0x256e)
    LL = chr(0x2570)
    LR = chr(0x256f)
    BL = " "
    LOCK00 = chr(0x1F512)
    BIKE00 = chr(0x1f6b2)
    SCOOTR = chr(0x1f6f4)

    ln1 = f"{BL}{UL}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{UR}"
    ln2 = f"{BL}{VR}{BL}{BIKE00}{BIKE00}{SCOOTR}{BIKE00}{BL}{VR}"
    ln3 = f"{LOCK00}{BL}{BIKE00}{BIKE00}{BIKE00}{SCOOTR}{BL}{VR}"
    ln4 = f"{BL}{LL}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{LR}"

    WHATSTYLE=cfg.ANSWER_STYLE

    print()
    iprint(f"            {ln1}             ",style=WHATSTYLE)
    iprint(f"   FREE     {ln2}     BIKE    ",style=WHATSTYLE)
    iprint(f"   SAFE     {ln3}     VALET   ",style=WHATSTYLE)
    iprint(f"            {ln4}             ",style=WHATSTYLE)
    print()

def earliest_event() -> ut.Time:
    """Return the earliest event of the day as HH:MM (or "" if none)."""
        # Find earliest and latest block of the day
    all_events = list(check_ins.keys()) + list(check_outs.keys())
    if not all_events:
        return ""
    return min(all_events)

def latest_event(as_of_when:Union[ut.Time,int,None]=None ) -> ut.Time:
    """Return the latest event of the day at or before as_of_when.

    If no events in the time period, return "".
    If as_of_when is blank or None, then this will use the whole day.
    FIXME: check that this is the right choice. Would it be better to
    go only up to the current moment?
    """
    if not as_of_when:
        as_of_when = "24:00"
    else:
        as_of_when = ut.time_str(as_of_when)
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

def deduce_valet_date(current_guess:str, filename:str) -> str:
    """Guess what date the current data is for.

    Logic:
        If current_guess is set (presumably read from the contents
        of the datafile) then it is used.
        Else if there appears to be a date embedded in the name of
        the datafile, it is used.
        Else today's date is used.
    """
    if current_guess:
        return current_guess
    r = ut.DATE_PART_RE.search(filename)
    if r:
        return (f"{int(r.group(2)):04d}-{int(r.group(3)):02d}-"
                f"{int(r.group(4)):02d}")
    return ut.get_date()

def initialize_today() -> bool:
    """Fetch today's data from file (if exists)."""
    # Does the file even exist? (If not we will just create it later)
    pathlib.Path("logs").mkdir(exist_ok = True) # make logs folder if missing
    if not os.path.exists(LOG_FILEPATH):
        iprint("No datafile for today found. Will create new datafile"
               f" {LOG_FILEPATH}.", style=cfg.SUBTITLE_STYLE)
        return True
    # Fetch data from file; errors go into error_msgs
    iprint(f"Reading data from {LOG_FILEPATH}...",
           end="", style=cfg.SUBTITLE_STYLE)
    error_msgs = []
    today_data = ut.read_datafile(LOG_FILEPATH,error_msgs,ALL_TAGS)
    if error_msgs:
        print()
        for text in error_msgs:
            iprint(text, style=cfg.ERROR_STYLE)
        return False
    # On success, set today's working data
    # pylint: disable=global-statement
    global VALET_DATE, VALET_OPENS, VALET_CLOSES
    global check_ins, check_outs
    # pylint: enable=global-statement
    VALET_DATE = today_data.date
    VALET_OPENS = today_data.opening_time
    VALET_CLOSES = today_data.closing_time
    check_ins = today_data.bikes_in
    check_outs = today_data.bikes_out

    iprint('done.', num_indents=0, style=cfg.SUBTITLE_STYLE)
    return True

class Visit():
    """Just a data structure to keep track of bike visits."""

    def __init__(self, tag:str) -> None:
        """Initialize blank."""
        self.tag = tag      # canonical
        self.time_in = ""   # HH:MM
        self.time_out = ""  # HH:MM
        self.duration = 0   # minutes
        self.type = None    # ut.REGULAR, ut.OVERSIZE
        self.still_here = None  # True or False

def calc_visits(as_of_when:Union[int,ut.Time]=None) -> dict[ut.Tag,Visit]:
    """Create a dict of visits keyed by tag as of as_of_when.

    If as_of_when is not given, then this will use the current time.

    If there are bikes that are not checked out, then this will
    consider their check-out time to be:
        earlier of:
            current time
            closing time if there is one, else time of latest event of the day.

    As a special case, this will also accept the word "now" to
    mean the current time.
    """
    if (not as_of_when or
            (isinstance(as_of_when,str) and as_of_when.lower() == "now")):
        as_of_when = ut.get_time()
    as_of_when = ut.time_str(as_of_when)

    # If a bike isn't checked out or its checkout is after the requested
    # time, then use what as its checkout time?
    latest_time = VALET_CLOSES if VALET_CLOSES else latest_event()
    missing_checkout_time = min([latest_time,as_of_when])

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
            this_visit.time_out = missing_checkout_time
            this_visit.still_here = True
        this_visit.duration = max(1,
                (ut.time_int(this_visit.time_out) -
                ut.time_int(this_visit.time_in)))
        if tag in NORMAL_TAGS:
            this_visit.type = ut.REGULAR
        else:
            this_visit.type = ut.OVERSIZE
        visits[tag] = this_visit
    return visits

class Event():
    """What happened at each discrete atime of day (that something happened)."""

    def __init__(self,event_time:ut.Time) -> None:
        """Create empty Event, attributes initialized to type."""
        self.event_time = event_time
        self.num_here_total = None  # will be int
        self.num_here_regular = None
        self.num_here_oversize = None
        self.bikes_in = []   # List of canonical tag ids.
        self.bikes_out = []
        self.num_ins = 0     # This is just len(self.bikes_in).
        self.num_outs = 0    # This is just len(self.bikes_out).

def calc_events(as_of_when:(int or ut.Time)=None ) -> dict[ut.Time,Event]:
    """Create a dict of events keyed by HH:MM time.

    If as_of_when is not given, then this will choose the latest
    check-out time of the day as its time.

    As a special case, this will also accept the word "now" to
    mean the current time.
    """
    if isinstance(as_of_when,str) and as_of_when.lower() == "now":
        as_of_when = ut.get_time()
    elif as_of_when is None:
        # Set as_of_when to be the time of the latest checkout of the day.
        if check_ins:
            as_of_when = min(list(check_ins.values()))
        else:
            as_of_when = ut.get_time()
    as_of_when = ut.time_str(as_of_when)
    # First pass, create all the Events and list their tags in & out.
    events = {}
    for tag,atime in check_ins.items():
        if atime > as_of_when:
            continue
        if atime not in events:
            events[atime] = Event(atime)
        events[atime].bikes_in.append(tag)
    for tag,atime in check_outs.items():
        if atime > as_of_when:
            continue
        if atime not in events:
            events[atime] = Event(atime)
        events[atime].bikes_out.append(tag)
    # Second pass, calculate other attributes of Events.
    num_regular = 0     # Running balance of regular & oversize bikes.
    num_oversize = 0
    for atime in sorted(events.keys()):
        vx = events[atime]
        vx.num_ins = len(vx.bikes_in)
        vx.num_outs = len(vx.bikes_out)
        # How many regular & oversize bikes have we added or lost?
        diff_normal = (
            len([x for x in vx.bikes_in if x in NORMAL_TAGS]) -
            len([x for x in vx.bikes_out if x in NORMAL_TAGS]))
        diff_oversize = (
            len([x for x in vx.bikes_in if x in OVERSIZE_TAGS]) -
            len([x for x in vx.bikes_out if x in OVERSIZE_TAGS]))
        num_regular += diff_normal
        num_oversize += diff_oversize
        vx.num_here_regular = num_regular
        vx.num_here_oversize = num_oversize
        vx.num_here_total = num_regular + num_oversize
        vx.num_ins = len(vx.bikes_in)
        vx.num_outs = len(vx.bikes_out)
    return events

def bike_check_ins_report(as_of_when:ut.Time) -> None:
    """Print the check-ins count part of the summary statistics.

    as_of_when is HH:MM time, assumed to be a correct time.
    """
    # Find the subset of check-ins at or before our cutoff time.
    these_check_ins = {}
    for tag,atime in check_ins.items():
        if atime <= as_of_when:
            these_check_ins[tag] = atime
    # Summary stats
    num_still_here = len(set(these_check_ins.keys()) -
        set([x for x in check_outs if check_outs[x] <= as_of_when]))
    num_bikes_ttl = len(these_check_ins)
    these_checkins_am = [x for x in these_check_ins if these_check_ins[x] < "12:00"]
    num_bikes_am = len(these_checkins_am)
    num_bikes_regular = len(
            [x for x in these_check_ins if x in NORMAL_TAGS])
    num_bikes_oversize = len(
            [x for x in these_check_ins if x in OVERSIZE_TAGS])

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
        """Calculat and print the mode info."""
        # Find the mode value(s), with visit durations rounded
        # to nearest ROUND_TO_NEAREST time.
        rounded = [round(x/cfg.MODE_ROUND_TO_NEAREST)*cfg.MODE_ROUND_TO_NEAREST
                for x in durations_list]
        modes_str = ",".join(
                [ut.pretty_time(x,trim=False)
                 for x in statistics.multimode( rounded )])
        modes_str = (f"{modes_str}  (times "
                f"rounded to {cfg.MODE_ROUND_TO_NEAREST} minutes)")
        one_line(f"Mode {cfg.VISIT_NOUN}:", modes_str)

    def make_tags_str(tags:list[ut.Tag]) -> str:
        """Make a 'list of tags' string that is sure not to be too long."""
        tagstr = "tag: " if len(tags) == 1 else "tags: "
        tagstr = (tagstr + ",".join(tags))
        if len(tagstr) > 30:
            tagstr = f"{len(tags)} tags"
        return tagstr

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
    iprint(f"{cfg.VISIT_NOUN.title()}-length statistics",
           style=cfg.SUBTITLE_STYLE)
    longest = max(list(duration_tags.keys()))
    long_tags = make_tags_str(duration_tags[longest])
    shortest = min(list(duration_tags.keys()))
    short_tags = make_tags_str(duration_tags[shortest])
    one_line(f"Longest {noun}:", f"{ut.pretty_time((longest))}  ({long_tags})")
    one_line(f"Shortest {noun}:", f"{ut.pretty_time((shortest))}  ({short_tags})")
    # Make a list of stay-lengths (for mean, median, mode)
    durations_list = [x.duration for x in visits.values()]
    one_line( f"Mean {noun}:", ut.pretty_time(statistics.mean(durations_list)))
    one_line( f"Median {noun}:", ut.pretty_time(statistics.median(list(duration_tags.keys()))))
    visits_mode(durations_list)


def highwater_report(events:dict) -> None:
    """Make a highwater table as at as_of_when."""
    # High-water mark for bikes in valet at any one time
    def one_line( header:str, events:dict, atime:ut.Time,
            highlight_field:int ) -> None:
        """Print one line for highwater_report."""
        values = [events[atime].num_here_regular,
                  events[atime].num_here_oversize,
                  events[atime].num_here_total]
        line = f"{header:15s}"
        for num,val in enumerate(values):
            bit = f"{val:3d}"
            if num == highlight_field:
                bit = text_style(bit,style=cfg.HIGHLIGHT_STYLE)
            line = f"{line}   {bit}"
        iprint(f"{line}    {atime}")
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
    for atime in sorted(events.keys()):
        if (events[atime].num_here_regular >= max_regular_num
                and not max_regular_time):
            max_regular_time = atime
        if (events[atime].num_here_oversize >= max_oversize_num
                and not max_oversize_time):
            max_oversize_time = atime
        if (events[atime].num_here_total >= max_total_num
                and not max_total_time):
            max_total_time = atime
    iprint("                 Reglr OvrSz Total WhenAchieved")
    one_line("Most regular:", events, max_regular_time, 0)
    one_line("Most oversize:", events, max_oversize_time, 1)
    one_line("Most combined:", events, max_total_time, 2)

def busy_report(events:dict[ut.Time,Event], as_of_when:ut.Time) -> None:
    """Report the busiest time(s) of day."""
    def one_line(rank:int, num_events:int, times:list[ut.Time]) -> None:
        """Format and print one line of busyness report."""
        iprint(f"{rank:2d}     {num_events:3d}      ",end="")
        for time_num,start_time in enumerate(sorted(times),start=1):
            end_time=ut.time_str(ut.time_int(start_time)+cfg.BLOCK_DURATION)
            print(f"{ut.pretty_time(start_time,trim=True)}-"
                  f"{ut.pretty_time(end_time,trim=True)}", end="")
            if time_num < len(times):
                print(", ",end="")
        print()

    # Make an empty dict of busyness of timeblocks.
    blocks = dict(zip(
        Block.timeblock_list(as_of_when),
        [0 for _ in range(0,100)]))
    # Count actions in each timeblock
    for atime, ev in events.items():
        start = Block.block_start(atime) # Which block?
        blocks[start] += ev.num_ins + ev.num_outs
    # Make a dict of busynesses with list of timeblocks for each.
    busy_times = {}
    for atime, activity in blocks.items():
        if activity not in busy_times:
            busy_times[activity] = []
        busy_times[activity].append(atime)
    # Report the results.
    print()
    iprint("Busiest times of day",style=cfg.SUBTITLE_STYLE)
    iprint("Rank  Ins&Outs  When")
    for rank, activity in enumerate(sorted(busy_times.keys(),reverse=True), start=1):
        if rank > cfg.BUSIEST_RANKS:
            break
        one_line(rank, activity, busy_times[activity])

def qstack_report(visits:dict[ut.Tag:Visit]) -> None:
    """Report whether visits are more queue-like or more stack-like."""
    # Make a list of tuples: start_time, end_time for all visits.
    visit_times = list(zip( [vis.time_in for vis in visits.values()],
        [vis.time_out for vis in visits.values()]))
    ##ut.squawk( f"{len(list(visit_times))=}")
    ##ut.squawk( f"{list(visit_times)=}")
    queueish = 0
    stackish = 0
    neutralish = 0
    visit_compares = 0
    total_possible_compares = int((len(visit_times)*(len(visit_times)-1))/2)

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
    neutralish = total_possible_compares - queueish - stackish
    queue_proportion = queueish / (queueish + stackish + neutralish)
    stack_proportion = stackish / (queueish + stackish + neutralish)
    iprint(f"The {total_possible_compares} compares of today's {len(visits)} "
           f"{cfg.VISIT_NOUN.lower()}s are:")
    iprint(f"{(queue_proportion):0.3f} queue-like "
           f"(overlapping {cfg.VISIT_NOUN.lower()}s)",num_indents=2)
    iprint(f"{(stack_proportion):0.3f} stack-like "
           f"(nested {cfg.VISIT_NOUN.lower()}s)",num_indents=2)
    iprint(f"{((1 - stack_proportion - queue_proportion)):0.3f} neither "
           f"(disjunct {cfg.VISIT_NOUN.lower()}s, "
           "or share a check-in or -out time)",num_indents=2)

def day_end_report(args:list) -> None:
    """Report summary statistics about visits, up to the given time.

    If not time given, calculates as of latest checkin/out of the day.
    """
    rightnow = ut.get_time()
    as_of_when = (args + [None])[0]
    if not as_of_when:
        as_of_when = rightnow
    else:
        as_of_when = ut.time_str(as_of_when)
        if not (as_of_when):
            iprint(f"Unrecognized time passed to visits summary ({args[0]})",
                style=cfg.WARNING_STYLE)
            return
    print()
    iprint(f"Summary statistics as at {ut.pretty_time(as_of_when,trim=True)}",
           style=cfg.TITLE_STYLE)
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

def more_stats_report(args:list) -> None:
    """Report more summary statistics about visits, up to the given time.

    If not time given, calculates as of latest checkin/out of the day.
    """
    rightnow = ut.get_time()
    as_of_when = (args + [None])[0]
    if not as_of_when:
        as_of_when = rightnow
    else:
        as_of_when = ut.time_str(as_of_when)
        if not (as_of_when):
            iprint(f"Unrecognized time passed to visits summary ({args[0]})",
                style=cfg.WARNING_STYLE)
            return
    print()
    iprint(f"More summary statistics as at {ut.pretty_time(as_of_when,trim=True)}",
           style=cfg.TITLE_STYLE)
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

def find_tag_durations(include_bikes_on_hand=True) -> ut.TagDict:
    """Make dict of tags with their stay duration in minutes.

    If include_bikes_on_hand, this will include checked in
    but not returned out.  If False, only bikes returned out.
    """
    timenow = ut.time_int(ut.get_time())
    tag_durations = {}
    for tag,in_str in check_ins.items():
        in_minutes = ut.time_int(in_str)
        if tag in check_outs:
            out_minutes = ut.time_int(check_outs[tag])
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

    def arg_prompt(maybe:str, prompt:str, optional:bool=False) -> str:
        """Prompt for one command argument (token)."""
        if optional or maybe:
            maybe = "" if maybe is None else f"{maybe}".strip().lower()
            return maybe
        prompt = text_style(f"{prompt} {cfg.CURSOR}",style=cfg.PROMPT_STYLE)
        return input(prompt).strip().lower()

    def nogood(msg:str="",syntax:bool=True) -> None:
        """Print the nogood msg + syntax msg."""
        if msg:
            iprint(msg, style=cfg.WARNING_STYLE)
        if syntax:
            iprint("syntax: delete <tag> <in|out|both> <y|n|!>",
                    style=cfg.WARNING_STYLE)

    (maybe_target,maybe_what,maybe_confirm) = (args + ["","",""])[:3]
    # What tag are we to delete parts of?
    maybe_target = arg_prompt(maybe_target,"Delete entries for what tag?")
    if not maybe_target:
        nogood()
        return
    target = ut.fix_tag(maybe_target, must_be_in=ALL_TAGS,uppercase=UC_TAGS)
    if not target:
        nogood(f"'{maybe_target}' is not a tag or not a tag in use.")
        return
    if target not in check_ins:
        nogood(f"Tag {target} not checked in or out, nothing to do.",
               syntax=False)
        return
    # Special case: "!" after what without a space
    if maybe_what and maybe_what[-1] == "!" and not maybe_confirm:
        maybe_what = maybe_what[:-1]
        maybe_confirm = "!"
    # Find out what kind of checkin/out we are to delete
    what = arg_prompt(maybe_what, "Delete check-IN, check-OUT or BOTH (i/o/b)?")
    if not what:
        nogood()
        return
    if what not in ["i","in","o","out","b","both"]:
        nogood("Must indicate in, out or both")
        return
    if what in ["i","in"] and target in check_outs:
        nogood(f"Bike {target} checked out.  Can't delete check-in "
               "for a returned bike without check-out too",
               syntax=False)
        return
    # Get a confirmation
    confirm = arg_prompt(maybe_confirm,"Are you sure (y/n)?")
    if confirm not in ["y","yes", "!"]:
        nogood("Delete cancelled",syntax=False)
        return
    # Perform the delete
    if what in ["b","both","o","out"] and target in check_outs:
        check_outs.pop(target)
    if what in ["b","both","i","in"] and target in check_ins:
        check_ins.pop(target)
    iprint("Deleted.",style=cfg.ANSWER_STYLE)

# pylint: disable=pointless-string-statement
'''
def old_delete_entry(args:list[str]) -> None:
    """Perform tag entry deletion dialogue."""
    # FIXME: this is superseded
    (target,which_to_del,confirm) = (args + [None,None,None])[:3]

    if target:
        target = ut.fix_tag(target)
    if not target:
        target = None
    del_syntax_message = text_style("Syntax: d <tag> <both or check-out only"
            " (b/o)> <optional pre-confirm (y)>",style=cfg.SUBPROMPT_STYLE)
    if not(target in [None] + ALL_TAGS or which_to_del in [None,'b','o']
           or confirm in [None, "y","yes"]):
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
        iprint(f"'{target}' not used yet today (delete cancelled)",
               style=cfg.WARNING_STYLE)
    elif checked_out: # both events recorded
        time_in_temp = check_ins[target]
        time_out_temp = check_outs[target]
        if not which_to_del: # ask which to del if not specified
            iprint(f"Bike {target} checked in at "
                   f"{ut.pretty_time(time_in_temp,trim=True)} and "
                   f"out at {ut.pretty_time(time_out_temp,trim=True)}.",
                   style=cfg.SUBPROMPT_STYLE)
            iprint("Delete (b)oth events, "
                   f"or just the check-(o)ut?  (b/o) {cfg.CURSOR}",
                   style=cfg.SUBPROMPT_STYLE,end="")
            which_to_del = input().lower()
        if which_to_del in ["b","both"]:
            if confirm in ["y","yes"]: # pre-confirmation
                sure = True
            else:
                iprint(f"Delete {target} check-in and check-out "
                       f"(y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                sure = input().lower() in ["y","yes"]
            if sure:
                check_ins.pop(target)
                check_outs.pop(target)
                iprint(f"Deleted {target} check-in and check-out",
                       style=cfg.ANSWER_STYLE)
            else:
                iprint("Delete cancelled",style=cfg.WARNING_STYLE)

        elif which_to_del in ["o","out"]: # selected to delete
            if confirm in ["y","yes"]:
                sure = True
            else:
                iprint(f"Delete {target} check-out? (y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="" )
                sure = input().lower() in ["y","yes"]

            if sure:
                time_temp = check_outs[target]
                check_outs.pop(target)
                iprint(f"Deleted {target} check-out", style=cfg.ANSWER_STYLE)
            else:
                iprint("Delete cancelled",style=cfg.WARNING_STYLE)
        else:
            iprint("Delete cancelled",style=cfg.WARNING_STYLE)
    else: # checked in only
        time_in_temp = check_ins[target]
        if which_to_del in ["b", "both", None]:
            if confirm in ["y","yes"]:
                sure = True
            else: # check
                iprint(f"Bike {target} checked in at "
                       f"{ut.pretty_time(time_in_temp,trim=True)}. "
                       f"Delete check-in? (y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                sure = input().lower() in ["y","yes"]
            if sure:
                time_temp = check_ins[target]
                check_ins.pop(target)
                iprint(f"Deleted {time_temp} check-in for {target}",
                       style=cfg.ANSWER_STYLE)
            else:
                iprint("Delete cancelled",style=cfg.WARNING_STYLE)
        else:#  which_to_del in ["o","out"]:
            iprint(f"{target} has only a check-in ({time_in_temp}) recorded; "
                   "can't delete a nonexistent check-out",
                   style=cfg.WARNING_STYLE)
'''
# pylint: enable=pointless-string-statement

def query_tag(args:list[str]) -> None:
    """Query the check in/out times of a specific tag."""
    target = (args + [None])[0]
    if not target: # only do dialog if no target passed
        iprint(f"Which tag would you like to query? (tag name) {cfg.CURSOR}",
               style=cfg.SUBPROMPT_STYLE, end="")
        target = input().lower()
    fixed_target = ut.fix_tag(target,must_be_in=ALL_TAGS,uppercase=UC_TAGS)
    print()
    if not fixed_target:
        iprint(f"Tag {target} is not available (retired, does not exist, etc)",
               style=cfg.WARNING_STYLE)
        return
    elif fixed_target not in check_ins:
        iprint(f"Tag '{fixed_target}' not used yet today",
               style=cfg.WARNING_STYLE)
        return
    iprint(f"{ut.pretty_time(check_ins[fixed_target])}  "
           f"{fixed_target} checked  IN",
           style=cfg.ANSWER_STYLE)
    if fixed_target in check_outs:
        iprint(f"{ut.pretty_time(check_outs[fixed_target])}  "
               f"{fixed_target} returned OUT",
               style=cfg.ANSWER_STYLE)
    else:
        iprint(f"(now)  {target} still at valet", style=cfg.ANSWER_STYLE)

def prompt_for_time(inp=False, prompt:str=None) -> bool or ut.Time:
    """Prompt for a time input if needed.

    Helper for edit_entry(); if no time passed in, get a valid
    24h time input from the user and return an HH:MM string.
    """
    if not inp:
        if not prompt:
            prompt = "What is the correct time for this event? (HHMM or 'now')"
        iprint(f"{prompt} {cfg.CURSOR}", style=cfg.SUBPROMPT_STYLE, end="")
        #iprint("Use 24-hour format, or 'now' to use "
        #       f"the current time ({ut.get_time()}) ",end="")
        inp = input()
    if inp.lower() == 'now':
        return ut.get_time()
    hhmm = ut.time_str(inp)
    if not hhmm:
        return False
    return hhmm

def set_valet_hours(args:list[str]) -> None:
    """Set the valet opening & closing hours."""
    global VALET_OPENS, VALET_CLOSES # pylint: disable=global-statement
    (open_arg, close_arg) = (args+["",""])[:2]
    print()
    # Valet opening time
    if VALET_OPENS:
        iprint(f"Valet opening time is currently set at: {VALET_OPENS}",
               style=cfg.PROMPT_STYLE)
    maybe_open = prompt_for_time(open_arg,
            prompt="Today's valet opening time")
    if not maybe_open:
        iprint(f"Input {open_arg} not recognized as a time.  Cancelled.",
               style=cfg.WARNING_STYLE)
        return
    VALET_OPENS = maybe_open
    iprint(f"Opening time now set to {VALET_OPENS}",style=cfg.ANSWER_STYLE)
    # Valet closing time
    if VALET_CLOSES:
        iprint(f"Valet closing time is currently set at: {VALET_CLOSES}",
               style=cfg.PROMPT_STYLE)
    maybe_close = prompt_for_time(close_arg,
            prompt="Enter today's valet closing time")
    if not maybe_close:
        iprint(f"Input {close_arg} not recognized as a time.  Cancelled.",
               style=cfg.WARNING_STYLE)
        return
    VALET_CLOSES = maybe_close
    iprint(f"Closing time now set to {VALET_CLOSES}",style=cfg.ANSWER_STYLE)

def edit_entry(args:list[str]):
    """Perform Dialog to correct a tag's check in/out time."""
    (target, in_or_out, new_time) = (args + [None,None,None])[:3]

    edit_syntax_message = text_style("Syntax: e <bike's tag> <in or out (i/o)> "
            "<new time or 'now'>",cfg.WARNING_STYLE)
    if not target:
        iprint(f"Which bike's record do you want to edit? (tag ID) {cfg.CURSOR}",
               style=cfg.SUBPROMPT_STYLE, end="")
        target = input().lower()
    elif not target in ALL_TAGS:
        iprint(edit_syntax_message)
        return False
    if target in ALL_TAGS:
        if target in check_ins:
            if not in_or_out:
                iprint("Do you want to change this bike's "
                       f"check-(i)n or check-(o)ut time? (i/o) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                in_or_out = input().lower()
                if not in_or_out in ["i","in","o","out"]:
                    iprint(f"Unrecognized answer '{in_or_out}' needs to be 'i' or 'o' "
                           "(edit cancelled)", style=cfg.WARNING_STYLE)
                    return False
            if not in_or_out in ["i","in","o","out"]:
                iprint(edit_syntax_message)
            else:
                new_time = prompt_for_time(new_time)
                if not new_time:
                    iprint('Invalid time entered (edit cancelled)',
                           style=cfg.WARNING_STYLE)
                elif in_or_out in ["i","in"]:
                    if (target in check_outs and
                            (ut.time_int(new_time) >
                            ut.time_int(check_outs[target]))):
                        iprint("Can't set a check-IN later than a check-OUT;",
                               style=cfg.WARNING_STYLE)
                        iprint(f"{target} was returned OUT at {check_outs[target]}",
                               style=cfg.WARNING_STYLE)
                    else:
                        iprint(f"Check-IN time for {target} "
                               f"set to {new_time}",style=cfg.ANSWER_STYLE)
                        check_ins[target] = new_time
                elif in_or_out in ["o","out"]:
                    if (ut.time_int(new_time) <
                            ut.time_int(check_ins[target])):
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

class Block():
    """Class to help with reporting.

    Each instance is a timeblock of duration cfg.BLOCK_DURATION.
    """

    def __init__(self, start_time:Union[ut.Time,int]) -> None:
        """Initialize. Assumes that start_time is valid."""
        if isinstance(start_time,str):
            self.start = ut.time_str(start_time)
        else:
            self.start = ut.time_str(start_time)
        self.ins_list = []      # Tags of bikes that came in.
        self.outs_list = []     # Tags of bikes returned out.
        self.num_ins = 0        # Number of bikes that came in.
        self.num_outs = 0       # Number of bikes that went out.
        self.here_list = []     # Tags of bikes in valet at end of block.
        self.num_here = 0       # Number of bikes in valet at end of block.

    @staticmethod
    def block_start(atime:Union[int,ut.Time], as_number:bool=False
                ) -> Union[ut.Time,int]:
        """Return the start time of the block that contains time 'atime'.

        'atime' can be minutes since midnight or HHMM.
        Returns HHMM unless as_number is True, in which case returns int.
        """
        # Get time in minutes
        atime = ut.time_int(atime) if isinstance(atime,str) else atime
        # which block of time does it fall in?
        block_start_min = (atime // cfg.BLOCK_DURATION) * cfg.BLOCK_DURATION
        if as_number:
            return block_start_min
        return ut.time_str(block_start_min)

    @staticmethod
    def block_end(atime:Union[int,ut.Time], as_number:bool=False
                ) -> Union[ut.Time,int]:
        """Return the last minute of the timeblock that contains time 'atime'.

        'atime' can be minutes since midnight or HHMM.
        Returns HHMM unless as_number is True, in which case returns int.
        """
        # Get block start
        start = Block.block_start(atime, as_number=True)
        # Calculate block end
        end = start + cfg.BLOCK_DURATION - 1
        # Return as minutes or HHMM
        if as_number:
            return end
        return ut.time_str(end)

    @staticmethod
    def timeblock_list(as_of_when:ut.Time=None) -> list[ut.Time]:
        """Build a list of timeblocks from beg of day until as_of_when.

        Latest block of the day will be the latest timeblock that
        had any transactions at or before as_of_when.
        """
        as_of_when = as_of_when if as_of_when else ut.get_time()
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
            timeblocks.append(ut.time_str(t))
        return timeblocks

    @staticmethod
    def calc_blocks(as_of_when:ut.Time=None) -> dict[ut.Time,object]:
        """Create a dictionary of Blocks {start:Block} for whole day."""
        as_of_when = as_of_when if as_of_when else "18:00"
        # Create dict with all the blocktimes as keys (None as values)
        blocktimes = Block.timeblock_list(as_of_when=as_of_when)
        if not blocktimes:
            return {}
        blocks = {}
        timeblock_list = Block.timeblock_list(as_of_when=as_of_when)
        for t in timeblock_list:
            blocks[t] = Block(t)
        # latest_time is the end of the latest block that interests us
        latest_time = Block.block_end(max(timeblock_list),as_number=False)
        for tag, atime in check_ins.items():
            if atime > latest_time:
                continue
            bstart = Block.block_start(atime)
            blocks[bstart].ins_list += [tag]
        for tag, atime in check_outs.items():
            if atime > latest_time:
                continue
            bstart = Block.block_start(atime)
            blocks[bstart].outs_list += [tag]
        here_set = set()
        for blk in blocks.values():
            blk.num_ins = len(blk.ins_list)
            blk.num_outs = len(blk.outs_list)
            here_set = (here_set | set(blk.ins_list)) - set(blk.outs_list)
            blk.here_list = here_set
            blk.num_here = len(here_set)
        return blocks

def recent(args:list[str]) -> None:
    """Display a look back at recent activity.

    Args are both optional, start_time and end_time.
    If end_time is missing, runs to current time.
    If start_time is missing, starts one hour before end_time.
    """
    def format_one( atime:str, tag:str, check_in:bool) -> str:
        """Format one line of output."""
        in_tag = tag if check_in else ""
        out_tag = "" if check_in else tag
        return f"{ut.pretty_time(atime,trim=False)}   {in_tag:<5s} {out_tag:<5s}"

    (start_time, end_time) = (args + [None,None])[:2]
    if not end_time:
        end_time = ut.get_time()
    if not start_time:
        start_time = ut.time_str(ut.time_int(end_time)-30)
    start_time = ut.time_str(start_time)
    end_time = ut.time_str(end_time)
    if not start_time or not end_time or start_time > end_time:
        iprint("Can not make sense of the given start/end times",
               style=cfg.WARNING_STYLE)
        return
    # Collect any bike-in/bike-out events that are in the time period.
    events = []
    for tag, atime in check_ins.items():
        if start_time <= atime <= end_time:
            events.append( format_one(atime, tag, True))
    for tag, atime in check_outs.items():
        if start_time <= atime <= end_time:
            events.append( format_one(atime, tag, False))
    # Print
    iprint()
    iprint(f"Recent activity (from {ut.pretty_time(start_time,trim=True)} "
           f"to {ut.pretty_time(end_time,trim=True)})",
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
        end_time = ut.get_time()
    end_time = ut.time_str(end_time)
    if not (end_time):
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
    for which in [ut.BIKE_IN,ut.BIKE_OUT]:
        titlebit = "checked IN" if which == ut.BIKE_IN else "returned OUT"
        title = f"Bikes {titlebit}"
        print()
        iprint(title, style=cfg.SUBTITLE_STYLE)
        iprint("-" * len(title), style=cfg.SUBTITLE_STYLE)
        for start,block in all_blocks.items():
            inouts = (block.ins_list if which == ut.BIKE_IN
                    else block.outs_list)
            endtime = ut.time_str(ut.time_int(start)+cfg.BLOCK_DURATION)
            iprint(f"{start}-{endtime}  {simplified_taglist(inouts)}")

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
        COLOUR_LETTERS
        NORMAL_TAGS
        OVERSIZE_TAGS
    """
    # FIXME: this is long and could get broken up with helper functions
    rightnow = ut.get_time()
    as_of_when = (args + [rightnow])[0]

    # What time will this audit report reflect?
    as_of_when = ut.time_str(as_of_when)
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
        if tag in NORMAL_TAGS:
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
    prefixes_on_hand = ut.tags_by_prefix(bikes_on_hand.keys())
    prefixes_returned_out = ut.tags_by_prefix(check_outs_to_now.keys())
    returns_by_colour = {}
    for prefix,numbers in prefixes_returned_out.items():
        colour_code = prefix[:-1]   # prefix without the tag_letter
        if colour_code not in returns_by_colour:
            returns_by_colour[colour_code] = len(numbers)
        else:
            returns_by_colour[colour_code] += len(numbers)

    # Audit report header.
    print()
    iprint(f"Audit report as at {ut.pretty_time(as_of_when,trim=True)}",
           style=cfg.TITLE_STYLE)
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
    iprint(f"Bikes still in valet at {as_of_when}",style=cfg.SUBTITLE_STYLE)
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
                f"{COLOUR_LETTERS[colour_code].title()}, ")
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

def csv_dump(args) -> None:
    """Dump a few stats into csv for pasting into spreadsheets."""
    filename = (args + [None])[0]
    if not filename:
        ##iprint("usage: csv <filename>",style=cfg.WARNING_STYLE)
        iprint("Printing to screen.",style=cfg.WARNING_STYLE)

    def time_hrs(atime) -> str:
        """Return atime (str or int) as a string of decimal hours."""
        hrs = ut.time_int(atime) / 60
        return f"{hrs:0.3}"
    as_of_when = "24:00"

    events = calc_events(as_of_when)
    # detailed fullness
    print()
    print("Time, Regular, Oversize, Total")
    for atime in sorted(events.keys()):
        ev = events[atime]
        print(f"{time_hrs(atime)},{ev.num_here_regular},"
              f"{ev.num_here_oversize},{ev.num_here_total}")

    # block, ins, outs, num_bikes_here
    blocks_ins = dict(zip(
        Block.timeblock_list(as_of_when),
        [0 for _ in range(0,100)]))
    blocks_outs = blocks_ins.copy()
    blocks_heres = blocks_ins.copy()
    for atime, ev in events.items():
        start = Block.block_start(atime) # Which block?
        blocks_ins[start] += ev.num_ins
        blocks_outs[start] += ev.num_outs
    prev_here = 0
    for atime in sorted(blocks_heres.keys()):
        blocks_heres[atime] = prev_here + blocks_ins[atime] - blocks_outs[atime]
        prev_here = blocks_heres[atime]
    print()
    print("Time period,Incoming,Outgoing,At Valet")
    for atime in sorted(blocks_ins.keys()):
        print( f"{atime},{blocks_ins[atime]},{blocks_outs[atime]},{blocks_heres[atime]}")
    print()

    # stay_start(hrs),duration(hrs),stay_end(hrs)
    visits = calc_visits(as_of_when)    # keyed by tag
    # make list of stays keyed by start time
    visits_by_start = {}
    for v in visits.values():
        start = v.time_in
        if start not in visits_by_start:
            visits_by_start[start] = []
        visits_by_start[start].append(v)
    print()
    print("Sequence, Start time, Length of stay")
    seq = 1
    for atime in sorted(visits_by_start.keys()):
        for v in visits_by_start[atime]:
            print(f"{seq},{time_hrs(v.time_in)},"
                  f"{time_hrs(v.duration)}")
            seq += 1

def tag_check(tag:ut.Tag) -> None:
    """Check a tag in or out.

    This processes a prompt that's just a tag ID.
    """
    def print_inout(tag:str, inout:str) -> None:
        """Pretty-print a tag-in or tag-out message."""
        if inout == ut.BIKE_IN:
            msg1 = f"Bike {tag} checked IN "
            msg2 = "" # f"bike #{len(check_ins)}"
        elif inout == ut.BIKE_OUT:
            msg1 = f"Bike {tag} checked OUT                "
            msg2 = ""   # Saying duration might have been confusing
            ##duration = ut.pretty_time(
            ##        ut.time_int((check_outs[tag]) - ut.time_int((check_ins[tag]),
            ##        trim=True)
            ##msg2 = f"at valet for {duration}h"
        else:
            iprint(f"PROGRAM ERROR: called print_inout({tag}, {inout})",
                   style=cfg.ERROR_STYLE)
            return
        # Print
        msg1 = text_style(f"  {msg1}  ",style=cfg.ANSWER_STYLE)
        if msg2:
            msg2 = text_style(f"({msg2})",style=cfg.NORMAL_STYLE)
        iprint( f"{ut.pretty_time(ut.get_time(),trim=False)} {msg1} {msg2}")

    if tag in RETIRED_TAGS: # if retired print specific retirement message
        iprint(f"{tag} is retired", style=cfg.WARNING_STYLE)
    else: # must not be retired so handle as normal
        if tag in check_ins:
            if tag in check_outs:# if tag has checked in & out
                query_tag([tag])
                iprint(f"Overwrite {check_outs[tag]} check-out with "
                       f"current time ({ut.get_time()})? "
                       f"(y/N) {cfg.CURSOR}",
                       style=cfg.SUBPROMPT_STYLE, end="")
                sure = input() in ["y","yes"]
                if sure:
                    edit_entry([tag, 'o', ut.get_time()])
                else:
                    iprint("Cancelled",style=cfg.WARNING_STYLE)
            else:# checked in only
                now_mins = ut.time_int(ut.get_time())
                check_in_mins = ut.time_int(check_ins[tag])
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
                    check_outs[tag] = ut.get_time()# check it out
                    print_inout(tag,inout=ut.BIKE_OUT)
                    ##iprint(f"{tag} returned OUT",style=cfg.ANSWER_STYLE)
                else:
                    iprint("Cancelled return bike out",style=cfg.WARNING_STYLE)
        else:# if string is in neither dict
            check_ins[tag] = ut.get_time()# check it in
            print_inout(tag,ut.BIKE_IN)
            ##iprint(f"{tag} checked IN",style=cfg.ANSWER_STYLE)

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
    command = ut.fix_tag(input_tokens[0], must_be_in=ALL_TAGS,uppercase=UC_TAGS)
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
        prompt_str = text_style(f"Bike tag or command {cfg.CURSOR}",
                cfg.PROMPT_STYLE)
        if cfg.INCLUDE_TIME_IN_PROMPT:
            prompt_str = f"{ut.pretty_time(ut.get_time(),trim=True)}  {prompt_str}"
        print()
        user_str = input(prompt_str)
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
            recent(args)
        elif cmd == cfg.CMD_QUERY:
            query_tag(args)
        elif cmd == cfg.CMD_STATS:
            day_end_report(args)
        elif cmd == cfg.CMD_MORE_STATS:
            more_stats_report(args)
        elif cmd == cfg.CMD_CSV:
            csv_dump(args)
        elif cmd == cfg.CMD_VALET_HOURS:
            set_valet_hours(args)
            data_dirty = True
        elif cmd == cfg.CMD_UPPERCASE or cmd == cfg.CMD_LOWERCASE:
            set_tag_case(cmd == cfg.CMD_UPPERCASE)
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
            save()
            data_dirty = False

def save():
    """Save today's data in the datafile."""
    ut.rotate_log(LOG_FILEPATH)
    day = ut.TrackerDay()
    day.bikes_in = VALET_DATE
    day.opening_time = VALET_OPENS
    day.closing_time = VALET_CLOSES
    day.bikes_in = check_ins
    day.bikes_out = check_outs
    day.regular = NORMAL_TAGS
    day.oversize = OVERSIZE_TAGS
    ut.write_datafile(LOG_FILEPATH, day)

def error_exit() -> None:
    """If an error has occurred, give a message and shut down.

    Any specific info about the error should already have been printed.
    """
    print()
    iprint("Closing in 30 seconds",style=cfg.ERROR_STYLE)
    time.sleep(30)
    exit()

def datafile_name() -> str:
    """Return the name of the data file (datafile) to read/write."""
    if len(sys.argv) <= 1:
        # Use default filename
        return f"logs/{cfg.LOG_BASENAME}{ut.get_date()}.log"

    # Custom datafile name or location
    file = sys.argv[1]
    # File there?
    if not os.path.exists(file):
        iprint(f"Error: File {file} not found",style=cfg.ERROR_STYLE)
        error_exit()

    # This is the custom datafile & it exists
    return file

def fold_tags_case(uppercase:bool):
    """Change main data structures to uppercase or lowercase."""
    global NORMAL_TAGS, OVERSIZE_TAGS, RETIRED_TAGS # pylint: disable=global-statement
    global ALL_TAGS, check_ins, check_outs # pylint: disable=global-statement
    if uppercase:
        NORMAL_TAGS = [t.upper() for t in NORMAL_TAGS]
        OVERSIZE_TAGS = [t.upper() for t in OVERSIZE_TAGS]
        RETIRED_TAGS = [t.upper() for t in RETIRED_TAGS]
        ALL_TAGS = [t.upper() for t in ALL_TAGS]
        check_ins = {k.upper(): v for k,v in check_ins.items()}
        check_outs = {k.upper(): v for k,v in check_outs.items()}
    else:
        NORMAL_TAGS = [t.lower() for t in NORMAL_TAGS]
        OVERSIZE_TAGS = [t.lower() for t in OVERSIZE_TAGS]
        RETIRED_TAGS = [t.lower() for t in RETIRED_TAGS]
        ALL_TAGS = [t.lower() for t in ALL_TAGS]
        check_ins = {k.lower(): v for k,v in check_ins.items()}
        check_outs = {k.lower(): v for k,v in check_outs.items()}

def set_tag_case(want_uppercase:bool) -> None:
    """Set tags to be uppercase or lowercase depending on 'command'."""
    global UC_TAGS # pylint: disable=global-statement
    case_str = "upper case" if want_uppercase else "lower case"
    if UC_TAGS == want_uppercase:
        iprint(f"Tags already {case_str}.",style=cfg.WARNING_STYLE)
        return
    UC_TAGS = want_uppercase
    fold_tags_case(UC_TAGS)
    iprint(f" Tags will now show in {case_str}. ", style=cfg.ANSWER_STYLE)

# STARTUP

# Tags uppercase or lowercase?
UC_TAGS = cfg.TAGS_UPPERCASE_DEFAULT

# These are the master dictionaries for tag status
# and are read and written globally.
#   key = canonical tag id (e.g. "wf4")
#   value = ISO8601 event time (e.g. "08:43" as str)
check_ins = {}
check_outs = {}
# Lists of tag ids of various categories
NORMAL_TAGS   = ut.build_tags_config('normal_tags.cfg')
OVERSIZE_TAGS = ut.build_tags_config('oversize_tags.cfg')
RETIRED_TAGS  = ut.build_tags_config('retired_tags.cfg')

ALL_TAGS = NORMAL_TAGS + OVERSIZE_TAGS
COLOUR_LETTERS = ut.build_colour_dict("tag_colour_abbreviations.cfg")
LOG_FILEPATH = datafile_name()

if __name__ == "__main__":

    print()
    print(text_style(f"TagTracker {ut.get_version()} by Julias Hocking",
            style=cfg.ANSWER_STYLE))
    print()
    # Configure check in- and out-lists and operating hours
    if not initialize_today(): # only run main() if tags read successfully
        error_exit()

    # Flip everything uppercase (or lowercase)
    fold_tags_case(UC_TAGS)

    if not VALET_DATE:
        VALET_DATE = deduce_valet_date(VALET_DATE,LOG_FILEPATH)

    if not VALET_OPENS or not VALET_CLOSES:
        print()
        iprint("Please enter today's opening/closing times.",
            style=cfg.ERROR_STYLE)
        set_valet_hours([VALET_OPENS,VALET_CLOSES])
    valet_logo()
    main()

#==========================================
