#!/usr/bin/env python3
"""Web report to show all tags & which were lost.

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

##from tt_globals import *

import tt_util as ut
import tt_dbutil as db
import cgi_common as cc
from tt_tag import TagID


STYLE_GOOD = "color:black;background:cornsilk;"
STYLE_NOW_LOST = "color:black;background:tomato;"
STYLE_EVER_LOST = "color:black;background:pink;"
STYLE_EMPTY = "background:lavender"


def tags_report(ttdb: sqlite3.Connection):
    """Report on all tags in an HTML page."""

    # Get a list of all the tags (VISIT)
    # For each tag, know:
    #   tag: TagID
    #   last_used: str = when it was last used ("" if never)
    #   last_lost: str = when it was last not-returned ("" if never)
    #   times_lost: (number of times not-returned?)
    #   times_used: (number of times used?)
    today = ut.date_str("today")
    tagrows = db.db_fetch(
        ttdb,
        f"""
        SELECT
            TAG,
            MAX(CASE WHEN TIME_OUT = '' THEN DATE END) AS LAST_LOST,
            COUNT(CASE WHEN TIME_OUT = '' THEN DATE END) AS TIMES_LOST,
            MAX(DATE) AS LAST_USED,
            COUNT(DATE) AS TIMES_USED
        FROM VISIT
        WHERE DATE != '{today}'
        GROUP BY TAG;
        """,
    )

    taginfo = {}
    bad_tags = []
    for row in tagrows:
        tag = TagID(row.tag)
        if tag:
            row.tag = tag
            taginfo[tag] = row
        else:
            bad_tags.append(tag.original)

    # Dictionary of tags. each value is the DBRow.
    taginfo = {row.tag: row for row in tagrows if row.tag}
    # Dictionary of prefixes. Each value is its highest-numbered tag.
    prefixes = {}
    for t in taginfo:
        prefixes[t.prefix] = max(t.number, prefixes.get(t.prefix, t.number))

    max_tag = max(prefixes.values())

    print("<h1>Index of all tags</h1>")
    print(f"{cc.back_button(1)}<br><br>")

    print(f"""
          <table><style>table td {{text-align:left;}}</style><tr><th colspan=2>Legend</th></tr>
          <tr>
          <td style='{STYLE_EVER_LOST}'>Tag lost at least once</td>
          <td style='{STYLE_GOOD}'>Tag used but never lost</td>
          </tr><tr>
          <td style='{STYLE_NOW_LOST}'>Tag not reused since lost</td>
          <td style='{STYLE_EMPTY}'>Tag never used or doesn't exist</td>
          </tr>
          <tr><td colspan=2><i>A tag is considered 'lost' if on a bike that was not
                picked up by end of day.</i></td></tr>
          <tr><td colspan=2><i>'Lost' counts exclude bikes today ({today}).</i></td></tr>
          </table><br>
          """
          )

    print("<table>")
    print(f"<tr><th colspan={max_tag+1}>Every tag ever used</th></tr>")
    for pre in sorted(prefixes.keys()):
        print("<tr>")
        for num in range(0, max_tag+1):
            tag = TagID(f"{pre}{num}")
            if tag in taginfo:
                taglink = cc.selfref(cc.WHAT_TAG_HISTORY,qtag=tag)
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
                print(f"  <td title='{hover}' style='background:{color}'>"
                      f"<a href='{taglink}'>{info.tag.upper()}</a></td>")
            else:
                print(f"  <td title='Tag {tag.upper()} unknown' style='{STYLE_EMPTY}'>&nbsp;</td>")
        print("</tr>")
    print("</table>")


