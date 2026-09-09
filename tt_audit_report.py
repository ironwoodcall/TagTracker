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

import common.tt_constants as k
from common.tt_time import VTime
from common.tt_tag import TagID
from common.tt_trackerday import TrackerDay
from common.tt_biketag import BikeTag
import common.tt_util as ut
import tt_printer as pr
import client_base_config as cfg
import tt_reports as rep


DEFAULT_RETIRED_TAG_STR = " ●"
# "○" is deliberately chosen from the same Unicode block (Geometric
# Shapes, U+25A0-25FF) as the already-in-use "●" (U+25CF) -- both share
# the same East Asian Width category ('Ambiguous'), so whatever
# single-column-width behaviour "●" already gets from a given
# terminal/font, "○" should get identically. "<"/">" need no such
# reasoning -- plain ASCII, and already this app's own convention for
# in/out (see print_tag_inout()'s "<---in---"/"---out--->"). Plain-text
# fallbacks for non-terminal destinations (e.g. tt_publish.py) are passed
# explicitly by the caller, same as retired_tag_str="<>" already is.
DEFAULT_HELD_TAG_STR = " ○"
DEFAULT_IN_USE_TAG_STR = " <"
DEFAULT_DONE_TAG_STR = " >"
# Matches the 'tags' command's own TAG_INV_AVAILABLE symbol
# (tt_tag_inv.py) -- distinguishes "this tag exists but simply hasn't
# been used today" from a cell with no defined tag at all, which is the
# only thing that now stays truly blank (NO_ITEM_STR).
DEFAULT_AVAILABLE_TAG_STR = " -"
NO_ITEM_STR = "  "  # what to show when there's no tag at all for this slot

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

    # Count bikes currently onsite
    regular_onsite = 0
    oversize_onsite = 0
    for tagid in day.tags_in_use(as_of_when=as_of_when):
        if day.biketags[tagid].bike_type == k.REGULAR:
            regular_onsite += 1
        else:
            oversize_onsite += 1
    total_onsite = regular_onsite + oversize_onsite
    ut.squawk(f"{total_onsite=}, {day.num_tags_in_use(as_of_when)=}", cfg.DEBUG)

    # Print summary of bikes in/out/here
    pr.iprint()
    pr.iprint("Summary             Regular Oversize Total", style=k.SUBTITLE_STYLE)
    pr.iprint(
        f"Bikes arrivals:       {regular_in:4d}    {oversize_in:4d}"
        f"    {total_in:4d}"
    )
    pr.iprint(
        f"Bike departures:      {regular_out:4d}    {oversize_out:4d}"
        f"    {total_out:4d}"
    )
    pr.iprint(
        f"Bikes on-site:        {(regular_onsite):4d}"
        f"    {(oversize_onsite):4d}    {total_onsite:4d}"
    )


def _draw_tag_grid(
    day: TrackerDay,
    prefixes,
    as_of_when: VTime,
    home_category: str,
    markers: dict,
    other_style: str = k.DIM_STYLE,
) -> None:
    """Print one prefix-by-tagnum grid.

    Each cell shows the tag number if the tag's current category (from
    status_as_at()) is home_category; otherwise it shows that category's
    marker via 'markers' (or blank if that category isn't in 'markers' --
    see AUDIT_GRID_FULL_MARKERS in client_base_config.py, which controls
    whether 'markers' has all five categories or just RETIRED). A cell is
    blank outright only when there's no tag defined for that slot at all.

    Cells that aren't this grid's own category of interest (i.e.
    everything shown as a marker rather than a number) print in
    'other_style' -- dimmed (k.DIM_STYLE) when AUDIT_GRID_FULL_MARKERS is
    on, so the numbers stand out from the rest; k.NORMAL_STYLE when it's
    off, matching the undimmed retired-dot-only look from before that
    option existed.
    """
    if not prefixes:
        pr.iprint("-no bikes-")
        return
    for prefix in sorted(prefixes):
        greatest_num = ut.greatest_tagnum(prefix, day.regular_tagids, day.oversize_tagids)
        if greatest_num is None:
            continue
        segments = [(f"{prefix:3>} ", k.NORMAL_STYLE)]
        for i in range(0, greatest_num + 1):
            biketag = day.biketags.get(TagID(f"{prefix}{i}"))
            if not biketag:
                s, style = NO_ITEM_STR, k.NORMAL_STYLE
            else:
                category = biketag.status_as_at(as_of_when)
                if category == home_category:
                    s, style = f"{i:02d}", k.NORMAL_STYLE
                else:
                    s, style = markers.get(category, NO_ITEM_STR), other_style
            segments.append((f" {s}", style))
        pr.iprint_segments(segments)


def audit_report(
    day: TrackerDay,
    args: list[str],
    include_notes: bool = True,
    include_returns: bool = False,
    retired_tag_str: str = DEFAULT_RETIRED_TAG_STR,
    held_tag_str: str = DEFAULT_HELD_TAG_STR,
    in_use_tag_str: str = DEFAULT_IN_USE_TAG_STR,
    done_tag_str: str = DEFAULT_DONE_TAG_STR,
    available_tag_str: str = DEFAULT_AVAILABLE_TAG_STR,
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

    # Audit report header.
    pr.iprint()
    pr.iprint(
        f"Audit report for {day.date} {rep.time_description(as_of_when,day=day)}",
        style=k.TITLE_STYLE,
    )
    rep.later_events_warning(day, as_of_when)

    # Summary of bikes in a& bikes out
    inout_summary(day, as_of_when)

    # Want list of biketags on hand and those returned but not reused
    tags_in_use = day.tags_in_use(as_of_when=as_of_when)
    tags_done = day.tags_done(as_of_when)
    ut.squawk(f"{tags_done=}",cfg.DEBUG)

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

    # AUDIT_GRID_FULL_MARKERS (client_base_config.py) switches every grid
    # below between two looks, uniformly (the "Tags held" grid included --
    # its existence isn't gated by this flag, only its own cell style is):
    #   True:  every cell shows a marker (retired/held/in-use/done/unused)
    #          for whichever category isn't that grid's own, dimmed, so
    #          the numbers -- what that grid is actually for -- stand out.
    #   False: only retired shows (undimmed, as it always has); every
    #          other non-home-category cell stays blank, exactly as
    #          before this option existed.
    full_markers = cfg.AUDIT_GRID_FULL_MARKERS
    if full_markers:
        markers = {
            BikeTag.RETIRED: retired_tag_str,
            BikeTag.HELD: held_tag_str,
            BikeTag.IN_USE: in_use_tag_str,
            BikeTag.DONE: done_tag_str,
            BikeTag.UNUSED: available_tag_str,
        }
        other_style = k.DIM_STYLE
    else:
        markers = {BikeTag.RETIRED: retired_tag_str}
        other_style = k.NORMAL_STYLE

    if full_markers:
        pr.iprint()
        pr.iprint(
            f"Key: '{retired_tag_str.strip()}'=retired  '{held_tag_str.strip()}'=held  "
            f"'{in_use_tag_str.strip()}'=checked in  '{done_tag_str.strip()}'=checked out  "
            f"'{available_tag_str.strip()}'=unused today",
            style=k.NORMAL_STYLE,
        )

    # Bikes still onsite.
    pr.iprint()
    onsite_header = f"Bikes still onsite at {as_of_when.short}"
    if not full_markers:
        onsite_header += f" ({retired_tag_str} --> retired tag)"
    pr.iprint(onsite_header, style=k.SUBTITLE_STYLE)
    _draw_tag_grid(day, prefixes_on_hand.keys(), as_of_when, BikeTag.IN_USE, markers, other_style)

    # Bikes returned out -- tags matrix.
    if include_returns:
        pr.iprint()
        pr.iprint(f"Tags potentially available for re-use ({len(tags_done)} tags)", style=k.SUBTITLE_STYLE)
        _draw_tag_grid(day, prefixes_returned_out.keys(), as_of_when, BikeTag.DONE, markers, other_style)

    # Held tags -- unavailable for reuse today, but not retired. Shown
    # only when there is at least one (an ordinary day's audit is
    # unchanged), and independent of include_returns since this is core
    # status information, not an optional detail. Note: HOLD/UNHOLD carry
    # no timestamp, so unlike the rest of this report, this always
    # reflects *current* held state, not state "as of" as_of_when.
    held_tags = day.tags_held()
    if held_tags:
        prefixes_held = ut.tagnums_by_prefix(held_tags)
        pr.iprint()
        pr.iprint(
            f"Tags held, marked unavailable for (re-)use today ({len(held_tags)} tags)",
            style=k.SUBTITLE_STYLE,
        )
        _draw_tag_grid(day, prefixes_held.keys(), as_of_when, BikeTag.HELD, markers, other_style)

    # if include_notes:
    #     notes_bit(day)

    return
