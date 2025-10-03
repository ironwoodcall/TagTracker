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

import sqlite3
from datetime import date, timedelta
import common.tt_util as ut
import web_common as cc
import datacolors as dc
import web_histogram
from web_daterange_selector import generate_date_filter_form
import common.tt_dbutil as db
from common.tt_time import VTime
from common.tt_daysummary import DayTotals

BLOCK_XY_BOTTOM_COLOR = dc.Color((252, 252, 248)).html_color
BLOCK_X_TOP_COLOR = "red"
BLOCK_Y_TOP_COLOR = "royalblue"
BLOCK_NORMAL_MARKER = chr(0x25A0)
BLOCK_HIGHLIGHT_MARKER = chr(0x2B24)


def _freq_nav_buttons(pages_back, start_date: str = "", end_date: str = "") -> str:
    """Make nav buttons for the season-frequency report.

    Buttons will be "Mon", "Tue", "Wed", etc, "All days", "Weekdays",
    """
    buttons = f"{cc.main_and_back_buttons(pages_back)}&nbsp;&nbsp;&nbsp;"

    buttons += f"""
        <button type="button"
        onclick="window.location.href='{
            cc.selfref(
                what=cc.WHAT_SUMMARY_FREQUENCIES,
                start_date=start_date,
                end_date=end_date,
                pages_back=cc.increment_pages_back(pages_back),
                text_note=""
            )
            }';">All days</button>
            &nbsp;&nbsp;&nbsp;
                    """
    buttons += f"""
        <button type="button"
        onclick="window.location.href='{
            cc.selfref(
                what=cc.WHAT_SUMMARY_FREQUENCIES,
                start_date=start_date,
                end_date=end_date,
                qdow="1,2,3,4,5",
                pages_back=cc.increment_pages_back(pages_back),
                text_note="weekdays"
            )
            }';">Weekdays</button>
        """
    buttons += f"""
        <button type="button"
        onclick="window.location.href='{
            cc.selfref(
                what=cc.WHAT_SUMMARY_FREQUENCIES,
                start_date=start_date,
                end_date=end_date,
                qdow="6,7",
                pages_back=cc.increment_pages_back(pages_back),
                text_note="weekends"
            )
            }';">Weekends</button>
            &nbsp;&nbsp;&nbsp;
        """

    for d in range(1, 8):
        link = cc.selfref(
            what=cc.WHAT_SUMMARY_FREQUENCIES,
            start_date=start_date,
            end_date=end_date,
            qdow=d,
            pages_back=cc.increment_pages_back(pages_back),
            text_note=ut.dow_str(d, 10) + "s",
        )
        label = ut.dow_str(d, 3)
        buttons += f"""
            <button type="button"
            onclick="window.location.href='{link}';">{label}</button>
            """

    buttons += "<br><br>"

    return buttons


def season_frequencies_report(
    ttdb: sqlite3.Connection,
    dow_parameter: str = "",
    title_bit: str = "",
    pages_back: int = 0,
    start_date: str = "",
    end_date: str = "",
    restrict_to_single_day:bool = False,
):
    """Web page showing histograms of visit frequency distributions.

    If restrict_to_single_day is set True, then this shows a single day
    without option to change the day, filter parameters, etc.
    """

    orgsite_id = 1  # FIXME: orgsite_id hardcoded

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
        orgsite_id=orgsite_id,
        start_date=requested_start,
        end_date=requested_end,
        db_limits=(db_start_date, db_end_date),
    )
    if restrict_to_single_day:
        end_date = start_date
        title_bit = ""
    else:
        title_bit = title_bit if title_bit else "all days of the week"
    table_vars = (
        (
            "duration",
            "Length of visits",
            "Frequency distribution of lengths of visits",
            "teal",
        ),
        (
            "time_in",
            "When bikes arrived",
            "Frequency distribution of arrival times",
            "crimson",
        ),
        (
            "time_out",
            "When bikes departed",
            "Frequency distribution of departure times",
            "royalblue",
        ),
    )
    back_button = f"{cc.main_and_back_buttons(pages_back)}<p></p>"

    if restrict_to_single_day:
        h1 = f"Distribution of visits {start_date}"
    else:
        h1 = f"Distribution of visits {start_date} to {end_date}"
        h1 = f"{h1} for {title_bit}" if title_bit else h1
    print(f"<h1>{h1}</h1>")
    if restrict_to_single_day:
        print(back_button)
    else:
        print(_freq_nav_buttons(pages_back, start_date=start_date, end_date=end_date))
        self_url = cc.selfref(
            what=cc.WHAT_SUMMARY_FREQUENCIES,
            qdow=dow_parameter,
            start_date=start_date,
            end_date=end_date,
            pages_back=cc.increment_pages_back(pages_back),
        )
        print(
            generate_date_filter_form(
                self_url, default_start_date=start_date, default_end_date=end_date
            )
        )

    for parameters in table_vars:
        column, title, subtitle, color = parameters
        title = f"{title} ({title_bit})" if title_bit else title
        title = f"<h2>{title}</h2>"
        print(
            web_histogram.times_hist_table(
                ttdb,
                orgsite_id=orgsite_id,
                query_column=column,
                days_of_week=dow_parameter,
                color=color,
                title=title,
                subtitle=subtitle,
                start_date=start_date,
                end_date=end_date,
            )
        )
        print("<br><br>")
    print(back_button)


# def mini_freq_tables(ttdb: sqlite3.Connection):
#     table_vars = (
#         ("duration", "Visit length", "teal"),
#         ("time_in", "Time in", "crimson"),
#         ("time_out", "Time out", "royalblue"),
#     )
#     orgsite_id = 1 # hardcoded orgsite_id FIXME
#     for parameters in table_vars:
#         column, title, color = parameters
#         title = f"<a href='{cc.selfref(cc.WHAT_SUMMARY_FREQUENCIES)}'>{title}</a>"
#         print(
#             web_histogram.times_hist_table(
#                 ttdb,
#                 orgsite_id=orgsite_id,
#                 query_column=column,
#                 mini=True,
#                 color=color,
#                 title=title,
#             )
#         )
#         print("<br>")


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
        if not isinstance(current, (int, float)) or not isinstance(previous, (int, float)):
            return "-"
        if abs(previous) < 1e-9:
            return "0.0%" if abs(current) < 1e-9 else "-"
        change = (current - previous) / previous * 100
        change = round(change, 1)
        if change == 0:
            return "0.0%"
        return f"{change:+.1f}%"

    def subtract_year_safe(day: date) -> date:
        """Return the same calendar day in the prior year, clamping as needed."""
        target_year = day.year - 1
        day_num = day.day
        month_num = day.month
        while day_num > 0:
            try:
                return date(target_year, month_num, day_num)
            except ValueError:
                day_num -= 1
        return date(target_year, month_num, 1)

    def fetch_totals(start_day: date, end_day: date) -> db.MultiDayTotals:
        if start_day > end_day:
            start_day = end_day
        return db.MultiDayTotals.fetch_from_db(
            conn=conn,
            orgsite_id=1,
            start_date=start_day.isoformat(),
            end_date=end_day.isoformat(),
        )

    def totals_attr(name: str):
        return lambda totals, attr=name: getattr(totals, attr, None)

    today = ut.date_str("today")
    today_date = date.fromisoformat(today)
    selected_year = today_date.year
    selected_year_str = str(selected_year)
    day_totals = {}

    # Fetching day totals for each day
    for i in range(6, -1, -1):  # Collect in reverse order
        d = ut.date_offset(today, -i)
        day_totals[d] = db.MultiDayTotals.fetch_from_db(
            conn=conn, orgsite_id=1, start_date=d, end_date=d
        )

    day_keys = list(day_totals.keys())
    display_day_keys = day_keys[2:] if len(day_keys) > 2 else day_keys

    start_of_year = date(selected_year, 1, 1)

    # Fetch data for YTD
    ytd_totals = fetch_totals(start_of_year, today_date)

    one_year_ago = subtract_year_safe(today_date)
    prior_year_start = date(selected_year - 1, 1, 1)
    if prior_year_start > one_year_ago:
        prior_year_start = one_year_ago
    prior_ytd_totals = fetch_totals(prior_year_start, one_year_ago)

    current_12mo_start = one_year_ago + timedelta(days=1)
    if current_12mo_start > today_date:
        current_12mo_start = today_date
    current_12mo_totals = fetch_totals(current_12mo_start, today_date)

    prev_12mo_end = one_year_ago
    prev_12mo_start = subtract_year_safe(current_12mo_start)
    if prev_12mo_start > prev_12mo_end:
        prev_12mo_start = prev_12mo_end
    prev_12mo_totals = fetch_totals(prev_12mo_start, prev_12mo_end)

    most_parked_link = cc.selfref(
        what=cc.WHAT_ONE_DAY, qdate=ytd_totals.max_parked_combined_date
    )
    fullest_link = cc.selfref(
        what=cc.WHAT_ONE_DAY, qdate=ytd_totals.max_fullest_combined_date
    )

    row_defs = [
        {
            "label": "Total bikes parked (visits)",
            "value_fn": totals_attr("total_parked_combined"),
            "day_value_fn": totals_attr("total_parked_combined"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "&nbsp;&nbsp;&nbsp;Regular bikes parked",
            "value_fn": totals_attr("total_parked_regular"),
            "day_value_fn": totals_attr("total_parked_regular"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "&nbsp;&nbsp;&nbsp;Oversize bikes parked",
            "value_fn": totals_attr("total_parked_oversize"),
            "day_value_fn": totals_attr("total_parked_oversize"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "Average bikes / day",
            "value_fn": lambda totals: (
                totals.total_parked_combined / totals.total_days_open
                if totals.total_days_open
                else None
            ),
            "display_fn": _display_average,
            "percent": True,
        },
        {
            "label": "Total bike registrations",
            "value_fn": totals_attr("total_bikes_registered"),
            "day_value_fn": totals_attr("total_bikes_registered"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "Total days open",
            "value_fn": totals_attr("total_days_open"),
            "day_value_fn": totals_attr("total_days_open"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "Total hours open",
            "value_fn": totals_attr("total_hours_open"),
            "day_value_fn": totals_attr("total_hours_open"),
            "display_fn": _display_hours_open,
            "percent": True,
        },
        {
            "label": "Bikes left",
            "value_fn": totals_attr("total_remaining_combined"),
            "day_value_fn": totals_attr("total_remaining_combined"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": (
                f"Most bikes parked (<a href='{most_parked_link}'>{ytd_totals.max_parked_combined_date}</a>)"
            ),
            "value_fn": totals_attr("max_parked_combined"),
            "display_fn": _display_default,
            "percent": None,
        },
        {
            "label": (
                f"Most bikes at once (<a href='{fullest_link}'>{ytd_totals.max_fullest_combined_date}</a>)"
            ),
            "value_fn": totals_attr("max_fullest_combined"),
            "day_value_fn": totals_attr("max_fullest_combined"),
            "display_fn": _display_default,
            "percent": None,
        },
        {
            "label": "Total precipitation",
            "value_fn": totals_attr("total_precipitation"),
            "day_value_fn": totals_attr("total_precipitation"),
            "display_fn": _display_default,
            "percent": True,
        },
        {
            "label": "Max daily temperature",
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
        f"  <tr><th>{selected_year_str} Summary</th>"
        f"<th style='text-align:center;border-right: 2px solid gray;'>YTD<br>{selected_year_str}</th>"
        "<th style='text-align:center'>%Δ<br>YTD</th>"
        "<th style='text-align:center;border-right: 2px solid gray;'>%Δ<br>12mo</th>"
    )
    for day in display_day_keys:
        daylabel = "Today" if day == today else day
        daylink = cc.selfref(what=cc.WHAT_ONE_DAY, qdate=day)
        header_html += (
            f"<th><a href='{daylink}'>{daylabel}</a><br>{ut.dow_str(day)}</th>"
        )
    header_html += "</tr>"
    print(header_html)

    # Table rows
    def html_row(label, ytd_value, pct_ytd, pct_12mo, day_values):
        """Build HTML for a table row."""
        row_html = (
            f"<tr><td style='text-align:left'>{label}</td>"
            f"<td style='text-align:right;border-right: 2px solid gray;'>{_p(ytd_value)}</td>"
            f"<td style='text-align:right'>{_p(pct_ytd)}</td>"
            f"<td style='text-align:right;border-right: 2px solid gray;'>{_p(pct_12mo)}</td>"
        )
        for day_value in day_values:
            row_html += f"<td style='text-align:right'>{_p(day_value)}</td>"
        row_html += "</tr>\n"
        return row_html

    for spec in row_defs:
        label = spec["label"](ytd_totals) if callable(spec["label"]) else spec["label"]
        value_fn = spec["value_fn"]
        display_fn = spec.get("display_fn", _display_default)
        day_display_fn = spec.get("day_display_fn", display_fn)

        ytd_raw = value_fn(ytd_totals)
        ytd_display = display_fn(ytd_raw)

        percent_setting = spec.get("percent", True)
        if percent_setting is True:
            prior_raw = value_fn(prior_ytd_totals)
            current_12_raw = value_fn(current_12mo_totals)
            prev_12_raw = value_fn(prev_12mo_totals)
            pct_ytd = format_percent_change(ytd_raw, prior_raw)
            pct_12mo = format_percent_change(current_12_raw, prev_12_raw)
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
        else:
            day_values = ["-" for _ in display_day_keys]

        print(html_row(label, ytd_display, pct_ytd, pct_12mo, day_values))

    total_columns = 4 + len(display_day_keys)
    explanation_text = (
        "%Δ YTD compares this calendar year from Jan 1 through today, to the same period last year.  "
        "%Δ 12mo compares the 12 months prior to today, to the 12 months before that."
    )
    print(
        #f"<tr><td colspan='{total_columns}'>"
        #"<i>%Δ YTD compares this calendar year from Jan 1 through today, to the same period last year.</i></td></tr>"
        f"<tr><td colspan='{total_columns}'>"
        "<i>%ΔYTD: compare YTD to same period last year; %Δ12mo: compare most reent 12 months to 12 months before that.</i></td></tr>"
    )

    print("</table>")


def season_summary(ttdb: sqlite3.Connection):
    """Print super-brief summary report of the current year."""

    detail_link = cc.selfref(what=cc.WHAT_DETAIL, pages_back=1)
    blocks_link = cc.selfref(what=cc.WHAT_BLOCKS, pages_back=1)
    tags_link = cc.selfref(what=cc.WHAT_TAGS_LOST, pages_back=1)
    today_link = cc.selfref(what=cc.WHAT_ONE_DAY, qdate="today")
    summaries_link = cc.selfref(what=cc.WHAT_DATERANGE)
    download_csv_link = cc.make_url("tt_download", what="csv")
    download_db_link = cc.make_url("tt_download", what="db")

    print(
        f"<h1 style='display: inline;'>{cc.titleize('Quick Overview')}</h1><br><br>")
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
          <b>Today<br>Detail</b></button>
        &nbsp;&nbsp;
        """
    )
    print(
        f"""
        <button onclick="window.location.href='{detail_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Day<br>Summaries</b></button>
        &nbsp;&nbsp;
          """
    )
    print(
        f"""
        <button onclick="window.location.href='{summaries_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Period<br>Summaries</b></button>
        &nbsp;&nbsp;
          """
    )
    print(
        f"""
        <button onclick="window.location.href='{blocks_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Time Block<br>Summaries</b></button>
        &nbsp;&nbsp;
        """
    )

    print(
        f"""
        <button onclick="window.location.href='{cc.selfref(cc.WHAT_SUMMARY_FREQUENCIES)}'"
            style="padding: 10px; display: inline-block;">
          <b>Activity<br>Graphs</b></button>
        &nbsp;&nbsp;
        """
    )
    print(
        f"""
        <button onclick="window.location.href='{tags_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Inventory<br>of Tags</b></button>
        &nbsp;&nbsp;
          """
    )
    # print(
    #     f"""
    #     <button onclick="window.location.href='{download_csv_link}'"
    #         style="padding: 10px; display: inline-block;">
    #       <b>Download<br>CSV</b></button>
    #     &nbsp;&nbsp;
    #     <button onclick="window.location.href='{download_db_link}'"
    #         style="padding: 10px; display: inline-block;">
    #       <b>Download<br>Database</b></button>
    #     <br><br>
    #       """
    # )
    print("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;")
    print(
    f"""
    <button onclick="window.location.href='{download_csv_link}'"
        style="padding: 10px; display: inline-block; background-color: #ddd; border: 1px solid #aaa;">
      <b>Download<br>CSV</b></button>
    &nbsp;&nbsp;
    <button onclick="window.location.href='{download_db_link}'"
        style="padding: 10px; display: inline-block; background-color: #ddd; border: 1px solid #aaa;">
      <b>Download<br>Database</b></button>
    <br><br>
      """
)



def season_detail(
    ttdb: sqlite3.Connection,
    sort_by=None,
    sort_direction=None,
    pages_back: int = 1,
    start_date: str = "",
    end_date: str = "",
):
    """A summary in which each row is one day."""

    requested_start = "" if start_date in ("", "0000-00-00") else start_date
    requested_end = "" if end_date in ("", "9999-99-99") else end_date

    db_start_date, db_end_date = db.fetch_date_range_limits(
        ttdb,
        orgsite_id=1,
    )

    start_date, end_date, _default_start, _default_end = cc.resolve_date_range(
        ttdb,
        orgsite_id=1,
        start_date=requested_start,
        end_date=requested_end,
        db_limits=(db_start_date, db_end_date),
    )

    # list of each day's totals
    all_days = cc.get_days_data(
        ttdb=ttdb, min_date=start_date, max_date=end_date
    )  # FIXME: needs to use orgsite_id
    # overall totals for the whole period
    # FIXME: hardwired to orgsite_id=1
    days_totals = db.MultiDayTotals.fetch_from_db(
        conn=ttdb, orgsite_id=1, start_date=start_date, end_date=end_date
    )

    # Sort the all_days ldataccording to the sort parameter
    sort_by = sort_by if sort_by else cc.SORT_DATE
    sort_direction = sort_direction if sort_direction else cc.ORDER_REVERSE
    self_url = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=sort_by,
        qdir=sort_direction,
        start_date=start_date,
        end_date=end_date,
        pages_back=cc.increment_pages_back(pages_back),
    )
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
        all_days = sorted(all_days, reverse=reverse_sort,
                          key=lambda x: x.weekday)
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
    sort_msg = f"Day Summaries, sorted by {sort_msg} "

    # Set up colour maps for shading cell backgrounds
    max_parked_colour = dc.Dimension(interpolation_exponent=2)
    max_parked_colour.add_config(0, "white")
    max_parked_colour.add_config(days_totals.max_parked_combined, "green")

    max_full_colour = dc.Dimension(interpolation_exponent=2)
    max_full_colour.add_config(0, "white")
    max_full_colour.add_config(days_totals.max_fullest_combined, "teal")

    max_left_colour = dc.Dimension()
    max_left_colour.add_config(0, "white")
    max_left_colour.add_config(10, "red")

    max_temp_colour = dc.Dimension()
    max_temp_colour.add_config(11, "beige")  # 'rgb(255, 255, 224)')
    max_temp_colour.add_config(35, "orange")
    max_temp_colour.add_config(0, "azure")

    max_precip_colour = dc.Dimension(interpolation_exponent=1)
    max_precip_colour.add_config(0, "white")
    if days_totals.max_precipitation not in (None, 0):
        max_precip_colour.add_config(days_totals.max_precipitation, "azure")

    print(f"<h1>{cc.titleize(': Day Summaries')}</h1>")
    print(f"{cc.main_and_back_buttons(pages_back)}<br>")
    print("<br>")
    print(
        generate_date_filter_form(
            self_url,
            default_start_date=start_date,
            default_end_date=end_date,
        )
    )

    print("<br><br>")

    sort_date_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_DATE,
        qdir=other_direction,
        pages_back=cc.increment_pages_back(pages_back),
    )
    sort_day_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_DAY,
        qdir=other_direction,
        pages_back=cc.increment_pages_back(pages_back),
    )
    sort_parked_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_PARKED,
        qdir=other_direction,
        pages_back=cc.increment_pages_back(pages_back),
    )
    sort_fullness_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_FULLNESS,
        qdir=other_direction,
        pages_back=cc.increment_pages_back(pages_back),
    )
    sort_leftovers_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_LEFTOVERS,
        qdir=other_direction,
        pages_back=cc.increment_pages_back(pages_back),
    )
    sort_precipitation_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_PRECIPITATAION,
        qdir=other_direction,
        pages_back=cc.increment_pages_back(pages_back),
    )
    sort_temperature_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_TEMPERATURE,
        qdir=other_direction,
        pages_back=cc.increment_pages_back(pages_back),
    )
    # mismatches_link = cc.selfref(cc.WHAT_MISMATCH)

    print("<table class='general_table'>")
    print(f"<tr><th colspan=12><br>{sort_msg}<br>&nbsp;</th></tr>")
    print("<style>td {text-align: right;}</style>")
    print(
        "<tr>"
        "<th colspan=2>Date</th>"
        "<th colspan=2>Hours</th>"
        "<th colspan=3>Bikes parked</th>"
        f"<th rowspan=2><a href={sort_leftovers_link}>Bikes<br />left<br />onsite</a></th>"
        f"<th rowspan=2><a href={sort_fullness_link}>Most<br />bikes<br />at once</a></th>"
        # "<th rowspan=2>Bike-<br />hours</th>"
        # "<th rowspan=2>Bike-<br />hours<br />per hr</th>"
        "<th rowspan=2>Bike<br />Regs</th>"
        "<th colspan=2>Weather</th>"
        "</tr>"
    )
    print(
        "<tr>"
        f"<th><a href={sort_date_link}>Date</a></th>"
        f"<th><a href={sort_day_link}>Day</a></th>"
        "<th>Open</th><th>Close</th>"
        f"<th>Reg</th><th>Ovr</th><th><a href={sort_parked_link}>Total</a></th>"
        # "<th>Left</th>"
        # "<th>Fullest</th>"
        f"<th><a href={sort_temperature_link}>Max<br />temp</a></th>"
        f"<th><a href={sort_precipitation_link}>Rain</a></th>"
        "</tr>"
    )

    for row in all_days:
        row: DayTotals
        date_link = cc.selfref(what=cc.WHAT_ONE_DAY, qdate=row.date)
        reg_str = "" if row.bikes_registered is None else f"{row.bikes_registered}"
        temp_str = "" if row.max_temperature is None else f"{row.max_temperature:0.1f}"
        precip_str = "" if row.precipitation is None else f"{row.precipitation:0.1f}"

        print(
            f"<tr>"
            f"<td><a href='{date_link}'>{row.date}</a></td>"
            f"<td style='text-align:left'>{ut.date_str(row.date,dow_str_len=3)}</td>"
            f"<td>{row.time_open}</td><td>{row.time_closed}</td>"
            f"<td>{row.num_parked_regular}</td>"
            f"<td>{row.num_parked_oversize}</td>"
            # f"<td style='background: {max_parked_colour.get_rgb_str(row.parked_total)}'>{row.parked_total}</td>"
            f"<td style='{max_parked_colour.css_bg_fg(row.num_parked_combined)}'>{row.num_parked_combined}</td>"
            f"<td style='{max_left_colour.css_bg_fg(row.num_remaining_combined)}'>{row.num_remaining_combined}</td>"
            f"<td style='{max_full_colour.css_bg_fg(row.num_fullest_combined)}'>{row.num_fullest_combined}</td>"
            # f"<td style='{max_bike_hours_colour.css_bg_fg(row.bike_hours)}'>{row.bike_hours:0.0f}</td>"
            # f"<td style='{max_bike_hours_per_hour_colour.css_bg_fg(row.bike_hours_per_hour)}'>{row.bike_hours_per_hour:0.2f}</td>"
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
    d1 = inout_colors.add_dimension(
        interpolation_exponent=0.82, label="Bikes parked")
    d1.add_config(0, BLOCK_XY_BOTTOM_COLOR)
    d1.add_config(block_maxes.num_in, BLOCK_X_TOP_COLOR)
    d2 = inout_colors.add_dimension(
        interpolation_exponent=0.82, label="Bikes returned")
    d2.add_config(0, BLOCK_XY_BOTTOM_COLOR)
    d2.add_config(block_maxes.num_out, BLOCK_Y_TOP_COLOR)

    fullness_colors = dc.Dimension(
        interpolation_exponent=0.85, label="Bikes onsite")
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
