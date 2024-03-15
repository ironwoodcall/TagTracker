#!/usr/bin/env python3
"""TagTracker report that rolls up data by periods (week/month/etc).

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
import os

# import tt_util as ut
import tt_dbutil as db
import cgi_common as cc

PERIOD_NAMES = {
    cc.WHAT_PERIOD_WEEK: "Weeks",
    cc.WHAT_PERIOD_MONTH: "Months",
    cc.WHAT_PERIOD_QUARTER: "Quarters",
    cc.WHAT_PERIOD_YEAR: "Years",
    cc.WHAT_PERIOD_FOREVER: "All Data"
}


class PeriodGroup:
    """Keep totals (int), average (float), max (int) or dates of occurence (str)."""

    def __init__(self, default=None):
        self.all_bikes = default
        self.regular_bikes = default
        self.oversize_bikes = default
        self.fullest = default
        self.reg529 = default


class PeriodRow:
    """One table-row of period-summary data."""

    def __init__(self) -> None:
        self.label: str = ""
        self.start_date: str = ""
        self.end_date: str = ""
        self.days: int = 0
        self.hours: int = 0
        self.totals = PeriodGroup(0)
        self.means = PeriodGroup(0.0)
        self.maxs = PeriodGroup(0)
        self.when_max = PeriodGroup("")

    def in_period(self, date) -> bool:
        """Checks if date is in this period."""
        return self.start_date <= date <= self.end_date

    def aggregate(self, day_dbrow):
        """Aggregates this db row into this period summary."""
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


def period_summary(
    ttdb,
    period_type: str = "",
    start_date: str = "",
    end_date: str = "",
    pages_back: int = 1,
):
    """Present a period summary page for a given period_type etc.

    If no period_type or just WHAT_PERIOD, does them all.
    """

    _period_summary_pagetop(pages_back)

    print("<br><br><br>")

    all_periods = [
        cc.WHAT_PERIOD_FOREVER,
        cc.WHAT_PERIOD_YEAR,
        cc.WHAT_PERIOD_QUARTER,
        cc.WHAT_PERIOD_MONTH,
        cc.WHAT_PERIOD_WEEK,
    ]
    if not period_type or period_type == cc.WHAT_PERIOD:
        periods_list = all_periods
    else:
        periods_list = [period_type]

    for period in periods_list:
        if period not in all_periods:
            print(f"<br><br><pre>unknown period '{period}'</pre><br><br>")
            continue
        _period_summary_table(ttdb, start_date, end_date, period, pages_back)
        print("<br><br><br>")


def _period_summary_pagetop(pages_back: int = 1):
    print(f"<h1>{cc.titleize(': Summaries')}</h1>")
    print(f"{cc.main_and_back_buttons(pages_back)}<br>")


def _fetch_period_summary_rows(
    ttdb, range_start, range_end, period_type
) -> list[PeriodRow]:
    """Fetch db data to make list of period summary rows.

    Fetch is limited to the given date range (if given)
    List will be sorted by label
    """
    range_start = range_start if range_start else "0000-00-00"
    range_end = range_end if range_end else "9999-99-99"

    sql = f"""SELECT
        date,
        ROUND((julianday(time_closed) - julianday(time_open)) * 24, 2) AS hours,
        parked_regular, parked_oversize,parked_total,
        max_reg, max_over, max_total,
        registrations
        FROM day
        WHERE date >= '{range_start}' and date <= '{range_end}'
        ORDER BY date
    """
    dbrows = db.db_fetch(ttdb, sql)
    if not dbrows:
        return []

    # Create PeriodRow objects and initialize variables
    period_rows = []
    current_period = None

    # Iterate through all dbrows
    for row in dbrows:
        date = row.date

        # If it's a new period, create a new PeriodRow
        if current_period is None or not current_period.in_period(date):
            if current_period is not None and current_period.days:
                period_rows.append(current_period)  # Append the previous period
            current_period = PeriodRow()
            (
                current_period.start_date,
                current_period.end_date,
                current_period.label,
            ) = _period_params(date, period_type=period_type)

        # Aggregate statistics for the current period
        current_period.aggregate(row)

    # Append the last period after the loop ends
    if current_period is not None and current_period.days:
        period_rows.append(current_period)

    # Calculate means for values of the periods
    for p in period_rows:
        p.finalize()

    return period_rows


def _period_params(onedate, period_type) -> tuple[str, str, str]:
    """Calculate parameters for one period.

    On entry onedate is a date anywhere in a desired period.

    Returns
        label for the period. E.g. for 2024-02-22
            Y 2024
            M 2024-02
            Q 2024-Q1 (starts Jan/Apr/Jul/Sep 1)
            W 2024-02-19 (starts a monday)
        first date in the period (YYY-MM-DD)
        last date in the period (YYYY-MM-DD)

    """

    # Convert input date string to datetime object
    date = datetime.strptime(onedate, "%Y-%m-%d")

    # Determine start and end dates of the period based on period type
    if period_type == cc.WHAT_PERIOD_FOREVER:
        start_date = "0000-00-00" # Sorts less than any date string
        end_date = "9999-99-99"  # Sorts greater than any date string
        label = "All data"
    elif period_type == cc.WHAT_PERIOD_YEAR:
        start_date = date.replace(month=1, day=1).strftime("%Y-%m-%d")
        end_date = date.replace(month=12, day=31).strftime("%Y-%m-%d")
        label = f"Y {start_date[:4]}"
    elif period_type == cc.WHAT_PERIOD_QUARTER:
        quarter_start_month = ((date.month - 1) // 3) * 3 + 1
        start_date = date.replace(month=quarter_start_month, day=1).strftime("%Y-%m-%d")
        end_date = (
            date.replace(month=quarter_start_month + 2) + timedelta(days=31)
        ).replace(day=1) - timedelta(days=1)
        end_date = end_date.strftime("%Y-%m-%d")
        label = f"Q {date.year}-Q{(quarter_start_month - 1) // 3 + 1}"
    elif period_type == cc.WHAT_PERIOD_MONTH:
        month_start = date.replace(day=1)
        start_date = month_start.strftime("%Y-%m-%d")
        sometime_next_month = month_start + timedelta(days=32)
        end_date = sometime_next_month.replace(day=1).strftime("%Y-%m-%d")
        label = f"M {start_date[:7]}"
    elif period_type == cc.WHAT_PERIOD_WEEK:
        start_date = (date - timedelta(days=date.weekday())).strftime("%Y-%m-%d")
        end_date = (date + timedelta(days=6 - date.weekday())).strftime("%Y-%m-%d")
        label = f"W {start_date}"
    else:
        raise ValueError(f"Invalid period_type {period_type}")

    # Return start_date, end_date, and label
    return start_date, end_date, label


def _period_summary_table_top(period_type):
    """Print the table def and header row for one period-summaries table."""
    print("<table class='general_table'>")
    print(
        f"<tr><th colspan=17>Summary of {PERIOD_NAMES[period_type]}</th></tr>"
    )
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
        "<th>529<br>reg</th>"
        "<th>All<br>bikes</th>"
        "<th>Reglr<br>bikes</th>"
        "<th>Ovrsz<br>bikes</th>"
        "<th>Most<br>full</th>"
        "<th>529<br>reg</th>"
        "<th>All<br>bikes</th>"
        "<th>Reglr<br>bikes</th>"
        "<th>Ovrsz<br>bikes</th>"
        "<th>Most<br>full</th>"
        "<th>529<br>reg</th>"
        "</th>"
    )


def _one_period_summary_row(pd: PeriodRow, pages_back: int):
    """Print one table row in a periods table."""

    # Calculate links to day detail for days of maximum values
    max_all_bikes_link = cc.selfref(
        cc.WHAT_ONE_DAY,
        qdate=pd.when_max.all_bikes
    )
    max_regular_bikes_link = cc.selfref(
        cc.WHAT_ONE_DAY,
        qdate=pd.when_max.regular_bikes
    )
    max_oversize_bikes_link = cc.selfref(
        cc.WHAT_ONE_DAY,
        qdate=pd.when_max.oversize_bikes
    )
    max_fullest_link = cc.selfref(
        cc.WHAT_ONE_DAY,
        qdate=pd.when_max.fullest
    )
    max_reg529_link = cc.selfref(
        cc.WHAT_ONE_DAY,
        qdate=pd.when_max.reg529
    )

    TD="<td  style='text-align: right;'>"
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


def _period_summary_table(
    ttdb: sqlite3.Connection,
    range_start: str,
    range_end: str,
    period_type: str,
    pages_back: int,
):
    """Calculate and print a table for a given period type.

    Looks at all the periods within the given date range;
    either start or end can be empty.
    """

    period_rows = _fetch_period_summary_rows(
        ttdb, range_start=range_start, range_end=range_end, period_type=period_type
    )

    if not period_rows:
        return
    _period_summary_table_top(period_type)

    for onerow in period_rows:
        onerow: PeriodRow
        _one_period_summary_row(onerow, pages_back=pages_back)

    # table bottom
    print("</table>")
