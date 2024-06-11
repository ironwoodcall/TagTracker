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
import common.tt_util as ut
import web_common as cc
import datacolors as dc
import web_histogram
import common.tt_dbutil as db
from common.tt_time import VTime

BLOCK_XY_BOTTOM_COLOR = dc.Color((252, 252, 248)).html_color
BLOCK_X_TOP_COLOR = "red"
BLOCK_Y_TOP_COLOR = "royalblue"
BLOCK_NORMAL_MARKER = chr(0x25A0)
BLOCK_HIGHLIGHT_MARKER = chr(0x2B24)


def _freq_nav_buttons(pages_back) -> str:
    """Make nav buttons for the season-frequency report.

    Buttons will be "Mon", "Tue", "Wed", etc, "All days", "Weekdays",
    """
    buttons = f"{cc.main_and_back_buttons(pages_back)}&nbsp;&nbsp;&nbsp;"

    buttons += f"""
        <button type="button"
        onclick="window.location.href='{
            cc.selfref(
                what=cc.WHAT_SUMMARY_FREQUENCIES,
                pages_back=pages_back + 1,
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
                qdow="1,2,3,4,5",
                pages_back=pages_back + 1,
                text_note="weekdays"
            )
            }';">Weekdays</button>
        """
    buttons += f"""
        <button type="button"
        onclick="window.location.href='{
            cc.selfref(
                what=cc.WHAT_SUMMARY_FREQUENCIES,
                qdow="6,7",
                pages_back=pages_back + 1,
                text_note="weekends"
            )
            }';">Weekends</button>
            &nbsp;&nbsp;&nbsp;
        """

    for d in range(1, 8):
        link = cc.selfref(
            what=cc.WHAT_SUMMARY_FREQUENCIES,
            qdow=d,
            pages_back=pages_back + 1,
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
):
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

    h1 = "Distribution of visits"
    h1 = f"{h1} for {title_bit}" if title_bit else h1
    print(f"<h1>{h1}</h1>")
    print(_freq_nav_buttons(pages_back))

    for parameters in table_vars:
        column, title, subtitle, color = parameters
        title = f"{title} ({title_bit})" if title_bit else title
        title = f"<h2>{title}</h2>"
        print(
            web_histogram.times_hist_table(
                ttdb,
                query_column=column,
                days_of_week=dow_parameter,
                color=color,
                title=title,
                subtitle=subtitle,
            )
        )
        print("<br><br>")
    print(back_button)


def mini_freq_tables(ttdb: sqlite3.Connection):
    table_vars = (
        ("duration", "Visit length", "teal"),
        ("time_in", "Time in", "crimson"),
        ("time_out", "Time out", "royalblue"),
    )
    for parameters in table_vars:
        column, title, color = parameters
        title = f"<a href='{cc.selfref(cc.WHAT_SUMMARY_FREQUENCIES)}'>{title}</a>"
        print(
            web_histogram.times_hist_table(
                ttdb,
                query_column=column,
                mini=True,
                color=color,
                title=title,
            )
        )
        print("<br>")


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
            return ""

    # Function to generate HTML row
    def html_row(label, ytd_value, *day_values):
        """Print a single row of data."""
        row_html = (
            f"<tr><td style='text-align:left'>{label}</td>"
            f"<td style='text-align:right'>{_p(ytd_value)}</td>"
        )
        for day_value in day_values:
            row_html += f"<td style='text-align:right'>{_p(day_value)}</td>"
        row_html += "</tr>\n"
        return row_html

    today = ut.date_str("today")
    selected_year = today[:4]
    day_totals = {}

    # Fetching day totals for each day
    for i in range(6, -1, -1):  # Collect in reverse order
        d = ut.date_offset(today, -i)
        day_totals[d] = db.MultiDayTotals.fetch_from_db(
            conn=conn, orgsite_id=1, start_date=d, end_date=d
        )

    # Fetch data for YTD
    ytd_totals = db.MultiDayTotals.fetch_from_db(
        conn=conn, orgsite_id=1, start_date=f"{selected_year}-01-01", end_date=today
    )

    most_parked_link = cc.selfref(
        what=cc.WHAT_ONE_DAY, qdate=ytd_totals.max_parked_combined_date
    )
    fullest_link = cc.selfref(
        what=cc.WHAT_ONE_DAY, qdate=ytd_totals.max_fullest_combined_date
    )

    rows = [
        (
            "Total bikes parked (visits)",
            ytd_totals.total_parked_combined,
            *[day_totals[day].total_parked_combined for day in day_totals.keys()],
        ),
        (
            "&nbsp;&nbsp;&nbsp;Regular bikes parked",
            ytd_totals.total_parked_regular,
            *[day_totals[day].total_parked_regular for day in day_totals.keys()],
        ),
        (
            "&nbsp;&nbsp;&nbsp;Oversize bikes parked",
            ytd_totals.total_parked_oversize,
            *[day_totals[day].total_parked_oversize for day in day_totals.keys()],
        ),
        (
            "Average bikes / day",
            round(ytd_totals.total_parked_combined / ytd_totals.total_days_open),
            *["-" for day in day_totals.keys()],
        ),
        (
            "Total bike registrations",
            ytd_totals.total_bikes_registered,
            *[day_totals[day].total_bikes_registered for day in day_totals.keys()],
        ),
        (
            "Total days open",
            ytd_totals.total_days_open,
            *[day_totals[day].total_days_open for day in day_totals.keys()],
        ),
        (
            "Total hours open",
            VTime(ytd_totals.total_hours_open * 60, allow_large=True),
            *[
                (
                    VTime(day_totals[day].total_hours_open * 60, allow_large=True)
                    if day_totals[day].total_hours_open
                    else ""
                )
                for day in day_totals.keys()
            ],
        ),
        (
            "Bikes left",
            ytd_totals.total_remaining_combined,
            *[day_totals[day].total_remaining_combined for day in day_totals.keys()],
        ),
        (
            f"Most bikes parked (<a href='{most_parked_link}'>"
            f"{ytd_totals.max_parked_combined_date}</a>)",
            ytd_totals.max_parked_combined,
            *["-" for day in day_totals.keys()],
        ),
        (
            f"Most bikes at once (<a href='{fullest_link}'>"
            f"{ytd_totals.max_fullest_combined_date}</a>)",
            ytd_totals.max_fullest_combined,
            *[day_totals[day].max_fullest_combined for day in day_totals.keys()],
        ),
        (
            "Total precipitation",
            ytd_totals.total_precipitation,
            *[day_totals[day].total_precipitation for day in day_totals.keys()],
        ),
        (
            "Max temperature",
            ytd_totals.max_max_temperature,
            *[day_totals[day].max_max_temperature for day in day_totals.keys()],
        ),
    ]

    print("")
    print("<table class='general_table'>")


    # Table header
    header_html = f"  <tr><th>Summary</th><th>YTD<br>{selected_year}</th>"
    for day, _ in day_totals.items():
        daylabel = "Today" if day == today else day
        header_html += f"<th>{daylabel}<br>{ut.dow_str(day)}</th>"
    header_html += "</tr>"
    print(header_html)

    # Table rows
    for label, ytd_value, *day_values in rows:
        print(html_row(label, ytd_value, *day_values))

    print("</table>")


def old_but_working_totals_table(conn: sqlite3.Connection):
    """Quick summary table of YTD, yesterday, and today totals."""

    def _p(val) -> str:
        """Format a single value."""
        if isinstance(val, int):
            return f"{val:,}"
        elif isinstance(val, float):
            return f"{val:,.1f}"
        elif isinstance(val, str):
            return f"{val:>}"
        else:
            return ""

    def html_row(label, ytd_value, yesterday_value, today_value):
        """Print a single row of data."""
        return (
            f"<tr><td style='text-align:left'>{label}</td>"
            f"<td style='text-align:right'>{_p(ytd_value)}</td>"
            f"<td style='text-align:right'>{_p(yesterday_value)}</td>"
            f"<td style='text-align:right'>{_p(today_value)}</td></tr>\n"
        )

    today = ut.date_str("today")
    selected_year = today[:4]
    yesterday = ut.date_str("yesterday")

    # Fetch data for YTD, Yesterday, and Today
    ytd_totals = db.MultiDayTotals.fetch_from_db(
        conn=conn, orgsite_id=1, start_date=f"{selected_year}-01-01", end_date=today
    )
    yesterday_totals = db.MultiDayTotals.fetch_from_db(
        conn=conn, orgsite_id=1, start_date=yesterday, end_date=yesterday
    )
    today_totals = db.MultiDayTotals.fetch_from_db(
        conn=conn, orgsite_id=1, start_date=today, end_date=today
    )

    most_parked_link = cc.selfref(
        what=cc.WHAT_ONE_DAY, qdate=ytd_totals.max_parked_combined_date
    )
    fullest_link = cc.selfref(
        what=cc.WHAT_ONE_DAY, qdate=ytd_totals.max_fullest_combined_date
    )

    rows = [
        (
            "Total bikes parked (visits)",
            ytd_totals.total_parked_combined,
            yesterday_totals.total_parked_combined,
            today_totals.total_parked_combined,
        ),
        (
            "&nbsp;&nbsp;&nbsp;Regular bikes parked",
            ytd_totals.total_parked_regular,
            yesterday_totals.total_parked_regular,
            today_totals.total_parked_regular,
        ),
        (
            "&nbsp;&nbsp;&nbsp;Oversize bikes parked",
            ytd_totals.total_parked_oversize,
            yesterday_totals.total_parked_oversize,
            today_totals.total_parked_oversize,
        ),
        (
            "Average bikes / day",
            round(ytd_totals.total_parked_combined / ytd_totals.total_days_open),
            "-",
            "-",
        ),
        (
            "Total bike registrations",
            ytd_totals.total_bikes_registered,
            yesterday_totals.total_bikes_registered,
            today_totals.total_bikes_registered,
        ),
        (
            "Total days open",
            ytd_totals.total_days_open,
            yesterday_totals.total_days_open,
            today_totals.total_days_open,
        ),
        (
            "Total hours open",
            VTime(ytd_totals.total_hours_open * 60, allow_large=True),
            VTime(
                (
                    yesterday_totals.total_hours_open * 60
                    if yesterday_totals.total_hours_open
                    else ""
                ),
                allow_large=True,
            ),
            VTime(
                (
                    today_totals.total_hours_open * 60
                    if today_totals.total_hours_open
                    else ""
                ),
                allow_large=True,
            ),
        ),
        (
            "Bikes left",
            ytd_totals.total_remaining_combined,
            yesterday_totals.total_remaining_combined,
            today_totals.total_remaining_combined,
        ),
        (
            f"Most bikes parked (<a href='{most_parked_link}'>"
            f"{ytd_totals.max_parked_combined_date}</a>)",
            ytd_totals.max_parked_combined,
            "-",
            "-",
        ),
        (
            f"Most bikes at once (<a href='{fullest_link}'>"
            f"{ytd_totals.max_fullest_combined_date}</a>)",
            ytd_totals.max_fullest_combined,
            yesterday_totals.max_fullest_combined,
            today_totals.max_fullest_combined,
        ),
    ]

    print("")
    print("<table class='general_table'>")
    print(
        f"  <tr><th>Summary</th><th>YTD<br>{selected_year}</th>"
        f"<th>Yesterday<br>{ut.dow_str(yesterday)}</th>"
        f"<th>Today<br>{ut.dow_str(today)}</th></tr>"
    )

    for label, ytd_value, yesterday_value, today_value in rows:
        print(html_row(label, ytd_value, yesterday_value, today_value))

    print("</table>")


def season_summary(ttdb: sqlite3.Connection):
    """Print super-brief summary report of the current year."""

    detail_link = cc.selfref(what=cc.WHAT_DETAIL, pages_back=1)
    blocks_link = cc.selfref(what=cc.WHAT_BLOCKS, pages_back=1)
    tags_link = cc.selfref(what=cc.WHAT_TAGS_LOST, pages_back=1)
    today_link = cc.selfref(what=cc.WHAT_ONE_DAY, qdate="today")
    summaries_link = cc.selfref(what=cc.WHAT_DATERANGE)

    print(f"<h1 style='display: inline;'>{cc.titleize('Quick Overview')}</h1><br><br>")
    print("<div style='display:inline-block'>")
    print("<div style='margin-bottom: 10px; display:inline-block; margin-right:5em'>")

    # today_totals = cc.MultiDayTotals.fetch_from_db(conn=ttdb,orgsite_id=1,start_date="2024-06-03",end_date="2024-06-03")
    # print(f"{today_totals=}")
    totals_table(conn=ttdb)
    print("</div>")
    print("<div style='display:inline-block; vertical-align: top;'>")
    ##mini_freq_tables(ttdb)
    print("</div>")
    print("</div>")
    print("<br>")

    print(
        f"""
        <br>
        <button onclick="window.location.href='{today_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Today's<br>Visits<br>Detail</b></button>
        &nbsp;&nbsp;
        <button onclick="window.location.href='{blocks_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Daily<br>Visits<br>Activity</b></button>
        &nbsp;&nbsp;
        <button onclick="window.location.href='{cc.selfref(cc.WHAT_SUMMARY_FREQUENCIES)}'"
            style="padding: 10px; display: inline-block;">
          <b>Overall<br>Visits<br>Graphs</b></button>
        <br><br>
        <button onclick="window.location.href='{detail_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Daily<br>Summaries</b></button>
        &nbsp;&nbsp;
        <button onclick="window.location.href='{summaries_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Period<br>Summaries</b></button>
       &nbsp;&nbsp;
        <button onclick="window.location.href='{tags_link}'"
            style="padding: 10px; display: inline-block;">
          <b>Tags<br>Inventory</b></button>
        <br><br>
          """
    )


def season_detail(
    ttdb: sqlite3.Connection,
    sort_by=None,
    sort_direction=None,
    pages_back: int = 1,
):
    # FIXME: priority report
    """Print new version of the all-days default report."""
    all_days = cc.get_days_data(ttdb)
    cc.incorporate_blocks_data(ttdb, all_days)
    # FIXME: orgsite_id is hardwired
    days_totals = db.MultiDayTotals.fetch_from_db(conn=ttdb, orgsite_id=1)
    ##blocks_totals = cc.get_blocks_summary(all_days)

    # Sort the all_days ldataccording to the sort parameter
    sort_by = sort_by if sort_by else cc.SORT_DATE
    sort_direction = sort_direction if sort_direction else cc.ORDER_REVERSE
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
        all_days = sorted(all_days, reverse=reverse_sort, key=lambda x: x.dow)
        sort_msg = f"day of week{direction_msg}"
    elif sort_by == cc.SORT_PARKED:
        all_days = sorted(all_days, reverse=reverse_sort, key=lambda x: x.total_bikes)
        sort_msg = f"bikes parked{direction_msg}"
    elif sort_by == cc.SORT_FULLNESS:
        all_days = sorted(all_days, reverse=reverse_sort, key=lambda x: x.max_bikes)
        sort_msg = f"most bikes at once{direction_msg}"
    elif sort_by == cc.SORT_LEFTOVERS:
        all_days = sorted(all_days, reverse=reverse_sort, key=lambda x: x.leftovers)
        sort_msg = f"bikes left onsite{direction_msg}"
    elif sort_by == cc.SORT_PRECIPITATAION:
        all_days = sorted(
            all_days, reverse=reverse_sort, key=lambda x: (x.precip if x.precip else 0)
        )
        sort_msg = f"precipitation{direction_msg}"
    elif sort_by == cc.SORT_TEMPERATURE:
        all_days = sorted(
            all_days,
            reverse=reverse_sort,
            key=lambda x: (x.temperature if x.temperature else -999),
        )
        sort_msg = f"temperature{direction_msg}"
    else:
        all_days = sorted(all_days, key=lambda x: x.tag)
        sort_msg = f"bike tag (sort parameter '{sort_by}' unrecognized)"
    sort_msg = f"Detail, sorted by {sort_msg} "

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
    max_temp_colour.add_config(11, "beige")  #'rgb(255, 255, 224)')
    max_temp_colour.add_config(35, "orange")
    max_temp_colour.add_config(0, "azure")

    max_precip_colour = dc.Dimension(interpolation_exponent=1)
    max_precip_colour.add_config(0, "white")
    max_precip_colour.add_config(days_totals.max_precipitation, "azure")

    print(f"<h1>{cc.titleize(': Detail')}</h1>")
    print(f"{cc.main_and_back_buttons(pages_back)}<br>")

    print("<br><br>")

    sort_date_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_DATE,
        qdir=other_direction,
        pages_back=pages_back + 1,
    )
    sort_day_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_DAY,
        qdir=other_direction,
        pages_back=pages_back + 1,
    )
    sort_parked_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_PARKED,
        qdir=other_direction,
        pages_back=pages_back + 1,
    )
    sort_fullness_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_FULLNESS,
        qdir=other_direction,
        pages_back=pages_back + 1,
    )
    sort_leftovers_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_LEFTOVERS,
        qdir=other_direction,
        pages_back=pages_back + 1,
    )
    sort_precipitation_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_PRECIPITATAION,
        qdir=other_direction,
        pages_back=pages_back + 1,
    )
    sort_temperature_link = cc.selfref(
        cc.WHAT_DETAIL,
        qsort=cc.SORT_TEMPERATURE,
        qdir=other_direction,
        pages_back=pages_back + 1,
    )
    # mismatches_link = cc.selfref(cc.WHAT_MISMATCH)

    print("<table class='general_table'>")
    print(f"<tr><th colspan=13><br>{sort_msg}<br>&nbsp;</th></tr>")
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
        "<th colspan=3>Environment</th>"
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
        f"<th><a href={sort_precipitation_link}>Rain</a></th><th>Dusk</th>"
        "</tr>"
    )

    for row in all_days:
        row: cc.SingleDay
        date_link = cc.selfref(what=cc.WHAT_ONE_DAY, qdate=row.date)
        reg_str = "" if row.registrations is None else f"{row.registrations}"
        temp_str = "" if row.temperature is None else f"{row.temperature:0.1f}"
        precip_str = "" if row.precip is None else f"{row.precip:0.1f}"

        print(
            f"<tr>"
            f"<td><a href='{date_link}'>{row.date}</a></td>"
            f"<td style='text-align:left'>{ut.date_str(row.date,dow_str_len=3)}</td>"
            f"<td>{row.valet_open}</td><td>{row.valet_close}</td>"
            f"<td>{row.regular_bikes}</td>"
            f"<td>{row.oversize_bikes}</td>"
            # f"<td style='background: {max_parked_colour.get_rgb_str(row.parked_total)}'>{row.parked_total}</td>"
            f"<td style='{max_parked_colour.css_bg_fg(row.total_bikes)}'>{row.total_bikes}</td>"
            f"<td style='{max_left_colour.css_bg_fg(row.leftovers)}'>{row.leftovers}</td>"
            f"<td style='{max_full_colour.css_bg_fg(row.max_bikes)}'>{row.max_bikes}</td>"
            # f"<td style='{max_bike_hours_colour.css_bg_fg(row.bike_hours)}'>{row.bike_hours:0.0f}</td>"
            # f"<td style='{max_bike_hours_per_hour_colour.css_bg_fg(row.bike_hours_per_hour)}'>{row.bike_hours_per_hour:0.2f}</td>"
            f"<td>{reg_str}</td>"
            f"<td style='{max_temp_colour.css_bg_fg(row.temperature)}'>{temp_str}</td>"
            f"<td style='{max_precip_colour.css_bg_fg(row.precip)}'>{precip_str}</td>"
            f"<td>{row.dusk}</td>"
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
