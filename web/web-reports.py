#!/usr/bin/env python3
"""CGI script for TagTracker reports against consolidated database.

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
import sys
import os
import urllib.parse

sys.path.append("../")
sys.path.append("./")

# pylint:disable=wrong-import-position
import web_common as cc
import web_block_report
from web_day_detail import one_day_tags_report, day_frequencies_report
import web_season_report
import web_tags_report
import web_daterange_summaries
import web_base_config as wcfg
from common.tt_tag import TagID
from common.tt_time import VTime
import common.tt_util as ut
from common.get_version import get_version_info
import common.tt_constants as k
import common.tt_dbutil as db
import tt_reports as rep
import tt_audit_report as aud
import tt_tag_inv
import tt_printer as pr

# pylint:enable=wrong-import-position


# def datafile(ttdb: sqlite3.Connection, date: str = ""):
#     """Print a reconstructed datafile for the given date."""
#     thisday = ut.date_str(date)
#     if not thisday:
#         cc.bad_date(date)

#     print(f"<h1>Reconstructed datafile for {ut.date_str(thisday)}</h1>")
#     print(f"{cc.main_and_back_buttons(1)}<br>")

#     print("<pre>")

#     day = db.db2day(ttdb, thisday)
#     print(f"# TagTracker datafile for {thisday}")
#     print(f"# Reconstructed on {ut.date_str('today')} at {VTime('now')}")
#     print(f"{df.HEADER_DATE} {day.date}")
#     print(f"{df.HEADER_OPENS} {day.time_open}")
#     print(f"{df.HEADER_CLOSES} {day.time_closed}")
#     print(f"{df.HEADER_BIKES_IN}")
#     sorted_bikes = sorted(day.bikes_in.items(), key=lambda x: x[1])
#     for this_tag, atime in sorted_bikes:
#         formatted_tag = f"{this_tag.lower()},   "[:6]
#         print(f"  {formatted_tag}{atime}")
#     print(f"{df.HEADER_BIKES_OUT}")
#     sorted_bikes = sorted(day.bikes_out.items(), key=lambda x: x[1])
#     for this_tag, atime in sorted_bikes:
#         formatted_tag = f"{this_tag.lower()},   "[:6]
#         print(f"  {formatted_tag}{atime}")
#     print(f"{df.HEADER_REGULAR}")
#     ut.line_wrapper(" ".join(sorted(day.regular)), print_handler=pr.iprint)
#     print(f"{df.HEADER_OVERSIZE}")
#     ut.line_wrapper(" ".join(sorted(day.oversize)), print_handler=pr.iprint)
#     print(f"{df.HEADER_RETIRED}")
#     ut.line_wrapper(" ".join(sorted(day.retired)), print_handler=pr.iprint)
#     print(f"{df.HEADER_COLOURS}")


def web_audit_report(
    ttdb: sqlite3.Connection,
    orgsite_id: int,
    date: str,
    whattime: VTime,
):
    """Print web audit report."""

    whattime = VTime(whattime)
    thisday = ut.date_str(date)
    if not thisday:
        cc.bad_date(thisday)

    # Find this day's day_id
    cursor = ttdb.cursor()
    day_id = db.fetch_day_id(cursor=cursor, date=thisday, maybe_orgsite_id=orgsite_id)
    cursor.close()

    # Make this page have a black background
    print("<style>body {background-color:black;color:white}</style>")
    print(f"<h1>Parking attendant report {thisday}</h1>")
    print("<h2>Audit</h2>")
    print("<pre>")

    day = db.db2day(ttdb=ttdb, day_id=day_id)
    if not day:
        print("<b>no information for this day</b><br>")
        return
    aud.audit_report(day, [whattime], include_notes=False, include_returns=True)
    print("\n</pre>")

    print("<h2>Bike registrations</h2>")
    print(f"<p>&nbsp;&nbsp;Registrations today: {day.registrations}\n</p>")

    # print("<h2>Busyness</h2>")
    # print("<pre>")
    # rep.busyness_report(day, [qtime])
    # print("\n</pre>")

    print("<h2>Tag inventory</h2>")
    print("<pre>")
    tt_tag_inv.tags_config_report(day, [whattime], include_empty_groups=True)
    print("</pre>")
    print("<br><br>")

    print("<h2>Notices</h2>")


def one_day_data_enry_reports(ttdb: sqlite3.Connection, date: str):
    """One-day chart."""
    thisday = ut.date_str(date)
    if not thisday:
        cc.bad_date(date)
    query_time = "now" if thisday == ut.date_str("today") else "24:00"
    query_time = VTime(query_time)
    print(f"<h1>Data Entry reports for {ut.date_str(thisday,long_date=True)}</h1>")
    print(f"{cc.main_and_back_buttons(1)}<br>")
    print("<pre>")
    day = db.db2day(ttdb, thisday)
    rep.summary_report(day, [qtime])
    # print()
    # rep.busyness_report(day, [qtime])
    print()
    aud.audit_report(day, [query_time], include_notes=False, include_returns=True)
    print()
    rep.full_chart(day, query_time)
    print()
    tt_tag_inv.tags_config_report(day, [query_time], True)
    # print()
    # rep.busy_graph(day, query_time)
    # print()
    # rep.fullness_graph(day, query_time)
    print()


def one_day_chart(ttdb: sqlite3.Connection, date: str):
    """One-day chart."""
    thisday = ut.date_str(date)
    if not thisday:
        cc.bad_date(date)
    query_time = "now" if thisday == ut.date_str("today") else "24:00"
    print(f"<h1>Data Entry reports for {ut.date_str(thisday,long_date=True)}</h1>")
    print("<pre>")
    rep.full_chart(db.db2day(ttdb, thisday), query_time)
    # rep.busy_graph(db.db2day(ttdb, thisday), query_time)
    # rep.fullness_graph(db.db2day(ttdb, thisday), query_time)


def one_day_summary(ttdb: sqlite3.Connection, thisday: str, query_time: VTime):
    """One-day busy report."""
    if not thisday:
        cc.bad_date(thisday)
    day = db.db2day(ttdb, thisday)
    print(f"<h1>Day-end report for {ut.date_str(thisday,long_date=True)}</h1>")
    print(f"{cc.main_and_back_buttons(1)}<br>")

    print(f"Hours: {day.time_open} - {day.time_closed}</p>")
    print("<pre>")
    rep.summary_report(day, [query_time])
    # print()
    # rep.busyness_report(day, [query_time])
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


def webpage_footer(ttdb: sqlite3.Connection):
    """Prints the footer for each webpage"""

    print("<pre>")

    if wcfg.DATA_OWNER:
        data_note = (
            wcfg.DATA_OWNER if isinstance(wcfg.DATA_OWNER, list) else [wcfg.DATA_OWNER]
        )
        for line in data_note:
            print(line)
        print()

    print(db.db_latest(ttdb))

    print(f"TagTracker version {get_version_info()}")


# =================================================================

org_handle = "no_org"  # FIXME
caller_org = "no_org"  # FIXME - read from web auth via env
ORGSITE_ID = 1  # FIXME hardwired. (This one uc so sub-functions can't read orgsite_id)

print("Content-type: text/html\n\n\n")

TagID.uc(wcfg.TAGS_UPPERCASE)

DBFILE = wcfg.DB_FILENAME
database = db.db_connect(DBFILE)
if not database:
    print("<br>No database")
    sys.exit()

# Set text colours off (for the text-based reports)
pr.COLOUR_ACTIVE = True
k.set_html_style()

# Parse query parameters from the URL if present
QUERY_STRING = ut.untaint(os.environ.get("QUERY_STRING", ""))
if os.getenv("TAGTRACKER_DEBUG"):
    print(
        "<pre style='color:red'>\nDEBUG -- TAGTRACKER_DEBUG flag is set\n\n" "</pre>"
    )
query_params = urllib.parse.parse_qs(QUERY_STRING)
what = query_params.get("what", [""])[0]
what = what if what else cc.WHAT_SUMMARY
maybedate = query_params.get("date", [""])[0]
maybetime = query_params.get("time", [""])[0]
tag = query_params.get("tag", [""])[0]
text = query_params.get("text", [""])[0]
dow_parameter = query_params.get("dow", [""])[0]
# if dow_parameter and dow_parameter not in [str(i) for i in range(1, 8)]:
#    cc.error_out(f"bad iso dow, need 1..7, not '{ut.untaint(dow_parameter)}'")
# if not dow_parameter:
#     # If no day of week, set it to today. FIXME: why? Disablling this.
#     dow_parameter = str(
#         datetime.datetime.strptime(ut.date_str("today"), "%Y-%m-%d").strftime("%u")
#     )
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

date_start = query_params.get("start_date", ["0000-00-00"])[0]
date_end = query_params.get("end_date", ["9999-99-99"])[0]


if what == cc.WHAT_TAG_HISTORY:
    web_tags_report.one_tag_history_report(database, tag)
elif what == cc.WHAT_BLOCKS:
    web_block_report.blocks_report(database)
elif what == cc.WHAT_BLOCKS_DOW:
    web_block_report.blocks_report(database, dow_parameter)
elif what == cc.WHAT_DETAIL:
    web_season_report.season_detail(
        database, sort_by=sort_by, sort_direction=sort_direction, pages_back=pages_back
    )
elif what == cc.WHAT_SUMMARY:
    web_season_report.season_summary(database)
elif what == cc.WHAT_SUMMARY_FREQUENCIES:
    web_season_report.season_frequencies_report(
        database,
        dow_parameter=dow_parameter,
        title_bit=text,
        pages_back=pages_back,
        start_date=date_start,
        end_date=date_end,
    )
elif what == cc.WHAT_TAGS_LOST:
    web_tags_report.tags_report(database)
elif what == cc.WHAT_ONE_DAY:
    one_day_tags_report(
        database,
        orgsite_id=ORGSITE_ID,
        whatday=qdate,
        sort_by=sort_by,
        pages_back=pages_back,
    )
elif what == cc.WHAT_ONE_DAY_FREQUENCIES:
    day_frequencies_report(database, whatday=qdate)
# elif what == cc.WHAT_DATAFILE:
#     datafile(database, qdate)
elif what == cc.WHAT_DATA_ENTRY:
    one_day_data_enry_reports(database, qdate)
elif what == cc.WHAT_AUDIT:
    web_audit_report(
        database, orgsite_id=1, date="today", whattime=VTime("now")
    )  # FIXME: orgsite_id
elif what in [
    cc.WHAT_DATERANGE,
    cc.WHAT_DATERANGE_WEEK,
    cc.WHAT_DATERANGE_MONTH,
    cc.WHAT_DATERANGE_QUARTER,
    cc.WHAT_DATERANGE_YEAR,
    cc.WHAT_DATERANGE_CUSTOM,
]:
    web_daterange_summaries.daterange_summary(
        database, what, start_date=date_start, end_date=date_end,pages_back=pages_back
    )
else:
    cc.error_out(f"Unknown request: {ut.untaint(what)}")
    sys.exit(1)

webpage_footer(database)
