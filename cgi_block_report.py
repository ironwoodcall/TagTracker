#!/usr/bin/env python3
"""CGI script for TagTracker time-block report(s).

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

"""

import sqlite3
import copy

##from tt_globals import *

import tt_dbutil as db
from tt_time import VTime
import tt_util as ut
import tt_block
import cgi_common as cc
import datacolors as dc
import colortable

XY_BOTTOM_COLOR = dc.Color((252, 252, 248)).html_color
X_TOP_COLOR = "red"
Y_TOP_COLOR = "royalblue"
NORMAL_MARKER = chr(0x25A0)  # chr(0x25AE)  # chr(0x25a0)#chr(0x25cf)
HIGHLIGHT_MARKER = chr(0x2B24)  # chr(0x25cf) #chr(0x25AE)  # chr(0x25a0)#chr(0x25cf)


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


def process_iso_dow(iso_dow) -> tuple[str, str]:
    # Use dow to make report title prefix, and day filter for SQL queries.
    if iso_dow:
        iso_dow = int(iso_dow)
    if not iso_dow:
        title_bit = ""
        day_where_clause = ""
    else:
        # sqlite uses unix dow, so need to adjust dow from 1->7 to 0->6.
        title_bit = f"{ut.dow_str(iso_dow)} "
        day_where_clause = f" where strftime('%w',date) = '{iso_dow % 7}' "

    return title_bit, day_where_clause


def fetch_visit_data(ttdb: sqlite3.Connection, day_filter: str, in_or_out: str):
    sel = (
        "select "
        "    date,"
        f"    round(2*(julianday(time_{in_or_out})-julianday('00:15'))*24,0)/2 block, "
        f"    count(time_{in_or_out}) bikes_{in_or_out} "
        "from visit "
        f"    {day_filter} "
        "group by date,block;"
    )
    return db.db_fetch(ttdb, sel)


def fetch_day_data(ttdb: sqlite3.Connection, day_filter: str):
    sel = (
        "select "
        "   date, parked_total day_total_bikes, "
        "      max_total day_max_bikes, time_max_total day_max_bikes_time "
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
    ins = {}
    for visitrow in visitrows_in:
        thisdate = visitrow.date
        if not thisdate or not visitrow.block or visitrow.bikes_in is None:
            continue
        blocktime = VTime(visitrow.block * 60)
        if thisdate not in ins:
            ins[thisdate] = {}
        ins[thisdate][blocktime] = visitrow.bikes_in

    outs = {}
    for visitrow in visitrows_out:
        thisdate = visitrow.date
        if not thisdate or not visitrow.block or visitrow.bikes_out is None:
            continue
        blocktime = VTime(visitrow.block * 60)
        if thisdate not in outs:
            outs[thisdate] = {}
        outs[thisdate][blocktime] = visitrow.bikes_out

    for date in sorted(ins.keys()):
        full_today = 0
        so_far_today = 0
        for block_key in sorted(tabledata[date].blocks.keys()):
            thisblock: _OneBlock = tabledata[date].blocks[block_key]
            thisblock.num_in = ins[date][block_key] if block_key in ins[date] else 0
            thisblock.num_out = (
                outs[date][block_key] if date in outs and block_key in outs[date] else 0
            )
            so_far_today += thisblock.num_in
            thisblock.so_far = so_far_today
            full_today += thisblock.num_in - thisblock.num_out
            thisblock.full = full_today

    # Find overall maximum values
    block_maxes = _OneBlock()
    block_maxes.num_in = max(
        [
            b.num_in
            for t_instance in tabledata.values()
            for b in t_instance.blocks.values()
        ]
    )
    block_maxes.num_out = max(
        [
            b.num_out
            for t_instance in tabledata.values()
            for b in t_instance.blocks.values()
        ]
    )
    block_maxes.full = max(
        [
            b.full
            for t_instance in tabledata.values()
            for b in t_instance.blocks.values()
        ]
    )
    block_maxes.so_far = max(
        [
            b.so_far
            for t_instance in tabledata.values()
            for b in t_instance.blocks.values()
        ]
    )

    return tabledata, block_maxes


def print_the_html(
    tabledata: dict,
    xy_colors: dc.MultiDimension,
    marker_colors: dc.Dimension,
    day_total_bikes_colors: dc.Dimension,
    day_full_colors: dc.Dimension,
    page_title_prefix: str = "",
):
    def print_gap():
        """Print a thicker vertical cell border to mark off sets of blocks."""
        print("<td style='width:auto;border: 2px solid rgb(200,200,200);padding: 0px 0px;'></td>")

    print(f"<h1>{page_title_prefix}Daily activity detail</h1>")

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
        title="<b>Legend for number of bikes at valet at once</b>",
        subtitle=f"{HIGHLIGHT_MARKER} = Time that the valet was fullest",
        marker=NORMAL_MARKER,
        bg_color="grey",  # bg_color=xy_colors.get_color(0,0).html_color
        num_columns=20,
    )
    print(tab)
    print("</p></p>")

    # Main table. Column headings
    print("<table>")
    print("<style>td {text-align: right;text-align: center; width: 13px;padding: 4px 4px;}</style>")
    print("<tr>")
    print(f"<th colspan=3><a href='{cc.selfref(what='blocks')}'>Date</a></th>")
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
        summary_report_link = cc.selfref(what="day_end", qdate=date)
        chart_report_link = cc.selfref(what="chart", qdate=date)
        dow_report_link = cc.selfref(what="dow_blocks", qdow=ut.dow_int(dayname))
        print("<tr style='text-align: center; width: 15px;padding: 0px 3px;'>")
        print(f"<td style=width:auto;><a href='{summary_report_link}'>{date}</a></td>")
        print(f"<td style=width:auto;><a href='{dow_report_link}'>{dayname}</a></td>")

        # Find which time block had the greatest num of bikes this day.
        fullest_block_this_day = tt_block.block_start(thisday.day_max_bikes_time)

        # Print the blocks for this day.
        for num, block_key in enumerate(sorted(thisday.blocks.keys())):
            if num % 6 == 0:
                print_gap()
            thisblock: _OneBlock = thisday.blocks[block_key]
            if thisblock.num_in == 0 and thisblock.num_out == 0:
                # No activity this block
                cell_color = f"{zero_bg};" f"{marker_colors.css_fg(thisblock.full)};"
                cell_title = (
                    f"Bikes in: 0\nBikes out: 0\n"
                    f"Bikes so far: {thisblock.so_far}\nBikes at end: {thisblock.full} "
                )
            elif date == date_today and block_key >= time_now:
                # Today, later than now
                cell_color = (
                    f"color:{XY_BOTTOM_COLOR};background-color:{XY_BOTTOM_COLOR};"
                )
                cell_title = "Future unknown"
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

            print(
                f"<td title='{cell_title}' style='{cell_color};"
                # "text-align: center; width: 15px;padding: 0px 3px;"
                "'>"
                f"{marker}</td>"  ##</a></td>"
            )
        print_gap()

        s = day_total_bikes_colors.css_bg_fg(thisday.day_total_bikes)
        print(
            f"<td style='{s};width:auto;'><a href='{chart_report_link}' style='{s}'>"
            f"{thisday.day_total_bikes}</a></td>"
        )
        s = day_full_colors.css_bg_fg(thisday.day_max_bikes)
        print(
            f"<td style='{s};width:auto;'><a href='{chart_report_link}' style='{s}'>"
            f"{thisday.day_max_bikes}</a></td>"
        )
        print("</tr>\n")

    print("</table>")


def blocks_report(ttdb: sqlite3.Connection, iso_dow: str | int = ""):
    """Print block-by-block colors report for all days

    If dow is None then do for all days of the week, otherwise do
    for ISO int dow (1=Monday-->7=Sunday)

    """
    title_bit, where = process_iso_dow(iso_dow)

    dayrows = fetch_day_data(ttdb, where)
    visitrows_in = fetch_visit_data(ttdb, where, "in")
    visitrows_out = fetch_visit_data(ttdb, where, "out")

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
        title_bit,
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
        interpolation_exponent=0.85, label="Bikes at valet"
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
