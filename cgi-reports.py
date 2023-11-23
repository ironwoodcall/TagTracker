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

from tt_globals import MaybeTag

import tt_dbutil as db
import tt_conf as cfg
import tt_reports as rep
import tt_datafile as df
from tt_tag import TagID
from tt_time import VTime
import tt_util as ut
import cgi_common as cc
import datacolors as dc
import cgi_block_report
import cgi_leftovers_report
from cgi_day_detail import one_day_tags_report
import cgi_season_report
import cgi_tags_report


def one_tag_history_report(ttdb: sqlite3.Connection, maybe_tag: MaybeTag) -> None:
    """Report a tag's history."""

    this_tag = TagID(maybe_tag)
    if not this_tag:
        print(f"Not a tag: '{ut.untaint(this_tag.original)}'")
        sys.exit()
    # Fetch all info about this tag.
    ##(last_date, last_in, last_out) = ("", "", "")
    rows = db.db_fetch(
        ttdb,
        "select date,time_in,time_out "
        "from visit "
        f"where tag = '{this_tag.lower()}' "
        "order by date desc;",
    )
    print(f"<h1>History of tag {this_tag.upper()}</h1>")
    print(f"{cc.back_button(1)}<br>")

    print(f"<h3>This tag has been used {len(rows)} {ut.plural(len(rows), 'time')}</h3>")
    print()
    if not rows:
        print(f"No record that {this_tag.upper()} ever used<br />")
    else:
        print("<table>")
        print("<style>td {text-align: right;}</style>")
        print("<tr><th>Date</th><th>BikeIn</th><th>BikeOut</th></tr>")
        for row in rows:
            out = VTime(row.time_out).tidy
            link = cc.selfref(what=cc.WHAT_ONE_DAY, qdate=row.date)
            print(
                f"<tr><td>"
                f"<a href='{link}'>{row.date}</a>"
                "</td>"
                f"<td>{VTime(row.time_in).tidy}</td><td>{out}</td></tr>"
            )
        print("</table>")
    print("</body></html>")


def datafile(ttdb: sqlite3.Connection, date: str = ""):
    """Print a reconstructed datafile for the given date."""
    thisday = ut.date_str(date)
    if not thisday:
        cc.bad_date(date)

    print(f"<h1>Reconstructed datafile for {ut.date_str(thisday)}</h1>")
    print(f"{cc.back_button(1)}<br>")

    print("<pre>")

    day = db.db2day(ttdb, thisday)
    print(f"# TagTracker datafile for {thisday}")
    print(f"# Reconstructed on {ut.date_str('today')} at {VTime('now')}")
    print(f"{df.HEADER_VALET_DATE} {day.date}")
    print(f"{df.HEADER_VALET_OPENS} {day.opening_time}")
    print(f"{df.HEADER_VALET_CLOSES} {day.closing_time}")
    print(f"{df.HEADER_BIKES_IN}")
    sorted_bikes = sorted(day.bikes_in.items(), key=lambda x: x[1])
    for this_tag, atime in sorted_bikes:
        formatted_tag = f"{this_tag.lower()},   "[:6]
        print(f"  {formatted_tag}{atime}")
    print(f"{df.HEADER_BIKES_OUT}")
    sorted_bikes = sorted(day.bikes_out.items(), key=lambda x: x[1])
    for this_tag, atime in sorted_bikes:
        formatted_tag = f"{this_tag.lower()},   "[:6]
        print(f"  {formatted_tag}{atime}")
    print(f"{df.HEADER_REGULAR}")
    print(f"{df.HEADER_OVERSIZE}")
    print(f"{df.HEADER_RETIRED}")
    print(f"{df.HEADER_COLOURS}")
    for col, name in day.colour_letters.items():
        print(f"  {col},{name}")


def audit_report(ttdb: sqlite3.Connection, thisday: str, whattime: VTime):
    """Print audit report."""
    if not thisday:
        cc.bad_date(thisday)
    print(f"<h1>Audit report for {ut.date_str(thisday,long_date=True)}</h1>")
    print("<pre>")
    day = db.db2day(ttdb, thisday)
    rep.audit_report(day, [VTime(whattime)], include_notes=False)


def one_day_data_enry_reports(ttdb: sqlite3.Connection, date: str):
    """One-day chart."""
    thisday = ut.date_str(date)
    if not thisday:
        cc.bad_date(date)
    query_time = "now" if thisday == ut.date_str("today") else "24:00"
    query_time = VTime(query_time)
    print(f"<h1>Data Entry reports for {ut.date_str(thisday,long_date=True)}</h1>")
    print(f"{cc.back_button(1)}<br>")
    print("<pre>")
    day = db.db2day(ttdb, thisday)
    rep.day_end_report(day, [qtime])
    print()
    rep.busyness_report(day, [qtime])
    print()
    rep.audit_report(day, [query_time], include_notes=False)
    print()
    rep.full_chart(day, query_time)
    print()
    rep.busy_graph(day, query_time)
    print()
    rep.fullness_graph(day, query_time)


def one_day_chart(ttdb: sqlite3.Connection, date: str):
    """One-day chart."""
    thisday = ut.date_str(date)
    if not thisday:
        cc.bad_date(date)
    query_time = "now" if thisday == ut.date_str("today") else "24:00"
    print(f"<h1>Data Entry reports for {ut.date_str(thisday,long_date=True)}</h1>")
    print("<pre>")
    rep.full_chart(db.db2day(ttdb, thisday), query_time)
    rep.busy_graph(db.db2day(ttdb, thisday), query_time)
    rep.fullness_graph(db.db2day(ttdb, thisday), query_time)


def one_day_summary(ttdb: sqlite3.Connection, thisday: str, query_time: VTime):
    """One-day busy report."""
    if not thisday:
        cc.bad_date(thisday)
    day = db.db2day(ttdb, thisday)
    print(f"<h1>Day-end report for {ut.date_str(thisday,long_date=True)}</h1>")
    print(f"{cc.back_button(1)}<br>")

    print(f"Hours: {day.opening_time} - {day.closing_time}</p>")
    print("<pre>")
    rep.day_end_report(day, [query_time])
    print()
    rep.busyness_report(day, [query_time])
    print("</pre>")


def html_head(
    title: str = "TagTracker",
):
    print(
        f"""
        <html><head>
        <title>{title}</title>
        <meta charset='UTF-8'>
        {cc.style()}
        <script>
          // (this fn courtesy of chatgpt)
          function goBack(pagesToGoBack = 1) {{
            window.history.go(-pagesToGoBack);
          }}
        </script>
        </head>"""
    )
    ##print(cc.style())
    print("<body>")


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
what = what if what else cc.WHAT_SUMMARY
maybedate = query_params.get("date", [""])[0]
maybetime = query_params.get("time", [""])[0]
tag = query_params.get("tag", [""])[0]
dow_parameter = query_params.get("dow", [""])[0]
if dow_parameter and dow_parameter not in [str(i) for i in range(1, 8)]:
    cc.error_out(f"bad iso dow, need 1..7, not '{ut.untaint(dow_parameter)}'")
if not dow_parameter:
    # If no day of week, set it to today.
    dow_parameter = str(
        datetime.datetime.strptime(ut.date_str("today"), "%Y-%m-%d").strftime("%u")
    )
sort_by = query_params.get("sort", [""])[0]
sort_direction = query_params.get("dir", [""])[0]
pages_back: str = query_params.get("back", "1")[0]
pages_back: int = int(pages_back) if pages_back.isdigit() else 0

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

html_head()

if not what:
    sys.exit()
if what == cc.WHAT_TAG_HISTORY:
    one_tag_history_report(database, tag)
elif what == cc.WHAT_BLOCKS:
    cgi_block_report.blocks_report(database)
elif what == cc.WHAT_BLOCKS_DOW:
    cgi_block_report.blocks_report(database, dow_parameter)
elif what == cc.WHAT_DETAIL:
    cgi_season_report.season_detail(
        database, sort_by=sort_by, sort_direction=sort_direction, pages_back=pages_back
    )
elif what == cc.WHAT_SUMMARY:
    cgi_season_report.season_summary(database)
# elif what == cc.WHAT_OVERVIEW:
#    overview_report(database)
# elif what == cc.WHAT_OVERVIEW_DOW:
#    overview_report(database, dow_parameter)
elif what == cc.WHAT_TAGS_LOST:
    cgi_tags_report.tags_report(database)
elif what == cc.WHAT_MISMATCH:
    cgi_leftovers_report.leftovers_report(database)
elif what == cc.WHAT_ONE_DAY:
    one_day_tags_report(database, whatday=qdate, sort_by=sort_by, pages_back=pages_back)
elif what == cc.WHAT_DATAFILE:
    datafile(database, qdate)
elif what == cc.WHAT_DATA_ENTRY:
    one_day_data_enry_reports(database, qdate)
else:
    cc.error_out(f"Unknown request: {ut.untaint(what)}")
    sys.exit(1)
print("<pre>")
print(db.db_latest(database))
print(f"TagTracker version {ut.get_version()}")
