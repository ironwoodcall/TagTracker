#!/usr/bin/env python3
"""TagTracker report that rolls up data by dateranges (week/month/etc).

Copyright (C) 2023-2024 Julias Hocking and Todd Glover

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
from datetime import datetime, timedelta

# import tt_util as ut
import common.tt_dbutil as db
import web_common as cc
from web_daterange_selector import generate_date_filter_form

DATERANGE_NAMES = {
    cc.WHAT_DATERANGE_WEEK: "Weeks",
    cc.WHAT_DATERANGE_MONTH: "Months",
    cc.WHAT_DATERANGE_QUARTER: "Quarters",
    cc.WHAT_DATERANGE_YEAR: "Years",
    cc.WHAT_DATERANGE_FOREVER: "All Data",
}


# FIXME: this can disappear when the _DateRangeRow goes away
class _DateRangeGroup:
    """Keep totals (int), average (float), max (int) or dates of occurence (str)."""

    def __init__(self, default=None):
        self.all_bikes = default
        self.regular_bikes = default
        self.oversize_bikes = default
        self.fullest = default
        self.reg529 = default


# FIXME: Can use a dict of start_date:MultiDayTotals instead of this.
# It's slightly different data but this set was not blessed or anything
class _DateRangeRow:
    """One table-row of daterange-summary data."""

    def __init__(self) -> None:
        self.label: str = ""
        self.start_date: str = ""
        self.end_date: str = ""
        self.days: int = 0
        self.hours: int = 0
        self.totals = _DateRangeGroup(0)
        self.means = _DateRangeGroup(0.0)
        self.maxs = _DateRangeGroup(0)
        self.when_max = _DateRangeGroup("")

    def in_daterange(self, date) -> bool:
        """Checks if date is in this daterange."""
        return self.start_date <= date <= self.end_date

    def aggregate(self, day_dbrow):
        """Aggregates this db row into this daterange summary."""
        self.days += 1
        self.hours += day_dbrow.hours
        self.totals.all_bikes += day_dbrow.parked_total
        self.totals.regular_bikes += day_dbrow.parked_regular
        self.totals.oversize_bikes += day_dbrow.parked_oversize
        self.totals.fullest += day_dbrow.max_total
        self.totals.reg529 += day_dbrow.registrations

        # Collect maximums (& date when maximum occurred)
        if day_dbrow.parked_total > self.maxs.all_bikes:
            self.maxs.all_bikes = day_dbrow.parked_total
            self.when_max.all_bikes = day_dbrow.date
        if day_dbrow.parked_regular > self.maxs.regular_bikes:
            self.maxs.regular_bikes = day_dbrow.parked_regular
            self.when_max.regular_bikes = day_dbrow.date
        if day_dbrow.parked_oversize > self.maxs.oversize_bikes:
            self.maxs.oversize_bikes = day_dbrow.parked_oversize
            self.when_max.oversize_bikes = day_dbrow.date
        if day_dbrow.max_total > self.maxs.fullest:
            self.maxs.fullest = day_dbrow.max_total
            self.when_max.fullest = day_dbrow.date
        if day_dbrow.registrations > self.maxs.reg529:
            self.maxs.reg529 = day_dbrow.registrations
            self.when_max.reg529 = day_dbrow.date

    def finalize(self):
        """Calculate the averages."""
        if self.days > 0:
            self.means.all_bikes = self.totals.all_bikes / self.days
            self.means.regular_bikes = self.totals.regular_bikes / self.days
            self.means.oversize_bikes = self.totals.oversize_bikes / self.days
            self.means.fullest = self.totals.fullest / self.days
            self.means.reg529 = self.totals.reg529 / self.days


def daterange_summary(
    ttdb,
    daterange_type: str = "",
    start_date: str = "",
    end_date: str = "",
    pages_back: int = 1,
):
    """Present a daterange summary page for a given daterange_type etc.

    If no daterange_type or just WHAT_DATERANGE, does them all.
    """

    orgsite_id = 1  # FIXME hardcoded orgsite_id

    # Fetch date range limits from the database
    db_start_date, db_end_date = db.fetch_date_range_limits(ttdb, orgsite_id=orgsite_id)

    # Adjust start_date and end_date based on fetched limits
    start_date = max(start_date or db_start_date, db_start_date)
    end_date = min(end_date or db_end_date, db_end_date)

    _daterange_summary_pagetop(start_date,end_date,pages_back)

    self_url = cc.selfref(
        what=cc.WHAT_DATERANGE_CUSTOM,
        start_date=start_date,
        end_date=end_date,
        pages_back=pages_back,
    )
    print("<br>")
    print(
        generate_date_filter_form(
            self_url, default_start_date=start_date, default_end_date=end_date
        )
    )

    print("<br><br><br>")

    all_dateranges = [
        cc.WHAT_DATERANGE_FOREVER,
        cc.WHAT_DATERANGE_YEAR,
        cc.WHAT_DATERANGE_QUARTER,
        cc.WHAT_DATERANGE_MONTH,
        cc.WHAT_DATERANGE_WEEK,
    ]
    if not daterange_type or daterange_type == cc.WHAT_DATERANGE:
        dateranges_list = all_dateranges
    else:
        dateranges_list = [daterange_type]

    for daterange in dateranges_list:
        if daterange not in all_dateranges and daterange != cc.WHAT_DATERANGE_CUSTOM:
            print(f"<br><br><pre>unknown daterange '{daterange}'</pre><br><br>")
            continue
        _daterange_summary_table(ttdb, start_date, end_date, daterange, pages_back)
        print("<br><br><br>")

def _daterange_summary_pagetop(start_date,end_date,pages_back: int = 1):
    print(f"<h1>{cc.titleize(f'<br>Summaries from {start_date} to {end_date}')}</h1>")
    # print(f"<h2>Summary of data from {start_date} to {end_date}</h2>")
    print(f"{cc.main_and_back_buttons(pages_back)}<br>")


def _fetch_daterange_summary_rows(
    ttdb, range_start, range_end, daterange_type
) -> list[_DateRangeRow]:
    """Fetch db data to make list of daterange summary rows.

    Fetch is limited to the given date range (if given)
    List will be sorted by label
    """
    orgsite_id = 1  # FIXME: hardcoded orgsite_id
    range_start = range_start if range_start else "0000-00-00"
    range_end = range_end if range_end else "9999-99-99"

    sql = f"""
        SELECT
            date,
            ROUND((julianday(time_closed) - julianday(time_open)) * 24, 2) AS hours,
            num_parked_regular parked_regular,
            num_parked_oversize parked_oversize,
            num_parked_combined parked_total,
            num_fullest_regular max_reg,
            num_fullest_oversize max_over,
            num_fullest_combined max_total,
            bikes_registered registrations
        FROM day
        WHERE date >= '{range_start}' and date <= '{range_end}'
            AND orgsite_id = {orgsite_id}
        ORDER BY date DESC
    """
    dbrows = db.db_fetch(ttdb, sql)
    if not dbrows:
        return []

    # Create _DateRangeRow objects and initialize variables
    daterange_rows = []
    current_daterange = None

    # Iterate through all dbrows
    for row in dbrows:
        date = row.date

        # If it's a new daterange, create a new _DateRangeRow
        if current_daterange is None or not current_daterange.in_daterange(date):
            if current_daterange is not None and current_daterange.days:
                daterange_rows.append(
                    current_daterange
                )  # Append the previous daterange
            current_daterange = _DateRangeRow()
            if daterange_type == cc.WHAT_DATERANGE_CUSTOM:
                (
                    current_daterange.start_date,
                    current_daterange.end_date,
                    current_daterange.label,
                ) = (range_start, range_end, "Custom date span")
            else:
                (
                    current_daterange.start_date,
                    current_daterange.end_date,
                    current_daterange.label,
                ) = _daterange_params(date, daterange_type=daterange_type)

        # Aggregate statistics for the current daterange
        current_daterange.aggregate(row)

    # Append the last daterange after the loop ends
    if current_daterange is not None and current_daterange.days:
        daterange_rows.append(current_daterange)

    # Calculate means for values of the dateranges
    for p in daterange_rows:
        p.finalize()

    return daterange_rows


def _daterange_params(onedate, daterange_type) -> tuple[str, str, str]:
    """Calculate parameters for one daterange.

    On entry onedate is a date anywhere in a desired daterange.

    Returns
        label for the daterange. E.g. for 2024-02-22
            Y 2024
            M 2024-02
            Q 2024-Q1 (starts Jan/Apr/Jul/Sep 1)
            W 2024-02-19 (starts a monday)
        first date in the daterange (YYY-MM-DD)
        last date in the daterange (YYYY-MM-DD)

    """

    # Convert input date string to datetime object
    date = datetime.strptime(onedate, "%Y-%m-%d")

    # Determine start and end dates of the daterange based on daterange type
    if daterange_type == cc.WHAT_DATERANGE_FOREVER:
        start_date = "0000-00-00"  # Sorts less than any date string
        end_date = "9999-99-99"  # Sorts greater than any date string
        label = "All data"
    elif daterange_type == cc.WHAT_DATERANGE_YEAR:
        start_date = date.replace(month=1, day=1).strftime("%Y-%m-%d")
        end_date = date.replace(month=12, day=31).strftime("%Y-%m-%d")
        label = f"Y {start_date[:4]}"
    elif daterange_type == cc.WHAT_DATERANGE_QUARTER:
        quarter_start_month = ((date.month - 1) // 3) * 3 + 1
        start_date = date.replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
        end_date = (
            date.replace(month=quarter_start_month + 2) + timedelta(days=31)
        ).replace(day=1) - timedelta(days=1)
        end_date = end_date.strftime("%Y-%m-%d")
        label = f"Q {date.year}-Q{(quarter_start_month - 1) // 3 + 1}"
    elif daterange_type == cc.WHAT_DATERANGE_MONTH:
        month_start = date.replace(day=1)
        start_date = month_start.strftime("%Y-%m-%d")
        sometime_next_month = month_start + timedelta(days=32)
        end_date = sometime_next_month.replace(day=1).strftime("%Y-%m-%d")
        label = f"M {start_date[:7]}"
    elif daterange_type == cc.WHAT_DATERANGE_WEEK:
        start_date = (date - timedelta(days=date.weekday())).strftime("%Y-%m-%d")
        end_date = (date + timedelta(days=6 - date.weekday())).strftime("%Y-%m-%d")
        label = f"W {start_date}"
    else:
        raise ValueError(f"Invalid daterange_type {daterange_type}")

    # Return start_date, end_date, and label
    return start_date, end_date, label


def _daterange_summary_table_top(
    daterange_type, start_date: str = "", end_date: str = ""
):
    """Print the table def and header row for one daterange-summaries table."""
    if daterange_type == cc.WHAT_DATERANGE_CUSTOM:
        name = f"{start_date} to {end_date}"
    else:
        name = DATERANGE_NAMES[daterange_type]
    print("<table class='general_table'>")
    print(f"<tr><th colspan=17>Summary of {name}</th></tr>")
    print("<style>td {text-align: right;}</style>")

    print(
        "<tr>"
        "<th rowspan=2>Period</th>"
        "<th colspan=2>Open</th>"
        "<th colspan=4>Total</th>"
        "<th colspan=5>Day Average</th>"
        "<th colspan=5>Day Maximum</th>"
        "</tr>"
    )

    print(
        "<tr>"
        "<th>Days</th>"
        "<th>Hours</th>"
        "<th>All<br>bikes</th>"
        "<th>Reglr<br>bikes</th>"
        "<th>Ovrsz<br>bikes</th>"
        "<th>Bike<br>reg</th>"
        "<th>All<br>bikes</th>"
        "<th>Reglr<br>bikes</th>"
        "<th>Ovrsz<br>bikes</th>"
        "<th>Most<br>full</th>"
        "<th>Bike<br>reg</th>"
        "<th>All<br>bikes</th>"
        "<th>Reglr<br>bikes</th>"
        "<th>Ovrsz<br>bikes</th>"
        "<th>Most<br>full</th>"
        "<th>Bike<br>reg</th>"
        "</th>"
    )


def _one_daterange_summary_row(pd: _DateRangeRow, pages_back: int):
    """Print one table row in a dateranges table."""

    # Calculate links to day detail for days of maximum values
    max_all_bikes_link = cc.selfref(cc.WHAT_ONE_DAY, qdate=pd.when_max.all_bikes)
    max_regular_bikes_link = cc.selfref(
        cc.WHAT_ONE_DAY, qdate=pd.when_max.regular_bikes
    )
    max_oversize_bikes_link = cc.selfref(
        cc.WHAT_ONE_DAY, qdate=pd.when_max.oversize_bikes
    )
    max_fullest_link = cc.selfref(cc.WHAT_ONE_DAY, qdate=pd.when_max.fullest)
    max_reg529_link = cc.selfref(cc.WHAT_ONE_DAY, qdate=pd.when_max.reg529)

    TD = "<td  style='text-align: right;'>"
    print(
        "<tr>"
        f"{TD}{pd.label}</td>"
        f"{TD}{pd.days}</td>"
        f"{TD}{pd.hours:,.1f}</td>"
        f"{TD}{pd.totals.all_bikes:,}</td>"
        f"{TD}{pd.totals.regular_bikes:,}</td>"
        f"{TD}{pd.totals.oversize_bikes:,}</td>"
        f"{TD}{pd.totals.reg529:,}</td>"
        f"{TD}{pd.means.all_bikes:,.1f}</td>"
        f"{TD}{pd.means.regular_bikes:,.1f}</td>"
        f"{TD}{pd.means.oversize_bikes:,.1f}</td>"
        f"{TD}{pd.means.fullest:,.1f}</td>"
        f"{TD}{pd.means.reg529:,.1f}</td>"
        f"{TD}<a href={max_all_bikes_link}>{pd.maxs.all_bikes:,}</a></td>"
        f"{TD}<a href={max_regular_bikes_link}>{pd.maxs.regular_bikes:,}</a></td>"
        f"{TD}<a href={max_oversize_bikes_link}>{pd.maxs.oversize_bikes:,}</a></td>"
        f"{TD}<a href={max_fullest_link}>{pd.maxs.fullest:,}</a></td>"
        f"{TD}<a href={max_reg529_link}>{pd.maxs.reg529:,}</a></td>"
        # f"<td>{pd}</td>"
        "</tr>"
    )


def _daterange_summary_table(
    ttdb: sqlite3.Connection,
    range_start: str,
    range_end: str,
    daterange_type: str,
    pages_back: int,
):
    """Calculate and print a table for a given daterange type.

    Looks at all the dateranges within the given date range;
    either start or end can be empty.
    """

    daterange_rows = _fetch_daterange_summary_rows(
        ttdb,
        range_start=range_start,
        range_end=range_end,
        daterange_type=daterange_type,
    )

    if not daterange_rows:
        return
    _daterange_summary_table_top(daterange_type, range_start, range_end)

    for onerow in daterange_rows:
        onerow: _DateRangeRow
        _one_daterange_summary_row(onerow, pages_back=pages_back)

    # table bottom
    print("</table>")
