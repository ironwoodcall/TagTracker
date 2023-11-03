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
import cgi_common as cc
import datacolors as dc
import colortable

XY_BOTTOM_COLOR = dc.Color((252, 252, 248)).html_color
X_TOP_COLOR = "red"
Y_TOP_COLOR = "royalblue"
NORMAL_MARKER = chr(0x25A0)  # chr(0x25AE)  # chr(0x25a0)#chr(0x25cf)
HIGHLIGHT_MARKER = chr(0x25AE)  # chr(0x25a0)#chr(0x25cf)


def process_iso_dow(iso_dow):
    # Convert iso_dow to an integer and set title_bit and where_clause
    if iso_dow:
        iso_dow = int(iso_dow)
    if not iso_dow:
        title_bit = ""
        where_clause = ""
    else:
        # sqlite uses unix dow, so need to adjust dow from 1->7 to 0->6.
        title_bit = f"{ut.dow_str(iso_dow)} "
        where_clause = f" where strftime('%w',date) = '{iso_dow % 7}' "

    return title_bit, where_clause


def fetch_data(ttdb, where_clause, table_name, time_column=None):
    if time_column:
        query = f"SELECT date, round(2*(julianday({time_column})-julianday('00:15'))*24,0)/2 block, count({time_column}) bikes FROM {table_name} {where_clause} GROUP BY date, block;"
    else:
        query = f"SELECT date, parked_total day_total_bikes, max_total day_max_bikes FROM {table_name} {where_clause} ORDER BY date DESC"

    # Fetch and return data from the database
    # ...
    data = None
    return data


def process_day_data(dayrows):
    tabledata = {}
    max_max_bikes = 0
    max_total_bikes = 0
    # Process day data and populate tabledata
    # ...
    return tabledata, max_max_bikes, max_total_bikes


def process_visit_data(visitrows_in, visitrows_out, tabledata):
    max_block_full = 0
    max_block_activity = 0
    # Process visit data and update tabledata
    # ...
    return max_block_full, max_block_activity


def print_html_report(
    title_bit,
    tabledata,
    max_max_bikes,
    max_total_bikes,
    max_block_full,
    max_block_activity,
):
    pass
    # Generate HTML report
    # ...


def NEW__blocks_report(ttdb: sqlite3.Connection, iso_dow: str | int = ""):
    title_bit, where = process_iso_dow(iso_dow)

    dayrows = fetch_data(ttdb, where, "day")
    visitrows_in = fetch_data(ttdb, where, "visit", "time_in")
    visitrows_out = fetch_data(ttdb, where, "visit", "time_out")

    tabledata, max_max_bikes, max_total_bikes = process_day_data(dayrows)
    max_block_full, max_block_activity = process_visit_data(
        visitrows_in, visitrows_out, tabledata
    )

    print_html_report(
        title_bit,
        tabledata,
        max_max_bikes,
        max_total_bikes,
        max_block_full,
        max_block_activity,
    )


def fetch_days():
    pass


def blocks_report(ttdb: sqlite3.Connection, iso_dow: str | int = ""):
    """Print block-by-block colors report for all days

    If dow is None then do for all days of the week, otherwise do
    for ISO int dow (1=Monday-->7=Sunday)

    """

    class OneBlock:
        """Data about a single timeblock."""

        def __init__(self):
            self.num_in = 0
            self.num_out = 0
            self.full = 0
            self.so_far = 0

        @property
        def activity(self):
            return self.num_in + self.num_out

    class OneDay:
        _allblocks = {}
        for t in range(6 * 60, 24 * 60, 30):
            _allblocks[VTime(t)] = OneBlock()

        def __init__(self) -> None:
            self.day_total_bikes = None
            self.day_max_bikes = None
            self.blocks = copy.deepcopy(OneDay._allblocks)

    if iso_dow:
        iso_dow = int(iso_dow)
    if not iso_dow:
        title_bit = ""
        where = ""
    else:
        # sqlite uses unix dow, so need to adjust dow from 1->7 to 0->6.
        title_bit = f"{ut.dow_str(iso_dow)} "
        where = f" where strftime('%w',date) = '{iso_dow % 7}' "
    sel = (
        "select "
        "   date, parked_total day_total_bikes, max_total day_max_bikes "
        "from day "
        f"  {where} "
        "   order by date desc"
    )
    dayrows = db.db_fetch(ttdb, sel)

    sel = (
        "select "
        "    date,"
        "    round(2*(julianday(time_in)-julianday('00:15'))*24,0)/2 block, "
        "    count(time_in) bikes_in "
        "from visit "
        f"    {where} "
        "group by date,block;"
    )
    visitrows_in = db.db_fetch(ttdb, sel)
    sel = (
        "select "
        "    date,"
        "    round(2*(julianday(time_out)-julianday('00:15'))*24,0)/2 block, "
        "    count(time_out) bikes_out "
        "from visit "
        f"    {where} "
        "group by date,block;"
    )
    visitrows_out = db.db_fetch(ttdb, sel)

    # Create structures for the html tables:
    #   tabledata[ date : day summary (a OneDay) ]
    #   max_total_bikes, max_max_bikes: greatest daily total and fullest

    tabledata = {}
    max_max_bikes = 0
    max_total_bikes = 0
    for dayrow in dayrows:
        date = dayrow.date
        day_summary = OneDay()
        day_summary.day_total_bikes = dayrow.day_total_bikes
        if day_summary.day_total_bikes > max_total_bikes:
            max_total_bikes = day_summary.day_total_bikes
        day_summary.day_max_bikes = dayrow.day_max_bikes
        if day_summary.day_max_bikes > max_max_bikes:
            max_max_bikes = day_summary.day_max_bikes
        tabledata[date] = day_summary

    # Consolidate activity info from the VISIT table
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

    block_maxes = OneBlock()
    for date in sorted(ins.keys()):
        full_today = 0
        so_far_today = 0
        for block_key in sorted(tabledata[date].blocks.keys()):
            thisblock: OneBlock = tabledata[date].blocks[block_key]
            thisblock.num_in = (
                ins[date][block_key] if block_key in ins[date] else 0
            )
            thisblock.num_out = (
                outs[date][block_key]
                if date in outs and block_key in outs[date]
                else 0
            )
            so_far_today += thisblock.num_in
            thisblock.so_far = so_far_today
            full_today += thisblock.num_in - thisblock.num_out
            thisblock.full = full_today

            # FIXME: below may overestimate max activity level
            block_maxes.num_in = max(thisblock.num_in, block_maxes.num_in)
            block_maxes.num_out = max(thisblock.num_out, block_maxes.num_out)
            block_maxes.full = max(thisblock.full, block_maxes.full)
            block_maxes.so_far = max(thisblock.so_far, block_maxes.so_far)
            block_maxes.full = max(thisblock.full, block_maxes.full)

    # Set up color map

    colors = dc.MultiDimension(blend_method=dc.BLEND_MULTIPLICATIVE)
    d1 = colors.add_dimension(interpolation_exponent=0.82, label="Bikes parked")
    d1.add_config(0, XY_BOTTOM_COLOR)
    d1.add_config(block_maxes.num_in, X_TOP_COLOR)
    d2 = colors.add_dimension(interpolation_exponent=0.82, label="Bikes returned")
    d2.add_config(0, XY_BOTTOM_COLOR)
    d2.add_config(block_maxes.num_out, Y_TOP_COLOR)

    block_parked_colors = dc.Dimension(
        interpolation_exponent=0.67, label="Bikes at valet"
    )
    block_parked_colors.add_config(
        0, colors.get_color(0, 0)
    )  # exactly match the off-hours background
    block_parked_colors.add_config(0.2 * block_maxes.full, "lightyellow")
    block_parked_colors.add_config(0.4 * block_maxes.full, "orange")
    block_parked_colors.add_config(0.6 * block_maxes.full, "red")
    block_parked_colors.add_config(block_maxes.full, "black")

    # These are for the right-most two columns
    day_total_bikes_colors = dc.Dimension(
        interpolation_exponent=1.5, label="Bikes parked this day"
    )
    day_total_bikes_colors.add_config(0, "white")
    day_total_bikes_colors.add_config(max_total_bikes, "green")
    day_full_colors = dc.Dimension(
        interpolation_exponent=1.5, label="Most bikes this day"
    )
    day_full_colors.add_config(0, "white")
    day_full_colors.add_config(max_max_bikes, "teal")

    print(f"<h1>{title_bit}Daily activity detail</h1>")

    tab = colortable.html_2d_color_table(
        colors,
        "<b>Legend for In & Out Activity</b>",
        "",
        "",
        8,
        8,
        20,
    )
    print(tab)

    print("</p></p>")
    tab = colortable.html_1d_text_color_table(
        block_parked_colors,
        title="<b>Legend for Number of bikes at valet</b>",
        subtitle=f"{HIGHLIGHT_MARKER} = Valet fullest at this time",
        marker=NORMAL_MARKER,
        bg_color="grey",  # bg_color=colors.get_color(0,0).html_color
    )
    print(tab)
    print("</p></p>")

    def print_gap():
        print(
            "<td style='border: 2px solid rgb(200,200,200);padding: 0px 0px;'></td>"
        )

    print("<table>")
    print("<style>td {text-align: right;}</style>")
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
        data: OneDay = tabledata[date]
        summary_report_link = cc.selfref(what="day_end", qdate=date)
        chart_report_link = cc.selfref(what="chart", qdate=date)

        dayname = ut.date_str(date, dow_str_len=3)
        dow_report_link = cc.selfref(
            what="dow_blocks", qdow=ut.dow_int(dayname)
        )

        print(
            f"<tr><td style='text-align:center;'>"
            f"<a href='{summary_report_link}'>{date}</a></td>"
        )
        print(
            f"<td style='text-align:center'>"
            f"<a href='{dow_report_link}'>{dayname}</a></td>"
        )

        # Find which block was fullest
        # pylint:disable-next=cell-var-from-loop
        fullest_block_this_day = max(
            data.blocks, key=lambda key: data.blocks[key].full
        )

        for num, block_key in enumerate(sorted(data.blocks.keys())):
            if num % 6 == 0:
                print_gap()
            thisblock: OneBlock = data.blocks[block_key]
            # For times in the future, don't show results
            if date == date_today and block_key > time_now:
                cell_color = f"color:{XY_BOTTOM_COLOR};background-color:{XY_BOTTOM_COLOR};"
                cell_title = "Future unknown"
            else:
                cell_color = (
                    f"{colors.css_bg((thisblock.num_in, thisblock.num_out))};"
                    f"{block_parked_colors.css_fg(thisblock.full)};"
                )
                cell_title = (
                    f"Bikes in: {thisblock.num_in}\nBikes out: {thisblock.num_out}\n"
                    f"Bikes so far: {thisblock.so_far}\nBikes at end: {thisblock.full} "
                )

            marker = marker = (
                HIGHLIGHT_MARKER
                if block_key == fullest_block_this_day
                else NORMAL_MARKER
            )
            print(
                f"<td title='{cell_title}' style='{cell_color};padding: 2px 6px;'>"
                f"<a href='{chart_report_link}' style='{cell_color};text-decoration:none;'>"
                f"{marker}</a></td>"
            )
        print_gap()

        s = day_total_bikes_colors.css_bg_fg(data.day_total_bikes)
        print(
            f"<td style='{s}'><a href='{chart_report_link}' style='{s}'>"
            f"{data.day_total_bikes}</a></td>"
        )
        s = day_full_colors.css_bg_fg(data.day_max_bikes)
        print(
            f"<td style='{s}'><a href='{chart_report_link}' style='{s}'>"
            f"{data.day_max_bikes}</a></td>"
        )
        print("</tr>\n")

    print("</table>")
