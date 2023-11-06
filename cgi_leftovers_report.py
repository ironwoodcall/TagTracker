#!/usr/bin/env python3
"""CGI helper script for TagTracker report on mismatches in leftover bike counts.

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

import tt_dbutil as db
import datacolors as dc

def leftovers_report(ttdb: sqlite3.Connection):
    rows = fetch_data(ttdb)

    max_diff = max([r.difference for r in rows])
    colors = dc.Dimension(interpolation_exponent=0.75)
    colors.add_config(0,'white')
    colors.add_config(max_diff,'tomato')

    print("<h1>TagTracker vs Day-End Form</h1>")
    print("<h2>Discrepencies between calculated and reported leftovers</h2>")
    print( """Discrepencies between the number of leftovers calculated from TagTracker data
          vs leftovers reported in the day end form are possibly the greatest
          outstanding source of data error at the bike valet.  It is typically
          avoidable.  The discrepencies come from:
          <ol><li>Not checking out bikes.  This is easily avoided by doing audits
          through the day or even simply checking out any bikes at the end of
          the day that appear as leftover but are not leftover
          <li>Accidentally entering the wrong number on the day-end form (this seems unlikely)
          <li>If the laptop is shut down or disconnected from the internet very quickly at the
          end of the day, it can affect the system's ability to push updates to the
          back end server.
          <li>Historically, the pre-TagTracker data is of notoriously low quality.<p></p>
""")
    print("<table style=text-align:center>")
    print("<tr><th colspan=3 style='text-align:center'>Leftover bike mismatches</th></tr>")
    print("<tr><th>Date</th><th>As recorded<br>in TagTracker</th><th>As reported on<br>day-end form</th></tr>")

    for row in rows:
        style = f"style='{colors.css_bg_fg(abs(row.difference))}'"
        print(f"<tr><td style='{colors.css_bg_fg(abs(row.difference))}'>{row.date}</td><td {style}>{row.calculated}</td><td {style}>{row.reported}</td></tr>")
    print("</table>")

def fetch_data(ttdb:sqlite3.Connection) -> list:
    sel = """SELECT
        d.date,
        d.leftover AS reported,
        v.calculated,
        abs(v.calculated-d.leftover) AS  difference
    FROM day AS d
    JOIN (
        SELECT date, COUNT(time_in) AS calculated
        FROM visit
        WHERE time_out <= ""
        GROUP BY date
    ) AS v ON d.date = v.date
    WHERE v.calculated != d.leftover
    ORDER BY d.date DESC
    """
    rowdata = db.db_fetch(ttdb, sel)
    return rowdata


