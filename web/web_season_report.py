#!/usr/bin/env python3
"""TagTracker whole-season overview report.

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

# import html
import sqlite3
from datetime import date
from functools import lru_cache
import common.tt_util as ut
import web_common as cc
import datacolors as dc
import web_histogram
from web.web_base_config import HIST_FIXED_Y_AXIS_DURATION
from web_daterange_selector import build_date_dow_filter_widget, DateDowSelection
from web.web_histogram_data import ArrivalDepartureMatrix
import common.tt_dbutil as db
from common.tt_time import VTime
from common.tt_daysummary import DayTotals

try:
    from common.commuter_hump import CommuterHumpAnalyzer
except ImportError:  # pragma: no cover - optional dependency
    CommuterHumpAnalyzer = None

BLOCK_XY_BOTTOM_COLOR = dc.Color((252, 252, 248)).html_color
BLOCK_X_TOP_COLOR = "red"
BLOCK_Y_TOP_COLOR = "royalblue"
BLOCK_NORMAL_MARKER = chr(0x25A0)
BLOCK_HIGHLIGHT_MARKER = chr(0x2B24)


def season_frequencies_report(
    ttdb: sqlite3.Connection,
    params: cc.ReportParameters,*,
    restrict_to_single_day: bool = False,
):
    """Web page showing histograms of visit frequency distributions.

    If restrict_to_single_day is set True, then this shows a single day
    without option to change the day, filter parameters, etc.
    """

    orgsite_id = 1  # FIXME: orgsite_id hardcoded
    title_bit = ""

    dow_parameter = params.dow
    pages_back = params.pages_back
    start_date = params.start_date
    end_date = params.end_date

    # Fetch date range limits from the database
    db_start_date, db_end_date = db.fetch_date_range_limits(
        ttdb,
        orgsite_id=orgsite_id,
    )
    if not db_start_date or not db_end_date:
        print(f"No data found for {orgsite_id=}")
        return

    requested_start = "" if start_date in ("", "0000-00-00") else start_date
    requested_end = "" if end_date in ("", "9999-99-99") else end_date

    start_date, end_date, _default_start, _default_end = cc.resolve_date_range(
        ttdb,
        start_date=requested_start,
        end_date=requested_end,
        db_limits=(db_start_date, db_end_date),
    )
    if restrict_to_single_day:
        end_date = start_date
        title_bit = ""
    else:
        title_bit = title_bit or ""
    table_vars = (
        (
            "duration",
            "Visit duration",
            "Average visit durations",
            "mediumseagreen",
        ),
        (
            "time_in",
            "Arrivals",
            "Average number of visits by arrival times",
            "lightcoral",
        ),
        (
            "time_out",
            "Departures",
            "Average number of visits by departure times",
            "lightskyblue",
        ),
    )
    back_button = f"{cc.main_and_back_buttons(pages_back)}<p></p>"

    if restrict_to_single_day:
        title = cc.titleize(f"Graphs for {start_date}")
    else:
        title = cc.titleize(f"Graphs for {start_date} to {end_date}")
        # if title_bit:
        #     h1 = f"{h1} for {title_bit}"
    print(title)
    print(back_button)

    if restrict_to_single_day:
        normalized_dow = ""
    else:
        self_url = cc.old_selfref(
            what=cc.WHAT_SUMMARY_FREQUENCIES,
            qdow=dow_parameter,
            start_date=start_date,
            end_date=end_date,
            pages_back=cc.increment_pages_back(pages_back),
        )
        filter_widget = build_date_dow_filter_widget(
            self_url,
            start_date=start_date,
            end_date=end_date,
            selected_dow=dow_parameter,
        )
        normalized_dow = filter_widget.selection.dow_value

        if not title_bit:
            title_bit = filter_widget.title_fragment()

        print(filter_widget.html)
        print("<br>")

    dow_parameter = "" if restrict_to_single_day else normalized_dow

    if not title_bit and not restrict_to_single_day:
        title_bit = "all days of the week"

    activity_title = "Activity"
    if title_bit:
        activity_title = f"{activity_title} ({title_bit})"
    activity_title = f"<h2>{activity_title}</h2>"
    activity_subtitle = (
        "Activity (averaged across {days} - red=bikes in, blue=bikes out)"
    )
    print(
        web_histogram.activity_hist_table(
            ttdb,
            orgsite_id=orgsite_id,
            days_of_week=dow_parameter,
            title=activity_title,
            subtitle=activity_subtitle,
            start_date=start_date,
            end_date=end_date,
        )
    )
    print("<br><br>")

    fullness_title = "Max bikes on-site"
    if title_bit:
        fullness_title = f"{fullness_title} ({title_bit})"
    fullness_title = f"<h2>{fullness_title}</h2>"
    fullness_subtitle = "Mean of max bikes on-site"
    print(
        web_histogram.fullness_hist_table(
            ttdb,
            orgsite_id=orgsite_id,
            days_of_week=dow_parameter,
            title=fullness_title,
            subtitle=fullness_subtitle,
            start_date=start_date,
            end_date=end_date,
        )
    )
    print("<br><br>")

    for parameters in table_vars:
        column, title, subtitle, color = parameters
        title = f"{title} ({title_bit})" if title_bit else title
        title = f"<h2>{title}</h2>"
        fixed_max = HIST_FIXED_Y_AXIS_DURATION if column == "duration" else None
        print(
            web_histogram.times_hist_table(
                ttdb,
                query_column=column,
                days_of_week=dow_parameter,
                color=color,
                title=title,
                subtitle=subtitle,
                start_date=start_date,
                end_date=end_date,
                max_value=fixed_max,
            )
        )
        print("<br><br>")

    arrival_duration_title = "Arrival-duration visit density map</br>"
    if title_bit:
        arrival_duration_title = f"{arrival_duration_title} ({title_bit})"
    arrival_duration_title = f"<h2>{arrival_duration_title}</h2>"
    arrival_duration_subtitle = "Data colour is normalized by average of whole-matrix and per-column maximums, darker means more visits. Click on individual cells for exact values."

    print(
        web_histogram.arrival_duration_hist_table(
            ttdb,
            days_of_week=dow_parameter,
            start_date=start_date,
            end_date=end_date,
            title=arrival_duration_title,
            subtitle=arrival_duration_subtitle,
            show_counts=False,
            normalization_mode=ArrivalDepartureMatrix.NORMALIZATION_BLEND,
            min_arrival_threshold="07:00",
            max_duration_threshold="12:30",
        )
    )
    print("<br><br>")
    print(back_button)


def totals_table(conn: sqlite3.Connection):
    """Quick summary table of YTD and daily totals."""

    # Function to format a single value
    def _p(val) -> str:
        """Format a single value."""
        if isinstance(val, int):
            return f"{val:,}"
        elif isinstance(val, float):
            return f"{val:,.1f}"
        elif isinstance(val, str):
            return f"{val:>}"
        else:
            return "-"

    def _display_default(val):
        return "" if val is None else val

    def _display_hours_open(hours_open):
        if hours_open:
            return VTime(hours_open * 60, allow_large=True)
        return ""

    def _display_average(val):
        if val is None:
            return ""
        return round(val)

    def format_percent_change(current, previous) -> str:
        """Return formatted percent change, or '-' if not computable."""
        if current is None or previous is None:
            return "-"
        if not isinstance(current, (int, float)) or not isinstance(
            previous, (int, float)
        ):
            return "-"
        if abs(previous) < 1e-9:
            return "0.0%" if abs(current) < 1e-9 else "-"
        change = (current - previous) / previous * 100
        change = round(change, 1)
        if change == 0:
            return "0.0%"
        return f"{change:+.1f}%"

    def fetch_totals(start_iso: str, end_iso: str) -> db.MultiDayTotals:
        """Fetch totals between two ISO-formatted dates (inclusive)."""
        if not start_iso or not end_iso:
            return db.MultiDayTotals()
        ordered_start, ordered_end = sorted((start_iso, end_iso))
        return db.MultiDayTotals.fetch_from_db(
            conn=conn,
            orgsite_id=1,
            start_date=ordered_start,
            end_date=ordered_end,
        )

    def totals_attr(name: str):
        return lambda totals, attr=name: getattr(totals, attr, None)

    def iso_date(value) -> str:
        if isinstance(value, date):
            return value.isoformat()
        return value or ""

    @lru_cache(maxsize=32)
    def commuter_mean_per_day(start_iso: str, end_iso: str):
        if not conn or not start_iso or not end_iso:
            return None
        if CommuterHumpAnalyzer is None:
            return None
        if start_iso > end_iso:
            start_iso, end_iso = end_iso, start_iso
        try:
            analyzer = CommuterHumpAnalyzer(
                db_path=conn,
                start_date=start_iso,
                end_date=end_iso,
                days_of_week=(1, 2, 3, 4, 5, 6, 7),
            ).run()
        except Exception:
            return None
        if getattr(analyzer, "error", None):
            return None
        mean = getattr(analyzer, "mean_commuter_per_day", None)
        if mean is None:
            return None
        try:
            mean_value = float(mean)
        except (TypeError, ValueError):
            return None
        if mean_value != mean_value:
            return None
        return mean_value

    def attach_commuter_metric(totals_obj, start_val, end_val):
        if not totals_obj:
            return
        start_iso = iso_date(start_val)
        end_iso = iso_date(end_val)
        if not start_iso or not end_iso:
            setattr(totals_obj, "commuter_mean_per_day", None)
            return
        ordered_start, ordered_end = sorted((start_iso, end_iso))
        setattr(
            totals_obj,
            "commuter_mean_per_day",
            commuter_mean_per_day(ordered_start, ordered_end),
        )

    today_iso = ut.date_str("today")
    selected_year_str = today_iso[:4]
    day_totals = {}

    # Fetching day totals for each day
    for i in range(6, -1, -1):  # Collect in reverse order
        d = ut.date_offset(today_iso, -i)
        day_totals[d] = db.MultiDayTotals.fetch_from_db(
            conn=conn, orgsite_id=1, start_date=d, end_date=d
        )

    day_keys = list(day_totals.keys())
    display_day_keys = day_keys[2:] if len(day_keys) > 2 else day_keys

    today_remaining_combined = 0
    # Track bikes currently onsite today so "Bikes left" can exclude them from current-period totals.
    today_totals = day_totals.get(today_iso)
    if today_totals:
        today_remaining_value = getattr(today_totals, "total_remaining_combined", 0)
        if today_remaining_value:
            today_remaining_combined = today_remaining_value

    ytd_start_iso, ytd_end_iso = DateDowSelection.date_range_for(
        DateDowSelection.RANGE_YTD,
    )
    ytd_totals = fetch_totals(ytd_start_iso, ytd_end_iso)

    prior_ytd_start_iso, prior_ytd_end_iso = DateDowSelection.date_range_for(
        DateDowSelection.RANGE_YTD_PRIOR_YEAR,
    )
    prior_ytd_totals = fetch_totals(prior_ytd_start_iso, prior_ytd_end_iso)

    current_12mo_start_iso, current_12mo_end_iso = DateDowSelection.date_range_for(
        DateDowSelection.RANGE_LAST_12MONTHS,
    )
    current_12mo_totals = fetch_totals(current_12mo_start_iso, current_12mo_end_iso)

    prev_12mo_start_iso, prev_12mo_end_iso = DateDowSelection.date_range_for(
        DateDowSelection.RANGE_LAST_12MONTHS_PRIOR_YEAR,
    )
    prev_12mo_totals = fetch_totals(prev_12mo_start_iso, prev_12mo_end_iso)

    ytd_summary_link = cc.old_selfref(
        what=cc.WHAT_DATERANGE,
        start_date=ytd_start_iso,
        end_date=ytd_end_iso,
        pages_back=1,
    )
    prior_ytd_compare_link = cc.old_selfref(
        what=cc.WHAT_COMPARE_RANGES,
        start_date=prior_ytd_start_iso,
        end_date=prior_ytd_end_iso,
        start_date2=ytd_start_iso,
        end_date2=ytd_end_iso,
        pages_back=1,
    )
    prior_12mo_compare_link = cc.old_selfref(
        what=cc.WHAT_COMPARE_RANGES,
        start_date=prev_12mo_start_iso,
        end_date=prev_12mo_end_iso,
        start_date2=current_12mo_start_iso,
        end_date2=current_12mo_end_iso,
        pages_back=1,
    )

    attach_commuter_metric(ytd_totals, ytd_start_iso, ytd_end_iso)
    attach_commuter_metric(prior_ytd_totals, prior_ytd_start_iso, prior_ytd_end_iso)
    attach_commuter_metric(
        current_12mo_totals, current_12mo_start_iso, current_12mo_end_iso
    )
    attach_commuter_metric(prev_12mo_totals, prev_12mo_start_iso, prev_12mo_end_iso)
    for key in display_day_keys:
        attach_commuter_metric(day_totals[key], key, key)

    most_parked_link = cc.old_selfref(
        what=cc.WHAT_ONE_DAY, start_date=ytd_totals.max_parked_combined_date
    )
    fullest_link = cc.old_selfref(
        what=cc.WHAT_ONE_DAY, start_date=ytd_totals.max_fullest_combined_date
    )

    row_defs = [
        {
            "label": "Days open",
            "row_class": "",
            "value_fn": totals_attr("total_days_open"),
            "day_value_fn": totals_attr("total_days_open"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "Hours open",
            "row_class": "class='heavy-bottom'",
            "value_fn": totals_attr("total_hours_open"),
            "day_value_fn": totals_attr("total_hours_open"),
            "display_fn": _display_hours_open,
            "percent": True,
        },
        {
            "label": "Visits",
            "row_class": "",
            "value_fn": totals_attr("total_parked_combined"),
            "day_value_fn": totals_attr("total_parked_combined"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "&nbsp;&nbsp;&nbsp;Regular bikes",
            "row_class": "",
            "value_fn": totals_attr("total_parked_regular"),
            "day_value_fn": totals_attr("total_parked_regular"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "&nbsp;&nbsp;&nbsp;Oversize bikes",
            "row_class": "",
            "value_fn": totals_attr("total_parked_oversize"),
            "day_value_fn": totals_attr("total_parked_oversize"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": (
                f"Visits per day (max, <a href='{most_parked_link}'>{ytd_totals.max_parked_combined_date}</a>)"
            ),
            "row_class": "",
            "value_fn": totals_attr("max_parked_combined"),
            "display_fn": _display_default,
            "percent": None,
        },
        {
            "label": "Visits per day (mean)",
            "row_class": "",
            "value_fn": lambda totals: (
                totals.total_parked_combined / totals.total_days_open
                if totals.total_days_open
                else None
            ),
            "display_fn": _display_average,
            "percent": True,
        },
        {
            "label": "&nbsp;&nbsp;&nbsp;Commuter portion (est.)",
            "row_class": "class='heavy-bottom'",
            "value_fn": lambda totals: getattr(totals, "commuter_mean_per_day", None),
            "day_value_fn": lambda totals: getattr(
                totals, "commuter_mean_per_day", None
            ),
            "display_fn": _display_average,
            "percent": True,
            "blank_last_day_value": True,
        },
        {
            "label": (
                f"Bikes on-site (max, <a href='{fullest_link}'>{ytd_totals.max_fullest_combined_date}</a>)"
            ),
            "row_class": "",
            "value_fn": totals_attr("max_fullest_combined"),
            "day_value_fn": totals_attr("max_fullest_combined"),
            "display_fn": _display_default,
            "percent": None,
        },
        {
            "label": "Bikes on-site (left)",
            "row_class": "class='heavy-bottom'",
            "value_fn": totals_attr("total_remaining_combined"),
            "day_value_fn": totals_attr("total_remaining_combined"),
            "display_fn": _display_default,
            "percent": True,
            "subtract_today_from_current": True,
        },
        {
            "label": "Registrations",
            "row_class": "class='heavy-bottom'",
            "value_fn": totals_attr("total_bikes_registered"),
            "day_value_fn": totals_attr("total_bikes_registered"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "Precipitation (mm)",
            "row_class": "",
            "value_fn": totals_attr("total_precipitation"),
            "day_value_fn": totals_attr("total_precipitation"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "Max temperature",
            "row_class": "",
            "value_fn": totals_attr("max_max_temperature"),
            "day_value_fn": totals_attr("max_max_temperature"),
            "display_fn": _display_default,
            "percent": None,
        },
    ]

    print("")
    print("<table class='general_table'>")

    # Table header
    header_html = (
        "<tr><th rowspan='2' class='heavy-right' style='text-align:center;'>Summary</th>"
        "<th colspan=3 class='heavy-right' style='text-align:center;'>This year</th>"
        "<th colspan=5>Recent days</th></tr>"
        # f"  <tr><th>{selected_year_str} Summary</th>"
        f"<th style='text-align:center;'><a href='{ytd_summary_link}'>"
        f"YTD<br>{selected_year_str}</a></th>"
        f"<th style='text-align:center'><a href='{prior_ytd_compare_link}'>%Δ<br>YTD</a></th>"
        "<th style='text-align:center;border-right: 2px solid gray;'>"
        f"<a href='{prior_12mo_compare_link}'>%Δ<br>12mo</a></th>"
    )
    for day in display_day_keys:
        if day == today_iso:
            daylabel = "Today"
            daylink = cc.old_selfref(what=cc.WHAT_ONE_DAY, start_date="today")
        else:
            daylabel = day
            daylink = cc.old_selfref(what=cc.WHAT_ONE_DAY, start_date=day)

        header_html += (
            f"<th><a href='{daylink}'>{daylabel}</a><br>{ut.dow_str(day)}</th>"
        )
    header_html += "</tr>"
    print(header_html)

    # Table rows
    def html_row(label, row_class, ytd_value, pct_ytd, pct_12mo, day_values):
        """Build HTML for a table row."""
        row_html = (
            f"<tr {row_class}><td class='heavy-right'style='text-align:left;'>{label}</td>"
            f"<td style='text-align:right;'>{_p(ytd_value)}</td>"
            f"<td style='text-align:right'>{_p(pct_ytd)}</td>"
            f"<td class='heavy-right' style='text-align:right;'>{_p(pct_12mo)}</td>"
        )
        for day_value in day_values:
            row_html += f"<td style='text-align:right'>{_p(day_value)}</td>"
        row_html += "</tr>\n"
        return row_html

    def _subtract_today_from_current(value):
        if value is None:
            return None
        adjusted_value = value - today_remaining_combined
        return adjusted_value if adjusted_value > 0 else 0

    for spec in row_defs:
        label = spec["label"](ytd_totals) if callable(spec["label"]) else spec["label"]
        value_fn = spec["value_fn"]
        display_fn = spec.get("display_fn", _display_default)
        day_display_fn = spec.get("day_display_fn", display_fn)
        subtract_today_flag = spec.get("subtract_today_from_current", False)

        ytd_raw = value_fn(ytd_totals)
        ytd_adjusted = (
            _subtract_today_from_current(ytd_raw) if subtract_today_flag else ytd_raw
        )
        ytd_display = display_fn(ytd_adjusted)

        percent_setting = spec.get("percent", True)
        if percent_setting is True:
            prior_raw = value_fn(prior_ytd_totals)
            current_12_raw = value_fn(current_12mo_totals)
            prev_12_raw = value_fn(prev_12mo_totals)
            current_12_adjusted = (
                _subtract_today_from_current(current_12_raw)
                if subtract_today_flag
                else current_12_raw
            )
            pct_ytd = format_percent_change(ytd_adjusted, prior_raw)
            pct_12mo = format_percent_change(current_12_adjusted, prev_12_raw)
        elif percent_setting is None:
            pct_ytd = pct_12mo = ""
        else:
            pct_ytd = pct_12mo = "-"

        if spec.get("day_value_fn"):
            day_values = []
            day_value_fn = spec["day_value_fn"]
            for key in display_day_keys:
                day_raw = day_value_fn(day_totals[key])
                day_display = day_display_fn(day_raw)
                day_values.append(day_display)
            if spec.get("blank_last_day_value") and day_values:
                day_values[-1] = ""
        else:
            day_values = ["-" for _ in display_day_keys]

        print(
            html_row(
                label, spec["row_class"], ytd_display, pct_ytd, pct_12mo, day_values
            )
        )

    total_columns = 4 + len(display_day_keys)
    print(
        f"<tr><td colspan='{total_columns}'>"
        f"<i>%ΔYTD compares <a href='{prior_ytd_compare_link}'>YTD to same period last year</a>; "
        f"%Δ12mo compares <a href='{prior_12mo_compare_link}'>most recent 12 months to 12 months before that</a>."
        "</i></td></tr>"
    )

    print("</table>")


def main_web_page(ttdb: sqlite3.Connection):
    """Print super-brief summary report of the current year."""

    detail_link = cc.old_selfref(what=cc.WHAT_DETAIL, pages_back=1)
    period_detail_link = cc.old_selfref(what=cc.WHAT_DATERANGE_DETAIL, pages_back=1)
    blocks_link = cc.old_selfref(what=cc.WHAT_BLOCKS, pages_back=1)
    tags_link = cc.old_selfref(what=cc.WHAT_TAGS_LOST, pages_back=1)
    today_link = cc.old_selfref(what=cc.WHAT_ONE_DAY, start_date="today")
    summaries_link = cc.old_selfref(what=cc.WHAT_DATERANGE)
    compare_link = cc.old_selfref(what=cc.WHAT_COMPARE_RANGES, pages_back=1)
    download_csv_link = cc.old_make_url("tt_download", what=cc.WHAT_DOWNLOAD_CSV)
    download_db_link = cc.old_make_url("tt_download", what=cc.WHAT_DOWNLOAD_DB)

    print(f"{cc.titleize('')}<br>")
    print("<div style='display:inline-block'>")
    print("<div style='margin-bottom: 10px; display:inline-block; margin-right:5em'>")

    # today_totals = cc.MultiDayTotals.fetch_from_db(conn=ttdb,orgsite_id=1,start_date="2024-06-03",end_date="2024-06-03")
    # print(f"{today_totals=}")
    totals_table(conn=ttdb)
    print("</div>")
    print("<div style='display:inline-block; vertical-align: top;'>")
    # mini_freq_tables(ttdb)
    print("</div>")
    print("</div>")
    print("<br>")

    print(
        f"""
        <br>
        <button onclick="window.location.href='{today_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Single Day<br>Detail</b></button>
        &nbsp;&nbsp;
        """
    )
    print(
        f"""
        <button onclick="window.location.href='{detail_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Day by Day<br>Summaries</b></button>
        &nbsp;&nbsp;
          """
    )
    print(
        f"""
        <button onclick="window.location.href='{blocks_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Day by Day<br>Activity</b></button>
        &nbsp;&nbsp;
        """
    )
    print("<br><br>")
    print(
        f"""
        <button onclick="window.location.href='{period_detail_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Date Range<br>Detail</b></button>
        &nbsp;&nbsp;
          """
    )
    print(
        f"""
        <button onclick="window.location.href='{summaries_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Date Range<br>Summaries</b></button>
        &nbsp;&nbsp;
          """
    )
    print(
        f"""
        <button onclick="window.location.href='{cc.old_selfref(cc.WHAT_SUMMARY_FREQUENCIES)}'"
            style="padding: 10px; display: inline-block;">
          <b>Date Range<br>Graphs</b></button>
        &nbsp;&nbsp;
        """
    )
    print(
        f"""
        <button onclick="window.location.href='{compare_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Date Range<br>Comparison</b></button>
        &nbsp;&nbsp;
        """
    )
    print("<br><br>")  # "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;")
    print(
        f"""
        <button onclick="window.location.href='{tags_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Bike Tag<br>Inventory</b></button>
        &nbsp;&nbsp;
          """
    )
    print(
        f"""
    <button onclick="window.location.href='{download_csv_link}'"
        style="padding: 10px; display: inline-block; background-color: #ddd; border: 1px solid #aaa;">
      <b>CSV Data<br>Download</b></button>
    &nbsp;&nbsp;
    <button onclick="window.location.href='{download_db_link}'"
        style="padding: 10px; display: inline-block; background-color: #ddd; border: 1px solid #aaa;">
      <b>Full Database<br>Download</b></button>
    <br><br>
      """
    )


def season_detail(
    ttdb: sqlite3.Connection,
    params:cc.ReportParameters,
):
    """A summary in which each row is one day."""

    requested_start = "" if params.start_date in ("", "0000-00-00") else params.start_date
    requested_end = "" if params.end_date in ("", "9999-99-99") else params.end_date

    db_start_date, db_end_date = db.fetch_date_range_limits(
        ttdb,
        orgsite_id=1,
    )

    params.start_date, params.end_date, _default_start, _default_end = cc.resolve_date_range(
        ttdb,
        start_date=requested_start,
        end_date=requested_end,
        db_limits=(db_start_date, db_end_date),
    )

    sort_by = params.sort_by if params.sort_by else cc.SORT_DATE
    sort_direction = params.sort_direction if params.sort_direction else cc.ORDER_REVERSE

    filter_base_url = cc.old_selfref(
        cc.WHAT_DETAIL,
        qsort=sort_by,
        qdir=sort_direction,
        qdow=params.dow,
        start_date=params.start_date,
        end_date=params.end_date,
        pages_back=cc.increment_pages_back(params.pages_back),
    )
    filter_widget = build_date_dow_filter_widget(
        filter_base_url,
        start_date=params.start_date,
        end_date=params.end_date,
        selected_dow=params.dow,
    )
    params.dow = filter_widget.selection.dow_value
    filter_description = filter_widget.description()

    all_days = cc.get_days_data(
        ttdb=ttdb, min_date=params.start_date, max_date=params.end_date
    )  # FIXME: needs to use orgsite_id
    if params.dow:
        allowed_dows = {
            int(token)
            for token in params.dow.split(",")
            if token and token.isdigit()
        }
        all_days = [
            day for day in all_days if getattr(day, "weekday", None) in allowed_dows
        ]

    # Sort the all_days ldataccording to the sort parameter
    if sort_direction == cc.ORDER_FORWARD:
        other_direction = cc.ORDER_REVERSE
        direction_msg = ""
    elif sort_direction == cc.ORDER_REVERSE:
        other_direction = cc.ORDER_FORWARD
        direction_msg = " (descending)"
    else:
        other_direction = cc.ORDER_REVERSE
        direction_msg = f" (sort direction '{sort_direction}' unrecognized)"
    reverse_sort = sort_direction == cc.ORDER_REVERSE

    all_days = sorted(all_days, reverse=reverse_sort, key=lambda x: x.date)
    if sort_by == cc.SORT_DATE:
        sort_msg = f"date{direction_msg}"
    elif sort_by == cc.SORT_DAY:
        all_days = sorted(all_days, reverse=reverse_sort, key=lambda x: x.weekday)
        sort_msg = f"day of week{direction_msg}"
    elif sort_by == cc.SORT_PARKED:
        all_days = sorted(
            all_days, reverse=reverse_sort, key=lambda x: x.num_parked_combined
        )
        sort_msg = f"bikes parked{direction_msg}"
    elif sort_by == cc.SORT_FULLNESS:
        all_days = sorted(
            all_days, reverse=reverse_sort, key=lambda x: x.num_fullest_combined
        )
        sort_msg = f"most bikes at once{direction_msg}"
    elif sort_by == cc.SORT_LEFTOVERS:
        all_days = sorted(
            all_days, reverse=reverse_sort, key=lambda x: x.num_remaining_combined
        )
        sort_msg = f"bikes left onsite{direction_msg}"
    elif sort_by == cc.SORT_PRECIPITATAION:
        all_days = sorted(
            all_days,
            reverse=reverse_sort,
            key=lambda x: (x.precipitation if x.precipitation else 0),
        )
        sort_msg = f"precipitation{direction_msg}"
    elif sort_by == cc.SORT_TEMPERATURE:
        all_days = sorted(
            all_days,
            reverse=reverse_sort,
            key=lambda x: (x.max_temperature if x.max_temperature else -999),
        )
        sort_msg = f"temperature{direction_msg}"
    else:
        all_days = sorted(all_days, key=lambda x: x.tag)
        sort_msg = f"bike tag (sort parameter '{sort_by}' unrecognized)"
    sort_msg = f"Daily summaries, sorted by {sort_msg} "
    if filter_description:
        sort_msg = f"{sort_msg}{filter_description}"

    max_parked_value = (
        max((day.num_parked_combined or 0) for day in all_days) if all_days else 0
    )
    max_full_value = (
        max((day.num_fullest_combined or 0) for day in all_days) if all_days else 0
    )
    max_precip_value = 0.0
    if all_days:
        precip_values = [
            day.precipitation for day in all_days if day.precipitation is not None
        ]
        if precip_values:
            max_precip_value = max(precip_values) or 0.0

    # Set up colour maps for shading cell backgrounds
    max_parked_colour = dc.Dimension(interpolation_exponent=2)
    max_parked_colour.add_config(0, "white")
    if max_parked_value:
        max_parked_colour.add_config(max_parked_value, "green")

    max_full_colour = dc.Dimension(interpolation_exponent=2)
    max_full_colour.add_config(0, "white")
    if max_full_value:
        max_full_colour.add_config(max_full_value, "teal")

    max_left_colour = dc.Dimension()
    max_left_colour.add_config(0, "white")
    max_left_colour.add_config(10, "red")

    max_temp_colour = dc.Dimension()
    max_temp_colour.add_config(11, "beige")  # 'rgb(255, 255, 224)')
    max_temp_colour.add_config(35, "orange")
    max_temp_colour.add_config(0, "azure")

    max_precip_colour = dc.Dimension(interpolation_exponent=1)
    max_precip_colour.add_config(0, "white")
    if max_precip_value not in (None, 0):
        max_precip_colour.add_config(max_precip_value, "azure")

    print(f"{cc.titleize('Daily summaries', filter_widget.description())}")
    print(f"{cc.main_and_back_buttons(params.pages_back)}<br>")
    print("<br>")
    print(filter_widget.html)
    print("<br><br>")

    sort_date_link = cc.old_selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_DATE,
        qdir=other_direction,
        qdow=params.dow,
        start_date=params.start_date,
        end_date=params.end_date,
        pages_back=cc.increment_pages_back(params.pages_back),
    )
    sort_parked_link = cc.old_selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_PARKED,
        qdir=other_direction,
        qdow=params.dow,
        start_date=params.start_date,
        end_date=params.end_date,
        pages_back=cc.increment_pages_back(params.pages_back),
    )
    sort_fullness_link = cc.old_selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_FULLNESS,
        qdir=other_direction,
        qdow=params.dow,
        start_date=params.start_date,
        end_date=params.end_date,
        pages_back=cc.increment_pages_back(params.pages_back),
    )
    sort_leftovers_link = cc.old_selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_LEFTOVERS,
        qdir=other_direction,
        qdow=params.dow,
        start_date=params.start_date,
        end_date=params.end_date,
        pages_back=cc.increment_pages_back(params.pages_back),
    )
    sort_precipitation_link = cc.old_selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_PRECIPITATAION,
        qdir=other_direction,
        qdow=params.dow,
        start_date=params.start_date,
        end_date=params.end_date,
        pages_back=cc.increment_pages_back(params.pages_back),
    )
    sort_temperature_link = cc.old_selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_TEMPERATURE,
        qdir=other_direction,
        qdow=params.dow,
        start_date=params.start_date,
        end_date=params.end_date,
        pages_back=cc.increment_pages_back(params.pages_back),
    )
    # mismatches_link = cc.old_selfref(cc.WHAT_MISMATCH)

    print("<table class='general_table'>")
    print(f"<tr><th colspan=12><br>{sort_msg}<br>&nbsp;</th></tr>")
    print("<style>td {text-align: right;}</style>")
    print(
        "<tr>"
        "<th colspan=2>Date</th>"
        "<th colspan=2>Hours</th>"
        "<th colspan=3>Bikes parked</th>"
        f"<th rowspan=2><a href={sort_leftovers_link}>Bikes<br />left<br />onsite</a></th>"
        f"<th rowspan=2><a href={sort_fullness_link}>Max<br />bikes</a></th>"
        # "<th rowspan=2>Bike-<br />hours</th>"
        # "<th rowspan=2>Bike-<br />hours<br />per hr</th>"
        "<th rowspan=2>Regns</th>"
        "<th colspan=2>Weather</th>"
        "</tr>"
    )
    print(
        "<tr>"
        f"<th><a href={sort_date_link}>Date</a></th>"
        f"<th>Day</th>"
        "<th>Open</th><th>Close</th>"
        f"<th><a href={sort_parked_link}>All<br>bikes</a></th>"
        "<th style='font-weight:normal'>Ovrsz<br>bikes</th>"
        "<th style='font-weight:normal'>Reglr<br>bikes</th>"
        f"<th><a href={sort_temperature_link}>Max<br />temp</a></th>"
        f"<th><a href={sort_precipitation_link}>Rain</a></th>"
        "</tr>"
    )

    for row in all_days:
        row: DayTotals
        date_link = cc.old_selfref(what=cc.WHAT_ONE_DAY, start_date=row.date)
        reg_str = "" if row.bikes_registered is None else f"{row.bikes_registered}"
        temp_str = "" if row.max_temperature is None else f"{row.max_temperature:0.1f}"
        precip_str = "" if row.precipitation is None else f"{row.precipitation:0.1f}"

        print(
            f"<tr>"
            f"<td><a href='{date_link}'>{row.date}</a></td>"
            f"<td style='text-align:left'>{ut.date_str(row.date,dow_str_len=3)}</td>"
            f"<td>{row.time_open}</td><td>{row.time_closed}</td>"
            f"<td style='{max_parked_colour.css_bg_fg(row.num_parked_combined)}'>{row.num_parked_combined}</td>"
            f"<td>{row.num_parked_regular}</td>"
            f"<td>{row.num_parked_oversize}</td>"
            f"<td style='{max_left_colour.css_bg_fg(row.num_remaining_combined)}'>{row.num_remaining_combined}</td>"
            f"<td style='{max_full_colour.css_bg_fg(row.num_fullest_combined)}'>{row.num_fullest_combined}</td>"
            f"<td>{reg_str}</td>"
            f"<td style='{max_temp_colour.css_bg_fg(row.max_temperature)}'>{temp_str}</td>"
            f"<td style='{max_precip_colour.css_bg_fg(row.precipitation)}'>{precip_str}</td>"
            "</tr>"
        )
    print(" </table>")


def create_blocks_color_maps(block_maxes: cc.BlocksSummary) -> tuple:
    """Create color maps for the blocks table.

    Returns
        inout_colors,
        fullness_colors,
    """
    # Set up color maps
    inout_colors = dc.MultiDimension(blend_method=dc.BLEND_MULTIPLICATIVE)
    d1 = inout_colors.add_dimension(interpolation_exponent=0.82, label="Bikes parked")
    d1.add_config(0, BLOCK_XY_BOTTOM_COLOR)
    d1.add_config(block_maxes.num_in, BLOCK_X_TOP_COLOR)
    d2 = inout_colors.add_dimension(interpolation_exponent=0.82, label="Bikes returned")
    d2.add_config(0, BLOCK_XY_BOTTOM_COLOR)
    d2.add_config(block_maxes.num_out, BLOCK_Y_TOP_COLOR)

    fullness_colors = dc.Dimension(interpolation_exponent=0.85, label="Bikes onsite")
    fullness_colors_list = [
        inout_colors.get_color(0, 0),
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
    for n, c in enumerate(fullness_colors_list):
        fullness_colors.add_config(
            n / (len(fullness_colors_list)) * (block_maxes.full), c
        )

    return inout_colors, fullness_colors
