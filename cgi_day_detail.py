#!/usr/bin/env python3
"""HTML report on tags in/out for one day.

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
from statistics import mean, median

import tt_dbutil as db
from tt_tag import TagID
from tt_time import VTime
import tt_util as ut
import cgi_common as cc
import datacolors as dc
import tt_estimator
import cgi_histogram


HIGHLIGHT_NONE = 0
HIGHLIGHT_WARN = 1
HIGHLIGHT_ERROR = 2
HIGHLIGHT_MAYBE_ERROR = 3
BAR_MARKERS = {"R": chr(0x25CF), "O": chr(0x25A0)}
BAR_COL_WIDTH = 80


def _nav_buttons(ttdb, thisday, pages_back) -> str:
    """Make nav buttons for the one-day report."""

    def find_prev_next_date(current_date, direction):
        """Return member after (or before) current_date in sorted all_dates."""
        # Check if the list of dates is empty
        if not all_dates:
            return None  # Return None if the list is empty

        # Check if the current date is within the range of dates
        if current_date < all_dates[0]:
            return all_dates[0] if direction == 1 else None
        elif current_date > all_dates[-1]:
            return all_dates[-1] if direction == -1 else None

        # Binary search for the closest date
        low, high = 0, len(all_dates) - 1
        while low <= high:
            mid = (low + high) // 2
            if all_dates[mid] == current_date:
                return (
                    all_dates[mid + direction]
                    if mid + direction >= 0 and mid + direction < len(all_dates)
                    else None
                )
            elif all_dates[mid] < current_date:
                low = mid + 1
            else:
                high = mid - 1

        # If the current date is not found, return the closest date based on direction
        if direction == 1:
            return all_dates[low] if low < len(all_dates) else None
        else:
            return all_dates[high] if high >= 0 else None

    def prev_next_button(label, offset) -> str:
        # target = adjacent_date(thisday,offset)
        target = find_prev_next_date(thisday, offset)
        if target is None:
            return f"""
                <button type="button" disabled
                    style="opacity: 0.5; cursor: not-allowed;">
                {label}</button>
                """
        link = cc.selfref(
            what=cc.WHAT_ONE_DAY,
            qdate=target,
            pages_back=pages_back + 1,
        )
        return f"""
            <button type="button"
            onclick="window.location.href='{link}';">{label}</button>
            """

    def today_button(label) -> str:
        target = ut.date_str("today")
        if target == thisday:
            return f"""
                <button type="button" disabled
                    style="opacity: 0.5; cursor: not-allowed;">
                {label}</button>
                """
        link = cc.selfref(
            what=cc.WHAT_ONE_DAY,
            qdate=target,
            pages_back=pages_back + 1,
        )
        return f"""
            <button type="button"
            onclick="window.location.href='{link}';">{label}</button>
            """

    dbrows = db.db_fetch(ttdb, "SELECT DATE FROM DAY ORDER BY DATE")
    all_dates = sorted([r.date for r in dbrows])

    buttons = f"{cc.main_and_back_buttons(pages_back)}&nbsp;&nbsp;&nbsp;&nbsp;"
    buttons += prev_next_button("Previous day", -1)
    buttons += prev_next_button("Next day", 1)
    buttons += today_button("Today")
    return buttons


def one_day_tags_report(
    ttdb: sqlite3.Connection, whatday: str = "", sort_by: str = "", pages_back: int = 1
):
    thisday = ut.date_str(whatday)
    if not thisday:
        cc.bad_date(whatday)
    is_today = bool(thisday == ut.date_str("today"))
    if is_today:
        day_str = "Today"
    elif thisday == ut.date_str("yesterday"):
        day_str = "Yesterday"
    else:
        day_str = ut.date_str(thisday, dow_str_len=10)

    # In the code below, 'next_*' are empty placeholders
    sql = f"""
        select
           tag, '' next_tag, type bike_type,
           time_in, '' next_time_in, time_out, duration
        from visit
        where date = '{thisday}'
        order by tag asc
    """
    rows = db.db_fetch(ttdb, sql)
    # if not rows:
    #     print(f"<pre>No activity recorded for {thisday}")
    #     sys.exit()

    # Process the rows
    durations = [VTime(v.duration).num for v in rows]
    for v in rows:
        v.tag = TagID(v.tag)
    rows = sorted(rows, key=lambda x: x.tag)
    # Calculate next_tag and next_time_in values
    for i, v in enumerate(rows):
        if i >= 1:
            rows[i - 1].next_time_in = v.time_in
            rows[i - 1].next_tag = v.tag

    # leftovers = len([t.time_out for t in rows if t.time_out <= ""])
    suspicious = len(
        [
            t.next_time_in
            for t in rows
            if t.next_time_in < t.time_in and t.time_out <= ""
        ]
    )

    daylight = dc.Dimension()
    daylight.add_config(VTime("07:30").num, "LightSkyBlue")
    daylight.add_config(VTime("12:00").num, "LightCyan")
    daylight.add_config(VTime("16:00").num, "YellowGreen")
    daylight.add_config(VTime("22:00").num, "DarkOrange")

    highlights = dc.Dimension(interpolation_exponent=1)
    highlights.add_config(HIGHLIGHT_NONE, "white")
    highlights.add_config(HIGHLIGHT_WARN, "khaki")
    highlights.add_config(HIGHLIGHT_ERROR, "magenta")
    highlights.add_config(HIGHLIGHT_MAYBE_ERROR, "cyan")

    duration_colors = dc.Dimension()
    duration_colors.add_config(0, "white")
    duration_colors.add_config(VTime("1200").num, "teal")

    h1 = cc.titleize(f"<br>{thisday} ({day_str}) Detail")
    html = f"<h1>{h1}</h1>"
    print(html)

    print(_nav_buttons(ttdb, thisday, pages_back))
    print("<br><br>")

    if not rows:
        print(f"No information in database for {thisday}")
        return

    # Get overall stats for the day
    day_data: cc.SingleDay = cc.get_days_data(ttdb, thisday, thisday)[0]
    day_data.min_stay = VTime(min(durations)).tidy
    day_data.max_stay = VTime(max(durations)).tidy
    day_data.mean_stay = VTime(mean(durations)).tidy
    day_data.median_stay = VTime(median(durations)).tidy

    day_data.modes_stay, day_data.modes_occurences = ut.calculate_visit_modes(
        durations, 30
    )

    ##print("<div style='display:flex;'><div style='margin-right: 20px;'>")
    ##print("<div style='display:flex;'><div style='margin-right: 20px;'>")
    print("<div style='display:inline-block'>")
    print("<div style='margin-bottom: 10px; display:inline-block; margin-right:5em'>")
    summary_table(day_data, highlights, is_today, suspicious)
    legend_table(daylight, duration_colors)
    print("</div>")
    print("<div style='display:inline-block; vertical-align: top;'>")
    ##print("</div><div>")
    mini_freq_tables(ttdb, thisday)
    print("</div>")
    print("</div>")
    print("<br>")
    ##print("</div></div>")

    visits_table(
        thisday,
        is_today,
        rows,
        highlights,
        daylight,
        duration_colors,
        sort_by,
        pages_back,
    )


def day_frequencies_report(ttdb: sqlite3.Connection, whatday: str = ""):
    today = ut.date_str(whatday)
    if not today:
        print(f"Not a valid date: {whatday}")
        return

    table_vars = (
        (
            "duration",
            "Length of stays",
            "Frequency distribution of lengths of stays",
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
    back_button = f"{cc.main_and_back_buttons(1)}<p></p>"

    print(f"<h1>Distribution of stays on {today}</h1>")
    print(f"{back_button}")

    for parameters in table_vars:
        column, title, subtitle, color = parameters
        title = f"<h2>{title}</h2>"
        print(
            cgi_histogram.times_hist_table(
                ttdb,
                query_column=column,
                start_date=today,
                end_date=today,
                color=color,
                title=title,
                subtitle=subtitle,
            )
        )
        print("<br><br>")
    print(back_button)


def mini_freq_tables(ttdb: sqlite3.Connection, today: str):
    table_vars = (
        ("duration", "Stay length", "teal"),
        ("time_in", "Time in", "crimson"),
        ("time_out", "Time out", "royalblue"),
    )
    for parameters in table_vars:
        column, title, color = parameters
        title = f"<a href='{cc.selfref(cc.WHAT_ONE_DAY_FREQUENCIES,qdate=today)}'>{title}</a>"
        print(
            cgi_histogram.times_hist_table(
                ttdb,
                query_column=column,
                start_date=today,
                end_date=today,
                mini=True,
                color=color,
                title=title,
            )
        )
        print("<br>")


def visits_table(
    thisday,
    is_today,
    rows,
    highlights,
    daylight,
    duration_colors,
    sort_by,
    pages_back,
):
    # Sort the rows list according to the sort parameter
    sort_by = sort_by if sort_by else cc.SORT_TIME_IN
    if sort_by == cc.SORT_TAG:
        rows = sorted(rows, key=lambda x: x.tag)
        sort_msg = "bike tag"
    elif sort_by == cc.SORT_TIME_IN:
        rows = sorted(rows, key=lambda x: x.time_in)
        sort_msg = "time in"
    elif sort_by == cc.SORT_TIME_OUT:
        rows = sorted(rows, key=lambda x: x.time_in)
        rows = sorted(rows, key=lambda x: (not x.time_out, x.time_out))
        sort_msg = "time out"
    elif sort_by == cc.SORT_DURATION:
        rows = sorted(rows, key=lambda x: x.time_in)
        rows = sorted(
            rows,
            reverse=True,
            key=lambda x: (
                x.time_out != "",
                1000000 if x.time_out == "" else x.duration,
            ),
        )
        sort_msg = "length of stay"
    else:
        rows = sorted(rows, key=lambda x: x.tag)
        sort_msg = f"bike tag (sort parameter '{sort_by}' unrecognized)"
    sort_msg = f"(Sorted by {sort_msg}) "

    link_sort_time = cc.selfref(
        what=cc.WHAT_ONE_DAY,
        qdate=thisday,
        qsort=cc.SORT_TIME_IN,
        pages_back=pages_back + 1,
    )
    link_sort_time_out = cc.selfref(
        what=cc.WHAT_ONE_DAY,
        qdate=thisday,
        qsort=cc.SORT_TIME_OUT,
        pages_back=pages_back + 1,
    )
    link_sort_tag = cc.selfref(
        what=cc.WHAT_ONE_DAY,
        qdate=thisday,
        qsort=cc.SORT_TAG,
        pages_back=pages_back + 1,
    )
    link_sort_duration = cc.selfref(
        what=cc.WHAT_ONE_DAY,
        qdate=thisday,
        qsort=cc.SORT_DURATION,
        pages_back=pages_back + 1,
    )

    # Earliest and latest event are for the bar graph
    earliest_event = VTime(min([r.time_in for r in rows if r.time_in > ""])).num
    max_visit = VTime(
        max([VTime(r.time_in).num + VTime(r.duration).num for r in rows])
        - earliest_event
    ).num
    bar_scaling_factor = BAR_COL_WIDTH / (max_visit)
    bar_offset = round(earliest_event * bar_scaling_factor)

    html = "<table style=text-align:right class=general_table>"
    html += (
        "<tr><th colspan=5 style='text-align:center'>"
        f"Bikes on {thisday}<br>{sort_msg}</th></tr>"
    )
    html += f"<tr><th><a href='{link_sort_tag}'>Bike</a></th>"
    html += f"<th><a href='{link_sort_time}'>Time in</a></th>"
    html += f"<th><a href='{link_sort_time_out}'>Time out</a></th>"
    html += f"<th><a href='{link_sort_duration}'>Length<br>of stay</a></th>"
    html += (
        "<th>Bar graph of this visit<br>"
        f"{BAR_MARKERS['R']} = Regular bike; "
        f"{BAR_MARKERS['O']} = Oversize bike</th></tr>"
    )
    print(html)

    for v in rows:
        time_in = VTime(v.time_in)
        time_out = VTime(v.time_out)
        duration = VTime(v.duration)
        print("<tr>")
        # Tag
        tag_link = cc.selfref(what=cc.WHAT_TAG_HISTORY, qtag=v.tag)
        c = "color:auto;"
        if v.next_time_in < time_in and time_out <= "" and not is_today:
            if v.tag[:1] == v.next_tag[:1]:
                c = highlights.css_bg_fg(HIGHLIGHT_ERROR)
            elif v.next_tag:
                c = highlights.css_bg_fg(HIGHLIGHT_MAYBE_ERROR)
        print(
            f"<td style='text-align:center;{c}'><a href='{tag_link}'>{v.tag}</a></td>"
        )
        # Time in
        c = daylight.css_bg_fg(time_in.num)
        print(f"<td style='{c}'>{time_in.tidy}</td>")
        # Time out
        if v.time_out <= "":
            c = highlights.css_bg_fg(HIGHLIGHT_WARN)
        else:
            c = daylight.css_bg_fg(time_out.num)
        print(f"<td style='{c}'>{time_out.tidy}</td>")
        # Duration
        c = duration_colors.css_bg_fg(duration.num)
        print(f"<td style='{c}'>{duration.tidy}</td>")
        # picture of the bike's visit.
        #   Bar start is based on time_in
        #   Bar length is based on duration
        #   Bar scaling factor is based on latest - earliest
        bar_marker = BAR_MARKERS[v.bike_type.upper()]
        bar_before_len = round(((time_in.num) * bar_scaling_factor)) - bar_offset
        bar_before = bar_before_len * "&nbsp;" if bar_before_len else ""
        bar_itself_len = round((duration.num * bar_scaling_factor))
        bar_itself_len = bar_itself_len if bar_itself_len else 1
        bar_itself = bar_itself_len * bar_marker
        c = "background:auto" if time_out else "background:khaki"  # "rgb(255, 230, 0)"
        print(
            f"<td style='text-align:left;font-family: monospace;color:purple;{c}'>"
            f"{bar_before}{bar_itself}</td>"
        )
        print("</tr>")
    html = ""
    html += (
        "<tr><td colspan=5 style='text-align:center'><i>"
        "Where no check-out time exists, duration is "
        "estimated assuming bike is checked in until "
        "the end of the day</i></td></tr>"
    )
    html += "</table></body></html>"
    print(html)


def summary_table(
    day_data: cc.SingleDay, highlights: dc.Dimension, is_today: bool, suspicious: int
):
    def fmt_none(obj) -> object:
        if obj is None:
            return ""
        return obj

    the_estimate = None
    if is_today:
        est = tt_estimator.Estimator(closing_time=day_data.valet_close)
        est.guess()
        if est.state != tt_estimator.ERROR and est.closing_time > VTime("now"):
            est_min = est.bikes_so_far + est.min
            est_max = est.bikes_so_far + est.max
            the_estimate = (
                str(est_min) if est_min == est_max else f"{est_min}-{est_max}"
            )

    print(
        "<table class=general_table><style>.general_table td {text-align:right}</style>"
    )
    print(
        f"""
        <tr><td colspan=3>Hours of operation:
            {day_data.valet_open.tidy} - {day_data.valet_close.tidy}</td></tr>
        <tr><td colspan=2>Total bikes parked (visits):</td>
            <td>{day_data.total_bikes}</td></tr>
            """
    )
    if is_today and the_estimate is not None:
        print(
            f"""
        <tr><td colspan=2>&nbsp;&nbsp;Predicted total bikes today:</td>
            <td>{the_estimate}</td></tr>
        """
        )
    print(
        f"""
        <tr><td colspan=2>Most bikes at once (at {day_data.max_bikes_time.tidy}):</td>
            <td>{day_data.max_bikes}</td></tr>
        <tr><td colspan=2>Bikes remaining:</td>
            <td  width=40 style='{highlights.css_bg_fg(int(day_data.leftovers>0)*HIGHLIGHT_WARN)}'>
                {day_data.leftovers}</td></tr>
        <tr><td colspan=2>Bikes registered:</td>
            <td>{day_data.registrations}</td></tr>
            """
    )

    if not is_today:
        print(
            f"""
            <tr><td colspan=2>Shortest visit:</td>
                <td>{day_data.min_stay}</td></tr>
            <tr><td colspan=2>Longest visit:</td>
                <td>{day_data.max_stay}</td></tr>
            <tr><td colspan=2>Mean visit length:</td>
                <td>{day_data.mean_stay}</td></tr>
            <tr><td colspan=2>Median visit length:</td>
                <td>{day_data.median_stay}</td></tr>
            <tr><td colspan=2>{ut.plural(len(day_data.modes_stay),'Mode')}
                    visit length ({day_data.modes_occurences} occurences):</td>
                <td>{'<br>'.join(day_data.modes_stay)}</td></tr>
            <tr><td colspan=2>Bike registrations:</td>
            <td>{fmt_none(day_data.registrations)}</td></tr>
            <tr><td colspan=2>High temperature:</td>
                <td>{fmt_none(day_data.temperature)}</td></tr>
            <tr><td colspan=2>Precipitation:</td>
                <td>{fmt_none(day_data.precip)}</td></tr>
    """
        )
    if not is_today and suspicious:
        print(
            f"""
            <tr><td colspan=2>Bikes possibly never checked in:</td>
            <td style='text-align:right;
                {highlights.css_bg_fg(int(suspicious>0)*HIGHLIGHT_ERROR)}'>
                {suspicious}</td></tr>
        """
        )
    de_link = cc.selfref(what=cc.WHAT_DATA_ENTRY, qdate=day_data.date)
    df_link = cc.selfref(what=cc.WHAT_DATAFILE, qdate=day_data.date)

    print(
        f"""
        <tr><td colspan=3><a href='{de_link}'>Data entry reports</a></td></tr>
        <tr><td colspan=3><a href='{df_link}'>Reconstructed datafile</a></td></tr>
        """
    )
    print("</table><p></p>")


def legend_table(daylight: dc.Dimension, duration_colors: dc.Dimension):
    print("<table class=general_table>")
    print("<tr><td>Colours for time of day:</td>")
    print(f"<td style={daylight.css_bg_fg(daylight.min)}>Early</td>")
    print(f"<td style={daylight.css_bg_fg((daylight.min+daylight.max)/2)}>Mid-day</td>")
    print(f"<td style={daylight.css_bg_fg(daylight.max)}>Later</td>")
    print("<tr><td>Colours for length of stay:</td>")
    print(f"<td style={duration_colors.css_bg_fg(duration_colors.min)}>Short</td>")
    print(
        f"<td style={duration_colors.css_bg_fg((duration_colors.min+duration_colors.max)/2)}>"
            "Medium</td>"
    )
    print(f"<td style={duration_colors.css_bg_fg(duration_colors.max)}>Long</td>")
    print("</table><p></p>")
