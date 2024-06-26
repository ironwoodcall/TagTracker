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

XY_BOTTOM_COLOR = dc.Color((252, 252, 248)).html_color
X_TOP_COLOR = "red"
Y_TOP_COLOR = "royalblue"
NORMAL_MARKER = chr(0x25A0)  # chr(0x25AE)  # chr(0x25a0)#chr(0x25cf)
HIGHLIGHT_MARKER = chr(0x2B24)  # chr(0x25cf) #chr(0x25AE)  # chr(0x25a0)#chr(0x25cf)


# FIXME: This block report could read blocks data from db instead of recalculating it

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


def _process_iso_dow(iso_dow, orgsite_id: int) -> tuple[str, str]:
    # Use dow to make report title prefix, and day filter for SQL queries.
    if iso_dow:
        iso_dow = int(iso_dow)
    if not iso_dow:
        title_bit = ""
        day_where_clause = f"where orgsite_id = {orgsite_id}"
    else:
        # sqlite uses unix dow, so need to adjust dow from 1->7 to 0->6.
        title_bit = f"{ut.dow_str(iso_dow)} "
        day_where_clause = (
            f" where orgsite_id = {orgsite_id} "
            f"and strftime('%w',date) = '{iso_dow % 7}' "
        )

    return title_bit, day_where_clause


def _fetch_visit_data(ttdb: sqlite3.Connection, day_filter: str, in_or_out: str) -> list[db.DBRow]:
    sel = (
        "select "
        "    day.date,"
        f"    round(2*(julianday(visit.time_{in_or_out})-julianday('00:15'))*24,0)/2 block, "
        f"    count(visit.time_{in_or_out}) num_bikes "
        "from day "
        "JOIN visit ON visit.day_id = day.id"
        f"    {day_filter} "
        "group by date,block;"
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
    tabledata: dict, visitrows_in: list, visitrows_out: list
) -> tuple[dict[VTime:_OneBlock], _OneBlock]:
    """Process data about timeblocks from visits table data.

    Changes the contents of tabledata and returns blocks_max."""

    def process_visitrows(visitrows):
        result_dict = defaultdict(dict)
        for visitrow in visitrows:
            this_date = visitrow.date
            if not this_date or not visitrow.block or visitrow.num_bikes is None:
                continue
            block_time = VTime(visitrow.block * 60)
            result_dict[this_date][block_time] = visitrow.num_bikes
        return result_dict

    ins = process_visitrows(visitrows_in)
    outs = process_visitrows(visitrows_out)

    for date in sorted(ins.keys()):
        full_today = 0
        so_far_today = 0
        date_outs = outs.get(date, {})
        for block_key in sorted(tabledata[date].blocks.keys()):
            thisblock: _OneBlock = tabledata[date].blocks[block_key]
            thisblock.num_in = ins[date].get(block_key, 0)
            thisblock.num_out = date_outs.get(block_key, 0)
            so_far_today += thisblock.num_in
            thisblock.so_far = so_far_today
            full_today += thisblock.num_in - thisblock.num_out
            thisblock.full = full_today

    # Find overall maximum values
    block_maxes = _OneBlock()
    all_blocks = [b for t in tabledata.values() for b in t.blocks.values()]

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
):
    def column_gap() -> str:
        """Make a thicker vertical cell border to mark off sets of blocks."""
        return "<td style='width:auto;border: 2px solid rgb(200,200,200);padding: 0px 0px;'></td>"

    print(f"<h1>{page_title_prefix}Daily activity detail</h1>")
    print(f"{cc.main_and_back_buttons(pages_back)}<br><br>")

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
):
    """Print block-by-block colors report for all days

    If dow is None then do for all days of the week, otherwise do
    for ISO int dow (1=Monday-->7=Sunday)

    """

    orgsite_id = 1  # orgsite_id hardcoded

    cc.test_dow_parameter(iso_dow, list_ok=False)
    title_bit, day_where_clause = _process_iso_dow(iso_dow,orgsite_id=orgsite_id)

    dayrows:list[db.DBRow] = _fetch_day_data(ttdb, day_where_clause)
    visitrows_in:list[db.DBRow] = _fetch_visit_data(ttdb, day_where_clause, "in")
    visitrows_out:list[db.DBRow] = _fetch_visit_data(ttdb, day_where_clause, "out")

    # Create structures for the html tables
    tabledata, day_maxes = process_day_data(dayrows)
    tabledata, block_maxes = process_blocks_data(tabledata, visitrows_in, visitrows_out)

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
