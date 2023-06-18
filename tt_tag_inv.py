"""All tags overview.

Symbols for:
- unknown (like, a missing member)  '  '
- available                         '--'
- bike in                           '<<'
- bike out                          '>>'
- retired                           ' ●'

"""
from tt_globals import *
import tt_printer as pr
from tt_realtag import Stay
import tt_trackerday as td
import tt_conf as cfg
import tt_util as ut


def tag_inventory_matrix(day: td.TrackerDay, as_of_when: str = "now") -> None:
    unknown_str = "  "
    available_str = " -"
    bike_in_str = "<<"
    bike_out_str = ">>"
    retired_str = " ●"

    as_of_when = VTime(as_of_when)
    pr.iprint()
    pr.iprint(f"Tags status {as_of_when.as_at}", style=cfg.TITLE_STYLE)
    pr.iprint(
        f"Key: '{available_str.strip()}'=Available; '{bike_in_str}'=Bike In; "
        f"'{bike_out_str}'=Bike Out; '{retired_str.strip()}'=Retired",
        style=cfg.SUBTITLE_STYLE,
    )
    pr.iprint()
    max_tag_num = 0
    prefixes = set()
    for tag in day.regular | day.oversize:
        if tag.number > max_tag_num:
            max_tag_num = tag.number
        prefixes.add(tag.prefix)
    pr.iprint(f"{' ':3s} ", end="")
    for i in range(0, max_tag_num + 1):
        pr.iprint(f" {i:02d}", end="")
    pr.iprint()
    for prefix in sorted(prefixes):
        pr.iprint(f"{prefix:3s} ", end="")
        for i in range(0, max_tag_num + 1):
            this_tag = Stay(f"{prefix}{i}", day, as_of_when)
            if not this_tag or not this_tag.state:
                s = unknown_str
            elif this_tag.state == USABLE:
                s = available_str
            elif this_tag.state == BIKE_IN:
                s = bike_in_str
            elif this_tag.state == BIKE_OUT:
                s = bike_out_str
            elif this_tag.state == RETIRED:
                s = retired_str
            else:
                s = " ?"
            pr.iprint(f" {s}", end="")
        pr.iprint()

def colours_report(day: td.TrackerDay) -> None:
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
    tag_count = dict(
        zip(list(day.colour_letters.keys()), [0 for _ in range(0, 100)])
    )
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


def retired_report(day: td.TrackerDay) -> None:
    """List retired tags."""
    pr.iprint()
    pr.iprint("Retired tags", style=cfg.SUBTITLE_STYLE)
    if not day.retired:
        pr.iprint("--no retired tags--")
        return
    pr.iprint(
        " ".join(
            [
                x.cased
                for sub in ut.taglists_by_prefix(day.retired)
                for x in sub
            ]
        )
    )


def tags_config_report(day: td.TrackerDay,args:list) -> None:
    """Report the current tags configuration."""
    as_of_when = (args + ["now"])[0]
    as_of_when = VTime(as_of_when)
    if not as_of_when:
        pr.iprint(
            f"Unrecognized time {as_of_when.original}", style=cfg.WARNING_STYLE
        )
        return
    pr.iprint()
    pr.iprint("Current tags configuration", style=cfg.TITLE_STYLE)
    colours_report(day)
    retired_report(day)
    tag_inventory_matrix(day, as_of_when)

