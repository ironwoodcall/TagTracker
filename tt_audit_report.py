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

DEFAULT_MARKERS = {
    BikeTag.RETIRED: DEFAULT_RETIRED_TAG_STR,
    BikeTag.HELD: DEFAULT_HELD_TAG_STR,
    BikeTag.IN_USE: DEFAULT_IN_USE_TAG_STR,
    BikeTag.DONE: DEFAULT_DONE_TAG_STR,
    BikeTag.UNUSED: DEFAULT_AVAILABLE_TAG_STR,
}

# def notes_bit(day: OldTrackerDay) -> None:
#     """Add a 'notes' section to a report."""
#     pr.iprint()

#     pr.iprint("Today's notes:", style=k.SUBTITLE_STYLE)
#     if day.notes:
#         for line in day.notes:
#             pr.iprint(line, style=k.NORMAL_STYLE, num_indents=1)
#     else:
#         pr.iprint("There are no notes yet today.", num_indents=2)


def inout_summary(day: TrackerDay, as_of_when: VTime = VTime(""), live: bool = True) -> None:
    """Print summary table of # of bikes in, out and still onsite.

    live is forwarded to TrackerDay.tags_in_use()/num_tags_in_use() --
    pass live=False when as_of_when is a genuinely historical time. See
    BikeTag.status_as_at()'s docstring.
    """
    # # Count the totals

    total_in, regular_in, oversize_in = day.num_bikes_parked(as_of_when)
    total_out, regular_out, oversize_out = day.num_bikes_returned(as_of_when)

    # Count bikes currently onsite
    regular_onsite = 0
    oversize_onsite = 0
    for tagid in day.tags_in_use(as_of_when=as_of_when, live=live):
        if day.biketags[tagid].bike_type == k.REGULAR:
            regular_onsite += 1
        else:
            oversize_onsite += 1
    total_onsite = regular_onsite + oversize_onsite
    ut.squawk(f"{total_onsite=}, {day.num_tags_in_use(as_of_when, live=live)=}", cfg.DEBUG)

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
    full_markers: bool,
    tagnum_cache: dict,
    live: bool = True,
) -> None:
    """Print one prefix-by-tagnum grid.

    Each cell shows the tag number if the tag's current category (from
    status_as_at()) is home_category. Otherwise: if full_markers, it shows
    that category's marker from 'markers' (dimmed, so the grid's own
    numbers stand out); if not full_markers, only RETIRED gets a marker
    (undimmed, matching the look from before AUDIT_GRID_FULL_MARKERS
    existed) and every other non-home category stays blank. Either way, a
    cell is blank outright when there's no tag defined for that slot at
    all -- see AUDIT_GRID_FULL_MARKERS in client_base_config.py.

    tagnum_cache is a plain {prefix: greatest_tagnum} dict the caller
    keeps across every grid drawn for one report -- prefixes commonly
    recur between the onsite/re-use/held grids, and greatest_tagnum() is
    an O(n) scan over all of today's tags, so this avoids redoing that
    scan for a prefix this report has already seen.

    live is forwarded to status_as_at() -- pass live=False when
    as_of_when is a genuinely historical time, so a tag held since then
    doesn't hide its true as-of-then category. See status_as_at()'s
    docstring.
    """
    if not prefixes:
        pr.iprint("-no bikes-")
        return
    for prefix in sorted(prefixes):
        if prefix not in tagnum_cache:
            tagnum_cache[prefix] = ut.greatest_tagnum(
                prefix, day.regular_tagids, day.oversize_tagids
            )
        greatest_num = tagnum_cache[prefix]
        if greatest_num is None:
            continue
        segments = [(f"{prefix:3>} ", k.NORMAL_STYLE)]
        for i in range(0, greatest_num + 1):
            biketag = day.biketags.get(TagID(f"{prefix}{i}"))
            if not biketag:
                s, style = NO_ITEM_STR, k.NORMAL_STYLE
            else:
                category = biketag.status_as_at(as_of_when, live=live)
                if category == home_category:
                    s, style = f"{i:02d}", k.NORMAL_STYLE
                elif full_markers or category == BikeTag.RETIRED:
                    s = markers.get(category, NO_ITEM_STR)
                    style = k.DIM_STYLE if full_markers else k.NORMAL_STYLE
                else:
                    s, style = NO_ITEM_STR, k.NORMAL_STYLE
            segments.append((f" {s}", style))
        pr.iprint_segments(segments)


def audit_report(
    day: TrackerDay,
    args: list[str],
    include_notes: bool = True,
    include_returns: bool = False,
    markers: dict = None,
) -> None:
    """Create & display audit report as at a particular time.

    markers, if given, overrides one or more of DEFAULT_MARKERS' symbols
    (keyed by BikeTag status/HELD) -- e.g. tt_publish.py's plain-text
    variants. Any status left out keeps its default symbol.

    On entry: as_of_when_args is a list that can optionally
    have a first element that's a time at which to make this for.

    If include_notes is True, includes any notes from the day.

    If include_returns is True, shows a matrix of bikes for which
    tags were returned, else won't.

    This is smart about any checkouts that are later than as_of_when.
    If as_of_when is missing, then counts as of current time.

    """

    # What time will this audit report reflect? A report for right now
    # (no arg given, or "now" given explicitly) is live: it should reflect
    # tags held since as well as the visits themselves. A report for an
    # explicit past time is historical: HOLD/UNHOLD carries no timestamp,
    # so a since-held tag's true as-of-then status has to be shown instead
    # -- see BikeTag.status_as_at()'s docstring.
    raw_when = args[0] if args else "now"
    is_live = str(raw_when).strip().lower() == "now"
    as_of_when = VTime(raw_when)
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
    inout_summary(day, as_of_when, live=is_live)

    # Want list of biketags on hand and those returned but not reused
    tags_in_use = day.tags_in_use(as_of_when=as_of_when, live=is_live)
    tags_done = day.tags_done(as_of_when, live=is_live)
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
    # tag_markers always has all five symbols regardless of the flag --
    # full_markers itself (passed to _draw_tag_grid) is what decides which
    # of them actually get shown; see _draw_tag_grid's docstring.
    full_markers = cfg.AUDIT_GRID_FULL_MARKERS
    tag_markers = {**DEFAULT_MARKERS, **(markers or {})}

    if full_markers:
        pr.iprint()
        pr.iprint(
            f"Key: '{tag_markers[BikeTag.RETIRED].strip()}'=retired  "
            f"'{tag_markers[BikeTag.HELD].strip()}'=suspended  "
            f"'{tag_markers[BikeTag.IN_USE].strip()}'=checked in  "
            f"'{tag_markers[BikeTag.DONE].strip()}'=checked out  "
            f"'{tag_markers[BikeTag.UNUSED].strip()}'=unused today",
            style=k.NORMAL_STYLE,
        )

    # Shared across every grid below -- greatest_tagnum() is an O(n) scan
    # and prefixes commonly recur between grids, so this avoids rescanning
    # for a prefix already looked up earlier in this same report.
    tagnum_cache: dict = {}

    # Bikes still onsite.
    pr.iprint()
    onsite_header = f"Bikes still onsite at {as_of_when.short}"
    if not full_markers:
        onsite_header += f" ({tag_markers[BikeTag.RETIRED]} --> retired tag)"
    pr.iprint(onsite_header, style=k.SUBTITLE_STYLE)
    _draw_tag_grid(
        day, prefixes_on_hand.keys(), as_of_when, BikeTag.IN_USE, tag_markers,
        full_markers, tagnum_cache, live=is_live,
    )

    # Bikes returned out -- tags matrix.
    if include_returns:
        pr.iprint()
        pr.iprint(f"Tags potentially available for re-use ({len(tags_done)} tags)", style=k.SUBTITLE_STYLE)
        _draw_tag_grid(
            day, prefixes_returned_out.keys(), as_of_when, BikeTag.DONE, tag_markers,
            full_markers, tagnum_cache, live=is_live,
        )

    # Held tags -- unavailable for reuse today, but not retired. Shown
    # only when there is at least one (an ordinary day's audit is
    # unchanged), and independent of include_returns since this is core
    # status information, not an optional detail. Note: HOLD/UNHOLD carry
    # no timestamp, so unlike the rest of this report, this grid always
    # reflects *current* held state, not state "as of" as_of_when --
    # deliberately live=True regardless of is_live above.
    held_tags = day.tags_held()
    if held_tags:
        prefixes_held = ut.tagnums_by_prefix(held_tags)
        pr.iprint()
        pr.iprint(
            f"Tags suspended, marked unavailable until tomorrow ({len(held_tags)} tags)",
            style=k.SUBTITLE_STYLE,
        )
        if not is_live:
            pr.iprint(
                f"(This shows tags currently suspended, not as of {as_of_when.short})",
                style=k.DIM_STYLE,
            )
        _draw_tag_grid(
            day, prefixes_held.keys(), as_of_when, BikeTag.HELD, tag_markers,
            full_markers, tagnum_cache, live=True,
        )

    # if include_notes:
    #     notes_bit(day)

    return
