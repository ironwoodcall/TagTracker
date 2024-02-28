"""All tags overview.

Copyright (C) 2023 Julias Hocking

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
- unknown (like, a missing member)  '  '
- available                         '--'
- bike in                           '<<'
- bike out                          '>>'
- retired                           ' ●'

"""
from tt_globals import *
import tt_printer as pr
from tt_time import VTime
from tt_tag import TagID
from tt_realtag import Stay
from tt_trackerday import TrackerDay
import tt_conf as cfg
import tt_util as ut


def index_line(max_tag_num):
    """Print an index line for the matrix."""
    pr.iprint(f"{' ':3s} ", style=cfg.HIGHLIGHT_STYLE, end="")
    for i in range(0, max_tag_num + 1):
        pr.iprint(f" {i:02d}", style=cfg.HIGHLIGHT_STYLE, end="")


def tag_inventory_matrix(
    day: TrackerDay, as_of_when: str = "now", include_empty_groups: bool = True
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
    pr.iprint(f"Tags status {as_of_when.as_at}", style=cfg.TITLE_STYLE)
    pr.iprint(
        f"Key: '{cfg.TAG_INV_AVAILABLE[0]}'=Available; "
        f"'{cfg.TAG_INV_BIKE_IN[0]}'=Bike In; "
        f"'{cfg.TAG_INV_BIKE_OUT[0]}'=Bike Out; "
        f"'{cfg.TAG_INV_RETIRED[0]}'=Retired",
        style=cfg.NORMAL_STYLE,
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
        used_prefix = False
        prefix_row = pr.text_style(f"{prefix:3s} ", style=cfg.HIGHLIGHT_STYLE)
        # pr.iprint(f"{prefix:3s} ", style=cfg.HIGHLIGHT_STYLE, end="")
        for i in range(0, max_tag_num + 1):
            this_tag = Stay(f"{prefix}{i}", day, as_of_when)
            if not this_tag or not this_tag.state:
                # pr.iprint(
                #     " " + cfg.TAG_INV_UNKNOWN[0],
                #     style=cfg.TAG_INV_UNKNOWN[1],
                #     end="",
                # )
                prefix_row += "  " + pr.text_style(
                    " " + cfg.TAG_INV_UNKNOWN[0],
                    style=cfg.TAG_INV_UNKNOWN[1],
                )
            elif this_tag.state == USABLE:
                # pr.iprint(
                #     " " + cfg.TAG_INV_AVAILABLE[0],
                #     style=cfg.TAG_INV_AVAILABLE[1],
                #     end="",
                # )
                prefix_row += "  " + pr.text_style(
                    " " + cfg.TAG_INV_AVAILABLE[0],
                    style=cfg.TAG_INV_AVAILABLE[1],
                )
            elif this_tag.state == BIKE_IN:
                used_prefix = True
                # pr.iprint(
                #     " " + cfg.TAG_INV_BIKE_IN[0],
                #     style=cfg.TAG_INV_BIKE_IN[1],
                #     end="",
                # )
                prefix_row += "  " + pr.text_style(
                    " " + cfg.TAG_INV_BIKE_IN[0],
                    style=cfg.TAG_INV_BIKE_IN[1],
                )
            elif this_tag.state == BIKE_OUT:
                used_prefix = True
                # pr.iprint(
                #     " " + cfg.TAG_INV_BIKE_OUT[0],
                #     style=cfg.TAG_INV_BIKE_OUT[1],
                #     end="",
                # )
                prefix_row += "  " + pr.text_style(
                    " " + cfg.TAG_INV_BIKE_OUT[0],
                    style=cfg.TAG_INV_BIKE_OUT[1],
                )
            elif this_tag.state == RETIRED:
                # pr.iprint(
                #     " " + cfg.TAG_INV_RETIRED[0],
                #     style=cfg.TAG_INV_RETIRED[1],
                #     end="",
                # )
                prefix_row += "  " + pr.text_style(
                    " " + cfg.TAG_INV_RETIRED[0],
                    style=cfg.TAG_INV_RETIRED[1],
                )
            else:
                # pr.iprint(" ?", style=cfg.ERROR_STYLE, end="")
                prefix_row += "  " + pr.text_style("?", style=cfg.ERROR_STYLE)
        if used_prefix or include_empty_groups:
            pr.iprint(prefix_row)
    index_line(max_tag_num)
    pr.iprint()


def colours_report(day: TrackerDay) -> None:
    """List colours in use."""
    type_names = {
        UNKNOWN: "None",
        REGULAR: "Regular",
        OVERSIZE: "Oversize",
        MIXED: "Mixed",
    }

    # Make a dict of the colour letters that's all lowercase
    colours = {k.lower(): v for k, v in day.colour_letters.items()}
    # Dict of bike types for tags: UNKNOWN, OVERSIZE, REGULAR or MIXED
    tag_type = dict(
        zip(list(day.colour_letters.keys()), [UNKNOWN for _ in range(0, 100)])
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
        btype = REGULAR if tag in day.regular else OVERSIZE
        if tag_type[code] == UNKNOWN:
            tag_type[code] = btype
        elif tag_type[code] != btype:
            tag_type[code] = MIXED
        # Tag count
        tag_count[code] += 1

    pr.iprint()
    pr.iprint("Code Colour   Bike type  Count", style=cfg.SUBTITLE_STYLE)
    for code in sorted(colours):
        name = colours[code].title()
        code_str = code.upper() if TagID.uc() else code
        pr.iprint(
            f" {code_str:>2}  {name:8} {type_names[tag_type[code]]:8}  "
            f"{tag_count[code]:4d} tags"
        )


def retired_report(day: TrackerDay) -> None:
    """List retired tags."""
    pr.iprint()
    pr.iprint("Retired tags", style=cfg.SUBTITLE_STYLE)
    if not day.retired:
        pr.iprint("--no retired tags--")
        return
    retireds_str = " ".join(
        [x.cased for sub in ut.taglists_by_prefix(day.retired) for x in sub]
    )
    ut.line_wrapper(retireds_str, print_handler=pr.iprint)


def tags_config_report(
    day: TrackerDay, args: list, include_empty_groups: bool = True
) -> None:
    """Report the current tags configuration."""
    as_of_when = (args + ["now"])[0]
    as_of_when = VTime(as_of_when)
    if not as_of_when:
        pr.iprint(f"Unrecognized time {as_of_when.original}", style=cfg.WARNING_STYLE)
        return
    pr.iprint()
    pr.iprint("Current tags configuration", style=cfg.TITLE_STYLE)
    colours_report(day)
    retired_report(day)
    tag_inventory_matrix(day, as_of_when, include_empty_groups=include_empty_groups)
