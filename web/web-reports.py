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
import time
import html
from pathlib import Path

sys.path.append("../")
sys.path.append("./")

# pylint:disable=wrong-import-position
import web_common as cc
import web_block_report
from web_day_detail import one_day_tags_report
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
from web_estimator import Estimator

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

):
    """Print web audit report."""

    as_of_time = VTime("now")
    thisday = ut.date_str("today")

    # Find this day's day_id
    cursor = ttdb.cursor()
    day_id = db.fetch_day_id(cursor=cursor, date=thisday, maybe_orgsite_id=orgsite_id)
    cursor.close()

    # Make this page have a black background
    # print("<style>body {background-color:black;color:white}</style>")
    print("""<meta name="format-detection" content="telephone=no"/>""")
    print(f"<h1>Audit report {as_of_time.tidy} {thisday}</h1>")

    day = db.db2day(ttdb=ttdb, day_id=day_id)
    if not day:
        print("<b>no information for this day</b><br>")
        return

    table_style = (
        "style='border-collapse:collapse;margin-bottom:1.5rem;"
        "border:0;font-family:monospace;font-size:1.5em;'"
    )
    cell_style = (
        "style='border:0;padding:4px 6px;white-space:nowrap;"
        "text-align:center;'"
    )
    retired_marker = html.escape(aud.DEFAULT_RETIRED_TAG_STR.strip()) or "&bullet;"

    def render_tag_matrix(title: str, tags: list[TagID]) -> None:
        prefixes = ut.tagnums_by_prefix(tags)
        print(f"<h3>{title}</h3>")
        print(f"<table {table_style}>")
        rows_rendered = 0
        previous_colour = None
        last_colspan = 0
        for prefix in sorted(prefixes.keys()):
            greatest = ut.greatest_tagnum(prefix, day.regular_tagids, day.oversize_tagids)
            if greatest is None:
                continue
            colour_code = prefix[0] if prefix else ""
            if rows_rendered and colour_code != previous_colour:
                gap_cols = last_colspan if last_colspan else 1
                if gap_cols <= 1:
                    print(
                        "<tr><td style='border:0;padding:0;height:0.4em'>&nbsp;</td></tr>"
                    )
                else:
                    print(
                        "<tr><td style='border:0;padding:0;height:0.4em'>&nbsp;</td>"
                        "<td style='border:0;padding:0;height:0.4em' "
                        f"colspan='{gap_cols - 1}'></td></tr>"
                    )
            rows_rendered += 1
            numbers = set(prefixes[prefix])
            cells = [f"<td {cell_style}><strong>{html.escape(prefix)}</strong></td>"]
            for i in range(greatest + 1):
                if i in numbers:
                    cell_value = f"{i:02d}"
                elif TagID(f"{prefix}{i}") in day.retired_tagids:
                    cell_value = retired_marker
                else:
                    cell_value = "&nbsp;&nbsp;"
                cells.append(f"<td {cell_style}>{cell_value}</td>")
            print("<tr>" + "".join(cells) + "</tr>")
            previous_colour = colour_code
            last_colspan = len(cells)
        if rows_rendered == 0:
            print(f"<tr><td {cell_style}>-no bikes-</td></tr>")
        print("</table>")

    render_tag_matrix(f"Tags in use", day.tags_in_use(as_of_when=as_of_time))
    render_tag_matrix("Tags potentially available for re-use", day.tags_done(as_of_when=as_of_time))

    print("<br><br>")

    print("<h2>Notices</h2>")


def one_day_data_entry_reports(ttdb: sqlite3.Connection, date: str):
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




# -----------------
def web_est_wrapper() -> None:
    """The estimation (verbose) page guts.

    Maybe move this to web_estimator.py
    """
    print(f"<h1>Estimation Details for {ut.date_str('today')}</h1>")
    print(f"{cc.main_and_back_buttons(1)}<br><br>")

    est = Estimator(estimation_type="verbose")
    est.guess()
    for line in est.result_msg(as_html=True):
        print(line)
    # print(
    #     "<p>A further "
    #     "<a href='https://raw.githubusercontent.com/ironwoodcall/TagTracker/refs/heads/main/docs/estimator_models.txt'>"
    #     "discussion of the estimation models</a> is available.</p>"
    # )

    models_path = Path(__file__).resolve().parent.parent / "docs" / "estimator_models.txt"
    if models_path.is_file():
        print("<h3>Background on the models</h3><pre>")
        with models_path.open(encoding="utf-8") as models_file:
            print(html.escape(models_file.read()))
        print("</pre><hr>")


# =================================================================

start_time = time.perf_counter()

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
    print("<pre style='color:red'>\nDEBUG -- TAGTRACKER_DEBUG flag is set\n\n" "</pre>")
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
pages_back: int = int(pages_back) if ut.is_int(pages_back) else 0

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

cc.html_head()

if not what:
    sys.exit()

requested_start = query_params.get("start_date", [""])[0]
requested_end = query_params.get("end_date", [""])[0]

date_start, date_end, _default_start_date, _default_end_date = cc.resolve_date_range(
    database,
    orgsite_id=ORGSITE_ID,
    start_date=requested_start,
    end_date=requested_end,
)


if what == cc.WHAT_TAG_HISTORY:
    web_tags_report.one_tag_history_report(database, tag)
elif what == cc.WHAT_BLOCKS:
    web_block_report.blocks_report(
        database,
        pages_back=pages_back,
        start_date=date_start,
        end_date=date_end,
    )
elif what == cc.WHAT_BLOCKS_DOW:
    web_block_report.blocks_report(
        database,
        dow_parameter,
        pages_back=pages_back,
        start_date=date_start,
        end_date=date_end,
    )
elif what == cc.WHAT_DETAIL:
    web_season_report.season_detail(
        database,
        sort_by=sort_by,
        sort_direction=sort_direction,
        pages_back=pages_back,
        start_date=date_start,
        end_date=date_end,
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
    web_season_report.season_frequencies_report(
        database,
        pages_back=pages_back,
        start_date=date_start,
        end_date=date_end,
        restrict_to_single_day=True,
    )

# elif what == cc.WHAT_DATAFILE:
#     datafile(database, qdate)
elif what == cc.WHAT_DATA_ENTRY:
    one_day_data_entry_reports(database, qdate)
elif what == cc.WHAT_AUDIT:
    web_audit_report(
        database, orgsite_id=1
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
        database, what, start_date=date_start, end_date=date_end, pages_back=pages_back
    )
elif what == cc.WHAT_ESTIMATE_VERBOSE:
    web_est_wrapper()

else:
    cc.error_out(f"Unknown request: {ut.untaint(what)}")
    sys.exit(1)


cc.webpage_footer(database, time.perf_counter() - start_time)
