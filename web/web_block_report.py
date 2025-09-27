#!/usr/bin/env python3
"""CGI script for TagTracker time-block report(s).

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

import sqlite3
import copy
from collections import defaultdict

import common.tt_dbutil as db
from common.tt_time import VTime
import common.tt_util as ut

# import tt_block
import web_common as cc
import datacolors as dc
import colortable
from web_daterange_selector import generate_date_filter_form

XY_BOTTOM_COLOR = dc.Color((252, 252, 248)).html_color
X_TOP_COLOR = "red"
Y_TOP_COLOR = "royalblue"
NORMAL_MARKER = chr(0x25A0)  # chr(0x25AE)  # chr(0x25a0)#chr(0x25cf)
HIGHLIGHT_MARKER = chr(0x2B24)  # chr(0x25cf) #chr(0x25AE)  # chr(0x25a0)#chr(0x25cf)


# Uses precomputed block summaries stored in the BLOCK table rather than
# rebuilding them from raw visit rows.

class _OneBlock:
    """Data about a single timeblock."""

    def __init__(self):
        self.num_in = 0
        self.num_out = 0
        self.full = 0
        self.so_far = 0

    @property
    def activity(self):
        return self.num_in + self.num_out


class _OneDay:
    _allblocks = {}
    for t in range(6 * 60, 24 * 60, 30):
        _allblocks[VTime(t)] = _OneBlock()

    def __init__(self) -> None:
        self.day_total_bikes = None
        self.day_max_bikes = None
        self.day_max_bikes_time = None
        self.blocks = copy.deepcopy(_OneDay._allblocks)


def _process_iso_dow(
    iso_dow,
    orgsite_id: int,
    start_date: str = "",
    end_date: str = "",
) -> tuple[str, str]:
    # Use dow to make report title prefix, and day filter for SQL queries.
    conditions = [f"orgsite_id = {orgsite_id}"]
    if iso_dow:
        iso_dow = int(iso_dow)
        title_bit = f"{ut.dow_str(iso_dow)} "
        conditions.append(f"strftime('%w',date) = '{iso_dow % 7}'")
    else:
        title_bit = ""
    if start_date:
        conditions.append(f"date >= '{start_date}'")
    if end_date:
        conditions.append(f"date <= '{end_date}'")

    day_where_clause = f" where {' and '.join(conditions)}"

    return title_bit, day_where_clause


def _fetch_block_rows(ttdb: sqlite3.Connection, day_filter: str) -> list[db.DBRow]:
    sel = (
        "select "
        "    day.date,"
        "    block.time_start,"
        "    block.num_incoming_combined,"
        "    block.num_outgoing_combined,"
        "    block.num_on_hand_combined "
        "from day "
        "JOIN block ON block.day_id = day.id"
        f"    {day_filter} "
        "order by day.date, block.time_start"
    )
    return db.db_fetch(ttdb, sel)


def _fetch_day_data(ttdb: sqlite3.Connection, day_filter: str):
    sel = (
        "select "
        "   date, num_parked_combined day_total_bikes, "
        "      num_fullest_combined day_max_bikes, "
        "      time_fullest_combined day_max_bikes_time "
        "from day "
        f"  {day_filter} "
        "   order by date desc"
    )
    return db.db_fetch(ttdb, sel)


def process_day_data(dayrows: list) -> tuple[dict[str:_OneDay], _OneDay]:
    tabledata = {}
    for dayrow in dayrows:
        date = dayrow.date
        day_summary = _OneDay()
        day_summary.day_total_bikes = dayrow.day_total_bikes
        day_summary.day_max_bikes = dayrow.day_max_bikes
        day_summary.day_max_bikes_time = dayrow.day_max_bikes_time
        tabledata[date] = day_summary

    day_maxes = _OneDay()
    day_maxes.day_max_bikes = max([d.day_max_bikes for d in tabledata.values()])
    day_maxes.day_total_bikes = max([d.day_total_bikes for d in tabledata.values()])
    return tabledata, day_maxes


def process_blocks_data(
    tabledata: dict, blockrows: list[db.DBRow]
) -> tuple[dict[VTime:_OneBlock], _OneBlock]:
    """Populate time-block data from BLOCK table rows."""

    rows_by_date = defaultdict(dict)
    for row in blockrows:
        block_time = VTime(row.time_start)
        if not block_time:
            continue
        rows_by_date[row.date][block_time] = row

    for date, day_summary in tabledata.items():
        blocks_for_day = rows_by_date.get(date, {})
        if not blocks_for_day:
            continue
        so_far_today = 0
        for block_key in sorted(day_summary.blocks.keys()):
            block_row = blocks_for_day.get(block_key)
            if not block_row:
                continue
            thisblock: _OneBlock = day_summary.blocks[block_key]
            num_in = block_row.num_incoming_combined or 0
            num_out = block_row.num_outgoing_combined or 0
            so_far_today += num_in
            thisblock.num_in = num_in
            thisblock.num_out = num_out
            thisblock.so_far = so_far_today
            thisblock.full = block_row.num_on_hand_combined or 0

    # Find overall maximum values
    block_maxes = _OneBlock()
    all_blocks = [b for t in tabledata.values() for b in t.blocks.values()]
    if all_blocks:
        block_maxes.num_in = max(b.num_in for b in all_blocks)
        block_maxes.num_out = max(b.num_out for b in all_blocks)
        block_maxes.full = max(b.full for b in all_blocks)
        block_maxes.so_far = max(b.so_far for b in all_blocks)

    return tabledata, block_maxes


def print_the_html(
    tabledata: dict,
    xy_colors: dc.MultiDimension,
    marker_colors: dc.Dimension,
    day_total_bikes_colors: dc.Dimension,
    day_full_colors: dc.Dimension,
    pages_back: int,
    page_title_prefix: str = "",
    date_filter_html: str = "",
    date_range_label: str = "",
):
    def column_gap() -> str:
        """Make a thicker vertical cell border to mark off sets of blocks."""
        return "<td style='width:auto;border: 2px solid rgb(200,200,200);padding: 0px 0px;'></td>"

    title = f"{page_title_prefix}Time block summaries"
    if date_range_label:
        title = f"{title} ({date_range_label})"
    print(f"<h1>{title}</h1>")
    print(f"{cc.main_and_back_buttons(pages_back)}<br><br>")
    if date_filter_html:
        print(date_filter_html)
    print("<br><br>")

    # We frequently use xycolors(0,0). Save & store it.
    zero_bg = xy_colors.css_bg((0, 0))

    # Legend for x/y (background colours)
    tab = colortable.html_2d_color_table(
        xy_colors,
        title="<b>Legend for in & out activity</b>",
        num_columns=9,
        num_rows=9,
        cell_size=20,
    )
    print(tab)

    # Legend for markers
    print("</p></p>")
    tab = colortable.html_1d_text_color_table(
        marker_colors,
        title="<b>Legend for number of bikes onsite at once</b>",
        subtitle=f"{HIGHLIGHT_MARKER} = Time with the most bikes onsite",
        marker=NORMAL_MARKER,
        bg_color="grey",  # bg_color=xy_colors.get_color(0,0).html_color
        num_columns=20,
    )
    print(tab)
    print("</p></p>")

    # Main table. Column headings
    print("<table class=general_table>")
    print(
        "<style>td {text-align: right;text-align: center; width: 13px;padding: 4px 4px;}</style>"
    )
    print("<tr>")
    print(f"<th colspan=3><a href='{cc.selfref(what=cc.WHAT_BLOCKS)}'>Date</a></th>")
    print("<th colspan=7>6:00 - 9:00</th>")
    print("<th colspan=7>9:00 - 12:00</th>")
    print("<th colspan=7>12:00 - 15:00</th>")
    print("<th colspan=7>15:00 - 18:00</th>")
    print("<th colspan=7>18:00 - 21:00</th>")
    print("<th colspan=7>21:00 - 24:00</th>")
    print("<th>Bikes<br>parked</th>")
    print("<th>Most<br/>bikes</th>")
    print("</tr>")

    date_today = ut.date_str("today")
    time_now = VTime("now")
    for date in sorted(tabledata.keys(), reverse=True):
        dayname = ut.date_str(date, dow_str_len=3)
        thisday: _OneDay = tabledata[date]
        tags_report_link = cc.selfref(what=cc.WHAT_ONE_DAY, qdate=date)
        dow_report_link = cc.selfref(what=cc.WHAT_BLOCKS_DOW, qdow=ut.dow_int(dayname))
        print("<tr style='text-align: center; width: 15px;padding: 0px 3px;'>")
        print(f"<td style=width:auto;><a href='{tags_report_link}'>{date}</a></td>")
        print(f"<td style=width:auto;><a href='{dow_report_link}'>{dayname}</a></td>")

        # Find which time block had the greatest num of bikes this day.
        fullest_block_this_day = ut.block_start(thisday.day_max_bikes_time)

        # Print the blocks for this day.
        html = ""
        for num, block_key in enumerate(sorted(thisday.blocks.keys())):
            if num % 6 == 0:
                html += column_gap()
            thisblock: _OneBlock = thisday.blocks[block_key]
            if date == date_today and block_key >= time_now:
                # Today, later than now
                cell_color = f"color:{XY_BOTTOM_COLOR};background:{XY_BOTTOM_COLOR};"
                cell_title = "Future unknown"
            elif thisblock.num_in == 0 and thisblock.num_out == 0:
                # No activity this block
                cell_color = f"{zero_bg};" f"{marker_colors.css_fg(thisblock.full)};"
                cell_title = (
                    f"Bikes in: 0\nBikes out: 0\n"
                    f"Bikes so far: {thisblock.so_far}\nBikes at end: {thisblock.full} "
                )
            else:
                # Regular block with activity in it
                cell_color = (
                    f"{xy_colors.css_bg((thisblock.num_in, thisblock.num_out))};"
                    f"{marker_colors.css_fg(thisblock.full)};"
                )
                cell_title = (
                    f"Bikes in: {thisblock.num_in}\nBikes out: {thisblock.num_out}\n"
                    f"Bikes so far: {thisblock.so_far}\nBikes at end: {thisblock.full} "
                )

            # Special marker & hover text if this is the fullest block of the day
            if block_key == fullest_block_this_day:
                marker = HIGHLIGHT_MARKER
                cell_title = f"{cell_title}\nMost bikes today: {thisday.day_max_bikes}"
            else:
                marker = NORMAL_MARKER

            html += (
                f"<td title='{cell_title}' style='{cell_color};"
                # "text-align: center; width: 15px;padding: 0px 3px;"
                "'>"
                f"{marker}</td>"  ##</a></td>"
            )
        html += column_gap()

        s = day_total_bikes_colors.css_bg_fg(thisday.day_total_bikes)
        html += f"<td style='{s};width:auto;'>{thisday.day_total_bikes}</td>"
        s = day_full_colors.css_bg_fg(thisday.day_max_bikes)
        html += f"<td style='{s};width:auto;'>{thisday.day_max_bikes}</td>"
        html += "</tr>\n"
        print(html)

    print("</table>")


def blocks_report(
    ttdb: sqlite3.Connection,
    iso_dow: str | int = "",
    pages_back: int = 1,
    start_date: str = "",
    end_date: str = "",
):
    """Print block-by-block colors report for all days

    If dow is None then do for all days of the week, otherwise do
    for ISO int dow (1=Monday-->7=Sunday)

    """

    orgsite_id = 1  # orgsite_id hardcoded

    cc.test_dow_parameter(iso_dow, list_ok=False)

    start_date, end_date, _default_start, _default_end = cc.resolve_date_range(
        ttdb,
        orgsite_id=orgsite_id,
        start_date=start_date,
        end_date=end_date,
    )

    title_bit, day_where_clause = _process_iso_dow(
        iso_dow,
        orgsite_id=orgsite_id,
        start_date=start_date,
        end_date=end_date,
    )

    target_what = cc.WHAT_BLOCKS_DOW if iso_dow else cc.WHAT_BLOCKS
    self_url = cc.selfref(
        what=target_what,
        qdow=iso_dow if iso_dow else None,
        start_date=start_date,
        end_date=end_date,
        pages_back=pages_back + 1,
    )
    date_filter_html = generate_date_filter_form(
        self_url,
        default_start_date=start_date,
        default_end_date=end_date,
    )

    dayrows:list[db.DBRow] = _fetch_day_data(ttdb, day_where_clause)
    blockrows:list[db.DBRow] = _fetch_block_rows(ttdb, day_where_clause)

    range_label = f"{start_date} to {end_date}" if start_date or end_date else ""

    if not dayrows:
        heading = f"{title_bit}Time block summaries"
        if range_label:
            heading = f"{heading} ({range_label})"
        print(f"<h1>{heading}</h1>")
        print(f"{cc.main_and_back_buttons(pages_back)}<br><br>")
        print(date_filter_html)
        print("<br><br>")
        print("<p>No data found for the selected date range.</p>")
        return

    if not blockrows:
        heading = f"{title_bit}Time block summaries"
        if range_label:
            heading = f"{heading} ({range_label})"
        print(f"<h1>{heading}</h1>")
        print(f"{cc.main_and_back_buttons(pages_back)}<br><br>")
        print(date_filter_html)
        print("<br><br>")
        print("<p>Block activity data not available for the selected date range.</p>")
        return

    # Create structures for the html tables
    tabledata, day_maxes = process_day_data(dayrows)
    tabledata, block_maxes = process_blocks_data(tabledata, blockrows)

    # Set up color maps
    (
        colors,
        block_parked_colors,
        day_total_bikes_colors,
        day_full_colors,
    ) = create_color_maps(day_maxes, block_maxes)

    # Print the report
    print_the_html(
        tabledata,
        colors,
        block_parked_colors,
        day_total_bikes_colors,
        day_full_colors,
        pages_back,
        page_title_prefix=title_bit,
        date_filter_html=date_filter_html,
        date_range_label=range_label,
    )


def create_color_maps(day_maxes: _OneDay, block_maxes: _OneBlock) -> tuple:
    """Create color maps for the table.

    Returns
        colors,
        block_parked_colors,
        day_total_bikes_colors,
        day_full_colors,"""
    # Set up color maps
    colors = dc.MultiDimension(blend_method=dc.BLEND_MULTIPLICATIVE)
    d1 = colors.add_dimension(interpolation_exponent=0.82, label="Bikes parked")
    d1.add_config(0, XY_BOTTOM_COLOR)
    d1.add_config(block_maxes.num_in, X_TOP_COLOR)
    d2 = colors.add_dimension(interpolation_exponent=0.82, label="Bikes returned")
    d2.add_config(0, XY_BOTTOM_COLOR)
    d2.add_config(block_maxes.num_out, Y_TOP_COLOR)

    block_parked_colors = dc.Dimension(
        interpolation_exponent=0.85, label="Bikes onsite"
    )
    block_colors = [
        colors.get_color(0, 0),
        "thistle",
        "plum",
        "violet",
        "mediumpurple",
        "blueviolet",
        "darkviolet",
        "darkorchid",
        "indigo",
        "black",
    ]
    for n, c in enumerate(block_colors):
        block_parked_colors.add_config(n / (len(block_colors)) * (block_maxes.full), c)

    # These are for the right-most two columns
    day_total_bikes_colors = dc.Dimension(
        interpolation_exponent=1.5, label="Bikes parked this day"
    )
    day_total_bikes_colors.add_config(0, "white")
    day_total_bikes_colors.add_config(day_maxes.day_total_bikes, "green")
    day_full_colors = dc.Dimension(
        interpolation_exponent=1.5, label="Most bikes this day"
    )
    day_full_colors.add_config(0, "white")
    day_full_colors.add_config(day_maxes.day_max_bikes, "teal")

    return colors, block_parked_colors, day_total_bikes_colors, day_full_colors
