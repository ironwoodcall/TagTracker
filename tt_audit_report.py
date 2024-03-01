"""TagTracker by Julias Hocking.

Audit report functions for  the TagTracker suite.

Copyright (C) 2023-2024 Julias Hocking and Todd Glover

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


# from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
from tt_globals import REGULAR, OVERSIZE
from tt_time import VTime
from tt_tag import TagID
from tt_realtag import Stay
from tt_trackerday import TrackerDay
import tt_util as ut
import tt_printer as pr
import tt_conf as cfg
import tt_reports as rep


def notes_bit(day: TrackerDay) -> None:
    """Add a 'notes' section to a report."""
    pr.iprint()

    pr.iprint("Today's notes:", style=cfg.SUBTITLE_STYLE)
    if day.notes:
        for line in day.notes:
            pr.iprint(line, style=cfg.NORMAL_STYLE, num_indents=1)
    else:
        pr.iprint("There are no notes yet today.", num_indents=2)


def inout_summary(day: TrackerDay, as_of_when: VTime = VTime("")) -> None:
    """Print summary table of # of bikes in, out and still onsite."""
    # Count the totals
    visits = Stay.calc_stays(day, as_of_when=as_of_when)
    bikes_on_hand = [v.tag for v in visits.values() if v.still_here]
    ##print(' '.join(bikes_on_hand))
    num_bikes_on_hand = len(bikes_on_hand)
    regular_in = 0
    regular_out = 0
    oversize_in = 0
    oversize_out = 0
    for v in visits.values():
        if v.type == REGULAR:
            regular_in += 1
            if not v.still_here:
                regular_out += 1
        elif v.type == OVERSIZE:
            oversize_in += 1
            if not v.still_here:
                oversize_out += 1

    sum_in = regular_in + oversize_in
    sum_out = regular_out + oversize_out
    sum_on_hand = regular_in + oversize_in - regular_out - oversize_out

    # Print summary of bikes in/out/here
    pr.iprint()
    pr.iprint("Summary             Regular Oversize Total", style=cfg.SUBTITLE_STYLE)
    pr.iprint(
        f"Bikes checked in:     {regular_in:4d}    {oversize_in:4d}" f"    {sum_in:4d}"
    )
    pr.iprint(
        f"Bikes returned out:   {regular_out:4d}    {oversize_out:4d}"
        f"    {sum_out:4d}"
    )
    pr.iprint(
        f"Bikes onsite:         {(regular_in-regular_out):4d}"
        f"    {(oversize_in-oversize_out):4d}    {sum_on_hand:4d}"
    )
    if sum_on_hand != num_bikes_on_hand:
        ut.squawk(f"inout_summary() {num_bikes_on_hand=} != {sum_on_hand=}")


def audit_report(
    day: TrackerDay,
    args: list[str],
    include_notes: bool = True,
    include_returns: bool = False,
) -> None:
    """Create & display audit report as at a particular time.

    On entry: as_of_when_args is a list that can optionally
    have a first element that's a time at which to make this for.

    If include_notes is True, includes any notes from the day.

    If include_returns is True, shows a matrix of bikes for which
    tags were returned, else won't.

    This is smart about any checkouts that are later than as_of_when.
    If as_of_when is missing, then counts as of current time.

    """

    # What time will this audit report reflect?
    as_of_when = (args + ["now"])[0]
    as_of_when = VTime(as_of_when)
    if not as_of_when:
        pr.iprint("Unrecognized time", style=cfg.WARNING_STYLE)
        return False

    # Audit report header. Special case if request is for "24:00"
    pr.iprint()
    pr.iprint(
        f"Audit report for {day.date} {as_of_when.as_at}",
        style=cfg.TITLE_STYLE,
    )
    rep.later_events_warning(day, as_of_when)

    # Summary of bikes in a& bikes out
    inout_summary(day, as_of_when)

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

    # Tags matrixes
    # Tags broken down by prefix (for tags matrix)
    prefixes_on_hand = ut.tagnums_by_prefix(bikes_on_hand.keys())
    prefixes_returned_out = ut.tagnums_by_prefix(check_outs_to_now.keys())
    returns_by_colour = {}
    for prefix, numbers in prefixes_returned_out.items():
        colour_code = prefix[:-1]  # prefix without the tag_letter
        if colour_code not in returns_by_colour:
            returns_by_colour[colour_code] = len(numbers)
        else:
            returns_by_colour[colour_code] += len(numbers)

    NO_ITEM_STR = "  "  # what to show when there's no tag
    RETIRED_TAG_STR = " ●"
    pr.iprint()
    # Bikes still; onsite
    pr.iprint(
        f"Bikes still onsite at {as_of_when.short}"
        f" ({RETIRED_TAG_STR} --> retired tag)",
        style=cfg.SUBTITLE_STYLE,
    )
    for prefix in sorted(prefixes_on_hand.keys()):
        numbers = prefixes_on_hand[prefix]
        line = f"{prefix:3>} "
        for i in range(0, ut.greatest_tagnum(prefix, day.regular, day.oversize) + 1):
            if i in numbers:
                s = f"{i:02d}"
            elif TagID(f"{prefix}{i}") in day.retired:
                s = RETIRED_TAG_STR
            else:
                s = NO_ITEM_STR
            line = f"{line} {s}"
        pr.iprint(line)
    if not prefixes_on_hand:
        pr.iprint("-no bikes-")

    # Bikes returned out -- tags matrix.
    if include_returns:
        pr.iprint()
        pr.iprint("Bikes returned", style=cfg.SUBTITLE_STYLE)
        for prefix in sorted(prefixes_returned_out.keys()):
            numbers = prefixes_returned_out[prefix]
            line = f"{prefix:3>} "
            for i in range(0, ut.greatest_tagnum(prefix, day.regular, day.oversize) + 1):
                if i in numbers:
                    s = f"{i:02d}"
                elif TagID(f"{prefix}{i}") in day.retired:
                    s = RETIRED_TAG_STR
                else:
                    s = NO_ITEM_STR
                line = f"{line} {s}"
            pr.iprint(line)
        if not prefixes_returned_out:
            pr.iprint("-no bikes-")

    if include_notes:
        notes_bit(day)

    return
