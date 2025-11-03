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

import common.tt_constants as k
import client_base_config as cfg
import tt_printer as pr
from common.tt_time import VTime
from common.tt_tag import TagID
import tt_reports as rep

# from tt_realtag import Stay
from common.tt_trackerday import TrackerDay

# import client_base_config as cfg
import common.tt_util as ut


# These are the symbols & styles used in the tag inventory matrix.
# Each is a tuple of (symbol,style).
# Each symbol should be 2 characters wide.  Warning if using fancy unicode
# that those characters come in various widths, platform-dependent.
TAG_INV_UNKNOWN = ("  ", k.NORMAL_STYLE)
TAG_INV_AVAILABLE = (" -", k.NORMAL_STYLE)
TAG_INV_BIKE_IN = ("In", k.ANSWER_STYLE)
TAG_INV_BIKE_OUT = ("Ou", k.PROMPT_STYLE)
TAG_INV_RETIRED = ("Rt", k.WARNING_STYLE)
TAG_INV_ERROR = ("!?", k.ERROR_STYLE)


def _index_line(max_tag_num):
    """Print an index line for the matrix."""
    pr.iprint("    ", style=k.HIGHLIGHT_STYLE, end="", num_indents=1)
    for i in range(0, max_tag_num + 1):
        pr.iprint(f"   {i:02d}", style=k.HIGHLIGHT_STYLE, end="", num_indents=0)


def tag_inventory_matrix(
    day: TrackerDay, as_of_when: str = "", include_empty_groups: bool = True
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

    as_of_when = VTime(as_of_when or "now")
    pr.iprint()
    pr.iprint(
        f"Tags status {rep.time_description(as_of_when,day=day)}", style=k.TITLE_STYLE
    )
    pr.iprint(
        f"Key: '{TAG_INV_AVAILABLE[0]}'=Unused today; "
        f"'{TAG_INV_BIKE_IN[0]}'=Bike In; "
        f"'{TAG_INV_BIKE_OUT[0]}'=Bike Out (tag is reusable); "
        f"'{TAG_INV_RETIRED[0]}'=Retired",
        style=k.NORMAL_STYLE,
    )
    pr.iprint()
    max_tag_num = 0
    prefixes = set()
    for tag in day.regular_tagids | day.oversize_tagids:
        if tag.number > max_tag_num:
            max_tag_num = tag.number
        prefixes.add(tag.prefix)
    _index_line(max_tag_num)
    pr.iprint()
    for prefix in sorted(prefixes):
        # Make a list of the tag states for this row.
        # tag_states is a list of tuples (same as cfg.TAG_INV_*)

        # UNKNOWN -> ?
        # AVAILABLE -> UNUSED
        # DONE
        # BIKE_IN -> IN_USE
        # RETIRED
        #

        tag_states = []
        for i in range(0, max_tag_num + 1):
            tagid = TagID(f"{prefix}{i}")
            if tagid not in day.biketags:
                tag_states.append(TAG_INV_UNKNOWN)
                continue
            this_biketag = day.biketags[tagid]
            if not this_biketag:
                tag_states.append(TAG_INV_UNKNOWN)
                continue
            tag_status = this_biketag.status_as_at(as_of_when)
            # this_tag = Stay(f"{prefix}{i}", day, as_of_when)
            if not tag_status:
                tag_states.append(TAG_INV_UNKNOWN)
            elif tag_status in {this_biketag.UNUSED}:
                tag_states.append(TAG_INV_AVAILABLE)
            elif tag_status == this_biketag.IN_USE:
                tag_states.append(TAG_INV_BIKE_IN)
            elif tag_status == this_biketag.DONE:
                tag_states.append(TAG_INV_BIKE_OUT)
            elif tag_status == this_biketag.RETIRED:
                tag_states.append(TAG_INV_RETIRED)
            else:
                tag_states.append(TAG_INV_ERROR)

        # Are there any used tags in this row?
        this_prefix_used = any(
            x[0] in [TAG_INV_BIKE_IN[0], TAG_INV_BIKE_OUT[0]] for x in tag_states
        )
        ut.squawk(f"{prefix=},{ [TAG_INV_BIKE_IN[0], TAG_INV_BIKE_OUT[0]]=}", cfg.DEBUG)
        ut.squawk(f"{this_prefix_used=},{[x[0] for x in tag_states]=}", cfg.DEBUG)
        if this_prefix_used or include_empty_groups:
            pr.iprint(f"{prefix:3s} ", style=k.HIGHLIGHT_STYLE, end="")
            for tup in tag_states:
                pr.iprint("   ", style=k.NORMAL_STYLE, end="", num_indents=0)
                pr.iprint(tup[0], style=tup[1], end="", num_indents=0)
            pr.iprint()

    _index_line(max_tag_num)
    pr.iprint()


def retired_report(day: TrackerDay) -> None:
    """List retired tags."""
    if not day.retired_tagids:
        return
    pr.iprint()
    pr.iprint("Retired tags", style=k.SUBTITLE_STYLE)

    for group in ut.taglists_by_colour(day.retired_tagids):
        retireds_str = " ".join(tag.cased for tag in group)
        ut.line_wrapper(retireds_str, print_handler=pr.iprint)

    # retireds_str = " ".join(
    #     [x.cased for sub in ut.taglists_by_colour(day.retired_tagids) for x in sub]
    # )
    # ut.line_wrapper(retireds_str, print_handler=pr.iprint)


def tags_config_report(
    day: TrackerDay, args: list, include_empty_groups: bool = True
) -> None:
    """Report the current tags configuration."""
    as_of_when = VTime((args and args[0]) or "now")
    if not as_of_when:
        pr.iprint(f"Unrecognized time {as_of_when.original}", style=k.WARNING_STYLE)
        return
    pr.iprint()
    pr.iprint("Current tags configuration", style=k.TITLE_STYLE)
    # colours_report(day)
    retired_report(day)
    tag_inventory_matrix(day, as_of_when, include_empty_groups=include_empty_groups)
