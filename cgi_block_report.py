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

##from tt_globals import *

import tt_dbutil as db
from tt_time import VTime
import tt_util as ut
import cgi_common as cc
import datacolors as dc
import colortable

ZERO_COLOUR_INIT = (252,252,248)
BUSY_COLOUR_INIT = 'red'
FULL_COLOUR_INIT = 'teal'
BUSY_COLOUR_TOP = 60    # None to use calculated max
FULL_COLOUR_TOP = 150   # None to use calculated max


def process_iso_dow(iso_dow):
    # Convert iso_dow to an integer and set title_bit and where
    # ...
    title_bit, where = (None,None)
    return title_bit, where

def fetch_data(ttdb, where, table_name, time_column=None):
    if time_column:
        query = f"SELECT date, round(2*(julianday({time_column})-julianday('00:15'))*24,0)/2 block, count({time_column}) bikes FROM {table_name} {where} GROUP BY date, block;"
    else:
        query = f"SELECT date, parked_total total_bikes, max_total max_full FROM {table_name} {where} ORDER BY date DESC"

    # Fetch and return data from the database
    # ...
    data = None
    return data

def process_day_data(dayrows):
    tabledata = {}
    day_fullest = 0
    day_busiest = 0
    # Process day data and populate tabledata
    # ...
    return tabledata, day_fullest, day_busiest

def process_visit_data(visitrows_in, visitrows_out, tabledata):
    block_fullest = 0
    block_busiest = 0
    # Process visit data and update tabledata
    # ...
    return block_fullest, block_busiest

def print_html_report(title_bit, tabledata, day_fullest, day_busiest, block_fullest, block_busiest):
    pass
    # Generate HTML report
    # ...


def NEW__blocks_report(ttdb: sqlite3.Connection, iso_dow: str | int = ""):
    title_bit, where = process_iso_dow(iso_dow)

    dayrows = fetch_data(ttdb, where, "day")
    visitrows_in = fetch_data(ttdb, where, "visit", "time_in")
    visitrows_out = fetch_data(ttdb, where, "visit", "time_out")

    tabledata, day_fullest, day_busiest = process_day_data(dayrows)
    block_fullest, block_busiest = process_visit_data(visitrows_in, visitrows_out, tabledata)

    print_html_report(title_bit, tabledata, day_fullest, day_busiest, block_fullest, block_busiest)



def blocks_report(ttdb: sqlite3.Connection, iso_dow: str | int = ""):
    """Print block-by-block colours report for all days

    If dow is None then do for all days of the week, otherwise do
    for ISO int dow (1=Monday-->7=Sunday)

    """

    class TableRow:
        _allblocks = {}
        for t in range(6 * 60, 24 * 60, 30):
            _allblocks[VTime(t)] = (0, 0)  # Activity,Fullness

        def __init__(self) -> None:
            self.total_bikes = None
            self.max_full = None
            self.blocks = TableRow._allblocks.copy()

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
        "   date, parked_total total_bikes, max_total max_full "
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

    tabledata = {}
    day_fullest = 0
    day_busiest = 0
    for row in dayrows:
        date = row.date
        daydata = TableRow()
        daydata.total_bikes = row.total_bikes
        if daydata.total_bikes > day_busiest:
            day_busiest = daydata.total_bikes
        daydata.max_full = row.max_full
        if daydata.max_full > day_fullest:
            day_fullest = daydata.max_full
        tabledata[date] = daydata

    # Consolidate activity info from the VISIT table
    ins = {}
    for row in visitrows_in:
        thisdate = row.date
        if not thisdate or not row.block or row.bikes_in is None:
            continue
        blocktime = VTime(row.block * 60)
        if thisdate not in ins:
            ins[thisdate] = {}
        ins[thisdate][blocktime] = row.bikes_in
    outs = {}
    for row in visitrows_out:
        thisdate = row.date
        if not thisdate or not row.block or row.bikes_out is None:
            continue
        blocktime = VTime(row.block * 60)
        if thisdate not in outs:
            outs[thisdate] = {}
        outs[thisdate][blocktime] = row.bikes_out

    block_fullest = 0
    block_busiest = 0
    for date in sorted(ins.keys()):
        full = 0
        for block in sorted(tabledata[date].blocks.keys()):
            num_in = ins[date][block] if block in ins[date] else 0
            num_out = (
                outs[date][block]
                if date in outs and block in outs[date]
                else 0
            )
            busy = num_in + num_out
            full += num_in - num_out
            if full > block_fullest:
                block_fullest = full
            if busy > block_busiest:
                block_busiest = busy
            tabledata[date].blocks[block] = (num_in, num_out, busy, full)

    # Set up colour map
    colours = dc.MultiDimension(blend_method=dc.BLEND_MULTIPLICATIVE)
    d1 = colours.add_dimension(interpolation_exponent=0.82)
    d1.add_config(0,ZERO_COLOUR_INIT)
    if BUSY_COLOUR_TOP is None:
        d1.add_config(block_busiest,BUSY_COLOUR_INIT)
    else:
        d1.add_config(BUSY_COLOUR_TOP,BUSY_COLOUR_INIT)
    d2 = colours.add_dimension(interpolation_exponent=0.82)
    d2.add_config(0,ZERO_COLOUR_INIT)
    if FULL_COLOUR_TOP is None:
        d2.add_config(block_fullest,FULL_COLOUR_INIT)
    else:
        d2.add_config(FULL_COLOUR_TOP,FULL_COLOUR_INIT)

    day_busy_colours = dc.Dimension(interpolation_exponent=1.5)
    day_busy_colours.add_config(0,'white')
    day_busy_colours.add_config(day_busiest,'green')
    day_full_colours = dc.Dimension(interpolation_exponent=1.5)
    day_full_colours.add_config(0,'white')
    day_full_colours.add_config(day_fullest,FULL_COLOUR_INIT)

    print(f"<h1>{title_bit}Daily activity detail</h1>")

    tab = colortable.make_html_color_table(colours,'<b>Legend</b>','Bikes In+Out', 'Bikes at valet',8,8,20)
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

    for date in sorted(tabledata.keys(), reverse=True):
        data: TableRow = tabledata[date]
        summary_link = cc.selfref(what="day_end", qdate=date)
        chartlink = cc.selfref(what="chart", qdate=date)

        dayname = ut.date_str(date, dow_str_len=3)
        daylink = cc.selfref(what="dow_blocks", qdow=ut.dow_int(dayname))

        print(
            f"<tr><td style='text-align:center;'><a href='{summary_link}'>{date}</a></td>"
        )
        print(
            f"<td style='text-align:center'><a href='{daylink}'>{dayname}</a></td>"
        )

        for num, block in enumerate(sorted(data.blocks.keys())):
            if num % 6 == 0:
                print_gap()
            (num_in, num_out, busy, full) = data.blocks[block]
            cell_colour = colours.css_bg_fg((busy, full))
            print(
                f"<td title='Bikes in: {num_in}\nBikes out: {num_out}\nBikes at end: {full}' "
                f"style='{cell_colour};padding: 2px 8px;'>"
                f"<a href='{chartlink}' style='{cell_colour};text-decoration:none;'>"
                "</a></td>"
            )
        print_gap()

        s = day_busy_colours.css_bg_fg(data.total_bikes)
        print(
            f"<td style='{s}'><a href='{chartlink}' style='{s}'>{data.total_bikes}</a></td>"
        )
        s = day_full_colours.css_bg_fg(data.max_full)
        print(
            f"<td style='{s}'><a href='{chartlink}' style='{s}'>{data.max_full}</a></td>"
        )
        print("</tr>\n")

    print("</table>")

