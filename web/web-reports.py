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
import common.tt_constants as k
import common.tt_dbutil as db
# import tt_reports as rep
# import tt_audit_report as aud
# import tt_tag_inv
# import tt_printer as pr
from web_estimator import Estimator


def web_audit_report(
    ttdb: sqlite3.Connection,
    orgsite_id: int,
):
    """Print web audit report."""

    as_of_time = VTime("now")
    thisday = ut.date_str("today")


    print("""<meta name="format-detection" content="telephone=no"/>""")
    print(f"<h1>Audit report {as_of_time.tidy} {thisday}</h1>")
    # Only put a "Back" button if this was called from itself
    if cc.called_by_self():
        print(f"{cc.back_button(1)}<br><br>")
        # print(f"{cc.main_and_back_buttons(pages_back=pages_back)}<br><br>")

    # Find this day's day_id
    cursor = ttdb.cursor()
    day_id = db.fetch_day_id(cursor=cursor, date=thisday, maybe_orgsite_id=orgsite_id)
    cursor.close()

    if not day_id:
        print("<br><b>No bike information in the database for this day.</b><br><br>")
        return

    day = db.db2day(ttdb=ttdb, day_id=day_id)


    tags_in_use = day.tags_in_use(as_of_when=as_of_time)
    regular_onsite = 0
    oversize_onsite = 0
    for tag_id in tags_in_use:
        bike = day.biketags.get(tag_id)
        if not bike:
            continue
        if bike.bike_type == k.OVERSIZE:
            oversize_onsite += 1
        else:
            regular_onsite += 1
    total_onsite = regular_onsite + oversize_onsite

    print(
        "<table class='general_table' "
        "style='max-width:22rem;margin-bottom:1.5rem;'>"
    )
    print("<tr><th colspan='2'>Bikes currently onsite</th></tr>")
    print(
        f"<tr><td>Regular bikes</td><td style='text-align:right;'>{regular_onsite}</td></tr>"
    )
    print(
        f"<tr><td>Oversize bikes</td><td style='text-align:right;'>{oversize_onsite}</td></tr>"
    )
    print(
        "<tr><td><b>Total bikes</b></td><td style='text-align:right;'>"
        f"<b>{total_onsite}</b></td></tr>"
    )
    print("</table>")

    base_table_style = (
        "border-collapse:collapse;margin-bottom:1.5rem;"
        "border:1px solid #666;font-family:monospace;font-size:1.5em;"
    )
    cell_style = (
        "style='border:0;padding:4px 6px;white-space:nowrap;"
        "text-align:center;'"
    )
    retired_marker = "&bullet;"

    tags_done = day.tags_done(as_of_when=as_of_time)
    combined_tags = list(tags_in_use) + list(tags_done)
    max_sequence = max((tag.number for tag in combined_tags), default=0)

    def render_tag_matrix(
        title: str, tags: list[TagID], max_seq: int, text_colour: str
    ) -> None:
        prefixes = ut.tagnums_by_prefix(tags)
        print(f"<h3>{title}</h3>")
        table_style = f"style='{base_table_style}color:{text_colour};'"
        print(f"<table {table_style}>")
        total_columns = max_seq + 3
        rows_rendered = 0
        previous_colour = None
        for prefix in sorted(prefixes.keys()):
            numbers = set(prefixes[prefix])
            colour_code = prefix[0] if prefix else ""
            if rows_rendered and colour_code != previous_colour:
                print(
                    f"<tr><td colspan='{total_columns}' style='border:0;padding:4px 0;'>"
                    "<hr style=\"border:0;border-top:1px solid #999;margin:0;\"></td></tr>"
                )
            cells = [f"<td {cell_style}><strong>{html.escape(prefix)}</strong></td>"]
            for i in range(max_seq + 1):
                tag_id = TagID(f"{prefix}{i}")
                if i in numbers:
                    cell_value = f"{i:02d}"
                elif tag_id in day.retired_tagids:
                    cell_value = retired_marker
                else:
                    cell_value = "&nbsp;&nbsp;"
                cells.append(f"<td {cell_style}>{cell_value}</td>")
            cells.append(f"<td {cell_style}><strong>{html.escape(prefix)}</strong></td>")
            row_bg_colour = "#f4f4f4" if rows_rendered % 2 else "#ffffff"
            row_style = f" style='background-color:{row_bg_colour};'" if row_bg_colour else ""
            print(f"<tr{row_style}>" + "".join(cells) + "</tr>")
            rows_rendered += 1
            previous_colour = colour_code
        if rows_rendered == 0:
            print(
                f"<tr><td colspan='{total_columns}' style='padding:4px;text-align:center;'>"
                "-none-</td></tr>"
            )
        print("</table>")

    render_tag_matrix("Tags in use", tags_in_use, max_sequence, text_colour="#7b0b54")
    render_tag_matrix(
        "Tags potentially available for re-use",
        tags_done,
        max_sequence,
        text_colour="#1c7f7a",
    )

    # print("<br><br>")

    print("<h2>Notices</h2>")


# -----------------
def web_est_wrapper() -> None:
    """The estimation (verbose) page guts.

    Maybe move this to web_estimator.py
    """
    print(f"<h1>Detailed prediction for {ut.date_str('today')}</h1>")
    print(f"{cc.main_and_back_buttons(1)}<br><br>")

    est = Estimator(estimation_type="verbose")
    est.guess()
    for line in est.result_msg(as_html=True):
        print(line)

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
# pr.COLOUR_ACTIVE = True
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
        iso_dow=dow_parameter,
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
        dow_parameter=dow_parameter,
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
# elif what == cc.WHAT_DATA_ENTRY:
#     one_day_data_entry_reports(database, qdate)
elif what == cc.WHAT_AUDIT:
    web_audit_report(
        database, orgsite_id=1,
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
