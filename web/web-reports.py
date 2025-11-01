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
import time
from datetime import date, timedelta
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
import web_period_summaries
import web_compare_ranges
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
    print(cc.titleize("Attendant audit report",f"As at {as_of_time.tidy} {thisday}"))
    # Only put a "Back" button if this was called from itself
    if cc.called_by_self():
        print(f"{cc.back_button(1)}<br><br>")
        # print(f"{cc.main_and_back_buttons(pages_back=pages_back)}<br><br>")

    # Find this day's day_id
    cursor = ttdb.cursor()
    day_id = db.fetch_day_id(cursor=cursor, date=thisday, maybe_orgsite_id=orgsite_id)
    cursor.close()

    if not day_id:
        print("<br><b>No visits in the database for this day.</b><br><br>")
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
    print(f"<tr><th>Bikes currently on-site</th><th><b>{total_onsite}</b></th></tr>")
    print(
        f"<tr><td>&nbsp;&nbsp;&nbsp;Regular bikes</td><td style='text-align:right;'>{regular_onsite}</td></tr>"
    )
    print(
        f"<tr><td>&nbsp;&nbsp;&nbsp;Oversize bikes</td><td style='text-align:right;'>{oversize_onsite}</td></tr>"
    )
    # print(
    #     "<tr><td><b>Total bikes</b></td><td style='text-align:right;'>"
    #     f"<b>{total_onsite}</b></td></tr>"
    # )
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


# Query parameter sanitizing ---------------------------------------------------------------
SAFE_QUERY_CHARS = frozenset(
    " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:,-"
)

# FIXME: Remove once moved to CGIManager

def validate_query_params(query_parms: dict[str, list[str]]) -> None:
    """Ensure all provided query parameter values only contain allowed characters."""
    for key, values in query_parms.items():
        for value in values:
            if not value:
                continue
            if any(char not in SAFE_QUERY_CHARS for char in value):
                cc.error_out(
                    f"Invalid characters in parameter '{ut.untaint(str(key))}'"
                )


# =================================================================

start_time = time.perf_counter()

org_handle = "no_org"  # FIXME
caller_org = "no_org"  # FIXME - read from web auth via env
ORGSITE_ID = 1  # FIXME hardwired. (This one uc so sub-functions can't read orgsite_id)

print("Content-type: text/html\n\n\n")

if os.getenv("TAGTRACKER_DEBUG"):
    print("<pre style='color:red'>\nDEBUG -- TAGTRACKER_DEBUG flag is set\n\n" "</pre>")


params = cc.CGIManager.cgi_to_params()
params.what_report = params.what_report or cc.WHAT_SUMMARY
params.pages_back = params.pages_back or 0
what = params.what_report
tag = params.tag
dow_parameter = params.dow
sort_by = params.sort_by
sort_direction = params.sort_direction
pages_back = params.pages_back

requested_start = params.start_date
requested_end = params.end_date
requested_start2 = params.start_date2
requested_end2 = params.end_date2
dow_parameter2 = params.dow2

TagID.uc(wcfg.TAGS_UPPERCASE)

DBFILE = wcfg.DB_FILENAME
database = db.db_connect(DBFILE)
if not database:
    print("<br>No database")
    sys.exit()

# Set text colours off (for the text-based reports)
# pr.COLOUR_ACTIVE = True
k.set_html_style()


cc.html_head()

if not what:
    sys.exit()


if params.what_report == cc.WHAT_COMPARE_RANGES:
    today_str = ut.date_str("today")
    try:
        today_date = date.fromisoformat(today_str)
    except ValueError:
        today_date = date.today()

    current_month_start = date(today_date.year, today_date.month, 1)
    last_month_end = current_month_start - timedelta(days=1)
    last_month_start = date(last_month_end.year, last_month_end.month, 1)

    def _month_end(start_day: date) -> date:
        """Return the final day of the month containing ``start_day``."""
        if start_day.month == 12:
            next_month_start = date(start_day.year + 1, 1, 1)
        else:
            next_month_start = date(start_day.year, start_day.month + 1, 1)
        return next_month_start - timedelta(days=1)

    period_b_start_default = last_month_start.isoformat()
    period_b_end_default = last_month_end.isoformat()

    prev_year_start = date(last_month_start.year - 1, last_month_start.month, 1)
    prev_year_end = _month_end(prev_year_start)

    period_a_start_default = prev_year_start.isoformat()
    period_a_end_default = prev_year_end.isoformat()

    if not requested_start:
        requested_start = period_a_start_default
    if not requested_end:
        requested_end = period_a_end_default
    if not requested_start2:
        requested_start2 = period_b_start_default
    if not requested_end2:
        requested_end2 = period_b_end_default

date_start, date_end, _default_start_date, _default_end_date = cc.resolve_date_range(
    database,
    orgsite_id=ORGSITE_ID,
    start_date=requested_start,
    end_date=requested_end,
)

date_start2, date_end2, _default_start_date2, _default_end_date2 = cc.resolve_date_range(
    database,
    orgsite_id=ORGSITE_ID,
    start_date=requested_start2,
    end_date=requested_end2,
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
    web_season_report.main_web_page(database)
elif what == cc.WHAT_SUMMARY_FREQUENCIES:
    web_season_report.season_frequencies_report(
        database,
        dow_parameter=dow_parameter,
        pages_back=pages_back,
        start_date=date_start,
        end_date=date_end,
    )
elif what == cc.WHAT_COMPARE_RANGES:
    web_compare_ranges.compare_ranges(
        database,
        params=params,
        pages_back=pages_back,
        start_date_a=date_start,
        end_date_a=date_end,
        dow_a=dow_parameter,
        start_date_b=date_start2,
        end_date_b=date_end2,
        dow_b=dow_parameter2,
        # query_params=compare_query_params,
    )
elif what == cc.WHAT_TAGS_LOST:
    web_tags_report.tags_report(database)
elif what == cc.WHAT_ONE_DAY:
    one_day_tags_report(
        database,
        orgsite_id=ORGSITE_ID,
        whatday=params.start_date,
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
    web_period_summaries.daterange_summary(
        database, what, start_date=date_start, end_date=date_end, pages_back=pages_back
    )
elif what == cc.WHAT_ESTIMATE_VERBOSE:
    web_est_wrapper()

else:
    cc.error_out(f"Unknown request: {ut.untaint(what)}")
    sys.exit(1)


cc.webpage_footer(database, time.perf_counter() - start_time)
