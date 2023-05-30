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
from typing import Union  # This is for type hints instead of (eg) int|str

# The readline module magically solves arrow keys creating ANSI esc codes
# on the Chromebook.  But it isn't on all platforms.
try:
    import readline # pylint:disable=unused-import
except ImportError:
    pass

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
import tt_util as ut
import tt_event
import tt_trackerday
import tt_visit
import tt_config as cfg
import tt_printer as pr
import tt_datafile as df

# Initialize valet open/close globals
# (These are all represented in TrackerDay attributes or methods)
VALET_OPENS = ""
VALET_CLOSES = ""
VALET_DATE = ""
NORMAL_TAGS = []
OVERSIZE_TAGS = []
RETIRED_TAGS = []
ALL_TAGS = []
COLOUR_LETTERS = {}
check_ins = {}
check_outs = {}


def simplified_taglist(tags: Union[list[ut.Tag], str]) -> str:
    """Make a simplified str of tag names from a list of tags.

    E.g. "wa0,2-7,9 wb1,9,10 be4"
    The tags list can be a string separated by whitespace or comma.
    or it can be a list of tags.
    """

    def hyphenize(nums: list[int]) -> str:
        """Convert a list of ints into a hypenated list."""
        # Warning: dark magic.
        # Build lists of sequences from the sorted list.
        # starts is list of starting values of sequences.
        # ends is matching list of ending values.
        # singles is list of ints that are not part of sequences.
        nums_set = set(nums)
        starts = [x for x in nums_set if x - 1 not in nums_set and x + 1 in nums_set]
        startset = set(starts)
        ends = [
            x
            for x in nums_set
            if x - 1 in nums_set and x + 1 not in nums_set and x not in startset
        ]
        singles = [
            x for x in nums_set if x - 1 not in nums_set and x + 1 not in nums_set
        ]
        # Build start & end into dictionary, rejecting any sequences
        # shorter than an arbitrary shortest length
        min_len = 3
        seqs = {}  # key = int start; value = str representing the sequence
        for start, end in zip(starts, ends):
            if (end - start) >= (min_len - 1):
                seqs[start] = f"{start}-{end}"
            else:
                # Too short, convert to singles
                singles = singles + list(range(start, end + 1))
        # Add the singles to the seqs dict
        for num in singles:
            seqs[num] = f"{num}"
        # Return the whole thing as a comma-joined string
        return ",".join([seqs[n] for n in sorted(seqs.keys())])

    if isinstance(tags, str):
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
        ##simplified_list.append(f"{prefix}" +
        ##        (",".join([str(num) for num in sorted(tag_prefixes[prefix])])))
        simplified_list.append(f"{prefix}{hyphenize(tag_prefixes[prefix])}")
    # Return all of these joined together
    simple_str = " ".join(simplified_list)
    simple_str = simple_str.upper() if UC_TAGS else simple_str.lower()
    return simple_str


def num_bikes_at_valet(as_of_when: Union[ut.Time, int] = None) -> int:
    """Return count of bikes at the valet as of as_of_when."""
    as_of_when = ut.time_str(as_of_when)
    if not as_of_when:
        as_of_when = ut.get_time()
    # Count bikes that came in & by the given time, and the diff
    num_in = len([t for t in check_ins.values() if t <= as_of_when])
    num_out = len([t for t in check_outs.values() if t <= as_of_when])
    return max(0, num_in - num_out)


def later_events_warning(when: ut.Time = "") -> None:
    """Warn about report that excludes later events.

    If  no later events, does nothing.
    """
    if not when:
        return
    # Buid the message
    later_events = pack_day_data().num_later_events(when)
    if not later_events:
        return
    msg = (
        f"Report excludes {later_events} events later than "
        f"{ut.pretty_time(when,trim=True)}"
    )
    pr.iprint(msg, style=pr.WARNING_STYLE)


def valet_logo():
    """Print a cute bike valet logo using unicode."""
    UL = chr(0x256D)
    VR = chr(0x2502)
    HR = chr(0x2500)
    UR = chr(0x256E)
    LL = chr(0x2570)
    LR = chr(0x256F)
    BL = " "
    LOCK00 = chr(0x1F512)
    BIKE00 = chr(0x1F6B2)
    SCOOTR = chr(0x1F6F4)

    ln1 = f"{BL}{UL}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{UR}"
    ln2 = f"{BL}{VR}{BL}{BIKE00}{BIKE00}{SCOOTR}{BIKE00}{BL}{VR}"
    ln3 = f"{LOCK00}{BL}{BIKE00}{BIKE00}{BIKE00}{SCOOTR}{BL}{VR}"
    ln4 = f"{BL}{LL}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{LR}"

    WHATSTYLE = pr.ANSWER_STYLE

    pr.iprint()
    pr.iprint(f"            {ln1}             ", style=WHATSTYLE)
    pr.iprint(f"   FREE     {ln2}     BIKE    ", style=WHATSTYLE)
    pr.iprint(f"   SAFE     {ln3}     VALET   ", style=WHATSTYLE)
    pr.iprint(f"            {ln4}             ", style=WHATSTYLE)
    pr.iprint()



def fix_2400_events() -> list[ut.Tag]:
    """Change any 24:00 events to 23:59, warn, return Tags changed."""
    changed = []
    for tag, atime in check_ins.items():
        if atime == "24:00":
            check_ins[tag] = "23:59"
            changed.append(tag)
    for tag, atime in check_outs.items():
        if atime == "24:00":
            check_outs[tag] = "23:59"
            changed.append(tag)
    changed = list(set(changed))  # Remove duplicates.
    if changed:
        pr.iprint(
            f"(Time for {simplified_taglist(changed)} adjusted to 23:59)",
            style=pr.WARNING_STYLE,
        )
    return changed


def deduce_valet_date(current_guess: str, filename: str) -> str:
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
        return f"{int(r.group(2)):04d}-{int(r.group(3)):02d}-" f"{int(r.group(4)):02d}"
    return ut.get_date()


def pack_day_data() -> tt_trackerday.TrackerDay:
    """Create a TrackerDay object loaded with today's data."""
    # Pack info into TrackerDay object
    day = tt_trackerday.TrackerDay()
    day.date = VALET_DATE
    day.opening_time = VALET_OPENS
    day.closing_time = VALET_CLOSES
    day.bikes_in = check_ins
    day.bikes_out = check_outs
    day.regular = NORMAL_TAGS
    day.oversize = OVERSIZE_TAGS
    day.retired = RETIRED_TAGS
    day.colour_letters = COLOUR_LETTERS
    day.is_uppercase = UC_TAGS
    return day


def unpack_day_data(today_data: tt_trackerday.TrackerDay) -> None:
    """Set globals from a TrackerDay data object."""
    # pylint: disable=global-statement
    global VALET_DATE, VALET_OPENS, VALET_CLOSES
    global check_ins, check_outs
    global NORMAL_TAGS, OVERSIZE_TAGS, RETIRED_TAGS
    global ALL_TAGS
    global COLOUR_LETTERS
    # pylint: enable=global-statement
    VALET_DATE = today_data.date
    VALET_OPENS = today_data.opening_time
    VALET_CLOSES = today_data.closing_time
    check_ins = today_data.bikes_in
    check_outs = today_data.bikes_out
    NORMAL_TAGS = today_data.regular
    OVERSIZE_TAGS = today_data.oversize
    RETIRED_TAGS = today_data.retired
    ALL_TAGS = NORMAL_TAGS + OVERSIZE_TAGS
    COLOUR_LETTERS = today_data.colour_letters


def initialize_today() -> bool:
    """Read today's info from logfile & maybe tags-config file."""
    # Does the file even exist? (If not we will just create it later)
    pathlib.Path(cfg.LOG_FOLDER).mkdir(exist_ok=True)  # make logs folder if missing
    if not os.path.exists(LOG_FILEPATH):
        pr.iprint(
            "No datafile for today found. Will create new datafile" f" {LOG_FILEPATH}.",
            style=pr.SUBTITLE_STYLE,
        )
        today = tt_trackerday.TrackerDay()
    else:
        # Fetch data from file; errors go into error_msgs
        pr.iprint(
            f"Reading data from {LOG_FILEPATH}...", end="", style=pr.SUBTITLE_STYLE
        )
        error_msgs = []
        today = df.read_logfile(LOG_FILEPATH, error_msgs)
        if error_msgs:
            pr.iprint()
            for text in error_msgs:
                pr.iprint(text, style=pr.ERROR_STYLE)
            return False
    # Figure out the date for this bunch of data
    if not today.date:
        today.date = deduce_valet_date(today.date, LOG_FILEPATH)
    # Find the tag reference lists (regular, oversize, etc).
    # If there's no tag reference lists, or it's today's date,
    # then fetch the tag reference lists from tags config
    if not (today.regular or today.oversize) or today.date == ut.get_date():
        tagconfig = get_taglists_from_config()
        today.regular = tagconfig.regular
        today.oversize = tagconfig.oversize
        today.retired = tagconfig.retired
        today.colour_letters = tagconfig.colour_letters
    # On success, set today's working data
    unpack_day_data(today)
    # Now do a consistency check.
    errs = pack_day_data().lint_check(strict_datetimes=False)
    if errs:
        pr.iprint()
        for msg in errs:
            pr.iprint(msg, style=pr.ERROR_STYLE)
        error_exit()
    # Done
    pr.iprint("done.", num_indents=0, style=pr.SUBTITLE_STYLE)
    if VALET_DATE != ut.get_date():
        pr.iprint(
            f"Warning: Valet information is from {ut.long_date(VALET_DATE)}",
            style=pr.WARNING_STYLE,
        )
    return True



def bike_check_ins_report(as_of_when: ut.Time) -> None:
    """Print the check-ins count part of the summary statistics.

    as_of_when is HH:MM time, assumed to be a correct time.
    """
    # Find the subset of check-ins at or before our cutoff time.
    these_check_ins = {}
    for tag, atime in check_ins.items():
        if atime <= as_of_when:
            these_check_ins[tag] = atime
    # Summary stats
    num_still_here = len(
        set(these_check_ins.keys())
        - set([x for x in check_outs if check_outs[x] <= as_of_when])
    )
    num_bikes_ttl = len(these_check_ins)
    these_checkins_am = [x for x in these_check_ins if these_check_ins[x] < "12:00"]
    num_bikes_am = len(these_checkins_am)
    num_bikes_regular = len([x for x in these_check_ins if x in NORMAL_TAGS])
    num_bikes_oversize = len([x for x in these_check_ins if x in OVERSIZE_TAGS])

    pr.iprint()
    pr.iprint("Bike check-ins", style=pr.SUBTITLE_STYLE)
    pr.iprint(f"Total bikes in:   {num_bikes_ttl:4d}")
    pr.iprint(f"AM bikes in:      {num_bikes_am:4d}")
    pr.iprint(f"PM bikes in:      {(num_bikes_ttl - num_bikes_am):4d}")
    pr.iprint(f"Regular in:       {num_bikes_regular:4d}")
    pr.iprint(f"Oversize in:      {num_bikes_oversize:4d}")
    pr.iprint(f"Bikes still here: {num_still_here:4d}")


def visit_lengths_by_category_report(visits: dict) -> None:
    """Report number of visits in different length categories."""

    def one_range(lower: float = None, upper: float = None) -> None:
        """Calculate and print visits in range lower:upper.

        If lower is missing, uses anything below upper
        If upper is missing, uses anything above lower
        """
        noun = "Stay"
        if not lower and not upper:
            pr.iprint(
                f"PROGRAM ERROR: called one_range(lower='{lower}'," f"upper='{upper}')",
                style=pr.ERROR_STYLE,
            )
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
            if v.duration >= lower * 60 and v.duration < upper * 60:
                num += 1
        pr.iprint(f"{header:18s}{num:4d}")

    pr.iprint()
    pr.iprint("Number of stays by duration", style=pr.SUBTITLE_STYLE)
    prev_boundary = None
    for boundary in cfg.VISIT_CATEGORIES:
        one_range(lower=prev_boundary, upper=boundary)
        prev_boundary = boundary
    one_range(lower=prev_boundary, upper=None)


def visit_statistics_report(visits: dict) -> None:
    """Max, min, mean, median, mode of visits."""
    noun = "stay"

    def one_line(key: str, value: str) -> None:
        """Print one line."""
        pr.iprint(f"{key:17s}{value}", style=pr.NORMAL_STYLE)

    def visits_mode(durations_list: list[int]) -> None:
        """Calculat and print the mode info."""
        # Find the mode value(s), with visit durations rounded
        # to nearest ROUND_TO_NEAREST time.
        rounded = [
            round(x / cfg.MODE_ROUND_TO_NEAREST) * cfg.MODE_ROUND_TO_NEAREST
            for x in durations_list
        ]
        modes_str = ",".join(
            [ut.pretty_time(x, trim=False) for x in statistics.multimode(rounded)]
        )
        modes_str = (
            f"{modes_str}  (times " f"rounded to {cfg.MODE_ROUND_TO_NEAREST} minutes)"
        )
        one_line("Mode stay:", modes_str)

    def make_tags_str(tags: list[ut.Tag]) -> str:
        """Make a 'list of tags' string that is sure not to be too long."""
        tagstr = "tag: " if len(tags) == 1 else "tags: "
        tagstr = tagstr + ",".join(tags)
        if len(tagstr) > 30:
            tagstr = f"{len(tags)} tags"
        return tagstr

    # Make a dict of stay-lengths with list tags (for longest/shortest).
    duration_tags = {}
    for tag, v in visits.items():
        dur = v.duration
        if dur not in duration_tags:
            duration_tags[dur] = []
        duration_tags[dur].append(tag)
    if not duration_tags:
        return  # No durations
    pr.iprint()
    pr.iprint("Stay-length statistics", style=pr.SUBTITLE_STYLE)
    longest = max(list(duration_tags.keys()))
    long_tags = make_tags_str(duration_tags[longest])
    shortest = min(list(duration_tags.keys()))
    short_tags = make_tags_str(duration_tags[shortest])
    one_line(f"Longest {noun}:", f"{ut.pretty_time((longest))}  ({long_tags})")
    one_line(f"Shortest {noun}:", f"{ut.pretty_time((shortest))}  ({short_tags})")
    # Make a list of stay-lengths (for mean, median, mode)
    durations_list = [x.duration for x in visits.values()]
    one_line(f"Mean {noun}:", ut.pretty_time(statistics.mean(durations_list)))
    one_line(
        f"Median {noun}:", ut.pretty_time(statistics.median(list(duration_tags.keys())))
    )
    visits_mode(durations_list)


def highwater_report(events: dict) -> None:
    """Make a highwater table as at as_of_when."""
    # High-water mark for bikes in valet at any one time
    def one_line(
        header: str, events: dict, atime: ut.Time, highlight_field: int
    ) -> None:
        """Print one line for highwater_report."""
        values = [
            events[atime].num_here_regular,
            events[atime].num_here_oversize,
            events[atime].num_here_total,
        ]
        line = f"{header:15s}"
        for num, val in enumerate(values):
            bit = f"{val:3d}"
            if num == highlight_field:
                bit = pr.text_style(bit, style=pr.HIGHLIGHT_STYLE)
            line = f"{line}   {bit}"
        pr.iprint(f"{line}    {atime}")

    # Table header
    pr.iprint()
    pr.iprint("Most bikes at valet at any one time", style=pr.SUBTITLE_STYLE)
    if not events:
        pr.iprint("(No bikes)")
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
        if events[atime].num_here_regular >= max_regular_num and not max_regular_time:
            max_regular_time = atime
        if (
            events[atime].num_here_oversize >= max_oversize_num
            and not max_oversize_time
        ):
            max_oversize_time = atime
        if events[atime].num_here_total >= max_total_num and not max_total_time:
            max_total_time = atime
    pr.iprint("                 Reglr OvrSz Total WhenAchieved")
    one_line("Most regular:", events, max_regular_time, 0)
    one_line("Most oversize:", events, max_oversize_time, 1)
    one_line("Most combined:", events, max_total_time, 2)


def busy_report(events: dict[ut.Time, tt_event.Event], as_of_when: ut.Time) -> None:
    """Report the busiest time(s) of day."""

    def one_line(rank: int, num_events: int, times: list[ut.Time]) -> None:
        """Format and print one line of busyness report."""
        pr.iprint(f"{rank:2d}     {num_events:3d}      ", end="")
        for time_num, start_time in enumerate(sorted(times), start=1):
            end_time = ut.time_str(ut.time_int(start_time) + cfg.BLOCK_DURATION)
            print(
                f"{ut.pretty_time(start_time,trim=True)}-"
                f"{ut.pretty_time(end_time,trim=True)}",
                end="",
            )
            if time_num < len(times):
                print(", ", end="")
        pr.iprint()

    # Make an empty dict of busyness of timeblocks.
    blocks = dict(zip(Block.timeblock_list(as_of_when), [0 for _ in range(0, 100)]))
    # Count actions in each timeblock
    for atime, ev in events.items():
        start = Block.block_start(atime)  # Which block?
        blocks[start] += ev.num_ins + ev.num_outs
    # Make a dict of busynesses with list of timeblocks for each.
    busy_times = {}
    for atime, activity in blocks.items():
        if activity not in busy_times:
            busy_times[activity] = []
        busy_times[activity].append(atime)
    # Report the results.
    pr.iprint()
    pr.iprint("Busiest times of day", style=pr.SUBTITLE_STYLE)
    pr.iprint("Rank  Ins&Outs  When")
    for rank, activity in enumerate(sorted(busy_times.keys(), reverse=True), start=1):
        if rank > cfg.BUSIEST_RANKS:
            break
        one_line(rank, activity, busy_times[activity])


def qstack_report(visits: dict[ut.Tag : tt_visit.Visit]) -> None:
    """Report whether visits are more queue-like or more stack-like."""
    # Make a list of tuples: start_time, end_time for all visits.
    visit_times = list(
        zip(
            [vis.time_in for vis in visits.values()],
            [vis.time_out for vis in visits.values()],
        )
    )
    ##ut.squawk( f"{len(list(visit_times))=}")
    ##ut.squawk( f"{list(visit_times)=}")
    queueish = 0
    stackish = 0
    neutralish = 0
    visit_compares = 0
    total_possible_compares = int((len(visit_times) * (len(visit_times) - 1)) / 2)

    for time_in, time_out in visit_times:
        earlier_visits = [
            (tin, tout)
            for (tin, tout) in visit_times
            if tin < time_in and tout > time_in
        ]
        visit_compares += len(earlier_visits)
        for earlier_out in [v[1] for v in earlier_visits]:
            if earlier_out < time_out:
                queueish += 1
            elif earlier_out > time_out:
                stackish += 1
            else:
                neutralish += 1

    print("")
    pr.iprint("Were today's stays more queue-like or stack-like?",
        style=pr.SUBTITLE_STYLE,
    )
    if not queueish and not stackish:
        pr.iprint("Unable to determine.")
        return
    neutralish = total_possible_compares - queueish - stackish
    queue_proportion = queueish / (queueish + stackish + neutralish)
    stack_proportion = stackish / (queueish + stackish + neutralish)
    pr.iprint(
        f"The {total_possible_compares} compares of today's {len(visits)} "
        "stays are:"
    )
    pr.iprint(
        f"{(queue_proportion):0.3f} queue-like (overlapping stays)",
        num_indents=2,
    )
    pr.iprint(
        f"{(stack_proportion):0.3f} stack-like (nested stays)",
        num_indents=2,
    )
    pr.iprint(
        f"{((1 - stack_proportion - queue_proportion)):0.3f} neither "
        "(disjunct stays, or share a check-in or -out time)",
        num_indents=2,
    )


def day_end_report(args: list) -> None:
    """Report summary statistics about visits, up to the given time.

    If not time given, calculates as of latest checkin/out of the day.
    """
    rightnow = ut.get_time()
    as_of_when = (args + [None])[0]
    this_day = pack_day_data()
    if not as_of_when:
        as_of_when = rightnow
    else:
        as_of_when = ut.time_str(as_of_when, allow_now=True)
        if not (as_of_when):
            pr.iprint(
                f"Unrecognized time passed to visits summary ({args[0]})",
                style=pr.WARNING_STYLE,
            )
            return
    pr.iprint()
    pr.iprint(
        f"Summary statistics as at {ut.pretty_time(as_of_when,trim=True)}",
        style=pr.TITLE_STYLE,
    )
    later_events_warning(as_of_when)
    if not this_day.latest_event(as_of_when):
        pr.iprint(f"No bikes checked in by {as_of_when}", style=pr.SUBTITLE_STYLE)
        return
    # Bikes in, in various categories.
    bike_check_ins_report(as_of_when)
    # Stats that use visits (stays)
    visits = tt_visit.calc_visits(as_of_when)
    visit_lengths_by_category_report(visits)
    visit_statistics_report(visits)


def more_stats_report(args: list) -> None:
    """Report more summary statistics about visits, up to the given time.

    If not time given, calculates as of latest checkin/out of the day.
    """
    # rightnow = ut.get_time()
    as_of_when = (args + [None])[0]
    as_of_when = ut.time_str(as_of_when, allow_now=True, default_now=True)
    if not (as_of_when):
        pr.iprint("Unrecognized time", style=pr.WARNING_STYLE)
        return
    this_day = pack_day_data()
    pr.iprint()
    pr.iprint(
        f"Busyness report, as at {ut.pretty_time(as_of_when,trim=True)}",
        style=pr.TITLE_STYLE,
    )
    later_events_warning(as_of_when)
    if not this_day.latest_event(as_of_when):
        pr.iprint(f"No bikes checked in by {as_of_when}", style=pr.SUBTITLE_STYLE)
        return
    # Stats that use visits (stays)
    visits = tt_visit.calc_visits(as_of_when)
    # Dict of time (events)
    events = tt_event.calc_events(as_of_when)
    highwater_report(events)
    # Busiest times of day
    busy_report(events, as_of_when)
    # Queue-like vs stack-like
    qstack_report(visits)


def find_tag_durations(include_bikes_on_hand=True) -> ut.TagDict:
    """Make dict of tags with their stay duration in minutes.

    If include_bikes_on_hand, this will include checked in
    but not returned out.  If False, only bikes returned out.
    """
    timenow = ut.time_int(ut.get_time())
    tag_durations = {}
    for tag, in_str in check_ins.items():
        in_minutes = ut.time_int(in_str)
        if tag in check_outs:
            out_minutes = ut.time_int(check_outs[tag])
            tag_durations[tag] = out_minutes - in_minutes
        elif include_bikes_on_hand:
            tag_durations[tag] = timenow - in_minutes
    # Any bike stays that are zero minutes, arbitrarily call one minute.
    for tag, duration in tag_durations.items():
        if duration < 1:
            tag_durations[tag] = 1
    return tag_durations


def delete_entry(args: list[str]) -> None:
    """Perform tag entry deletion dialogue."""

    def arg_prompt(maybe: str, prompt: str, optional: bool = False) -> str:
        """Prompt for one command argument (token)."""
        if optional or maybe:
            maybe = "" if maybe is None else f"{maybe}".strip().lower()
            return maybe
        prompt = pr.text_style(f"{prompt} {cfg.CURSOR}", style=pr.PROMPT_STYLE)
        return input(prompt).strip().lower()

    def nogood(msg: str = "", syntax: bool = True) -> None:
        """Print the nogood msg + syntax msg."""
        if msg:
            pr.iprint(msg, style=pr.WARNING_STYLE)
        if syntax:
            pr.iprint(
                "Syntax: delete <tag> <in|out|both> <y|n|!>", style=pr.WARNING_STYLE
            )

    (maybe_target, maybe_what, maybe_confirm) = (args + ["", "", ""])[:3]
    # What tag are we to delete parts of?
    maybe_target = arg_prompt(maybe_target, "Delete entries for what tag?")
    if not maybe_target:
        nogood()
        return
    target = ut.fix_tag(maybe_target, must_be_in=ALL_TAGS, uppercase=UC_TAGS)
    if not target:
        nogood(f"'{maybe_target}' is not a tag or not a tag in use.")
        return
    if target not in check_ins:
        nogood(f"Tag {target} not checked in or out, nothing to do.", syntax=False)
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
    if what not in ["i", "in", "o", "out", "b", "both"]:
        nogood("Must indicate in, out or both")
        return
    if what in ["i", "in"] and target in check_outs:
        nogood(
            f"Bike {target} checked out.  Can't delete check-in "
            "for a returned bike without check-out too",
            syntax=False,
        )
        return
    # Get a confirmation
    confirm = arg_prompt(maybe_confirm, "Are you sure (y/N)?")
    if confirm not in ["y", "yes", "!"]:
        nogood("Delete cancelled", syntax=False)
        return
    # Perform the delete
    if what in ["b", "both", "o", "out"] and target in check_outs:
        check_outs.pop(target)
    if what in ["b", "both", "i", "in"] and target in check_ins:
        check_ins.pop(target)
    pr.iprint("Deleted.", style=pr.ANSWER_STYLE)


def retired_report() -> None:
    """List retired tags."""
    pr.iprint()
    pr.iprint("Retired tags", style=pr.SUBTITLE_STYLE)
    if not RETIRED_TAGS:
        pr.iprint("--no retired tags--")
        return
    for tag in RETIRED_TAGS:
        pr.iprint(tag, num_indents=2)


def query_tag(args: list[str]) -> None:
    """Query the check in/out times of a specific tag."""
    target = (args + [None])[0]
    if not target:  # only do dialog if no target passed
        pr.iprint(
            f"Query which tag? (tag name) {cfg.CURSOR}",
            style=pr.SUBPROMPT_STYLE,
            end="",
        )
        target = input().lower()
    pr.iprint()
    fixed_target = ut.fix_tag(target, uppercase=UC_TAGS)
    if not fixed_target:
        pr.iprint(f"'{target}' does not look like a tag name", style=pr.WARNING_STYLE)
        return
    if fixed_target in RETIRED_TAGS:
        pr.iprint(f"Tag '{fixed_target}' is retired", style=pr.ANSWER_STYLE)
        return
    if fixed_target not in ALL_TAGS:
        pr.iprint(
            f"Tag '{fixed_target}' is not available for use", style=pr.WARNING_STYLE
        )
        return
    if fixed_target not in check_ins:
        pr.iprint(f"Tag '{fixed_target}' not used yet today", style=pr.WARNING_STYLE)
        return
    pr.iprint(
        f"{ut.pretty_time(check_ins[fixed_target])}  " f"{fixed_target} checked  IN",
        style=pr.ANSWER_STYLE,
    )
    if fixed_target in check_outs:
        pr.iprint(
            f"{ut.pretty_time(check_outs[fixed_target])}  "
            f"{fixed_target} returned OUT",
            style=pr.ANSWER_STYLE,
        )
    else:
        pr.iprint(f"       {fixed_target} still at valet", style=pr.ANSWER_STYLE)


def prompt_for_time(inp=False, prompt: str = None) -> bool or ut.Time:
    """Prompt for a time input if needed.

    Helper for edit_entry(); if no time passed in, get a valid
    24h time input from the user and return an HH:MM string.
    """
    if not inp:
        if not prompt:
            prompt = "What is the correct time for this event? (HHMM or 'now')"
        pr.iprint(f"{prompt} {cfg.CURSOR}", style=pr.SUBPROMPT_STYLE, end="")
        # pr.iprint("Use 24-hour format, or 'now' to use "
        #       f"the current time ({ut.get_time()}) ",end="")
        inp = input()
    hhmm = ut.time_str(inp, allow_now=True)
    if not hhmm:
        return False
    return hhmm


def set_valet_hours(args: list[str]) -> None:
    """Set the valet opening & closing hours."""
    global VALET_OPENS, VALET_CLOSES  # pylint: disable=global-statement
    (open_arg, close_arg) = (args + ["", ""])[:2]
    pr.iprint()
    if VALET_DATE:
        pr.iprint(
            f"Bike Valet information for {ut.long_date(VALET_DATE)}",
            style=pr.HIGHLIGHT_STYLE,
        )
    # Valet opening time
    if VALET_OPENS:
        pr.iprint(f"Opening time is: {VALET_OPENS}", style=pr.HIGHLIGHT_STYLE)
    if VALET_CLOSES:
        pr.iprint(f"Closing time is: {VALET_CLOSES}", style=pr.HIGHLIGHT_STYLE)

    maybe_open = prompt_for_time(
        open_arg, prompt="New valet opening time (<Enter> to cancel)"
    )
    if not maybe_open:
        pr.iprint(
            f"Input '{open_arg}' not a time.  Opening time unchanged.",
            style=pr.WARNING_STYLE,
        )
        return
    VALET_OPENS = maybe_open
    pr.iprint(f"Opening time now set to {VALET_OPENS}", style=pr.ANSWER_STYLE)
    # Valet closing time
    maybe_close = prompt_for_time(
        close_arg, prompt="New valet closing time (<Enter> to cancel)"
    )
    if not maybe_close:
        pr.iprint(
            f"Input '{close_arg}' not a time.  Closing time unchanged.",
            style=pr.WARNING_STYLE,
        )
        return
    VALET_CLOSES = maybe_close
    pr.iprint(f"Closing time now set to {VALET_CLOSES}", style=pr.ANSWER_STYLE)


def multi_edit(args: list[str]):
    """Perform Dialog to correct a tag's check in/out time.

    Command syntax: edit [tag-list] [in|out] [time]
    Where:
        tag-list is a comma or whitespace-separated list of tags
        inout is 'in', 'i', 'out', 'o'
        time is a valid time (including 'now')
    """

    def prompt_for_stuff(prompt: str):
        pr.iprint(f"{prompt} {cfg.CURSOR}", style=pr.SUBPROMPT_STYLE, end="")
        return input().lower()

    def error(msg: str, severe: bool = True) -> None:
        if severe:
            pr.iprint(msg, style=pr.WARNING_STYLE)
        else:
            pr.iprint(msg, style=pr.HIGHLIGHT_STYLE)

    def cancel():
        error("Edit cancelled", severe=False)

    class TokenSet:
        """Local class to hold parsed portions of command."""

        def __init__(self, token_str: str) -> None:
            """Break token_str into token portions."""
            # In future this might do hyphenated tag lists
            #       - num_tokens is total of tokens in that list
            #       - add elements to taglist as long as look like tags
            #       - next element if present is INOUT
            #       - next element if present is TIME
            #       - remaining elements are REMAINDER
            parts = ut.splitline(token_str)
            self.num_tokens = len(parts)
            # FIXME: parse chunks into tags (valid tag ids), inout, atime
            self.tags = []  # valid Tags (though possibly not available)
            self.inout_str = ""  # what the user said
            self.inout_value = ut.BADVALUE  # or BIKE_IN, BIKE_OUT
            self.atime_str = ""  # What the user said
            self.atime_value = ut.BADVALUE  # A valid time, or BADVALUE
            self.remainder = []  # whatever is left (hopefully nothing)
            if self.num_tokens == 0:
                return
            # Break into tags list and other list
            done_tags = False
            for part in parts:
                tag = ut.fix_tag(part, uppercase=UC_TAGS)
                if done_tags or not tag:
                    self.remainder.append(part)
                else:
                    self.tags.append(tag)
            # Anything left over?
            if not self.remainder:
                return
            # Is next part IN/OUT?
            self.inout_str = self.remainder[0]
            self.remainder = self.remainder[1:]
            if self.inout_str.lower() in ["i", "in"]:
                self.inout_value = ut.BIKE_IN
            elif self.inout_str.lower() in ["o", "out"]:
                self.inout_value = ut.BIKE_OUT
            else:
                return
            # Anything left over?
            if not self.remainder:
                return
            # Next part a time value?
            self.atime_str = self.remainder[0]
            self.remainder = self.remainder[1:]
            atime = ut.time_str(self.atime_str, allow_now=True)
            if not atime:
                return
            self.atime_value = atime
            # All done here
            return

    def edit_processor(tag: ut.Tag, inout: str, target_time: ut.Time) -> bool:
        """Execute one edit command with all its args known.

        On entry:
            tag: is a valid tag id (though possibly not usable)
            inout: is ut.BIKE_IN or ut.BIKE_OUT
            target_time: is a valid ut.Time
        On exit, either:
            tag has been changed, msg delivered, returns True; or
            no change, error msg delivered, returns False
        """

        def success(tag: ut.Tag, inout_str: str, newtime: ut.Time) -> None:
            """Print change message. inout_str is 'in' or 'out."""
            pr.iprint(
                f"{tag} check-{inout_str} set to "
                f"{ut.pretty_time(newtime,trim=True)}",
                style=pr.ANSWER_STYLE,
            )

        # Error conditions to test for
        # Unusable tag (not known, retired)
        # For checking in:
        #   Existing Out is earler than target time
        # For checking out:
        #   Not yet checked in
        #   Existing In later than target_time
        if tag in RETIRED_TAGS:
            error(f"Tag '{tag}' is marked as retired")
            return False
        if ut.fix_tag(tag, ALL_TAGS, uppercase=UC_TAGS) != tag:
            error(f"Tag '{tag}' unrecognized or not available for use")
            return False
        if inout == ut.BIKE_IN and tag in check_outs and check_outs[tag] < target_time:
            error(f"Tag '{tag}' has check-out time earlier than {target_time}")
            return False
        if inout == ut.BIKE_OUT:
            if tag not in check_ins:
                error(f"Tag '{tag}' not checked in")
                return False
            if check_ins[tag] > target_time:
                error(
                    f"Tag '{tag}' has check-in time later than "
                    f"{ut.pretty_time(target_time,trim=True)}"
                )
                return False
        # Have checked for errors, can now commit the change
        if inout == ut.BIKE_IN:
            check_ins[tag] = target_time
            success(tag, "in", target_time)
        elif inout == ut.BIKE_OUT:
            check_outs[tag] = target_time
            success(tag, "out", target_time)
        else:
            ut.squawk(f"Bad inout in call to edit_processor: '{inout}'")
            return False
        return True

    syntax = "Syntax: edit [tag(s)] [in|out] [time|'now']"
    # Turn all the args into a string, discarding the 'edit' at the front

    argstring = " ".join(args)
    cmd = TokenSet(argstring)
    if cmd.num_tokens > 0 and not cmd.tags:
        error(f"Bad input. {syntax}")
        return
    if not cmd.tags:
        response = prompt_for_stuff("Change time for which bike tag(s)?")
        if not response:
            cancel()
            return
        argstring += " " + response
        cmd = TokenSet(argstring)
        if not cmd.tags:
            error("Bad tag values", severe=True)
            return
    # At this point we know we have tags
    while not cmd.inout_str:
        response = prompt_for_stuff("Change bike check-IN or OUT (i/o)?")
        if not response:
            cancel()
            return
        argstring += " " + response
        cmd = TokenSet(argstring)
    if cmd.inout_value not in [ut.BIKE_IN, ut.BIKE_OUT]:
        error(f"Must specify IN or OUT, not '{cmd.inout_str}'. " f"{syntax}")
        return
    # Now we know we have tags and an INOUT
    while not cmd.atime_str:
        response = prompt_for_stuff("Set to what time?")
        if not response:
            cancel()
            return
        argstring += " " + response
        cmd = TokenSet(argstring)
    if cmd.atime_value == ut.BADVALUE:
        error(f"Bad time '{cmd.atime_str}', " f"must be HHMM or 'now'. {syntax}")
        return
    # That should be the whole command, with nothing left over.
    if cmd.remainder:
        error("Bad input at end " f"'{' '.join(cmd.remainder)}'. {syntax}")
        return
    # Now we have a list of maybe-ish Tags, a usable INOUT and a usable Time
    for tag in cmd.tags:
        edit_processor(tag, cmd.inout_value, cmd.atime_value)


class Block:
    """Class to help with reporting.

    Each instance is a timeblock of duration cfg.BLOCK_DURATION.
    """

    def __init__(self, start_time: Union[ut.Time, int]) -> None:
        """Initialize. Assumes that start_time is valid."""
        if isinstance(start_time, str):
            self.start = ut.time_str(start_time)
        else:
            self.start = ut.time_str(start_time)
        self.ins_list = []  # Tags of bikes that came in.
        self.outs_list = []  # Tags of bikes returned out.
        self.num_ins = 0  # Number of bikes that came in.
        self.num_outs = 0  # Number of bikes that went out.
        self.here_list = []  # Tags of bikes in valet at end of block.
        self.num_here = 0  # Number of bikes in valet at end of block.

    @staticmethod
    def block_start(
        atime: Union[int, ut.Time], as_number: bool = False
    ) -> Union[ut.Time, int]:
        """Return the start time of the block that contains time 'atime'.

        'atime' can be minutes since midnight or HHMM.
        Returns HHMM unless as_number is True, in which case returns int.
        """
        # Get time in minutes
        atime = ut.time_int(atime) if isinstance(atime, str) else atime
        # which block of time does it fall in?
        block_start_min = (atime // BLOCK_DURATION) * BLOCK_DURATION
        if as_number:
            return block_start_min
        return ut.time_str(block_start_min)

    @staticmethod
    def block_end(
        atime: Union[int, ut.Time], as_number: bool = False
    ) -> Union[ut.Time, int]:
        """Return the last minute of the timeblock that contains time 'atime'.

        'atime' can be minutes since midnight or HHMM.
        Returns HHMM unless as_number is True, in which case returns int.
        """
        # Get block start
        start = Block.block_start(atime, as_number=True)
        # Calculate block end
        end = start + BLOCK_DURATION - 1
        # Return as minutes or HHMM
        if as_number:
            return end
        return ut.time_str(end)

    @staticmethod
    def timeblock_list(as_of_when: ut.Time = None) -> list[ut.Time]:
        """Build a list of timeblocks from beg of day until as_of_when.

        Latest block of the day will be the latest timeblock that
        had any transactions at or before as_of_when.
        """
        as_of_when = as_of_when if as_of_when else ut.get_time()
        # Make list of transactions <= as_of_when
        transx = [
            x
            for x in (list(check_ins.values()) + list(check_outs.values()))
            if x <= as_of_when
        ]
        # Anything?
        if not transx:
            return []
        # Find earliest and latest block of the day
        min_block_min = Block.block_start(min(transx), as_number=True)
        max_block_min = Block.block_start(max(transx), as_number=True)
        # Create list of timeblocks for the the whole day.
        timeblocks = []
        for t in range(
            min_block_min, max_block_min + BLOCK_DURATION, BLOCK_DURATION
        ):
            timeblocks.append(ut.time_str(t))
        return timeblocks

    @staticmethod
    def calc_blocks(as_of_when: ut.Time = None) -> dict[ut.Time, object]:
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
        latest_time = Block.block_end(max(timeblock_list), as_number=False)
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


def recent(args: list[str]) -> None:
    """Display a look back at recent activity.

    Args are: start_time, end_time
        If no args ==> now-30, now
        If start_time but no end_time ==> start, now
        If start_time and end_time ==> start, end
    """

    def format_one(atime: str, tag: str, check_in: bool) -> str:
        """Format one line of output."""
        in_tag = tag if check_in else ""
        out_tag = "" if check_in else tag
        return f"{ut.pretty_time(atime,trim=False)}   {in_tag:<5s} {out_tag:<5s}"

    (start_time, end_time) = (args + [None, None])[:2]
    if not start_time:
        end_time = ut.get_time()
        start_time = ut.time_str(ut.time_int(end_time) - 30)
    elif not end_time:
        end_time = ut.get_time()
    else:
        start_time = ut.time_str(start_time, allow_now=True, default_now=True)
        end_time = ut.time_str(end_time, allow_now=True, default_now=True)
    # ANything we can work with?
    if not start_time or not end_time or start_time > end_time:
        pr.iprint(
            "Can not make sense of the given start/end times", style=pr.WARNING_STYLE
        )
        return
    # Print header.
    pr.iprint()
    pr.iprint(
        f"Recent activity (from {ut.pretty_time(start_time,trim=True)} "
        f"to {ut.pretty_time(end_time,trim=True)})",
        style=pr.TITLE_STYLE,
    )
    pr.iprint()
    pr.iprint("Time  BikeIn BikeOut", style=pr.SUBTITLE_STYLE)
    # Collect & print any bike-in/bike-out events in the time period.
    events = tt_event.calc_events(end_time)
    current_block_end = None
    for atime in sorted(events.keys()):
        # Ignore events outside the desired time range.
        if not (start_time <= atime <= end_time):
            continue
        # Possibly put a line between blocks of activity.
        if not current_block_end:
            current_block_end = Block.block_end(atime)
        if atime > current_block_end:
            pr.iprint(f"{ut.pretty_time(Block.block_start(atime))}-------------")
            current_block_end = Block.block_end(atime)
        # Print all the activity that happened at this time.
        for tag in sorted(events[atime].bikes_in):
            pr.iprint(format_one(atime, tag, True))
        for tag in sorted(events[atime].bikes_out):
            pr.iprint(format_one(atime, tag, False))


def dataform_report(args: list[str]) -> None:
    """Print days activity in timeblocks.

    This is to match the (paper/google) data tracking sheets.
    Single args are both optional, end_time.
    If end_time is missing, runs to current time.
    If start_time is missing, starts one hour before end_time.
    """
    end_time = (args + [None])[0]
    if not end_time:
        end_time = ut.get_time()
    end_time = ut.time_str(end_time, allow_now=True)
    if not end_time:
        pr.iprint("Unrecognized time", style=pr.WARNING_STYLE)
        return
    # Special case: allow "24:00"
    if end_time != "24:00":
        end_time = Block.block_end(end_time)
        if not (end_time):
            pr.iprint()
            pr.iprint(f"Unrecognized time {args[0]}", style=pr.WARNING_STYLE)
            return

    pr.iprint()
    pr.iprint(
        "Tracking form data from start of day until "
        f"{ut.pretty_time(end_time,trim=True)}",
        style=pr.TITLE_STYLE,
    )
    later_events_warning(end_time)
    all_blocks = Block.calc_blocks(end_time)
    if not all_blocks:
        earliest = min(list(check_ins.values()) + list(check_outs.values()))
        pr.iprint(
            f"No bikes came in before {end_time} " f"(earliest came in at {earliest})",
            style=pr.HIGHLIGHT_STYLE,
        )
        return
    for which in [ut.BIKE_IN, ut.BIKE_OUT]:
        titlebit = "checked IN" if which == ut.BIKE_IN else "returned OUT"
        title = f"Bikes {titlebit}"
        pr.iprint()
        pr.iprint(title, style=pr.SUBTITLE_STYLE)
        pr.iprint("-" * len(title), style=pr.SUBTITLE_STYLE)
        for start, block in all_blocks.items():
            inouts = block.ins_list if which == ut.BIKE_IN else block.outs_list
            end = Block.block_end(start)
            pr.iprint(f"{start}-{end}  {simplified_taglist(inouts)}")


def audit_report(args: list[str]) -> None:
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
    as_of_when = (args + [""])[0]
    as_of_when = ut.time_str(as_of_when, allow_now=True, default_now=True)

    # What time will this audit report reflect?
    as_of_when = ut.time_str(as_of_when)
    if not as_of_when:
        pr.iprint("Unrecognized time", style=pr.WARNING_STYLE)
        return False

    # Get rid of any check-ins or -outs later than the requested time.
    # (Yes I know there's a slicker way to do this but this is nice and clear.)
    check_ins_to_now = {}
    for tag, ctime in check_ins.items():
        if ctime <= as_of_when:
            check_ins_to_now[tag] = ctime
    check_outs_to_now = {}
    for tag, ctime in check_outs.items():
        if ctime <= as_of_when:
            check_outs_to_now[tag] = ctime
    bikes_on_hand = {}
    for tag, ctime in check_ins_to_now.items():
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
    for prefix, numbers in prefixes_returned_out.items():
        colour_code = prefix[:-1]  # prefix without the tag_letter
        if colour_code not in returns_by_colour:
            returns_by_colour[colour_code] = len(numbers)
        else:
            returns_by_colour[colour_code] += len(numbers)

    # Audit report header.
    pr.iprint()
    pr.iprint(
        f"Audit report as at {ut.pretty_time(as_of_when,trim=True)}",
        style=pr.TITLE_STYLE,
    )
    later_events_warning(as_of_when)

    # Audit summary section.
    pr.iprint()
    pr.iprint("Summary             Regular Oversize Total", style=pr.SUBTITLE_STYLE)
    pr.iprint(
        f"Bikes checked in:     {normal_in:4d}    {oversize_in:4d}" f"    {sum_in:4d}"
    )
    pr.iprint(
        f"Bikes returned out:   {normal_out:4d}    {oversize_out:4d}"
        f"    {sum_out:4d}"
    )
    pr.iprint(
        f"Bikes in valet:       {(normal_in-normal_out):4d}"
        f"    {(oversize_in-oversize_out):4d}    {sum_total:4d}"
    )
    if sum_total != num_bikes_on_hand:
        pr.iprint(
            "** Totals mismatch, expected total "
            f"{num_bikes_on_hand} != {sum_total} **",
            style=pr.ERROR_STYLE,
        )

    # Tags matrixes
    no_item_str = "  "  # what to show when there's no tag
    pr.iprint()
    # Bikes returned out -- tags matrix.
    pr.iprint(f"Bikes still in valet at {as_of_when}", style=pr.SUBTITLE_STYLE)
    for prefix in sorted(prefixes_on_hand.keys()):
        numbers = prefixes_on_hand[prefix]
        line = f"{prefix.upper():3>} "
        for i in range(0, max(numbers) + 1):
            s = f"{i:02d}" if i in numbers else no_item_str
            line = f"{line} {s}"
        pr.iprint(line)
    if not prefixes_on_hand:
        pr.iprint("-no bikes-")
    pr.iprint()

    # Bikes returned out -- tags matrix.
    bikes_out_title = "Bikes returned out ("
    for colour_code in sorted(returns_by_colour.keys()):
        num = returns_by_colour[colour_code]
        bikes_out_title = (
            f"{bikes_out_title}{num} " f"{COLOUR_LETTERS[colour_code].title()}, "
        )
    bikes_out_title = f"{bikes_out_title}{sum_out} Total)"
    pr.iprint(bikes_out_title, style=pr.SUBTITLE_STYLE)
    for prefix in sorted(prefixes_returned_out.keys()):
        numbers = prefixes_returned_out[prefix]
        line = f"{prefix.upper():3>} "
        for i in range(0, max(numbers) + 1):
            s = f"{i:02d}" if i in numbers else no_item_str
            line = f"{line} {s}"
        pr.iprint(line)
    if not prefixes_returned_out:
        pr.iprint("-no bikes-")

    return


def csv_dump(args) -> None:
    """Dump a few stats into csv for pasting into spreadsheets."""
    filename = (args + [None])[0]
    if not filename:
        ##pr.iprint("usage: csv <filename>",style=pr.WARNING_STYLE)
        pr.iprint("Printing to screen.", style=pr.WARNING_STYLE)

    def time_hrs(atime) -> str:
        """Return atime (str or int) as a string of decimal hours."""
        hrs = ut.time_int(atime) / 60
        return f"{hrs:0.3}"

    as_of_when = "24:00"

    events = tt_event.calc_events(as_of_when)
    # detailed fullness
    pr.iprint()
    print("Time, Regular, Oversize, Total")
    for atime in sorted(events.keys()):
        ev = events[atime]
        print(
            f"{time_hrs(atime)},{ev.num_here_regular},"
            f"{ev.num_here_oversize},{ev.num_here_total}"
        )

    # block, ins, outs, num_bikes_here
    blocks_ins = dict(zip(Block.timeblock_list(as_of_when), [0 for _ in range(0, 100)]))
    blocks_outs = blocks_ins.copy()
    blocks_heres = blocks_ins.copy()
    for atime, ev in events.items():
        start = Block.block_start(atime)  # Which block?
        blocks_ins[start] += ev.num_ins
        blocks_outs[start] += ev.num_outs
    prev_here = 0
    for atime in sorted(blocks_heres.keys()):
        blocks_heres[atime] = prev_here + blocks_ins[atime] - blocks_outs[atime]
        prev_here = blocks_heres[atime]
    pr.iprint()
    print("Time period,Incoming,Outgoing,At Valet")
    for atime in sorted(blocks_ins.keys()):
        print(f"{atime},{blocks_ins[atime]},{blocks_outs[atime]},{blocks_heres[atime]}")
    pr.iprint()

    # stay_start(hrs),duration(hrs),stay_end(hrs)
    visits = tt_visit.calc_visits(as_of_when)  # keyed by tag
    # make list of stays keyed by start time
    visits_by_start = {}
    for v in visits.values():
        start = v.time_in
        if start not in visits_by_start:
            visits_by_start[start] = []
        visits_by_start[start].append(v)
    pr.iprint()
    print("Sequence, Start time, Length of stay")
    seq = 1
    for atime in sorted(visits_by_start.keys()):
        for v in visits_by_start[atime]:
            print(f"{seq},{time_hrs(v.time_in)}," f"{time_hrs(v.duration)}")
            seq += 1


def tag_check(tag: ut.Tag) -> None:
    """Check a tag in or out.

    This processes a prompt that's just a tag ID.
    """

    def print_inout(tag: str, inout: str) -> None:
        """Pretty-print a tag-in or tag-out message."""
        if inout == ut.BIKE_IN:
            msg1 = f"Bike {tag} checked IN {' ' * 10}<---in---  "
            msg2 = ""  # f"bike #{len(check_ins)}"
        elif inout == ut.BIKE_OUT:
            msg1 = f"Bike {tag} checked OUT {' ' * 25}---out--->  "
            msg2 = ""  # Saying duration might have been confusing
            ##duration = ut.pretty_time(
            ##        ut.time_int((check_outs[tag]) - ut.time_int((check_ins[tag]),
            ##        trim=True)
            ##msg2 = f"at valet for {duration}h"
        else:
            pr.iprint(
                f"PROGRAM ERROR: called print_inout({tag}, {inout})",
                style=pr.ERROR_STYLE,
            )
            return
        # Print
        msg1 = pr.text_style(f"{msg1}  ", style=pr.ANSWER_STYLE)
        if msg2:
            msg2 = pr.text_style(f"({msg2})", style=pr.NORMAL_STYLE)
        pr.iprint(f"{msg1} {msg2}")

    if tag in RETIRED_TAGS:  # if retired print specific retirement message
        pr.iprint(f"{tag} is retired", style=pr.WARNING_STYLE)
    else:  # must not be retired so handle as normal
        if tag in check_ins:
            if tag in check_outs:  # if tag has checked in & out
                query_tag([tag])
                pr.iprint(
                    f"Overwrite {check_outs[tag]} check-out with "
                    f"current time ({ut.get_time()})? "
                    f"(y/N) {cfg.CURSOR}",
                    style=pr.SUBPROMPT_STYLE,
                    end="",
                )
                sure = input() in ["y", "yes"]
                if sure:
                    multi_edit([tag, "o", ut.get_time()])
                else:
                    pr.iprint("Cancelled", style=pr.WARNING_STYLE)
            else:  # checked in only
                now_mins = ut.time_int(ut.get_time())
                check_in_mins = ut.time_int(check_ins[tag])
                time_diff_mins = now_mins - check_in_mins
                if time_diff_mins < cfg.CHECK_OUT_CONFIRM_TIME:  # if < 1/2 hr
                    pr.iprint(
                        "This bike checked in at "
                        f"{check_ins[tag]} ({time_diff_mins} mins ago)",
                        style=pr.SUBPROMPT_STYLE,
                    )
                    pr.iprint(
                        "Do you want to check it out? " f"(y/N) {cfg.CURSOR}",
                        style=pr.SUBPROMPT_STYLE,
                        end="",
                    )
                    sure = input().lower() in ["yes", "y"]
                else:  # don't check for long stays
                    sure = True
                if sure:
                    check_outs[tag] = ut.get_time()  # check it out
                    print_inout(tag, inout=ut.BIKE_OUT)
                    ##pr.iprint(f"{tag} returned OUT",style=pr.ANSWER_STYLE)
                else:
                    pr.iprint("Cancelled return bike out", style=pr.WARNING_STYLE)
        else:  # if string is in neither dict
            check_ins[tag] = ut.get_time()  # check it in
            print_inout(tag, ut.BIKE_IN)
            ##pr.iprint(f"{tag} checked IN",style=pr.ANSWER_STYLE)


def parse_command(user_input: str) -> list[str]:
    """Parse user's input into list of [tag] or [command, command args].

    Returns [] if not a recognized tag or command.
    """
    user_input = user_input.lower().strip()
    if not (user_input):
        return []
    # Special case - if user input starts with '/' or '?' add a space.
    if user_input[0] in ["/", "?"]:
        user_input = user_input[0] + " " + user_input[1:]
    # Split to list, test to see if tag.
    input_tokens = user_input.split()
    command = ut.fix_tag(input_tokens[0], must_be_in=ALL_TAGS, uppercase=UC_TAGS)
    if command:
        return [command]  # A tag
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


def show_help():
    """Show help_message with colour style highlighting.

    Prints first non-blank line as title;
    lines that are flush-left as subtitles;
    other lines in normal style.
    """
    title_done = False
    for line in cfg.HELP_MESSAGE.split("\n"):
        if not line:
            pr.iprint()
        elif not title_done:
            title_done = True
            pr.iprint(line, style=pr.TITLE_STYLE)
        elif line[0] != " ":
            pr.iprint(line, style=pr.SUBTITLE_STYLE)
        else:
            pr.iprint(line, style=pr.NORMAL_STYLE)


def dump_data():
    """For debugging. Dump current contents of core data structures."""
    pr.iprint()
    pr.iprint("Retired", style=pr.ANSWER_STYLE)
    print(f"{RETIRED_TAGS=}")
    pr.iprint("All Tags", style=pr.ANSWER_STYLE)
    print(f"{ALL_TAGS=}")
    pr.iprint("Regular", style=pr.ANSWER_STYLE)
    print(f"{NORMAL_TAGS=}")
    pr.iprint("Oversize", style=pr.ANSWER_STYLE)
    print(f"{OVERSIZE_TAGS=}")
    pr.iprint("Colour letters", style=pr.ANSWER_STYLE)
    print(f"{COLOUR_LETTERS=}")
    pr.iprint("Check ins", style=pr.ANSWER_STYLE)
    print(f"{check_ins=}")
    pr.iprint("Check outs", style=pr.ANSWER_STYLE)
    print(f"{check_outs=}")


def main():
    """Run main program loop and dispatcher."""
    done = False
    todays_date = ut.get_date()
    last_published = "00:00"
    while not done:
        prompt_str = pr.text_style(f"Bike tag or command {cfg.CURSOR}", pr.PROMPT_STYLE)
        if cfg.INCLUDE_TIME_IN_PROMPT:
            prompt_str = f"{ut.pretty_time(ut.get_time(),trim=True)}  {prompt_str}"
        pr.iprint()
        user_str = input(prompt_str)
        # If midnight has passed then need to restart
        if midnight_passed(todays_date):
            done = True
            continue
        # Break command into tokens, parse as command
        tokens = parse_command(user_str)
        if not tokens:
            continue  # No input, ignore
        (cmd, *args) = tokens
        # Dispatcher
        data_dirty = False
        if cmd == cfg.CMD_EDIT:
            multi_edit(args)
            data_dirty = True
        elif cmd == cfg.CMD_AUDIT:
            audit_report(args)
        elif cmd == cfg.CMD_DELETE:
            delete_entry(args)
            data_dirty = True
        elif cmd == cfg.CMD_EXIT:
            done = True
        elif cmd == cfg.CMD_BLOCK:
            dataform_report(args)
        elif cmd == cfg.CMD_HELP:
            show_help()
        elif cmd == cfg.CMD_LOOKBACK:
            recent(args)
        elif cmd == cfg.CMD_RETIRED:
            retired_report()
        elif cmd == cfg.CMD_QUERY:
            query_tag(args)
        elif cmd == cfg.CMD_STATS:
            day_end_report(args)
            # Force publication when do day-end reports
            last_published = maybe_publish(last_published, force=True)
        elif cmd == cfg.CMD_BUSY:
            more_stats_report(args)
        elif cmd == cfg.CMD_CSV:
            csv_dump(args)
        elif cmd == cfg.CMD_DUMP:
            dump_data()
        elif cmd == cfg.CMD_LINT:
            lint_report(strict_datetimes=True)
        elif cmd == cfg.CMD_VALET_HOURS:
            set_valet_hours(args)
            data_dirty = True
        elif cmd == cfg.CMD_UPPERCASE or cmd == cfg.CMD_LOWERCASE:
            set_tag_case(cmd == cfg.CMD_UPPERCASE)
        elif cmd == cfg.CMD_UNKNOWN:
            pr.iprint()
            pr.iprint(
                "Unrecognized tag or command, enter 'h' for help",
                style=pr.WARNING_STYLE,
            )
        else:
            # This is a tag
            tag_check(cmd)
            data_dirty = True
        # If anything has becomne "24:00" change it to "23:59"
        if data_dirty:
            fix_2400_events()
        # Save if anything has changed
        if data_dirty:
            data_dirty = False
            save()
            last_published = maybe_publish(last_published)


def datafile_name(folder: str) -> str:
    """Return the name of the data file (datafile) to read/write."""
    # Use default filename
    return f"{folder}/{cfg.LOG_BASENAME}{ut.get_date()}.log"


def custom_datafile() -> str:
    """Return custom datafilename from command line arg or ""."""
    if len(sys.argv) <= 1:
        return ""
    # Custom datafile name or location
    file = sys.argv[1]
    # File there?
    if not os.path.exists(file):
        pr.iprint(f"Error: File {file} not found", style=pr.ERROR_STYLE)
        error_exit()
    # This is the custom datafile & it exists
    return file


def save():
    """Save today's data in the datafile."""
    # Save .bak
    df.rotate_log(LOG_FILEPATH)
    # Pack data into a TrackerDay object to store
    day = pack_day_data()
    # Store the data
    df.write_logfile(LOG_FILEPATH, day)


ABLE_TO_PUBLISH = True


def maybe_publish(last_pub: ut.Time, force: bool = False) -> ut.Time:
    """Maybe save current log to 'publish' directory."""
    global ABLE_TO_PUBLISH  # pylint:disable=global-statement
    # Nothing to do if not configured to publish or can't publish
    if not ABLE_TO_PUBLISH or not cfg.PUBLISH_FOLDER or not cfg.PUBLISH_FREQUENCY:
        return last_pub
    # Is it time to re-publish?
    if not force and (
        ut.time_int(ut.get_time()) < (ut.time_int(last_pub) + cfg.PUBLISH_FREQUENCY)
    ):
        # Nothing to do yet.
        return last_pub
    # Nothing to do if publication dir does not exist
    if not os.path.exists(cfg.PUBLISH_FOLDER):
        ABLE_TO_PUBLISH = False
        pr.iprint()
        pr.iprint(
            f"Publication folder '{cfg.PUBLISH_FOLDER}' not found, "
            "will not try to Publish",
            style=pr.ERROR_STYLE,
        )
        return last_pub
    # Pack info into TrackerDay object, save the data
    day = pack_day_data()
    df.write_logfile(datafile_name(cfg.PUBLISH_FOLDER), day)
    # Return new last_published time
    return ut.get_time()


def error_exit() -> None:
    """If an error has occurred, give a message and shut down.

    Any specific info about the error should already have been printed.
    """
    pr.iprint()
    pr.iprint("Closing in 30 seconds", style=pr.ERROR_STYLE)
    time.sleep(30)
    exit()


def fold_tags_case(uppercase: bool):
    """Change main data structures to uppercase or lowercase."""
    # FIXME: eventually make this obj=pack(), obj.fold_case(), unpack(obj)
    #           followed by re-asserting all_tags = regular + oversize
    global NORMAL_TAGS, OVERSIZE_TAGS, RETIRED_TAGS  # pylint: disable=global-statement
    global ALL_TAGS, check_ins, check_outs  # pylint: disable=global-statement
    if uppercase:
        NORMAL_TAGS = [t.upper() for t in NORMAL_TAGS]
        OVERSIZE_TAGS = [t.upper() for t in OVERSIZE_TAGS]
        RETIRED_TAGS = [t.upper() for t in RETIRED_TAGS]
        ALL_TAGS = [t.upper() for t in ALL_TAGS]
        check_ins = {k.upper(): v for k, v in check_ins.items()}
        check_outs = {k.upper(): v for k, v in check_outs.items()}
    else:
        NORMAL_TAGS = [t.lower() for t in NORMAL_TAGS]
        OVERSIZE_TAGS = [t.lower() for t in OVERSIZE_TAGS]
        RETIRED_TAGS = [t.lower() for t in RETIRED_TAGS]
        ALL_TAGS = [t.lower() for t in ALL_TAGS]
        check_ins = {k.lower(): v for k, v in check_ins.items()}
        check_outs = {k.lower(): v for k, v in check_outs.items()}


def set_tag_case(want_uppercase: bool) -> None:
    """Set tags to be uppercase or lowercase depending on 'command'."""
    global UC_TAGS  # pylint: disable=global-statement
    case_str = "upper case" if want_uppercase else "lower case"
    if UC_TAGS == want_uppercase:
        pr.iprint(f"Tags already {case_str}.", style=pr.WARNING_STYLE)
        return
    UC_TAGS = want_uppercase
    fold_tags_case(UC_TAGS)
    pr.iprint(f" Tags will now show in {case_str}. ", style=pr.ANSWER_STYLE)


def lint_report(strict_datetimes: bool = True) -> None:
    """Check tag lists and event lists for consistency."""
    errs = pack_day_data().lint_check(strict_datetimes)
    if errs:
        for msg in errs:
            pr.iprint(msg, style=pr.WARNING_STYLE)
    else:
        pr.iprint("No inconsistencies found", style=pr.HIGHLIGHT_STYLE)
    # And while we're at it, fix up any times that are set to "24:00"
    fix_2400_events()


def midnight_passed(today_is: str) -> bool:
    """Check if it's still the same day."""
    if today_is == ut.get_date():
        return False
    # Time has rolled over past midnight so need a new datafile.
    print("\n\n\n")
    pr.iprint("Program has been running since yesterday.", style=pr.WARNING_STYLE)
    pr.iprint(
        "Please restart program to reset for today's data.", style=pr.WARNING_STYLE
    )
    pr.iprint()
    print("\n\n\n")
    print("Automatically exiting in 15 seconds")
    time.sleep(15)
    return True


def get_taglists_from_config() -> tt_trackerday.TrackerDay:
    """Read tag lists (oversize, etc) from tag config file."""
    # Lists of normal, oversize, retired tags
    # Return a TrackerDay object, though its bikes_in/out are meaningless.
    errs = []
    day = df.read_logfile(TAG_CONFIG_FILE, errs)
    if errs:
        print(f"Errors in file, {errs=}")
        error_exit()
    return day
    ##global NORMAL_TAGS, OVERSIZE_TAGS #pylint:disable=global-statement
    ##global RETIRED_TAGS #pylint:disable=global-statement
    ##NORMAL_TAGS   = day.regular
    ##OVERSIZE_TAGS = day.oversize
    ##RETIRED_TAGS  = day.retired
    ##return True


# STARTUP

# Tags uppercase or lowercase?
UC_TAGS = cfg.TAGS_UPPERCASE_DEFAULT
# Log file
LOG_FILEPATH = custom_datafile()
CUSTOM_LOG = bool(LOG_FILEPATH)
if not CUSTOM_LOG:
    LOG_FILEPATH = datafile_name(cfg.LOG_FOLDER)

if __name__ == "__main__":
    pr.iprint()
    print(
        pr.text_style(
            f"TagTracker {ut.get_version()} by Julias Hocking", style=pr.ANSWER_STYLE
        )
    )
    pr.iprint()
    # If no tags file, create one and tell them to edit it.
    if not os.path.exists(cfg.TAG_CONFIG_FILE):
        ut.new_tag_config_file(cfg.TAG_CONFIG_FILE)
        pr.iprint("No tags configuration file found.", style=pr.WARNING_STYLE)
        pr.iprint(
            f"Creating new configuration file {cfg.TAG_CONFIG_FILE}",
            style=pr.WARNING_STYLE,
        )
        pr.iprint("Edit this file then re-rerun TagTracker.", style=pr.WARNING_STYLE)
        print("\n" * 3, "Exiting automatically in 15 seconds.")
        time.sleep(15)
        exit()

    # Configure check in- and out-lists and operating hours from file
    if not initialize_today():  # only run main() if tags read successfully
        error_exit()
    lint_report(strict_datetimes=False)

    # Flip everything uppercase (or lowercase)
    fold_tags_case(UC_TAGS)

    # Get/set valet date & time
    if not VALET_OPENS or not VALET_CLOSES:
        pr.iprint()
        pr.iprint("Please enter today's opening/closing times.", style=pr.ERROR_STYLE)
        set_valet_hours([VALET_OPENS, VALET_CLOSES])
        if VALET_OPENS or VALET_CLOSES:
            save()

    valet_logo()
    main()
    # Exiting now; one last save
    save()
    maybe_publish("", force=True)
# ==========================================
