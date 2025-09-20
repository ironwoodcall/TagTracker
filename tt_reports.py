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

import common.tt_constants as k
from common.tt_time import VTime
from common.tt_tag import TagID

# from tt_realtag import Stay
from common.tt_trackerday import TrackerDay
import common.tt_util as ut
from common.tt_daysummary import DaySummary, PeriodDetail, MomentDetail
from common.tt_statistics import VisitStats
from tt_notes import Note
# import tt_block
import tt_printer as pr

import client_base_config as cfg


# Time ranges for categorizing stay-lengths, in hours.
# First category will always be 0 - [0], last will always be > [-1]
VISIT_CATEGORIES = [1.5, 5]

# size of 'buckets' for calculating the mode stay time
MODE_ROUND_TO_NEAREST = 30  # mins

# List ow many ranked busiest times of day in report?
BUSIEST_RANKS = 4


def time_description(time: VTime, day: TrackerDay) -> str:
    """Make a descriptionof the time of day to use in report titles."""
    time = VTime(time)
    if time == day.time_closed:
        return f"as at today's closing time ({time.short})"
    if time < day.time_open:
        return f"as at {time.short} (before opening time)"
    if time > day.time_closed:
        return f"as at {time.short} (after closing time)"
    return f"as at {time.short}"


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
        for i, visit in enumerate(biketag.visits, start=1):
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

    def format_one(atime: VTime, tag: TagID, is_check_in: bool) -> str:
        """Format one line of output."""
        in_tag = f"{tag}" if is_check_in else ""
        out_tag = "" if is_check_in else f"{tag}"
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
            end_time = start_time.num + 60
    else:
        start_time = VTime(start_time)
        end_time = VTime(end_time)

    ut.squawk(f"{args=}; {start_time=},{end_time=}", cfg.DEBUG)
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
        "The number following the tag shows which of the "
        "tag's visits this event represents.",
        style=k.SUBTITLE_STYLE,
    )
    pr.iprint()
    pr.iprint("Time     BikeIn   BikeOut", style=k.SUBTITLE_STYLE)
    # Collect & print any bike-in/bike-out events in the time period.
    summary = DaySummary(day=day, as_of_when=end_time)

    # events = _events_in_period(day, start_time, end_time)

    ins = 0
    outs = 0
    current_block_end = None  # block ends are for putting divider lines

    for moment_time in sorted(summary.moments.keys()):
        moment: MomentDetail = summary.moments[moment_time]
        if end_time > moment_time < start_time:
            continue

        if not current_block_end:
            current_block_end = ut.block_end(moment_time)
        if moment_time > current_block_end:
            pr.iprint(f"{ut.block_start(moment_time).tidy} --------------------")
            current_block_end = ut.block_end(moment_time)

        for tag_desc in moment.tag_descriptions_incoming:
            pr.iprint(format_one(moment_time, tag_desc, True))
            ins += 1
        for tag_desc in moment.tag_descriptions_outgoing:
            pr.iprint(format_one(moment_time, tag_desc, False))
            outs += 1
    pr.iprint()
    pr.iprint(f"Total   {ins:6} {outs:7}", style=k.SUBTITLE_STYLE)


def registrations_report(day: TrackerDay):
    """Display current count of registrations."""
    pr.iprint()
    pr.iprint("Bike registrations (whole day)", style=k.SUBTITLE_STYLE)
    day.registrations.display_current_count()


def later_events_warning(day: TrackerDay, when: VTime = "") -> None:
    """Warn about report that excludes later events.

    If  no later events, does nothing.
    """
    when = VTime(when or "now")

    # Build the message
    later_events = day.num_later_events(when)
    if not later_events:
        return
    msg = (
        f"Report excludes {later_events} {ut.plural(later_events,'event')} "
        f"later than {when.short}."
    )
    pr.iprint(msg, style=k.ERROR_STYLE)


def print_tag_notes(day: TrackerDay, target_tag: str):
    """Print active/recovered notes for a given tag."""
    for note in day.notes.active_notes():
        for note_tag in note.tags:
            if TagID(target_tag) == note_tag.tagid:
                pr.iprint(note.pretty(), style=k.WARNING_STYLE)
                break


def bike_check_ins_report(day: TrackerDay, as_of_when: VTime) -> None:
    """Print the check-ins count part of the summary statistics.

    as_of_when is HH:MM time, assumed to be a correct time.
    """

    num_bikes_ttl, num_bikes_regular, num_bikes_oversize = day.num_bikes_parked(
        as_of_when
    )
    num_bikes_am, _, _ = day.num_bikes_parked(min("11:59", as_of_when))
    num_still_here = day.num_tags_in_use(as_of_when)

    pr.iprint()
    pr.iprint("Bike check-ins", style=k.SUBTITLE_STYLE)
    pr.iprint(f"Total bikes in:   {num_bikes_ttl:4d}")
    pr.iprint(f"AM bikes in:      {num_bikes_am:4d}")
    pr.iprint(f"PM bikes in:      {(num_bikes_ttl - num_bikes_am):4d}")
    pr.iprint(f"Regular in:       {num_bikes_regular:4d}")
    pr.iprint(f"Oversize in:      {num_bikes_oversize:4d}")
    pr.iprint(f"Bikes still here: {num_still_here:4d}")


def visit_lengths_by_category_report(durations_list: list[int]) -> None:
    """Report number of visits in different length categories.

    visits is ....
    """

    def one_range(lower: float = None, upper: float = None) -> None:
        """Calculate and print visits in visit-duration range lower:upper (hours?).

        If lower is missing, uses anything below upper
        If upper is missing, uses anything above lower
        """
        if not lower and not upper:
            pr.iprint(
                f"PROGRAM ERROR: called one_range(lower='{lower}'," f"upper='{upper}')",
                style=k.ERROR_STYLE,
            )
            return None
        if not lower:
            header = f"Visits < {upper:3.1f}h:"
            lower = 0
        elif not upper:
            header = f"Visits >= {lower:3.1f}h:"
            upper = 999
        else:
            header = f"Visits {lower:3.1f}-{upper:3.1f}h:"
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

    def one_line(key: str, value: str) -> None:
        """Print one line."""
        pr.iprint(f"{key:17s}{value}", style=k.NORMAL_STYLE)

    stats = VisitStats(durations_list)

    pr.iprint()
    pr.iprint("Visit-length statistics", style=k.SUBTITLE_STYLE)
    one_line("Longest visit:", stats.longest)
    one_line("Shortest visit:", stats.shortest)
    # Make a list of stay-lengths (for mean, median, mode)
    one_line("Mean visit:", stats.mean)
    one_line("Median visit:", stats.median)
    modes_str = f"{','.join(stats.modes)} ({stats.mode_occurences} occurences)"
    one_line("Mode visit:", modes_str)


def highwater_report(summary: DaySummary) -> None:
    """Make a highwater table."""

    # High-water mark for bikes onsite at any one time
    def one_line(header: str, num: int, atime: VTime, highlight_field: int) -> None:
        """Print one line for highwater_report."""

        values = [
            summary.moments[atime].num_on_hand[k.REGULAR],
            summary.moments[atime].num_on_hand[k.OVERSIZE],
            summary.moments[atime].num_on_hand[k.COMBINED],
        ]

        # values = [
        #     events[atime].num_here_regular,
        #     events[atime].num_here_oversize,
        #     events[atime].num_here_total,
        # ]
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
    if len(summary.moments) <= 0:
        pr.iprint("-no bikes-")
        return

    num_fullest = {k.REGULAR: 0, k.OVERSIZE: 0, k.COMBINED: 0}
    time_fullest = {k.REGULAR: "", k.OVERSIZE: "", k.COMBINED: ""}
    for moment_time, moment in summary.moments.items():
        for bike_type in [k.REGULAR, k.OVERSIZE, k.COMBINED]:
            if moment.num_on_hand[bike_type] > num_fullest[bike_type]:
                num_fullest[bike_type] = moment.num_on_hand[bike_type]
                time_fullest[bike_type] = moment_time

    pr.iprint("                 Reglr OvrSz Total WhenAchieved")
    one_line("Most regular:", num_fullest[k.REGULAR], time_fullest[k.REGULAR], 0)
    one_line("Most oversize:", num_fullest[k.OVERSIZE], time_fullest[k.OVERSIZE], 1)
    one_line("Most combined:", num_fullest[k.COMBINED], time_fullest[k.COMBINED], 2)


def full_chart(day: TrackerDay, as_of_when: str = "") -> None:
    """Make chart of main stats by timeblock."""
    as_of_when = VTime(as_of_when or day.time_closed)

    if not day.num_bikes_parked(as_of_when=as_of_when):
        pr.iprint()
        pr.iprint("-no bikes-", style=k.WARNING_STYLE)
        return

    summary = DaySummary(day=day, as_of_when=as_of_when)

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

    for blk_start in sorted(summary.blocks.keys()):
        blk: PeriodDetail = summary.blocks[blk_start]

        pr.iprint(
            f"{blk_start.tidy}    "
            f"{blk.num_incoming[k.COMBINED]:3}   {blk.num_outgoing[k.COMBINED]:3}    "
            f"{blk.num_on_hand[k.REGULAR]:4}  {blk.num_on_hand[k.OVERSIZE]:4}  "
            f"{blk.num_on_hand[k.COMBINED]:4}    {blk.num_fullest[k.COMBINED]:4}"
        )


def busiest_times_report(summary: dict[VTime, DaySummary]) -> None:
    """Report the busiest time(s) of day."""

    def one_line(rank: int, num_events: int, times: list[VTime]) -> None:
        """Format and print one line of busyness report."""
        if num_events == 0:
            return
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

    busy_times = {}
    for atime, block in summary.blocks.items():
        activity = block.num_incoming[k.COMBINED] + block.num_outgoing[k.COMBINED]
        if activity not in busy_times:
            busy_times[activity] = []
        busy_times[activity].append(atime)

    # # Make an empty dict of busyness of timeblocks.
    # blocks = dict(
    #     zip(
    #         tt_block.get_timeblock_list(day, as_of_when),
    #         [0 for _ in range(0, 100)],
    #     )
    # )
    # # Count actions in each timeblock
    # for atime, ev in events.items():
    #     start = ut.block_start(atime)  # Which block?
    #     blocks[start] += ev.num_bikes_parked + ev.num_bikes_returned
    # # Make a dict of busynesses with list of timeblocks for each.
    # busy_times = {}
    # for atime, activity in blocks.items():
    #     if activity not in busy_times:
    #         busy_times[activity] = []
    #     busy_times[activity].append(atime)
    # # Report the results.
    pr.iprint()
    pr.iprint("Busiest times of day", style=k.SUBTITLE_STYLE)
    pr.iprint("Rank  Ins&Outs  When")
    for rank, activity in enumerate(sorted(busy_times.keys(), reverse=True), start=1):
        if rank > BUSIEST_RANKS:
            break
        one_line(rank, activity, busy_times[activity])


def summary_report(day: TrackerDay, args: list) -> None:
    """Report summary statistics about visits, up to the given time.

    If not time given (arg[0]), calculates as if end of the day (closing time).
    """
    as_of_when = VTime((args and args[0]) or day.time_closed)
    if not as_of_when:
        pr.iprint(
            f"Unrecognized time passed to visits summary ({args[0]})",
            style=k.WARNING_STYLE,
        )
        return
    pr.iprint()
    pr.iprint(
        f"Summary report for {day.site_name} {time_description(as_of_when,day=day)}",
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

    # Today's highwater (fullest) times.
    summary = DaySummary(day=day, as_of_when=as_of_when)
    highwater_report(summary)

    # Today's busiest periods.
    busiest_times_report(summary=summary)

    # Number of bike registrations
    registrations_report(day)


def busy_graph(day: TrackerDay, as_of_when: str = "") -> None:
    """Make a quick & dirty graph of busyness."""
    in_marker = "+"  # OØ OX  <>  ↓↑
    out_marker = "x"

    as_of_when = as_of_when if as_of_when else "24:00"
    if not day.all_visits():
        pr.iprint()
        pr.iprint("-no bikes-", style=k.WARNING_STYLE)
        return

    daysum = DaySummary(day=day, as_of_when=as_of_when)
    blocks = daysum.blocks
    # ut.squawk(f"{[b.num_incoming for b in blocks.values()]=}")
    max_ins = max([b.num_incoming[k.COMBINED] for b in blocks.values()], default=0)
    max_outs = max([b.num_outgoing[k.COMBINED] for b in blocks.values()], default=0)
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
        blk: PeriodDetail
        blk = blocks[start]
        insize = round(blk.num_incoming[k.COMBINED] / scale_factor)
        outsize = round(blk.num_outgoing[k.COMBINED] / scale_factor)

        pr.iprint(
            f"{' ' * (ins_field_width-insize)}{(in_marker * insize)}  "
            f"{start}  {out_marker * outsize}"
        )


def fullness_graph(day: TrackerDay, as_of_when: str = "") -> None:
    """Make a quick & dirty graph of how full the site is."""
    regular_marker = "r"
    oversize_marker = "O"

    as_of_when = as_of_when if as_of_when else "24:00"
    if not day.all_visits():
        pr.iprint()
        pr.iprint("-no bikes-", style=k.WARNING_STYLE)
        return

    daysum = DaySummary(day=day, as_of_when=as_of_when)
    blocks = daysum.blocks

    max_full = daysum.whole_day.num_fullest_combined
    # max_full = max([b.num_here for b in blocks.values()] + [0])
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
        b: PeriodDetail = blocks[start]
        regs = round(b.num_fullest[k.REGULAR] / scale_factor)
        overs = round(b.num_fullest[k.OVERSIZE] / scale_factor)
        pr.iprint(f"{start} {regular_marker * regs}{oversize_marker * overs}")


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
#     as_of_when = VTime((args + ["now"])[0])
#     if not as_of_when:
#         pr.iprint("Unrecognized time", style=k.WARNING_STYLE)
#         return
#     pr.iprint()
#     pr.iprint(
#         f"Busyness report {rep.time_description(as_of_when,day=day)}",
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
