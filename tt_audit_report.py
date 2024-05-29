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

import tt_constants as k
from tt_time import VTime
from tt_tag import TagID
from tt_trackerday import TrackerDay
from tt_biketag import BikeTag
from tt_bikevisit import BikeVisit
import tt_util as ut
import tt_printer as pr
import client_base_config as cfg
import tt_reports as rep


DEFAULT_RETIRED_TAG_STR = " ●"

# def notes_bit(day: OldTrackerDay) -> None:
#     """Add a 'notes' section to a report."""
#     pr.iprint()

#     pr.iprint("Today's notes:", style=k.SUBTITLE_STYLE)
#     if day.notes:
#         for line in day.notes:
#             pr.iprint(line, style=k.NORMAL_STYLE, num_indents=1)
#     else:
#         pr.iprint("There are no notes yet today.", num_indents=2)


def inout_summary(day: TrackerDay, as_of_when: VTime = VTime("")) -> None:
    """Print summary table of # of bikes in, out and still onsite."""
    # # Count the totals

    total_in, regular_in, oversize_in = day.num_bikes_parked(as_of_when)
    total_out, regular_out, oversize_out = day.num_bikes_returned(as_of_when)
    # for biketag in day.biketags.values():
    #     regular_in += len([v for v in biketag.visits if v.time_in <= as_of_when if biketag.bike_type == k.REGULAR])
    #     oversize_in += len([v for v in biketag.visits if v.time_in <= as_of_when if biketag.bike_type == k.OVERSIZE])
    #     regular_out += len([v for v in biketag.visits if as_of_when <= v.time_out if biketag.bike_type == k.REGULAR])
    #     oversize_out += len([v for v in biketag.visits if as_of_when <= v.time_out if biketag.bike_type == k.OVERSIZE])
    # total_in = regular_in + oversize_in
    # total_out = regular_out + oversize_out

    # Count bikes currently onsite
    regular_onsite = 0
    oversize_onsite = 0
    for tagid in day.tags_in_use(as_of_when=as_of_when):
        if day.biketags[tagid].bike_type == k.REGULAR:
            regular_onsite += 1
        else:
            oversize_onsite += 1
    total_onsite = regular_onsite + oversize_onsite
    ut.squawk(f"{total_onsite=}, {day.num_tags_in_use(as_of_when)=}",cfg.DEBUG)

    # Print summary of bikes in/out/here
    pr.iprint()
    pr.iprint("Summary             Regular Oversize Total", style=k.SUBTITLE_STYLE)
    pr.iprint(
        f"Bikes checked in:     {regular_in:4d}    {oversize_in:4d}" f"    {total_in:4d}"
    )
    pr.iprint(
        f"Bikes returned out:   {regular_out:4d}    {oversize_out:4d}"
        f"    {total_out:4d}"
    )
    pr.iprint(
        f"Bikes onsite:         {(regular_onsite):4d}"
        f"    {(oversize_onsite):4d}    {total_onsite:4d}"
    )


def audit_report(
    day: TrackerDay,
    args: list[str],
    include_notes: bool = True,
    include_returns: bool = False,
    retired_tag_str:str = DEFAULT_RETIRED_TAG_STR
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
    as_of_when = args[0] if args else "now"
    as_of_when = VTime(as_of_when)
    if not as_of_when:
        pr.iprint("Unrecognized time", style=k.WARNING_STYLE)
        return False

    # Audit report header. Special case if request is for "24:00"
    pr.iprint()
    pr.iprint(
        f"Audit report for {day.date} {as_of_when.as_at}",
        style=k.TITLE_STYLE,
    )
    rep.later_events_warning(day, as_of_when)

    # Summary of bikes in a& bikes out
    inout_summary(day, as_of_when)

    # Want list of biketags on hand and those returned but not reused
    tags_in_use = day.tags_in_use(as_of_when=as_of_when)
    tags_done = day.tags_done(as_of_when)


    # Tags matrixes
    # Tags broken down by prefix (for tags matrix)
    prefixes_on_hand = ut.tagnums_by_prefix(tags_in_use)
    prefixes_returned_out = ut.tagnums_by_prefix(tags_done)
    returns_by_colour = {}
    for prefix, numbers in prefixes_returned_out.items():
        colour_code = prefix[:-1]  # prefix without the tag_letter
        if colour_code not in returns_by_colour:
            returns_by_colour[colour_code] = len(numbers)
        else:
            returns_by_colour[colour_code] += len(numbers)

    NO_ITEM_STR = "  "  # what to show when there's no tag
    pr.iprint()
    # Bikes still; onsite
    pr.iprint(
        f"Bikes still onsite at {as_of_when.short}"
        f" ({retired_tag_str} --> retired tag)",
        style=k.SUBTITLE_STYLE,
    )
    for prefix in sorted(prefixes_on_hand.keys()):
        numbers = prefixes_on_hand[prefix]
        line = f"{prefix:3>} "
        for i in range(0, ut.greatest_tagnum(prefix, day.regular_tagids, day.oversize_tagids) + 1):
            if i in numbers:
                s = f"{i:02d}"
            elif TagID(f"{prefix}{i}") in day.retired_tagids:
                s = retired_tag_str
            else:
                s = NO_ITEM_STR
            line = f"{line} {s}"
        pr.iprint(line)
    if not prefixes_on_hand:
        pr.iprint("-no bikes-")

    # Bikes returned out -- tags matrix.
    if include_returns:
        pr.iprint()
        pr.iprint("Tags available for re-use", style=k.SUBTITLE_STYLE)
        for prefix in sorted(prefixes_returned_out.keys()):
            numbers = prefixes_returned_out[prefix]
            line = f"{prefix:3>} "
            for i in range(
                0, ut.greatest_tagnum(prefix, day.regular_tagids, day.oversize_tagids) + 1
            ):
                if i in numbers:
                    s = f"{i:02d}"
                elif TagID(f"{prefix}{i}") in day.retired_tagids:
                    s = retired_tag_str
                else:
                    s = NO_ITEM_STR
                line = f"{line} {s}"
            pr.iprint(line)
        if not prefixes_returned_out:
            pr.iprint("-no bikes-")

    # if include_notes:
    #     notes_bit(day)

    return
