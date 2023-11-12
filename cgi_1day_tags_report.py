#!/usr/bin/env python3
"""HTML report on tags in/out for one day.

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
from statistics import mean, median

##from tt_globals import MaybeTag

import tt_dbutil as db
from tt_tag import TagID
from tt_time import VTime
import tt_util as ut
import cgi_common as cc
import datacolors as dc


HIGHLIGHT_NONE = 0
HIGHLIGHT_WARN = 1
HIGHLIGHT_ERROR = 2
HIGHLIGHT_MAYBE_ERROR = 3
BAR_MARKERS = {"R": chr(0x25CF), "O": chr(0x25A0)}
BAR_COL_WIDTH = 80


def _nav_buttons(ttdb,thisday,pages_back) -> str:
    """Make nav buttons for the one-day report."""

    def prev_next_button(label, offset) -> str:
        target = ut.date_offset(thisday,offset)
        if target < earliest_date or target > latest_date:
            return f""" <button type="button" disabled style="opacity: 0.5; cursor: not-allowed;">{label}</button>"""
        link = cc.selfref(what=cc.WHAT_ONE_DAY,qdate=ut.date_offset(thisday,offset),pages_back=pages_back+1)
        return f""" <button type="button" onclick="window.location.href='{link}';">{label}</button>"""

    date_range = db.db_fetch(ttdb,"select min(date) earliest,max(date) latest from day")[0]
    earliest_date = date_range.earliest
    latest_date = date_range.latest

    buttons = f"{cc.back_button(pages_back)}"
    buttons += prev_next_button("Previous day",-1)
    buttons += prev_next_button("Next day",1)
    return buttons

def one_day_tags_report(
    ttdb: sqlite3.Connection, whatday: str = "", sort_by: str = "", pages_back: int = 1
):
    thisday = ut.date_str(whatday)
    if not thisday:
        cc.bad_date(whatday)
    is_today = bool(thisday == ut.date_str("today"))

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
    if not rows:
        print(f"<pre>No activity recorded for {thisday}")
        sys.exit()

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

    leftovers = len([t.time_out for t in rows if t.time_out <= ""])
    suspicious = len(
        [
            t.next_time_in
            for t in rows
            if t.next_time_in < t.time_in and t.time_out <= ""
        ]
    )
    # Earliest and latest event are for the bar graph
    earliest_event = VTime(min([r.time_in for r in rows if r.time_in > ""])).num
    max_visit = VTime(
        max([VTime(r.time_in).num + VTime(r.duration).num for r in rows])
        - earliest_event
    ).num
    bar_scaling_factor = BAR_COL_WIDTH / (max_visit)
    bar_offset = round(earliest_event * bar_scaling_factor)

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

    # Get overall stats for the day
    day_data: cc.SingleDay = cc.get_days_data(ttdb, thisday, thisday)[0]
    min_stay = VTime(min(durations)).tidy
    max_stay = VTime(max(durations)).tidy
    mean_stay = VTime(mean(durations)).tidy
    median_stay = VTime(median(durations)).tidy

    de_link = cc.selfref(what=cc.WHAT_DATA_ENTRY, qdate=thisday)
    df_link = cc.selfref(what=cc.WHAT_DATAFILE, qdate=thisday)

    h1 = cc.titleize(f": {thisday} ({ut.date_str(thisday,dow_str_len=10)})")
    html = f"<h1>{h1}</h1>"
    print(html)

    print(_nav_buttons(ttdb,thisday,pages_back))
    print("<br><br>")

    print("<table><style>table td {text-align:right}</style>")
    print(
        f"""
        <tr><td colspan=3>Valet hours:{day_data.valet_open.tidy} - {day_data.valet_close.tidy}</td></tr>
        <tr><td colspan=2>Total bikes parked:</td><td>{day_data.total_bikes}</td></tr>
        <tr><td colspan=2>Most bikes at once (at {day_data.max_bikes_time.tidy}):</td><td>{day_data.max_bikes}</td></tr>
        <tr><td colspan=2>529 registrations:</td><td>{day_data.registrations}</td></tr>
        <tr><td colspan=2>High temperature:</td><td>{day_data.temperature}</td></tr>
        <tr><td colspan=2>Precipitation:</td><td>{day_data.precip}</td></tr>
        <tr><td colspan=2>Shortest stay:</td><td>{min_stay}</td></tr>
        <tr><td colspan=2>Longest stay:</td><td>{max_stay}</td></tr>
        <tr><td colspan=2>Average stay:</td><td>{mean_stay}</td></tr>
        <tr><td colspan=2>Median stay:</td><td>{median_stay}</td></tr>
        <tr><td colspan=2>Bikes left at valet (recorded in TagTracker):</td>
        <td  width=40 style='{highlights.css_bg_fg(int(leftovers>0)*HIGHLIGHT_WARN)}'>{leftovers}</td></tr>
    """
    )
    if not is_today:
        print(
            f"""
            <tr><td colspan=2>Bikes left at valet (reported in day end form):</td><td>{day_data.leftovers_reported}</td></tr>
            <tr><td colspan=2>Bikes possibly never checked in:</td>
            <td style='text-align:right;
            {highlights.css_bg_fg(int(suspicious>0)*HIGHLIGHT_ERROR)}'>
            {suspicious}</td></tr>
        """
        )
    print(
        f"""
        <tr><td colspan=3><a href='{de_link}'>Data entry reports</a></td></tr>
        <tr><td colspan=3><a href='{df_link}'>Reconstructed datafile</a></td></tr>
        """
    )
    print("</table><p></p>")
    print("<table>")
    print("<tr><td>Colours for time of day:</td>")
    print(f"<td style={daylight.css_bg_fg(daylight.min)}>Early</td>")
    print(f"<td style={daylight.css_bg_fg((daylight.min+daylight.max)/2)}>Mid-day</td>")
    print(f"<td style={daylight.css_bg_fg(daylight.max)}>Later</td>")
    print("<tr><td>Colours for length of stay:</td>")
    print(f"<td style={duration_colors.css_bg_fg(duration_colors.min)}>Short</td>")
    print(
        f"<td style={duration_colors.css_bg_fg((duration_colors.min+duration_colors.max)/2)}>Medium</td>"
    )
    print(f"<td style={duration_colors.css_bg_fg(duration_colors.max)}>Long</td>")
    print("</table><p></p>")

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

    html = "<table style=text-align:center>"
    html += (
        "<tr><th colspan=5 style='text-align:center'>"
        f"Bikes on {thisday}<br>{sort_msg}</th></tr>"
    )
    html += f"<tr><th><a href='{link_sort_tag}'>Bike</a></th>"
    html += f"<th><a href='{link_sort_time}'>Time in</a></th>"
    html += f"<th><a href='{link_sort_time_out}'>Time out</a></th>"
    html += f"<th><a href='{link_sort_duration}'>Length<br>of stay</a></th>"
    html += f"<th>Bar graph of this visit<br>{BAR_MARKERS['R']} = Regular bike; {BAR_MARKERS['O']} = Oversize bike</th></tr>"
    print(html)

    for i, v in enumerate(rows):
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
        c = (
            "background-color:auto" if time_out else "background-color:khaki"
        )  # "rgb(255, 230, 0)"
        print(
            f"<td style='text-align:left;font-family: monospace;color:purple;{c}'>{bar_before}{bar_itself}</td>"
        )
        print("</tr>")
    html = ""
    html += (
        "<tr><td colspan=5 style='text-align:center'><i>"
        "Where no check-out time exists, duration is "
        "estimated assuming bike is at valet until "
        "the end of the day</i></td></tr>"
    )
    html += "</table></body></html>"
    print(html)
