"""TagTracker by Julias Hocking.

Reporting functions for  the TagTracker suite.

Copyright (C) 2023-2024 Julias Hocking & Todd Glover

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

import statistics

import tt_constants as k
from tt_time import VTime
from tt_tag import TagID
# from tt_realtag import Stay
from tt_trackerday import TrackerDay, OldTrackerDay
import tt_util as ut
from tt_snapshot import Snapshot
import tt_block
import tt_printer as pr
import client_base_config as cfg
import tt_registrations as reg


# Time ranges for categorizing stay-lengths, in hours.
# First category will always be 0 - [0], last will always be > [-1]
VISIT_CATEGORIES = [1.5, 5]

# size of 'buckets' for calculating the mode stay time
MODE_ROUND_TO_NEAREST = 30  # mins

# List ow many ranked busiest times of day in report?
BUSIEST_RANKS = 4


def _events_in_period(
    day: TrackerDay, start: VTime, end: VTime
) -> list[tuple[VTime, str, str]]:
    """Make a list of all the events in a time period.

    Returns sorted list of tuples (time, tag_description, check_in):
        time: is the time of the event
        tag_description: is the TagID + a visit counter
        check_in: is True if checking in, False if checking out
    """
    event_list = []
    for biketag in day.biketags.values():
        for i, visit in enumerate(biketag.visits):
            if start <= visit.time_in <= end:
                event_list.append((visit.time_in, f"{biketag.tagid}:{i}", True))
            if visit.time_out and start <= visit.time_out <= end:
                event_list.append((visit.time_out, f"{biketag.tagid}:{i}", False))

    event_list.sort(key=lambda event: event[0])
    return event_list


def recent(day: TrackerDay, args: list[VTime]) -> None:
    """Display a look back at recent activity.

    Args are: start_time, end_time
        If no args ==> now-30, now
        If start_time but no end_time
            if start < now ==> start, now
            if start >= now ==> now, now+60
        If both start_time and end_time ==> start, end
    """

    def format_one(atime: VTime, tag: TagID, check_in: bool) -> str:
        """Format one line of output."""
        in_tag = f"{tag}" if check_in else ""
        out_tag = "" if check_in else f"{tag}"
        return f"{atime.tidy}    {in_tag:<7s}  {out_tag:<7s}"

    (start_time, end_time) = (args + [None, None])[:2]
    now = VTime("now")
    if not start_time and not end_time:
        end_time = now
        start_time = VTime(end_time.num - 30)
    elif start_time and not end_time:
        if start_time < now:
            start_time = VTime(start_time)
            end_time = now
        else:
            start_time = VTime(start_time)
            end_time = start_time.num+60
    else:
        start_time = VTime(start_time)
        end_time = VTime(end_time)
    # Anything we can work with?
    if not start_time or not end_time or start_time > end_time:
        pr.iprint(
            "Can not make sense of the given start/end times",
            style=k.WARNING_STYLE,
        )
        return
    # Print header.
    pr.iprint()
    pr.iprint(
        f"Activity (from {start_time.short} to {end_time.short})",
        style=k.TITLE_STYLE,
    )
    pr.iprint(
        "The number following the tag shows which of the tag's visits this event represents.",
        style=k.SUBTITLE_STYLE,
    )
    pr.iprint()
    pr.iprint("Time     BikeIn   BikeOut", style=k.SUBTITLE_STYLE)
    # Collect & print any bike-in/bike-out events in the time period.
    events = _events_in_period(day, start_time, end_time)

    current_block_end = None  # block ends are for putting divider lines
    for event_time, tag_desc, check_in in events:
        if not current_block_end:
            current_block_end = tt_block.block_end(event_time)
        if event_time > current_block_end:
            pr.iprint(f"{tt_block.block_start(event_time).tidy} --------------------")
            current_block_end = tt_block.block_end(event_time)
        pr.iprint(format_one(event_time, tag_desc, check_in))


def registrations_report(reg_count: int):
    """Display current count of registrations."""
    pr.iprint()
    pr.iprint("Bike registrations", style=k.SUBTITLE_STYLE)
    reg.Registrations.display_current_count(reg_count=reg_count, num_indents=2)


def later_events_warning(day: TrackerDay, when: VTime="") -> None:
    """Warn about report that excludes later events.

    If  no later events, does nothing.
    """
    when = VTime(when or "now")

    # Build the message
    later_events = day.num_later_events(when)
    if not later_events:
        return
    msg = f"Report excludes {later_events} events later than {when.short}"
    pr.iprint(msg, style=k.WARNING_STYLE)


# def simplified_taglist(tags: list[TagID] | str) -> str:
#     """Make a simplified str of tag names from a list of tags.

#     E.g. "wa0,2-7,9 wb1,9,10 be4"
#     The tags list can be a string separated by whitespace or comma.
#     or it can be a list of tags.
#     """

#     # FIXME: not adjusting this one to VTime/TagID yet, may not need to
#     def hyphenize(nums: list[int]) -> str:
#         """Convert a list of ints into a hyphenated list."""
#         # Warning: dark magic.
#         # Build lists of sequences from the sorted list.
#         # starts is list of starting values of sequences.
#         # ends is matching list of ending values.
#         # singles is list of ints that are not part of sequences.
#         nums_set = set(nums)
#         starts = [x for x in nums_set if x - 1 not in nums_set and x + 1 in nums_set]
#         startset = set(starts)
#         ends = [
#             x
#             for x in nums_set
#             if x - 1 in nums_set and x + 1 not in nums_set and x not in startset
#         ]
#         singles = [
#             x for x in nums_set if x - 1 not in nums_set and x + 1 not in nums_set
#         ]
#         # Build start & end into dictionary, rejecting any sequences
#         # shorter than an arbitrary shortest length
#         min_len = 3
#         seqs = {}  # key = int start; value = str representing the sequence
#         for start, end in zip(starts, ends):
#             if (end - start) >= (min_len - 1):
#                 seqs[start] = f"{start}-{end}"
#             else:
#                 # Too short, convert to singles
#                 singles = singles + list(range(start, end + 1))
#         # Add the singles to the seqs dict
#         for num in singles:
#             seqs[num] = f"{num}"
#         # Return the whole thing as a comma-joined string
#         return ",".join([seqs[n] for n in sorted(seqs.keys())])

#     if isinstance(tags, str):
#         # Break the tags down into a list.  First split comma.
#         tags = tags.split(",")
#         # Split on whitespace.  This makes a list of lists.
#         tags = [item.split() for item in tags]
#         # Flatten the list of lists into a single list.
#         tags = [item for sublist in tags for item in sublist]
#     # Make dict of [prefix]:list of tag_numbers_as_int
#     tag_prefixes = ut.tagnums_by_prefix(tags)
#     simplified_list = []
#     for prefix in sorted(tag_prefixes.keys()):
#         # A list of the tag numbers for this prefix
#         ##simplified_list.append(f"{prefix}" +
#         ##        (",".join([str(num) for num in sorted(tag_prefixes[prefix])])))
#         simplified_list.append(f"{prefix}{hyphenize(tag_prefixes[prefix])}")
#     # Return all of these joined together
#     simple_str = " ".join(simplified_list)
#     ##simple_str = simple_str.upper() if UC_TAGS else simple_str.lower()
#     return simple_str



def bike_check_ins_report(day: TrackerDay, as_of_when: VTime) -> None:
    """Print the check-ins count part of the summary statistics.

    as_of_when is HH:MM time, assumed to be a correct time.
    """

    num_bikes_ttl,num_bikes_regular,num_bikes_oversize = day.num_bikes_parked(as_of_when)
    num_bikes_am,_,_ = day.num_bikes_parked("11:59")
    num_still_here = day.num_tags_in_use(as_of_when)

    pr.iprint()
    pr.iprint("Bike check-ins", style=k.SUBTITLE_STYLE)
    pr.iprint(f"Total bikes in:   {num_bikes_ttl:4d}")
    pr.iprint(f"AM bikes in:      {num_bikes_am:4d}")
    pr.iprint(f"PM bikes in:      {(num_bikes_ttl - num_bikes_am):4d}")
    pr.iprint(f"Regular in:       {num_bikes_regular:4d}")
    pr.iprint(f"Oversize in:      {num_bikes_oversize:4d}")
    pr.iprint(f"Bikes still here: {num_still_here:4d}")


def visit_lengths_by_category_report(durations_list:list[int]) -> None:
    """Report number of visits in different length categories.

    visits is ....
    """

    def one_range(lower: float = None, upper: float = None) -> None:
        """Calculate and print visits in visit-duration range lower:upper (hours?).

        If lower is missing, uses anything below upper
        If upper is missing, uses anything above lower
        """
        noun = "Visit"
        if not lower and not upper:
            pr.iprint(
                f"PROGRAM ERROR: called one_range(lower='{lower}'," f"upper='{upper}')",
                style=k.ERROR_STYLE,
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
        for d in durations_list:
            if d >= lower * 60 and d < upper * 60:
                num += 1
        pr.iprint(f"{header:18s}{num:4d}")

    pr.iprint()
    pr.iprint("Number of visits by duration", style=k.SUBTITLE_STYLE)
    prev_boundary = None
    for boundary in VISIT_CATEGORIES:
        one_range(lower=prev_boundary, upper=boundary)
        prev_boundary = boundary
    one_range(lower=prev_boundary, upper=None)


def visit_statistics_report(durations_list: list[int]) -> None:
    """Max, min, mean, median, mode of visits.

    On entry:
        durations_list is a list of visit durations.
    """
    noun = "visit"

    def one_line(key: str, value: str) -> None:
        """Print one line."""
        pr.iprint(f"{key:17s}{value}", style=k.NORMAL_STYLE)

    def visits_mode(durations_list: list[int]) -> None:
        """Calculate and print the mode info."""
        # Find the mode value(s), with visit durations rounded
        # to nearest ROUND_TO_NEAREST time.
        modes, mode_occurences = ut.calculate_visit_modes(
            durations_list, category_width=MODE_ROUND_TO_NEAREST
        )
        modes_str = ",".join(modes)
        modes_str = (
            f"{modes_str}  ({mode_occurences} occurences; "
            f"{MODE_ROUND_TO_NEAREST} minute categories)"
        )
        one_line("Mode visit:", modes_str)

    # def make_tags_str(tags: list[TagID]) -> str:
    #     """Make a 'list of tags' string that is sure not to be too long."""
    #     tagstr = "tag: " if len(tags) == 1 else "tags: "
    #     tagstr = tagstr + ",".join([t.cased for t in tags])
    #     if len(tagstr) > 30:
    #         tagstr = f"{len(tags)} tags"
    #     return tagstr

    # Make a dict of stay-lengths with list tags (for longest/shortest).
    # duration_tags = {}
    # for tag, v in visits.items():
    #     dur = v.duration
    #     if dur not in duration_tags:
    #         duration_tags[dur] = []
    #     duration_tags[dur].append(tag)
    # if not duration_tags:
    #     return  # No durations
    # durations_list = [x.duration for x in visits.values()]
    longest = max(durations_list,default=None)
    # long_tags = make_tags_str(duration_tags[longest])
    shortest = min(durations_list,default=None)
    # short_tags = make_tags_str(duration_tags[shortest])
    pr.iprint()
    pr.iprint("Visit-length statistics", style=k.SUBTITLE_STYLE)
    one_line(f"Longest {noun}:", f"{VTime(longest).tidy}")
    one_line(f"Shortest {noun}:", f"{VTime(shortest).tidy}")
    # Make a list of stay-lengths (for mean, median, mode)
    one_line(f"Mean {noun}:", VTime(statistics.mean(durations_list)).tidy)
    one_line(
        f"Median {noun}:",
        VTime(statistics.median(durations_list)).tidy,
    )
    visits_mode(durations_list)


def highwater_report(events: dict) -> None:
    """Make a highwater table as at as_of_when."""

    # High-water mark for bikes onsite at any one time
    def one_line(header: str, events: dict, atime: VTime, highlight_field: int) -> None:
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
                bit = pr.text_style(bit, style=k.HIGHLIGHT_STYLE)
            line = f"{line}   {bit}"
        pr.iprint(f"{line}    {atime}")

    # Table header
    pr.iprint()
    pr.iprint("Most bikes onsite at any one time", style=k.SUBTITLE_STYLE)
    if not events:
        pr.iprint("-no bikes-")
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


def full_chart(day: OldTrackerDay, as_of_when: str = "") -> None:
    """Make chart of main stats by timeblock."""
    as_of_when = as_of_when if as_of_when else "24:00"
    if not day.bikes_in:
        pr.iprint()
        pr.iprint("-no bikes-", style=k.WARNING_STYLE)
        return

    blocks = tt_block.calc_blocks(day, as_of_when=as_of_when)
    pr.iprint()
    pr.iprint(f"Activity chart {day.date}", style=k.TITLE_STYLE)
    pr.iprint()
    pr.iprint(
        "          Activity    --Bikes onsite---    Max",
        style=k.SUBTITLE_STYLE,
    )
    pr.iprint(
        " Time     In   Out    Reglr Ovrsz Total   Bikes",
        style=k.SUBTITLE_STYLE,
    )
    for blk_start in sorted(blocks.keys()):
        blk: tt_block.Block
        blk = blocks[blk_start]
        pr.iprint(
            f"{blk_start.tidy}    "
            f"{blk.num_ins:3}   {blk.num_outs:3}    "
            f"{blk.num_here_regular:4}  {blk.num_here_oversize:4}  {blk.num_here:4}    "
            f"{blk.max_here:4}"
        )


def busy_graph(day: OldTrackerDay, as_of_when: str = "") -> None:
    """Make a quick & dirty graph of busyness."""
    in_marker = "+"  # OØ OX  <>  ↓↑
    out_marker = "x"

    as_of_when = as_of_when if as_of_when else "24:00"
    if not day.bikes_in:
        pr.iprint()
        pr.iprint("-no bikes-", style=k.WARNING_STYLE)
        return

    blocks = tt_block.calc_blocks(day, as_of_when=as_of_when)
    max_ins = max([b.num_ins for b in blocks.values()] + [0])
    max_outs = max([b.num_outs for b in blocks.values()] + [0])
    max_needed = max_ins + max_outs + 10
    available_width = cfg.SCREEN_WIDTH
    scale_factor = (max_needed // available_width) + 1
    ##scale_factor = round((max_activity / available_width))
    ##scale_factor = max(scale_factor, 1)

    # Print graph
    pr.iprint()
    pr.iprint(f"Chart of busyness for {day.date}", style=k.TITLE_STYLE)
    pr.iprint(
        f"Each marker represents {scale_factor} "
        f"{ut.plural(scale_factor,'bike')} in ({in_marker}) or out ({out_marker})",
        style=k.SUBTITLE_STYLE,
    )
    ins_field_width = round(max_ins / scale_factor) + 1
    for start in sorted(blocks.keys()):
        blk: tt_block.Block
        blk = blocks[start]
        insize = round(blk.num_ins / scale_factor)
        outsize = round(blk.num_outs / scale_factor)

        pr.iprint(
            f"{' ' * (ins_field_width-insize)}{(in_marker * insize)}  "
            f"{start}  {out_marker * outsize}"
        )


def fullness_graph(day: OldTrackerDay, as_of_when: str = "") -> None:
    """Make a quick & dirty graph of how full the site is."""
    regular_marker = "r"
    oversize_marker = "O"

    as_of_when = as_of_when if as_of_when else "24:00"

    blocks = tt_block.calc_blocks(day, as_of_when=as_of_when)
    if not day.bikes_in:
        pr.iprint()
        pr.iprint("-no bikes-", style=k.WARNING_STYLE)
        return

    max_full = max([b.num_here for b in blocks.values()] + [0])
    available_width = cfg.SCREEN_WIDTH - 10
    scale_factor = round((max_full / available_width))
    scale_factor = max(scale_factor, 1)
    # Print graph
    pr.iprint()
    pr.iprint(
        f"Max bikes onsite within a time block for {day.date}",
        style=k.TITLE_STYLE,
    )
    pr.iprint(
        f"Each marker represents {scale_factor} regular ({regular_marker}) "
        f"or oversize ({oversize_marker}) {ut.plural(scale_factor,'bike')}",
        style=k.SUBTITLE_STYLE,
    )
    for start in sorted(blocks.keys()):
        b: tt_block.Block
        b = blocks[start]
        regs = round(b.max_here_regular / scale_factor)
        overs = round(b.max_here_oversize / scale_factor)
        pr.iprint(f"{start} {regular_marker * regs}{oversize_marker * overs}")


def busiest_times_report(
    day: OldTrackerDay,
    events: dict[VTime, Snapshot],
    as_of_when: VTime,
) -> None:
    """Report the busiest time(s) of day."""

    def one_line(rank: int, num_events: int, times: list[VTime]) -> None:
        """Format and print one line of busyness report."""
        pr.iprint(f"{rank:2d}     {num_events:3d}      ", end="")
        for time_num, start_time in enumerate(sorted(times), start=1):
            end_time = VTime(start_time.num + k.BLOCK_DURATION)
            pr.iprint(
                f"{start_time.short}-{end_time.short}",
                num_indents=0,
                end="",
            )
            if time_num < len(times):
                pr.iprint(", ", end="", num_indents=0)
        pr.iprint()

    # Make an empty dict of busyness of timeblocks.
    blocks = dict(
        zip(
            tt_block.get_timeblock_list(day, as_of_when),
            [0 for _ in range(0, 100)],
        )
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
    pr.iprint("Busiest times of day", style=k.SUBTITLE_STYLE)
    pr.iprint("Rank  Ins&Outs  When")
    for rank, activity in enumerate(sorted(busy_times.keys(), reverse=True), start=1):
        if rank > BUSIEST_RANKS:
            break
        one_line(rank, activity, busy_times[activity])



def day_end_report(day: TrackerDay, args: list) -> None:
    """Report summary statistics about visits, up to the given time.

    If not time given (arg[0]), calculates as if end of the day (closing time).
    """
    as_of_when = VTime((args and args[0]) or day.closing_time)
    if not as_of_when:
        pr.iprint(
            f"Unrecognized time passed to visits summary ({args[0]})",
            style=k.WARNING_STYLE,
        )
        return
    pr.iprint()
    pr.iprint(
        f"Summary statistics {as_of_when.as_at}",
        style=k.TITLE_STYLE,
    )
    later_events_warning(day, as_of_when)
    if not day.latest_event(as_of_when):
        pr.iprint(f"No bikes checked in by {as_of_when}", style=k.SUBTITLE_STYLE)
        return
    # Bikes in, in various categories.
    bike_check_ins_report(day, as_of_when)
    # Stats that use visits (stays)
    durations_list = [v.duration(as_of_when) for v in day.all_visits()]
    durations_list = [d for d in durations_list if d is not None]
    visit_lengths_by_category_report(durations_list)
    visit_statistics_report(durations_list)

    # FIXME: move highwater report to here

    # FIXME: move busy-ess report to here

    # Number of bike registrations
    registrations_report(day.registrations)


# def qstack_report(visits: dict) -> None:
#     """Report whether visits are more queue-like or more stack-like."""
#     # Make a list of tuples: start_time, end_time for all visits.
#     visit_times = list(
#         zip(
#             [vis.time_in for vis in visits.values()],
#             [vis.time_out for vis in visits.values()],
#         )
#     )
#     ##ut.squawk( f"{len(list(visit_times))=}")
#     ##ut.squawk( f"{list(visit_times)=}")
#     queueish = 0
#     stackish = 0
#     neutralish = 0
#     visit_compares = 0
#     total_possible_compares = int((len(visit_times) * (len(visit_times) - 1)) / 2)

#     for time_in, time_out in visit_times:
#         earlier_visits = [
#             (tin, tout)
#             for (tin, tout) in visit_times
#             if tin < time_in and tout > time_in
#         ]
#         visit_compares += len(earlier_visits)
#         for earlier_out in [v[1] for v in earlier_visits]:
#             if earlier_out < time_out:
#                 queueish += 1
#             elif earlier_out > time_out:
#                 stackish += 1
#             else:
#                 neutralish += 1

#     pr.iprint()
#     pr.iprint(
#         "Were today's vists more queue-like or stack-like?",
#         style=k.SUBTITLE_STYLE,
#     )
#     if not queueish and not stackish:
#         pr.iprint("Unable to determine.")
#         return
#     neutralish = total_possible_compares - queueish - stackish
#     queue_proportion = queueish / (queueish + stackish + neutralish)
#     stack_proportion = stackish / (queueish + stackish + neutralish)
#     pr.iprint(
#         f"The {total_possible_compares} compares of today's {len(visits)} "
#         "visits are:"
#     )
#     pr.iprint(
#         f"{(queue_proportion):0.3f} queue-like (overlapping visits)",
#         num_indents=2,
#     )
#     pr.iprint(
#         f"{(stack_proportion):0.3f} stack-like (nested visits)",
#         num_indents=2,
#     )
#     pr.iprint(
#         f"{((1 - stack_proportion - queue_proportion)):0.3f} neither "
#         "(disjunct visits, or share a check-in or -out time)",
#         num_indents=2,
#     )



# def busyness_report(day: OldTrackerDay, args: list) -> None:
#     """Report more summary statistics about visits, up to the given time.

#     If not time given, calculates as of latest checkin/out of the day.
#     """
#     # rightnow = ut.get_time()
#     as_of_when = VTime((args + ["now"])[0])
#     if not as_of_when:
#         pr.iprint("Unrecognized time", style=k.WARNING_STYLE)
#         return
#     pr.iprint()
#     pr.iprint(
#         f"Busyness report {as_of_when.as_at}",
#         style=k.TITLE_STYLE,
#     )
#     later_events_warning(day, as_of_when)
#     if not day.latest_event(as_of_when):
#         pr.iprint(f"No bikes checked in by {as_of_when}", style=k.SUBTITLE_STYLE)
#         return
#     # Dict of time (events)
#     events = Snapshot.calc_moments(day, as_of_when)
#     highwater_report(events)
#     # Busiest times of day
#     busiest_times_report(day, events, as_of_when)

#     Queue-like vs stack-like
#     FIXME: re-enable someday maybe. But maybe not.
#     visits = Stay.calc_stays(day, as_of_when)
#     qstack_report(visits)


# def dataform_report(day: OldTrackerDay, args: list[str]) -> None:
#     """Print days activity in timeblocks.

#     This is to match the (paper/google) data tracking sheets.
#     Single args are both optional, end_time.
#     If end_time is missing, runs to current time.
#     If start_time is missing, starts one hour before end_time.
#     """
#     end_time = VTime((args + ["now"])[0])
#     if not end_time:
#         pr.iprint(f"Unrecognized time {end_time.original}", style=k.WARNING_STYLE)
#         return
#     # Special case: allow "24:00"
#     if end_time != "24:00":
#         end_time = tt_block.block_end(end_time)
#         if not (end_time):
#             pr.iprint()
#             pr.iprint(f"Unrecognized time {args[0]}", style=k.WARNING_STYLE)
#             return

#     pr.iprint()
#     pr.iprint(
#         f"Tracking form data from start of day until {end_time.short}",
#         style=k.TITLE_STYLE,
#     )
#     later_events_warning(day, end_time)
#     all_blocks = tt_block.calc_blocks(day, end_time)
#     if not all_blocks:
#         earliest = day.earliest_event()
#         pr.iprint(
#             f"No bikes checked in before {end_time} " f"(earliest in at {earliest})",
#             style=k.HIGHLIGHT_STYLE,
#         )
#         return
#     for which in [k.BIKE_IN, k.BIKE_OUT]:
#         if which == k.BIKE_IN:
#             titlebit = "checked IN"
#             prefix = "<<<<"
#             suffix = ""
#         else:
#             titlebit = "returned OUT"
#             prefix = ">>>>"
#             suffix = ""
#         title = f"Bikes {titlebit}"
#         pr.iprint()
#         pr.iprint(title, style=k.SUBTITLE_STYLE)
#         pr.iprint("-" * len(title), style=k.SUBTITLE_STYLE)
#         for start, block in all_blocks.items():
#             inouts = block.ins_list if which == k.BIKE_IN else block.outs_list
#             end = tt_block.block_end(start)
#             tagslist = simplified_taglist(inouts)
#             if TagID.uc():
#                 tagslist = tagslist.upper()
#             else:
#                 tagslist = tagslist.lower()
#             pr.iprint(f"{start}-{end} {prefix} {tagslist} {suffix}")
