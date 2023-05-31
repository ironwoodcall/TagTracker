"""TagTracker by Julias Hocking.

Reporting functions for  the TagTracker suite.

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

import statistics
from typing import Union

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
import tt_util as ut
import tt_event
import tt_trackerday
import tt_visit
import tt_block
import tt_printer as pr

# Time ranges for categorizing stay-lengths, in hours.
# First category will always be 0 - [0], last will always be > [-1]
VISIT_CATEGORIES = [1.5, 5]

# size of 'buckets' for calculating the mode stay time
MODE_ROUND_TO_NEAREST = 30  # mins

# List ow many ranked busiest times of day in report?
BUSIEST_RANKS = 4


def recent(day: tt_trackerday.TrackerDay, args: list[str]) -> None:
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
    events = tt_event.calc_events(day, end_time)
    current_block_end = None
    for atime in sorted(events.keys()):
        # Ignore events outside the desired time range.
        if not (start_time <= atime <= end_time):
            continue
        # Possibly put a line between blocks of activity.
        if not current_block_end:
            current_block_end = tt_block.block_end(atime)
        if atime > current_block_end:
            pr.iprint(f"{ut.pretty_time(tt_block.block_start(atime))}-------------")
            current_block_end = tt_block.block_end(atime)
        # Print all the activity that happened at this time.
        for tag in sorted(events[atime].bikes_in):
            pr.iprint(format_one(atime, tag, True))
        for tag in sorted(events[atime].bikes_out):
            pr.iprint(format_one(atime, tag, False))


def later_events_warning(day: tt_trackerday.TrackerDay, when: ut.Time) -> None:
    """Warn about report that excludes later events.

    If  no later events, does nothing.
    """
    if not when:
        return
    # Buid the message
    later_events = day.num_later_events(when)
    if not later_events:
        return
    msg = (
        f"Report excludes {later_events} events later than "
        f"{ut.pretty_time(when,trim=True)}"
    )
    pr.iprint(msg, style=pr.WARNING_STYLE)


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
    ##simple_str = simple_str.upper() if UC_TAGS else simple_str.lower()
    return simple_str


def audit_report(day: tt_trackerday.TrackerDay, args: list[str]) -> None:
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
    for tag, ctime in day.bikes_in.items():
        if ctime <= as_of_when:
            check_ins_to_now[tag] = ctime
    check_outs_to_now = {}
    for tag, ctime in day.bikes_out.items():
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
        if tag in day.regular:
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
    later_events_warning(day, as_of_when)

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
            f"{bikes_out_title}{num} " f"{day.colour_letters[colour_code].title()}, "
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


def csv_dump(day: tt_trackerday.TrackerDay, args) -> None:
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

    events = tt_event.calc_events(day, as_of_when)
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
    blocks_ins = dict(
        zip(tt_block.get_timeblock_list(day,as_of_when), [0 for _ in range(0, 100)])
    )
    blocks_outs = blocks_ins.copy()
    blocks_heres = blocks_ins.copy()
    for atime, ev in events.items():
        start = tt_block.block_start(atime)  # Which block?
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
    visits = tt_visit.calc_visits(day, as_of_when)  # keyed by tag
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


def bike_check_ins_report(day: tt_trackerday.TrackerDay, as_of_when: ut.Time) -> None:
    """Print the check-ins count part of the summary statistics.

    as_of_when is HH:MM time, assumed to be a correct time.
    """
    # Find the subset of check-ins at or before our cutoff time.
    these_check_ins = {}
    for tag, atime in day.bikes_in.items():
        if atime <= as_of_when:
            these_check_ins[tag] = atime
    # Summary stats
    num_still_here = len(
        set(these_check_ins.keys())
        - set([x for x in day.bikes_out if day.bikes_out[x] <= as_of_when])
    )
    num_bikes_ttl = len(these_check_ins)
    these_checkins_am = [x for x in these_check_ins if these_check_ins[x] < "12:00"]
    num_bikes_am = len(these_checkins_am)
    num_bikes_regular = len([x for x in these_check_ins if x in day.regular])
    num_bikes_oversize = len([x for x in these_check_ins if x in day.oversize])

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
    for boundary in VISIT_CATEGORIES:
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
            round(x / MODE_ROUND_TO_NEAREST) * MODE_ROUND_TO_NEAREST
            for x in durations_list
        ]
        modes_str = ",".join(
            [ut.pretty_time(x, trim=False) for x in statistics.multimode(rounded)]
        )
        modes_str = (
            f"{modes_str}  (times " f"rounded to {MODE_ROUND_TO_NEAREST} minutes)"
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


def busy_report(
    day: tt_trackerday.TrackerDay,
    events: dict[ut.Time, tt_event.Event],
    as_of_when: ut.Time,
) -> None:
    """Report the busiest time(s) of day."""

    def one_line(rank: int, num_events: int, times: list[ut.Time]) -> None:
        """Format and print one line of busyness report."""
        pr.iprint(f"{rank:2d}     {num_events:3d}      ", end="")
        for time_num, start_time in enumerate(sorted(times), start=1):
            end_time = ut.time_str(ut.time_int(start_time) + BLOCK_DURATION)
            print(
                f"{ut.pretty_time(start_time,trim=True)}-"
                f"{ut.pretty_time(end_time,trim=True)}",
                end="",
            )
            if time_num < len(times):
                print(", ", end="")
        pr.iprint()

    # Make an empty dict of busyness of timeblocks.
    blocks = dict(
        zip(tt_block.get_timeblock_list(day, as_of_when), [0 for _ in range(0, 100)])
    )
    # Count actions in each timeblock
    for atime, ev in events.items():
        start = tt_block.block_start(atime)  # Which block?
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
        if rank > BUSIEST_RANKS:
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
    pr.iprint(
        "Were today's stays more queue-like or stack-like?",
        style=pr.SUBTITLE_STYLE,
    )
    if not queueish and not stackish:
        pr.iprint("Unable to determine.")
        return
    neutralish = total_possible_compares - queueish - stackish
    queue_proportion = queueish / (queueish + stackish + neutralish)
    stack_proportion = stackish / (queueish + stackish + neutralish)
    pr.iprint(
        f"The {total_possible_compares} compares of today's {len(visits)} " "stays are:"
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


def day_end_report(day: tt_trackerday.TrackerDay, args: list) -> None:
    """Report summary statistics about visits, up to the given time.

    If not time given, calculates as of latest checkin/out of the day.
    """
    rightnow = ut.get_time()
    as_of_when = (args + [None])[0]
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
    later_events_warning(day, as_of_when)
    if not day.latest_event(as_of_when):
        pr.iprint(f"No bikes checked in by {as_of_when}", style=pr.SUBTITLE_STYLE)
        return
    # Bikes in, in various categories.
    bike_check_ins_report(day, as_of_when)
    # Stats that use visits (stays)
    visits = tt_visit.calc_visits(day, as_of_when)
    visit_lengths_by_category_report(visits)
    visit_statistics_report(visits)


def more_stats_report(day: tt_trackerday.TrackerDay, args: list) -> None:
    """Report more summary statistics about visits, up to the given time.

    If not time given, calculates as of latest checkin/out of the day.
    """
    # rightnow = ut.get_time()
    as_of_when = (args + [None])[0]
    as_of_when = ut.time_str(as_of_when, allow_now=True, default_now=True)
    if not (as_of_when):
        pr.iprint("Unrecognized time", style=pr.WARNING_STYLE)
        return
    pr.iprint()
    pr.iprint(
        f"Busyness report, as at {ut.pretty_time(as_of_when,trim=True)}",
        style=pr.TITLE_STYLE,
    )
    later_events_warning(day, as_of_when)
    if not day.latest_event(as_of_when):
        pr.iprint(f"No bikes checked in by {as_of_when}", style=pr.SUBTITLE_STYLE)
        return
    # Stats that use visits (stays)
    visits = tt_visit.calc_visits(day,as_of_when)
    # Dict of time (events)
    events = tt_event.calc_events(day,as_of_when)
    highwater_report(events)
    # Busiest times of day
    busy_report(day, events, as_of_when)
    # Queue-like vs stack-like
    qstack_report(visits)


def retired_report(day: tt_trackerday.TrackerDay) -> None:
    """List retired tags."""
    pr.iprint()
    pr.iprint("Retired tags", style=pr.SUBTITLE_STYLE)
    if not day.retired:
        pr.iprint("--no retired tags--")
        return
    for tag in day.retired:
        pr.iprint(tag, num_indents=2)


def dataform_report(day: tt_trackerday.TrackerDay, args: list[str]) -> None:
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
        end_time = tt_block.block_end(end_time)
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
    later_events_warning(day, end_time)
    all_blocks = tt_block.calc_blocks(day, end_time)
    if not all_blocks:
        earliest = day.earliest_event()
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
            end = tt_block.block_end(start)
            tagslist = simplified_taglist(inouts)
            if day.is_uppercase:
                tagslist = tagslist.upper()
            else:
                tagslist = tagslist.lower()
            pr.iprint(f"{start}-{end}  {tagslist}")
