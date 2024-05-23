"""All tags overview.

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


Symbols for:
- unknown (like, a missing member)  '!?'
- available                         ' -'
- bike in                           'In'
- bike out                          'Ou'
- retired                           'Re'
==> These are set in tt_base_conf.py (can be overridden in tt_conf.py)

"""

import tt_constants as k
import tt_printer as pr
from tt_time import VTime
from tt_tag import TagID
from tt_realtag import Stay
from tt_trackerday import OldTrackerDay
#import client_base_config as cfg
import tt_util as ut


def index_line(max_tag_num):
    """Print an index line for the matrix."""
    pr.iprint("    ", style=k.HIGHLIGHT_STYLE, end="",num_indents=1)
    for i in range(0, max_tag_num + 1):
        pr.iprint(f"   {i:02d}", style=k.HIGHLIGHT_STYLE, end="",num_indents=0)


def tag_inventory_matrix(
    day: OldTrackerDay, as_of_when: str = "now", include_empty_groups: bool = True
) -> None:
    """Print a matrix of status of all known tags.

    If include_empty_groups is False, this will suppress any prefix groups
    for which there are no bikes In or Out.

    This reads these variables from config, each is a symbol/style tuple:
        TAG_INV_UNKNOWN
        TAG_INV_AVAILABLE
        TAG_INV_BIKE_IN
        TAG_INV_BIKE_OUT
        TAG_INV_RETIRED

    """

    as_of_when = VTime(as_of_when)
    pr.iprint()
    pr.iprint(f"Tags status {as_of_when.as_at}", style=k.TITLE_STYLE)
    pr.iprint(
        f"Key: '{k.TAG_INV_AVAILABLE[0]}'=Available; "
        f"'{k.TAG_INV_BIKE_IN[0]}'=Bike In; "
        f"'{k.TAG_INV_BIKE_OUT[0]}'=Bike Out; "
        f"'{k.TAG_INV_RETIRED[0]}'=Retired",
        style=k.NORMAL_STYLE,
    )
    pr.iprint()
    max_tag_num = 0
    prefixes = set()
    for tag in day.regular | day.oversize:
        if tag.number > max_tag_num:
            max_tag_num = tag.number
        prefixes.add(tag.prefix)
    index_line(max_tag_num)
    pr.iprint()
    for prefix in sorted(prefixes):
        # Make a list of the tag states for this row.
        # tag_states is a list of tuples (same as cfg.TAG_INV_*)
        tag_states = []
        for i in range(0, max_tag_num + 1):
            this_tag = Stay(f"{prefix}{i}", day, as_of_when)
            if not this_tag or not this_tag.state:
                tag_states.append(k.TAG_INV_UNKNOWN)
            elif this_tag.state == k.USABLE:
                tag_states.append(k.TAG_INV_AVAILABLE)
            elif this_tag.state == k.BIKE_IN:
                tag_states.append(k.TAG_INV_BIKE_IN)
            elif this_tag.state == k.BIKE_OUT:
                tag_states.append(k.TAG_INV_BIKE_OUT)
            elif this_tag.state == k.RETIRED:
                tag_states.append(k.TAG_INV_RETIRED)
            else:
                tag_states.append(k.TAG_INV_ERROR)

        # Are there any used tags in this row?
        this_prefix_used = any(
            x[0] in [k.TAG_INV_BIKE_IN[0], k.TAG_INV_BIKE_OUT[0]]
            for x in tag_states
        )
        # ut.squawk(f"{prefix=},{ [cfg.TAG_INV_BIKE_IN[0], cfg.TAG_INV_BIKE_OUT[0]]=}")
        # ut.squawk(f"{this_prefix_used=},{[x[0] for x in tag_states]=}")
        if this_prefix_used or include_empty_groups:
            pr.iprint(f"{prefix:3s} ", style=k.HIGHLIGHT_STYLE, end="")
            for tup in tag_states:
                pr.iprint("   ",style=k.NORMAL_STYLE,end="",num_indents=0)
                pr.iprint(tup[0], style=tup[1], end="",num_indents=0)
            pr.iprint()

    index_line(max_tag_num)
    pr.iprint()


def colours_report(day: OldTrackerDay) -> None:
    """List colours in use."""
    type_names = {
        k.UNKNOWN: "None",
        k.REGULAR: "Regular",
        k.OVERSIZE: "Oversize",
        k.MIXED: "Mixed",
    }

    # Make a dict of the colour letters that's all lowercase
    colours = {k.lower(): v for k, v in day.colour_letters.items()}
    # Dict of bike types for tags: UNKNOWN, OVERSIZE, REGULAR or MIXED
    tag_type = dict(
        zip(list(day.colour_letters.keys()), [k.UNKNOWN for _ in range(0, 100)])
    )
    # Dictionary of how many tags are of each colour.
    tag_count = dict(zip(list(day.colour_letters.keys()), [0 for _ in range(0, 100)]))
    # Count and categorize the tags (all available for use)
    for tag in day.all_tags():
        code = tag.colour.lower()
        if code not in colours:
            ut.squawk(f"bad colour for {tag}: '{code}' in colours_report()")
            continue
        # Tag type
        btype = k.REGULAR if tag in day.regular else k.OVERSIZE
        if tag_type[code] == k.UNKNOWN:
            tag_type[code] = btype
        elif tag_type[code] != btype:
            tag_type[code] = k.MIXED
        # Tag count
        tag_count[code] += 1

    pr.iprint()
    pr.iprint("Code Colour   Bike type  Count", style=k.SUBTITLE_STYLE)
    for code in sorted(colours):
        name = colours[code].title()
        code_str = code.upper() if TagID.uc() else code
        pr.iprint(
            f" {code_str:>2}  {name:8} {type_names[tag_type[code]]:8}  "
            f"{tag_count[code]:4d} tags"
        )


def retired_report(day: OldTrackerDay) -> None:
    """List retired tags."""
    pr.iprint()
    pr.iprint("Retired tags", style=k.SUBTITLE_STYLE)
    if not day.retired:
        pr.iprint("--no retired tags--")
        return
    retireds_str = " ".join(
        [x.cased for sub in ut.taglists_by_prefix(day.retired) for x in sub]
    )
    ut.line_wrapper(retireds_str, print_handler=pr.iprint)


def tags_config_report(
    day: OldTrackerDay, args: list, include_empty_groups: bool = True
) -> None:
    """Report the current tags configuration."""
    as_of_when = (args + ["now"])[0]
    as_of_when = VTime(as_of_when)
    if not as_of_when:
        pr.iprint(f"Unrecognized time {as_of_when.original}", style=k.WARNING_STYLE)
        return
    pr.iprint()
    pr.iprint("Current tags configuration", style=k.TITLE_STYLE)
    colours_report(day)
    retired_report(day)
    tag_inventory_matrix(day, as_of_when, include_empty_groups=include_empty_groups)
