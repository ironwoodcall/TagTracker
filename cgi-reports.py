#!/usr/bin/env python3
"""CGI script for TagTracker reports against consolidated database.

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
import sys
import os
import urllib.parse
import datetime
import pathlib

from tt_globals import *

import tt_dbutil as db
import tt_conf as cfg
import tt_reports as rep
import tt_datafile as df
from tt_tag import TagID
from tt_time import VTime
import tt_util as ut
import cgi_common as cc
import datacolors as dc
import colortable
import cgi_block_report

def form(
    title: str = "TagTracker",
    default_what: str = "overview",
    default_date: str = "",
    default_tag: str = "",
    default_dow: str = "Sunday",
):
    if not default_date:
        default_date = ut.date_str("today")

    what_choices = {
        "overview": "Overview",
        "dow_overview": "Overview for one day of the week [specify Day of Week]",
        "blocks": "Colour-coded daily activity overview",
        "dow_blocks": "Colour-coded daily activity overview for one day of the week",
        "abandoned": "Lost tags report",
        "day_end": "Day-end report for a given date",
        "audit": "Audit report for a given date",
        "last_use": "History of use for a given tag",
        "one_day_tags": "Tags in/out activity for a given date",
        "datafile": "Recreated datafile for a given date",
        "chart": "Activity charts for a given date [specify Date]",
    }
    dow_choices = {  # These are ISO days of week not unix.
        "7": "Sunday",
        "1": "Monday",
        "2": "Tuesday",
        "3": "Wednesday",
        "4": "Thursday",
        "5": "Friday",
        "6": "Saturday",
    }

    me_action = pathlib.Path(
        ut.untaint(os.environ.get("SCRIPT_NAME", ""))
    ).name
    if not me_action:
        cc.error_out("bad")

    print(f"<html><head><title>{title}</title><meta charset='UTF-8'></head>")
    print(cc.style())
    print("<body>")
    print("<h2>TagTracker reports</h2>")
    print(
        f"""
    <form accept-charset="UTF-8" action="{me_action}" autocomplete="off" method="GET">


    <label for="name">Report to create:</label>
    <select name="what" id="what">
"""
    )
    for choice, descr in what_choices.items():
        if choice == default_what:
            print(
                f'<option value="{choice}" selected="selected">{descr}</option>'
            )
        else:
            print(f'<option value="{choice}">{descr}</option>')
    print(
        f"""

    </select>
    <br /><br />
    Date: <input name="date" type="text" value="{default_date}" />
    <br />
    Tag: <input name="tag" type="text" value="{default_tag}" />
    <br />
    Day of week:
        <select name="dow" id="dow">"""
    )
    for choice, descr in dow_choices.items():
        if choice == default_dow:
            print(
                f'<option value="{choice}" selected="selected">{descr}</option>'
            )
        else:
            print(f'<option value="{choice}">{descr}</option>')
    print(
        """
        </select>

    <br /><br />
    <button type="submit" value="Submit">Create report</button>

    </form>
    <hr>
"""
    )



def one_tag_history_report(
    ttdb: sqlite3.Connection, maybe_tag: MaybeTag
) -> None:
    """Report a tag's history."""

    tag = TagID(maybe_tag)
    if not tag:
        print(f"Not a tag: '{ut.untaint(tag.original)}'")
        sys.exit()
    # Fetch all info about this tag.
    (last_date, last_in, last_out) = ("", "", "")
    curs = ttdb.cursor()
    rows = curs.execute(
        "select date,time_in,time_out "
        "from visit "
        f"where tag = '{tag.lower()}' "
        "order by date desc;"
    ).fetchall()

    print(f"<h1>History of tag {tag.upper()}</h1>")
    print(
        f"<h3>This tag has been used {len(rows)} {ut.plural(len(rows), 'time')}</h3>"
    )
    print()
    if not rows:
        print(f"No record that {tag.upper()} ever used<br />")
    else:
        print("<table>")
        print("<style>td {text-align: right;}</style>")
        print("<tr><th>Date</th><th>BikeIn</th><th>BikeOut</th></tr>")
        for row in rows:
            out = VTime(row[2]).tidy if row[2] else "     "
            linkdate = row[0]
            link = cc.selfref(what="one_day_tags", qdate=linkdate)
            print(
                f"<tr><td>"
                f"<a href='{link}'>{row[0]}</a>"
                "</td>"
                f"<td>{VTime(row[1]).tidy}</td><td>{out}</td></tr>"
            )
        print("</table>")
    print("</body></html>")


def ytd_totals_table(ttdb: sqlite3.Connection, csv: bool = False):
    """Print a table of YTD totals.

    YTD Total:

    Regular parked  xx
    Oversize parked xx
    Total Parked    xx
    Bike-hours      xx
    Valet hours     xx
    Bike-hrs/hr     xx
    """
    sel = (
        "select "
        "   sum(parked_regular) parked_regular, "
        "   sum(parked_oversize) parked_oversize, "
        "   sum(parked_total) parked_total, "
        "   sum((julianday(time_closed)-julianday(time_open))*24) hours_open, "
        "   sum(registrations) registrations "
        "from day "
    )
    drows = db.db_fetch(ttdb, sel)
    # Find the total bike-hours
    vrows = db.db_fetch(
        ttdb,
        "select "
        "   sum(julianday(duration)-julianday('00:00'))*24 bike_hours "
        "from visit ",
    )
    day: db.DBRow = drows[0]
    day.bike_hours = vrows[0].bike_hours
    # Get total # of days of operation
    day.num_days = db.db_fetch(ttdb, "select count(date) num_days from day")[
        0
    ].num_days

    if csv:
        print("measure,ytd_total")
        html_tr_start = ""
        html_tr_mid = ","
        html_tr_end = "\n"
    else:
        print("<table><tr><th colspan=2>Year to date totals</th></tr>")
        html_tr_start = "<tr><td style='text-align:left'>"
        html_tr_mid = "</td><td style='text-align:right'>"
        html_tr_end = "</td></tr>\n"
    print(
        f"{html_tr_start}Total bikes parked{html_tr_mid}"
        f"  {day.parked_total}{html_tr_end}"
        f"{html_tr_start}Regular bikes parked{html_tr_mid}"
        f"  {day.parked_regular}{html_tr_end}"
        f"{html_tr_start}Oversize bikes parked{html_tr_mid}"
        f"  {day.parked_oversize}{html_tr_end}"
        f"{html_tr_start}529 Registrations{html_tr_mid}"
        f"  {day.registrations}{html_tr_end}"
        f"{html_tr_start}Total days open{html_tr_mid}"
        f"  {day.num_days}{html_tr_end}"
        f"{html_tr_start}Total hours open{html_tr_mid}"
        f"  {day.hours_open:0.1f}{html_tr_end}"
        f"{html_tr_start}Bike-hours total{html_tr_mid}"
        f"  {day.bike_hours:0.0f}{html_tr_end}"
        f"{html_tr_start}Average bikes / day{html_tr_mid}"
        f"  {(day.parked_total/day.num_days):0.1f}{html_tr_end}"
        f"{html_tr_start}Average stay length{html_tr_mid}"
        f"  {VTime((day.bike_hours/day.parked_total)*60).short}{html_tr_end}"
        "</table>"
    )


def overview_report(ttdb: sqlite3.Connection, iso_dow: str | int = ""):
    """Print new version of the all-days default report.

    If dow is None then do for all days of the week, otherwise do
    for ISO int dow (1=Monday-->7=Sunday)

    """
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
        "   date, time_open, time_closed, "
        "   (julianday(time_closed)-julianday(time_open))*24 hours_open, "
        "   parked_regular, parked_oversize, parked_total, "
        "   leftover, "
        "   max_total, "
        "   registrations, "
        "   precip_mm, temp, sunset "
        "from day "
        f"  {where} "
        "   order by date desc"
    )
    drows = db.db_fetch(ttdb, sel)

    # Find the bike-hours for each day
    vrows = db.db_fetch(
        ttdb,
        "select "
        "   sum(julianday(duration)-julianday('00:00'))*24 bike_hours, "
        "   date "
        "from visit "
        f"  {where} "
        "   group by date order by date desc;",
    )
    for rownum, vday in enumerate(vrows):
        if drows[rownum].date != vday.date:
            print(f"oops {rownum=}; {drows[rownum].date=} != {vday.date=}")
            drows[rownum].bike_hours = ""
        else:
            drows[rownum].bike_hours = vday.bike_hours

    max_parked = 0
    max_parked_date = ""
    max_full = 0
    max_full_date = ""
    max_bike_hours = 0
    max_bike_hours_date = ""
    max_bike_hours_per_hour = 0
    max_bike_hours_per_hour_date = ""

    for r in drows:
        r.bike_hours_per_hour = r.bike_hours / r.hours_open
        if r.bike_hours_per_hour > max_bike_hours_per_hour:
            max_bike_hours_per_hour = r.bike_hours_per_hour
            max_bike_hours_per_hour_date = r.date
        if r.parked_total > max_parked:
            max_parked = r.parked_total
            max_parked_date = r.date
        if r.max_total > max_full:
            max_full = r.max_total
            max_full_date = r.date
        if r.bike_hours > max_bike_hours:
            max_bike_hours = r.bike_hours
            max_bike_hours_date = r.date

    max_precip = max(
        [1] + [r.precip_mm for r in drows if r.precip_mm is not None]
    )
    ##max_temp = max([1] + [r.temp for r in drows if r.temp is not None])

    # Set up colour maps for shading cell backgrounds
    max_parked_colour = dc.Dimension(interpolation_exponent=2)
    max_parked_colour.add_config(0,'white')
    max_parked_colour.add_config(max_parked,'green')

    max_full_colour = dc.Dimension(interpolation_exponent=2)
    max_full_colour.add_config(0,'white')
    max_full_colour.add_config(max_full,'teal')

    max_left_colour = dc.Dimension()
    max_left_colour.add_config(0,'white')
    max_left_colour.add_config(10,'red')

    max_bike_hours_colour = dc.Dimension(interpolation_exponent=2)
    max_bike_hours_colour.add_config(0,'white')
    max_bike_hours_colour.add_config(max_bike_hours,'mediumpurple')

    max_bike_hours_per_hour_colour = dc.Dimension(interpolation_exponent=2)
    max_bike_hours_per_hour_colour.add_config(0, 'white')
    max_bike_hours_per_hour_colour.add_config(max_bike_hours_per_hour, 'mediumpurple')

    max_temp_colour = dc.Dimension()
    max_temp_colour.add_config(11,'beige')#'rgb(255, 255, 224)')
    max_temp_colour.add_config(35,'orange')
    max_temp_colour.add_config(0,'azure')

    max_precip_colour = dc.Dimension(interpolation_exponent=1)
    max_precip_colour.add_config(0,'white')
    max_precip_colour.add_config(max_precip,'azure')

    print(f"<h1>{title_bit}Bike valet overview</h1>")
    print(
        f"<p><b>Most bikes parked:</b> "
        f"  {max_parked} bikes on {ut.date_str(max_parked_date,long_date=True)}<br />"
        f"<b>Valet was fullest:</b> "
        f"  with {max_full} bikes on {ut.date_str(max_full_date,long_date=True)}<br />"
        f"<b>Greatest utilization:</b> "
        f"  {round(max_bike_hours)} bike-hours "
        f"      on {ut.date_str(max_bike_hours_date,long_date=True)}<br />"
        f"<b>Greatest utilization per hour:</b> "
        f"  {round(max_bike_hours_per_hour,2)} bike-hours per valet hour "
        f"      on {ut.date_str(max_bike_hours_per_hour_date,long_date=True)}</p>"
    )
    print("<p>&nbsp;</p>")

    if not iso_dow:
        ytd_totals_table(ttdb, csv=False)
        print("<p>&nbsp;</p>")

    print("<table>")
    print("<style>td {text-align: right;}</style>")
    print(
        "<tr>"
        "<th rowspan=2 colspan=2>Date<br />(newest to oldest)</th>"
        "<th colspan=2>Valet Hours</th>"
        "<th colspan=3>Bike Parked</th>"
        "<th rowspan=2>Bikes<br />Left at<br />Valet</th>"
        "<th rowspan=2>Most<br />Bikes<br />at Once</th>"
        "<th rowspan=2>Bike-<br />hours</th>"
        "<th rowspan=2>Bike-<br />hours<br />per hr</th>"
        "<th rowspan=2>529<br />Regs</th>"
        "<th colspan=3>Environment</th>"
        "</tr>"
    )
    print(
        "<tr>"
        # "<th>Date</th>"
        "<th>Open</th><th>Close</th>"
        "<th>Reg</th><th>Ovr</th><th>Total</th>"
        # "<th>Left</th>"
        # "<th>Fullest</th>"
        "<th>Max<br />Temp</th><th>Rain</th><th>Dusk</th>"
        "</tr>"
    )

    for row in drows:
        date_link = cc.selfref(what="day_end", qdate=row.date)
        reg_str = "" if row.registrations is None else f"{row.registrations}"
        temp_str = "" if row.temp is None else f"{row.temp:0.1f}"
        precip_str = "" if row.precip_mm is None else f"{row.precip_mm:0.1f}"
        print(
            f"<tr>"
            f"<td><a href='{date_link}'>{row.date}</a></td>"
            f"<td style='text-align:left'>{ut.date_str(row.date,dow_str_len=3)}</td>"
            f"<td>{row.time_open}</td><td>{row.time_closed}</td>"
            f"<td>{row.parked_regular}</td>"
            f"<td>{row.parked_oversize}</td>"
            #f"<td style='background-color: {max_parked_colour.get_rgb_str(row.parked_total)}'>{row.parked_total}</td>"
            f"<td style='{max_parked_colour.css_bg_fg(row.parked_total)}'>{row.parked_total}</td>"
            f"<td style='{max_left_colour.css_bg_fg(row.leftover)}'>{row.leftover}</td>"
            f"<td style='{max_full_colour.css_bg_fg(row.max_total)}'>{row.max_total}</td>"
            f"<td style='{max_bike_hours_colour.css_bg_fg(row.bike_hours)}'>{row.bike_hours:0.0f}</td>"
            f"<td style='{max_bike_hours_per_hour_colour.css_bg_fg(row.bike_hours_per_hour)}'>{row.bike_hours_per_hour:0.2f}</td>"
            f"<td>{reg_str}</td>"
            f"<td style='{max_temp_colour.css_bg_fg(row.temp)}'>{temp_str}</td>"
            f"<td style='{max_precip_colour.css_bg_fg(row.precip_mm)}'>{precip_str}</td>"
            f"<td>{row.sunset}</td>"
            "</tr>"
        )
    print(" </table>")


def lost_tags(ttdb: sqlite3.Connection):
    too_many = 10
    curs = ttdb.cursor()
    rows = curs.execute(
        "select tag,date,time_in from visit "
        f"where date not in (select date from day where leftover > {too_many}) "
        'and (time_out is null or time_out = "")'
        # "and date < strftime('%Y-%m-%d') "
        "order by date desc;"
    ).fetchall()

    # print("<pre>")
    print("<h1>Tags of abandoned bikes</h1>")
    print("<ul>")
    print("<li>Listed newest to oldest</li>")
    print(
        f"<li>Excludes dates with more than {too_many} supposed leftovers</li>"
    )
    print(
        "<li>Tags might have been returned to use after the dates listed</li>"
    )
    print("</ul>")

    print("<table>")
    print("<style>td {text-align: left;}</style>")
    print("<tr><th>Tag</th><th>Last check-in</th></tr>")
    for row in rows:
        tag = TagID(row[0])
        in_date = row[1]
        in_time = row[2]
        tag_link = cc.selfref(what="last_use", qtag=tag)
        date_link = cc.selfref(what="one_day_tags", qdate=in_date)

        print(
            f"<tr><td>"
            f"<a href='{tag_link}'>{tag.cased}</a>"
            "</td>"
            f"<td><a href='{date_link}'>{in_date}</a> {in_time}</td></tr>"
        )
    print(" </table>")


def one_day_tags_report(ttdb: sqlite3.Connection, whatday: str = ""):
    thisday = ut.date_str(whatday)
    if not thisday:
        bad_date(whatday)

    rows = (
        ttdb.cursor()
        .execute(
            "select tag,time_in,time_out,duration from visit "
            f"where date = '{thisday}' "
            "order by time_in desc;"
        )
        .fetchall()
    )

    visits = {}
    for row in rows:
        tag = TagID(row[0])
        if not tag:
            continue
        v: db.VisitRow = db.VisitRow()
        v.tag = tag
        v.time_in = VTime(row[1])
        v.time_out = VTime(row[2])
        v.duration = VTime(row[3])
        visits[tag] = v

    print(
        f"<h1>Tags report for {thisday} ({ut.date_str(thisday,dow_str_len=10)})</h1>"
    )
    print("<pre>")
    if not visits:
        print(f"No activity recorded for {thisday}")
        sys.exit()
    print(f"Tags for {thisday}")
    print("-------------------")
    print(
        "- Where no check-out time exists, duration is estimated\n  assuming bike is at valet until the end of the day"
    )
    print()
    print("BIKE   --IN- -OUT-  DURTN")
    for tag in sorted(visits.keys()):
        v: db.VisitRow = visits[tag]
        print(
            f"{cc.padval(tag,6)} {cc.padval(v.time_in.tidy,5)} {cc.padval(v.time_out.tidy,5)}  {v.duration.tidy}"
        )
    print("</pre></body></html>")


def datafile(ttdb: sqlite3.Connection, date: str = ""):
    """Print a reconstructed datafile for the given date."""
    thisday = ut.date_str(date)
    if not thisday:
        bad_date(date)
    print(
        f"<h1>Reconstructed datafile for {ut.date_str(thisday,long_date=True)}</h1>"
    )
    print("<pre>")

    day = db.db2day(ttdb, thisday)
    print(f"# TagTracker datafile for {thisday}")
    print(f"# Reconstructed on {ut.date_str('today')} at {VTime('now')}")
    print(f"{df.HEADER_VALET_DATE} {day.date}")
    print(f"{df.HEADER_VALET_OPENS} {day.opening_time}")
    print(f"{df.HEADER_VALET_CLOSES} {day.closing_time}")
    print(f"{df.HEADER_BIKES_IN}")
    for tag, atime in day.bikes_in.items():
        print(f"  {tag.lower()},{atime}")
    print(f"{df.HEADER_BIKES_OUT}")
    for tag, atime in day.bikes_out.items():
        print(f"  {tag.lower()},{atime}")
    print(f"{df.HEADER_REGULAR}")
    print(f"{df.HEADER_OVERSIZE}")
    print(f"{df.HEADER_RETIRED}")
    print(f"{df.HEADER_COLOURS}")
    for col, name in day.colour_letters.items():
        print(f"  {col},{name}")


def bad_date(bad_date: str = ""):
    """Print message about bad date & exit."""
    cc.error_out(
        f"Bad date '{ut.untaint(bad_date)}'. "
        "Use YYYY-MM-DD or 'today' or 'yesterday'."
    )


def audit_report(ttdb: sqlite3.Connection, thisday: str, whattime: VTime):
    """Print audit report."""
    if not thisday:
        bad_date(thisday)
    print(f"<h1>Audit report for {ut.date_str(thisday,long_date=True)}</h1>")
    print("<pre>")
    day = db.db2day(ttdb, thisday)
    rep.audit_report(day, [VTime(whattime)])


def one_day_chart(ttdb: sqlite3.Connection, date: str):
    """One-day chart."""
    thisday = ut.date_str(date)
    if not thisday:
        bad_date(date)
    query_time = "now" if thisday == ut.date_str("today") else "24:00"
    print(
        f"<h1>Activity charts for {ut.date_str(thisday,long_date=True)}</h1>"
    )
    print("<pre>")
    rep.full_chart(db.db2day(ttdb, thisday), query_time)
    rep.busy_graph(db.db2day(ttdb, thisday), query_time)
    rep.fullness_graph(db.db2day(ttdb, thisday), query_time)


def one_day_summary(ttdb: sqlite3.Connection, thisday: str, qtime: VTime):
    """One-day busy report."""
    if not thisday:
        bad_date(thisday)
    day = db.db2day(ttdb, thisday)
    print(f"<h1>Day-end report for {ut.date_str(thisday,long_date=True)}</h1>")
    print("<pre>")
    rep.day_end_report(day, [qtime])
    print()
    rep.busyness_report(day, [qtime])
    print("</pre>")


# =================================================================
print("Content-type: text/html\n\n\n")

TagID.uc(cfg.TAGS_UPPERCASE)

DBFILE = cfg.DB_FILENAME
database = db.db_connect(DBFILE)

# Parse query parameters from the URL if present
query_string = ut.untaint(os.environ.get("QUERY_STRING", ""))
if os.getenv("TAGTRACKER_DEV"):
    print(
        "<pre style='color:red'>"
        "\n\nDEV DEV DEV DEV DEV DEV DEV DEV\n\n"
        f"export QUERY_STRING='{query_string}'; "
        f"export SERVER_PORT={os.environ.get('SERVER_PORT')}\n\n"
        "</pre>"
    )


query_params = urllib.parse.parse_qs(query_string)
what = query_params.get("what", [""])[0]
what = what if what else "overview"
maybedate = query_params.get("date", [""])[0]
maybetime = query_params.get("time", [""])[0]
tag = query_params.get("tag", [""])[0]
dow_parameter = query_params.get("dow", [""])[0]
if dow_parameter and dow_parameter not in [str(i) for i in range(1, 8)]:
    cc.error_out(f"bad iso dow, need 1..7, not '{ut.untaint(dow_parameter)}'")
if not dow_parameter:
    # If no day of week, set it to today.
    dow_parameter = str(
        datetime.datetime.strptime(ut.date_str("today"), "%Y-%m-%d").strftime(
            "%u"
        )
    )


# Date will be 'today' or 'yesterday' or ...
# Time of day will be 24:00 unless it's today (or specified)
qdate = ut.date_str(maybedate)
if not maybetime:
    if qdate == ut.date_str("today"):
        qtime = VTime("now")
    else:
        qtime = VTime("24:00")
else:
    qtime = VTime(maybetime)
if not qtime:
    cc.error_out(f"Bad time: '{ut.untaint(maybetime)}")
form(
    default_what=what,
    default_date=maybedate,
    default_tag=tag,
    default_dow=dow_parameter,
)
if not what:
    sys.exit()
if what == "last_use":
    one_tag_history_report(database, tag)
elif what == "blocks":
    cgi_block_report.blocks_report(database)
elif what == "dow_blocks":
    cgi_block_report.blocks_report(database, dow_parameter)
elif what == "overview":
    overview_report(database)
elif what == "dow_overview":
    overview_report(database, dow_parameter)
elif what == "abandoned":
    lost_tags(database)
elif what == "one_day_tags":
    one_day_tags_report(database, qdate)
elif what == "datafile":
    datafile(database, qdate)
elif what == "audit":
    audit_report(database, qdate, qtime)
elif what == "day_end":
    one_day_summary(database, qdate, qtime)
elif what == "chart" or what == "busy-graph":
    one_day_chart(database, qdate)
else:
    cc.error_out(f"Unknown request: {ut.untaint(what)}")
    sys.exit(1)
print("<pre>")
print(db.db_latest(database))
print(f"TagTracker version {ut.get_version()}")
