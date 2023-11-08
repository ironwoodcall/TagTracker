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
BAR_MARKERS = { "R": chr(0x25cf), "O":chr(0x25a0)}
BAR_COL_WIDTH = 80

def one_day_tags_report(ttdb: sqlite3.Connection, whatday: str = "",sort_by=cc.SORT_TIME):
    thisday = ut.date_str(whatday)
    if not thisday:
        cc.bad_date(whatday)
    is_today = bool(thisday == ut.date_str('today'))


    me = cc.selfref()

    # In the code below, 'next_*' are empty placeholders
    sql = (
        "select tag, '' next_tag, type bike_type, time_in, '' next_time_in, time_out, duration "
        f"from visit where date = '{thisday}' order by tag asc"
    )
    rows = db.db_fetch(ttdb, sql)

    # Process the rows
    for v in rows:
        v.tag = TagID(v.tag)
    rows = sorted(rows, key=lambda x: x.tag)
    # Calculate next_tag and next_time_in values
    for i, v in enumerate(rows):
        if i >= 1:
            rows[i - 1].next_time_in = v.time_in
            rows[i - 1].next_tag = v.tag
    if not rows:
        print(f"<pre>No activity recorded for {thisday}")
        sys.exit()

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
    max_visit = VTime(max([VTime(r.time_in).num+VTime(r.duration).num for r in rows]) -earliest_event).num
    bar_scaling_factor = BAR_COL_WIDTH/(max_visit)
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
    duration_colors.add_config(0,'white')
    duration_colors.add_config(VTime('1200').num,'teal')

    html = f"<h1>Bikes in & out on {thisday} ({ut.date_str(thisday,dow_str_len=10)})</h1>"
    print(html)

    print("<table>")
    print(f"<tr><td colspan=2>Bikes not checked out:</td><td  width=40 style={highlights.css_bg_fg(int(leftovers>0)*HIGHLIGHT_WARN)}>{leftovers}</td></tr>")
    if not is_today:
        print(f"<tr><td colspan=2>Bikes possibly never checked in:</td><td style={highlights.css_bg_fg(int(suspicious>0)*HIGHLIGHT_ERROR)}>{suspicious}</td></tr>")
    print("</table><p></p>")
    print("<table>")
    print("<tr><td>Colours for Time of day:</td>")
    print(f"<td style={daylight.css_bg_fg(daylight.min)}>Early</td>")
    print(f"<td style={daylight.css_bg_fg((daylight.min+daylight.max)/2)}>Mid-day</td>")
    print(f"<td style={daylight.css_bg_fg(daylight.max)}>Later</td>")
    print("<tr><td>Colours for Length of stay:</td>")
    print(f"<td style={duration_colors.css_bg_fg(duration_colors.min)}>Short</td>")
    print(f"<td style={duration_colors.css_bg_fg((duration_colors.min+duration_colors.max)/2)}>Medium</td>")
    print(f"<td style={duration_colors.css_bg_fg(duration_colors.max)}>Long</td>")
    print("</table><p></p>")


    # Sort the rows list according to the sort parameter
    if sort_by == cc.SORT_TAG:
        pass
    elif sort_by == cc.SORT_TIME:
        rows = sorted(rows, key=lambda x: x.time_in)
    elif sort_by == cc.SORT_DURATION:
        rows = sorted(rows, key=lambda x: x.time_in)
    else:
        print( f"<p><span style='color=white;background-color:darkred'>Cannot sort by '{sort_by}</span></p>")

    html = "<table style=text-align:center>"
    html += f"<tr><th colspan=5 style='text-align:center'>Bikes on {thisday}</th></tr>"
    html += "<tr><th>Bike</th><th>Time In</th><th>Time Out</th><th>Length<br>of stay</th>"
    html += f"<th>Bar graph of this visit<br>{BAR_MARKERS['R']} = Regular bike; {BAR_MARKERS['O']} = Oversize bike</th></tr>"
    print(html)

    for i, v in enumerate(rows):
        time_in = VTime(v.time_in)
        time_out = VTime(v.time_out)
        duration = VTime(v.duration)
        print("<tr>")
        # Tag
        c = "color:auto;"
        if v.next_time_in < time_in and time_out <= "" and not is_today:
            if v.tag[:1] == v.next_tag[:1]:
                c = highlights.css_bg_fg(HIGHLIGHT_ERROR)
            elif i < len(rows) - 1:
                c = highlights.css_bg_fg(HIGHLIGHT_MAYBE_ERROR)
        print(f"<td style='text-align:center;{c}'>{v.tag}</td>")
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
        bar_before_len = round(((time_in.num)* bar_scaling_factor)) - bar_offset
        bar_before = bar_before_len * "&nbsp;" if bar_before_len else ""
        bar_itself_len = round((duration.num * bar_scaling_factor))
        bar_itself_len = bar_itself_len if bar_itself_len else 1
        bar_itself = bar_itself_len * bar_marker
        c = "background-color:auto" if time_out else "background-color:khaki" #"rgb(255, 230, 0)"
        print(f"<td style='text-align:left;font-family: monospace;color:purple;{c}'>{bar_before}{bar_itself}</td>")
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

