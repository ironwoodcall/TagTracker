#!/usr/bin/env python3
"""Web report to show all tags & which were lost.

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
from dataclasses import dataclass
import sys

import common.tt_constants as k
import common.tt_util as ut
from common.tt_tag import TagID
from common.tt_time import VTime
import web.web_common as cc

STYLE_GOOD = "color:black;background:cornsilk;"
STYLE_NOW_LOST = "color:black;background:tomato;"
STYLE_EVER_LOST = "color:black;background:pink;"
STYLE_EMPTY = "background:lavender"


@dataclass
class _TagInfo:
    tagid: TagID = TagID()
    times_lost: int = 0
    last_lost: str = ""
    times_used: int = 0
    last_used: str = ""


def tags_report(conn: sqlite3.Connection):
    """Report on all tags in an HTML page."""

    # Get a list of all the tags (VISIT)
    # For each tag, know:
    #   tag: TagID
    #   last_used: str = when it was last used ("" if never)
    #   last_lost: str = when it was last not-returned ("" if never)
    #   times_lost: (number of times not-returned?)
    #   times_used: (number of times used?)
    today = ut.date_str("today")
    orgsite_id = 1  # FIXME: hardiwred orgsite_id

    cursor = conn.cursor()

    # Define the orgsite_id you want to filter by
    orgsite_id = 1  # Replace with your desired orgsite_id

    # Define the query with a WHERE clause to filter by orgsite_id
    query = """
    SELECT
        v.bike_id AS tag,
        COUNT(CASE WHEN v.time_out IS NULL OR v.time_out = '' THEN 1 END) AS times_lost,
        MAX(CASE WHEN v.time_out IS NULL OR v.time_out = '' THEN d.date END) AS last_lost,
        COUNT(v.id) AS times_used,
        MAX(d.date) AS last_used

    FROM
        VISIT v
    JOIN
        DAY d ON v.day_id = d.id
    WHERE
        d.orgsite_id = ?
    GROUP BY
        v.bike_id;
    """

    # Execute the query with the orgsite_id as a parameter
    tagrows = cursor.execute(query, (orgsite_id,)).fetchall()
    cursor.close()

    taginfo = {}
    for row in tagrows:
        tagid = TagID(row[0])
        taginfo[tagid] = _TagInfo(
            tagid=tagid,
            times_lost=row[1] or 0,
            last_lost=row[2] or "",
            times_used=row[3] or 0,
            last_used=row[4] or "",
        )


    # Dictionary of prefixes. Each value is its highest-numbered tag.
    prefixes = {}
    for t in taginfo:
        prefixes[t.prefix] = max(t.number, prefixes.get(t.prefix, t.number))

    max_tag = max(prefixes.values())

    print("<h1>Inventory of tags</h1>")
    print(f"{cc.main_and_back_buttons(1)}<br><br>")

    print(
        f"""
          <table class='general_table'><style>table td {{text-align:left;}}</style><tr><th colspan=2>Legend</th></tr>
          <tr>
          <td style='{STYLE_EVER_LOST}'>Tag lost at least once</td>
          <td style='{STYLE_GOOD}'>Tag used but never lost</td>
          </tr><tr>
          <td style='{STYLE_NOW_LOST}'>Tag not reused since lost</td>
          <td style='{STYLE_EMPTY}'>Tag never used or doesn't exist</td>
          </tr>
          <tr><td colspan=2><i>A tag is considered 'lost' if on a bike that was not
                picked up by end of day.</i></td></tr>
          <tr><td colspan=2><i>Lost tag counts exclude bikes today ({today}).</i></td></tr>
          </table><br>
          """
    )

    print("<table class=general_table>")
    print(f"<tr><th colspan={max_tag+1}>Every tag ever used</th></tr>")
    for pre in sorted(prefixes.keys()):
        print("<tr>")
        for num in range(0, max_tag + 1):
            tag = TagID(f"{pre}{num}")
            if tag in taginfo:
                taglink = cc.CGIManager.selfref(what_report=cc.WHAT_TAG_HISTORY, tag=tag)
                info = taginfo[tag]
                hover = f"Tag: {tag.upper()}\nUsed {info.times_used} {ut.plural(info.times_used,'time')}\nLast used {info.last_used}\n"
                if info.times_lost == 0:
                    color = STYLE_GOOD
                else:
                    hover = f"{hover}\nLost {info.times_lost} {ut.plural(info.times_lost,'time')}\nLast lost {info.last_lost}"
                    if info.last_used == info.last_lost:
                        hover = f"{hover}\nNot used since last lost"
                        color = STYLE_NOW_LOST
                    else:
                        color = STYLE_EVER_LOST
                print(
                    f"  <td title='{hover}' style='background:{color}'>"
                    f"<a href='{taglink}'>{info.tagid.upper()}</a></td>"
                )
            else:
                print(
                    f"  <td title='Tag {tag.upper()} unknown' style='{STYLE_EMPTY}'>&nbsp;</td>"
                )
        print("</tr>")
    print("</table>")

def one_tag_history_report(ttdb: sqlite3.Connection, maybe_tag: k.MaybeTag) -> None:
    """Report a tag's history."""

    tagid = TagID(maybe_tag)
    if not tagid:
        print(f"Not a tag ID: '{ut.untaint(tagid.original)}'")
        sys.exit()

    cursor = ttdb.cursor()
    query = """
    SELECT
        d.date,
        v.time_in,
        v.time_out
    FROM
        VISIT v
    JOIN
        DAY d ON v.day_id = d.id
    WHERE
        v.bike_id = ? AND d.orgsite_id = ?
    ORDER BY
        d.date DESC;
    """
    orgsite_id = 1  # FIXME hardwired orgsite_id
    rows = cursor.execute(query, (tagid, orgsite_id)).fetchall()
    cursor.close()

    print(f"<h1>History of tag {tagid.upper()}</h1>")
    print(f"{cc.main_and_back_buttons(1)}<br>")

    print(f"<h3>This tag has been used {len(rows)} {ut.plural(len(rows), 'time')}</h3>")
    print()
    if not rows:
        print(f"No record that {tagid.upper()} was ever used<br />")
    else:
        print("<table class=general_table>")
        print("<style>td {text-align: right;}</style>")
        print("<tr><th>Date</th><th>BikeIn</th><th>BikeOut</th></tr>")
        for row in rows:
            date,time_in,time_out = row[0],VTime(row[1]),VTime(row[2])
            link = cc.CGIManager.selfref(what_report=cc.WHAT_ONE_DAY, start_date=date)
            print(
                f"<tr><td>"
                f"<a href='{link}'>{date}</a>"
                "</td>"
                f"<td>{time_in.tidy}</td><td>{time_out.tidy}</td></tr>"
            )
        print("</table>")
    print("</body></html>")


