#!/usr/bin/env python3
"""Estimate how many more bikes to expect.

Call (as itself) as:
    self    bikes_so_far, as_of_when, dow, closing_time
    where
        bikes_so_far: is how many bikes in by as_of_when (mandatory)
        as_of_when: is the time for which the estimate is made, HH:MM, H:MM, HMM
            (default if missing or "": now)
        dow: ISO day of week (1=Mo..7=Su), YYYY-MM-DD, "today" or "yesterday"
            (default if missing or "": today)
        closing_time: HHMM of time the valet closes day of estimate
            (default if missing or "": will try to determine using config functions)

Or call in a CGI script, and the parameters are read from QUERY_STRING.
The parameter names are the same as above.

Copyright (C) 2023 Julias Hocking

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

import urllib.request
import os
import sys
import re
import statistics

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
import tt_conf as cfg
import tt_util as ut
from tt_time import VTime
import tt_dbutil as db


# These are model states
INCOMPLETE = "incomplete"  # initialized but not ready to use
READY = "ready"  # model is ready to use
OK = "ok"  # model has been used to create a guess OK
ERROR = "error"  # the model is unusable, in an error state


class SimpleModel:
    """A simple model using mean & median for similar days."""

    def __init__(self) -> None:
        self.befores = None
        self.afters = None
        self.match_tolerance = None
        self.matched_afters = []
        self.num_points = None
        self.trim_tolerance = None
        self.trimmed_afters = []
        self.num_discarded = None

        self.min = None
        self.max = None
        self.mean = None
        self.median = None

        self.commentary = []
        self.error = ""
        self.state = INCOMPLETE

    def _discard_outliers(
        self,
    ) -> None:
        """Create trimmed_data by discarding outliers."""
        # For 2 or fewer data points, the idea of outliers means nothing.
        if len(self.matched_afters) <= 2:
            self.trimmed_afters = self.matched_afters
            self.num_discarded = self.num_points - len(self.trimmed_afters)
            return
        # Make new list, discarding outliers.
        mean = statistics.mean(self.matched_afters)
        std_dev = statistics.stdev(self.matched_afters)
        if std_dev == 0:
            self.trimmed_afters = self.matched_afters
            self.num_discarded = self.num_points - len(self.trimmed_afters)
            return

        z_scores = [(x - mean) / std_dev for x in self.matched_afters]
        self.trimmed_afters = [
            self.matched_afters[i]
            for i in range(len(self.matched_afters))
            if abs(z_scores[i]) <= self.trim_tolerance
        ]
        self.num_discarded = self.num_points - len(self.trimmed_afters)

    def create_model(
        self,
        befores: list[int],
        afters: list[int],
        tolerance: float,
        z_threshold: float,
    ):
        if self.state == ERROR:
            return
        self.befores = befores
        self.afters = afters
        self.match_tolerance = tolerance
        self.trim_tolerance = z_threshold
        self.state = READY

    def guess(self, bikes_so_far: int):
        """Calculate results for our simple mean & median) model."""
        if self.state == ERROR:
            return
        if self.state not in [READY, OK]:
            self.state = ERROR
            self.error = "Can not guess when model not in ready state."
            return

        # Find data points that match our bikes-so-far
        # values within this dist are considered same
        self.matched_afters = []
        for i, bikes_so_far in enumerate(self.befores):
            if abs(bikes_so_far - bikes_so_far) <= self.match_tolerance:
                self.matched_afters.append(self.afters[i])
        self.num_points = len(self.matched_afters)

        # Discard outliers (z score > z cutodd)
        self._discard_outliers()

        # Check for no data.
        if not self.matched_afters:
            self.error = "No matching data"
            self.state = ERROR
            return

        # Calculate return value statistics
        # (Both data and trimmed_data now have length > 0)
        self.min = min(self.trimmed_afters)
        self.max = max(self.trimmed_afters)
        self.mean = int(statistics.mean(self.trimmed_afters))
        self.median = int(statistics.median(self.trimmed_afters))
        self.state = OK

    def result_msg(self) -> list[str]:
        """Return list of strings as long message."""

        if self.state != OK:
            lines = [
                "Simple model prediction, averaging similar previous days:",
                "    Can't estimate because: {self.error}",
            ]
            return lines

        one_line = f"Simple model prediction, averaging {self.num_points} similar previous {ut.plural(self.num_points,'day')}"
        if self.num_discarded:
            one_line = f"{one_line} ({self.num_discarded} {ut.plural(self.num_discarded,'outlier')} discarded)"
        lines = [f"{one_line}:"]

        mean_median = [self.mean, self.median]
        mean_median.sort()
        if mean_median[0] == mean_median[1]:
            mm_str = f"best guess: {mean_median[0]}"
        else:
            mm_str = f"best guesses: {mean_median[0]} [median] or {mean_median[1]} [mean]"

        if self.max == self.min:
            lines.append(f"    Expect {self.min} more bikes")
        else:
            lines.append(
                f"    Expect {self.min} to {self.max} more bikes ({mm_str})"
            )

        return lines


class LRModel:
    """A linear regression model using least squares."""

    def __init__(self):
        self.commentary = []
        self.state = INCOMPLETE
        self.error = None

        self.num_points = None
        self.slope = None
        self.intercept = None
        self.r_squared = None

        self.further_bikes = None

    def calculate_model(self, xy_data):
        if self.state == ERROR:
            return

        self.num_points = len(xy_data)
        self.commentary.append(
            f"Initializing LRModel with {self.num_points} data points"
        )
        if self.num_points < 2:
            self.commentary.append("Not enough data points to continue")
            self.state = ERROR
            return

        if [x for x, _ in xy_data] == [0] * len(xy_data):
            self.error = "all x values are 0"
            self.state = ERROR
            return

        sum_x, sum_y, sum_xy, sum_x_squared, sum_y_squared = 0, 0, 0, 0, 0

        for x, y in xy_data:
            sum_x += x
            sum_y += y
            sum_xy += x * y
            sum_x_squared += x**2
            sum_y_squared += y**2

        mean_x = sum_x / self.num_points
        mean_y = sum_y / self.num_points

        try:
            self.slope = (self.num_points * sum_xy - sum_x * sum_y) / (
                self.num_points * sum_x_squared - sum_x**2
            )
        except ZeroDivisionError:
            self.error = f"DIV/0 in slope calculation."
            self.state = ERROR
            return
        self.intercept = mean_y - self.slope * mean_x

        # Calculate R-squared
        ss_total = sum((y - mean_y) ** 2 for x, y in xy_data)
        ss_residual = sum(
            (y - (self.slope * x + self.intercept)) ** 2 for x, y in xy_data
        )
        if ss_residual == 0:
            self.r_squared = 1.0
        elif ss_total == 0:
            self.r_squared = "DIV/0"
        else:
            self.r_squared = 1 - (ss_residual / ss_total)

        self.commentary.append(
            f"Model ok: intercept: {self.intercept}, slope: {self.slope}, R^2: {self.r_squared}"
        )
        self.state = READY

    def guess(self, x: float) -> float:
        # Predict y based on the linear regression equation
        if self.state == ERROR:
            return
        if self.state not in [READY, OK]:
            self.state = ERROR
            self.error = "Model not ready, can not guess"
            return
        self.further_bikes = round(self.slope * x + self.intercept)
        self.state = OK
        return

    def result_msg(self) -> list[str]:
        """Return list of strings as long message."""

        lines = [
            f"Linear regression model prediction, based on {self.num_points} data points:"
        ]
        if self.state != OK:
            lines.append(f"    Can't estimate because: {self.error}")
            return lines
        rs = (
            "unknown"
            if not isinstance(self.r_squared, (float, int))
            else f"{round(self.r_squared*100)}%"
        )
        lines = lines + [
            f"    Expect {self.further_bikes} more {ut.plural(self.further_bikes,'bike')} with {rs} confidence."
        ]

        return lines


class Estimator:
    """Data and methods to estimate how many more bikes to expect."""

    def __init__(
        self,
        bikes_so_far="",
        as_of_when="",
        dow_in="",
        closing_time="",
    ) -> None:
        """Set up the inputs and results vars.

        Inputs are thoroughly checked and default values figured out.

        This will make guesses about any missing inputs
        except the number of bikes so far.
        """

        # This will be INCOMPLETE, OK or ERROR
        self.state = INCOMPLETE
        # This stays empty unless set to an error message.
        self.error = ""  # Error message
        # These are inputs
        self.bikes_so_far = None
        self.dow = None
        self.as_of_when = None
        self.closing_time = None
        # This is the raw data
        self.befores = []
        self.afters = []
        # These are for the resulting 'simple model' estimate
        self.simple_model = SimpleModel()
        # This is for the linear regression model
        self.lr_model = LRModel()

        # Now process the inputs from passed-in values.
        bikes_so_far = str(bikes_so_far).strip()
        if not bikes_so_far.isdigit():
            self.error = "Missing or bad bikes_so_far parameter."
            self.state = ERROR
            return
        self.bikes_so_far = int(bikes_so_far)

        as_of_when = as_of_when if as_of_when else "now"
        self.as_of_when = VTime(as_of_when)
        if not self.as_of_when:
            self.error = "Bad as_of_when parameter."
            self.state = ERROR
            return

        # dow is 1..7; dow_date is most recent date of that dow,
        # in case there is no closing time given, we will have a
        # date on which to base the closing time
        dow_in = dow_in if dow_in else "today"
        dow_date = None
        maybe_dow = ut.dow_int(dow_in)
        if maybe_dow:
            dow_in = maybe_dow
        if str(dow_in).strip() in ["1", "2", "3", "4", "5", "6", "7"]:
            self.dow = int(dow_in)
            dow_date = ut.most_recent_dow(self.dow)
        else:
            dow_date = ut.date_str(dow_in)
            if dow_date:
                self.dow = ut.dow_int(dow_date)
            else:
                self.error = "Bad dow parameter."
                self.state = ERROR
                return

        # closing time, if not given, will be most recent day that matches
        # the given day of the week, or of the date if that was given as dow.
        if not closing_time:
            closing_time = cfg.valet_hours(dow_date)[1]
        self.closing_time = VTime(closing_time)  # Closing time today
        if not self.closing_time:
            self.error = "Missing or bad closing_time parameter."
            self.state = ERROR
            return

    def _sql_str(self) -> str:
        """Build SQL query."""
        if self.dow in [6, 7]:
            dow_set = f"({self.dow})"
        else:
            dow_set = "(1,2,3,4,5)"
        today = ut.get_date("today")
        sql = f"""
            WITH all_dates AS (
                SELECT DISTINCT date
                FROM visit
                WHERE date != "{today}"
            )
            SELECT
                day.date AS date,
                COALESCE(v1.before, 0) AS before,
                COALESCE(v2.after, 0) AS after
            FROM day
            LEFT JOIN (
                SELECT
                    all_dates.date,
                    COUNT(visit.date) AS before
                FROM
                    all_dates
                LEFT JOIN
                    visit ON all_dates.date = visit.date
                        AND visit.time_in <= "{self.as_of_when}"
                GROUP BY
                    all_dates.date
            ) AS v1 ON day.date = v1.date
            LEFT JOIN (
                SELECT
                    all_dates.date,
                    COUNT(visit.date) AS after
                FROM all_dates
                LEFT JOIN
                    visit ON all_dates.date = visit.date
                        AND visit.time_in > "{self.as_of_when}"
                GROUP BY
                    all_dates.date
            ) AS v2 ON day.date = v2.date
            WHERE
                day.weekday IN {dow_set}
                AND day.time_closed = "{self.closing_time}"
            ORDER BY
                day.date;
        """
        return sql

    def _fetch_raw_data(self) -> None:
        """Get raw data from the database into self.befores, self.afters."""
        # Collect data from database
        # pylint: disable-next=invalid-name
        DBFILE = "../data/cityhall_bikevalet.db"
        if not os.path.exists(DBFILE):
            self.error = "Database not found"
            self.state = ERROR
            return

        database = db.db_connect(DBFILE)
        sql = self._sql_str()
        data_rows = db.db_fetch(database, sql, ["date", "before", "after"])
        if not data_rows:
            self.error = "No data returned from database."
            self.state = ERROR
            return

        self.befores = [int(r.before) for r in data_rows]
        self.afters = [int(r.after) for r in data_rows]

    def guess(self) -> None:
        """Set self result info from the database."""

        # Get data from the database
        self._fetch_raw_data()
        if self.state == ERROR:
            return

        # Rounding for how close a historic bikes_so_far
        # is to the requested to be considered the same
        VARIANCE = 10  # pylint: disable=invalid-name
        # Z score at which to eliminate a data point an an outlier
        Z_CUTOFF = 2.5  # pylint: disable=invalid-name
        self.simple_model.create_model(
            self.befores, self.afters, VARIANCE, Z_CUTOFF
        )
        self.simple_model.guess(self.bikes_so_far)

        # Calculate using linear regression.
        self.lr_model.calculate_model(list(zip(self.befores, self.afters)))
        self.lr_model.guess(self.bikes_so_far)

    def result_msg(self) -> list[str]:
        """Return list of strings as long message."""

        lines = []
        if self.state == ERROR:
            lines.append(f"Can't estimate because: {self.error}")
            return lines

        if self.dow == 6:
            dayname = "Saturday"
        elif self.dow == 7:
            dayname = "Sunday"
        else:
            dayname = "weekday"

        lines = ["How many more bikes?"]
        lines += [""] + [
            f"With {self.bikes_so_far} {ut.plural(self.bikes_so_far,'bike')} "
            f"parked by {self.as_of_when.short} "
            f"on a typical {dayname}, closing at {self.closing_time}:"
        ]
        if self.as_of_when < "13:30":
            lines += "(Keep in mind that estimates early in the day will be of low quality)"

        lines += [""] + self.simple_model.result_msg()
        lines += [""] + self.lr_model.result_msg()

        return lines


def get_estimate_via_url(
    bikes_so_far: int,
    as_of_when="",
    dow: int = None,
    closing_time=""
) -> list[str]:
    """Call estimator URL to get the estimate.

    This is presumably what one would call if the database
    is not on the same machine.
    """
    # Call Estimator to clean up the parameters.
    est = Estimator(bikes_so_far, as_of_when, dow, closing_time)
    if not cfg.ESTIMATOR_URL_BASE:
        return ["No estimator URL defined"]
    url_parms = (
        f"bikes_so_far={est.bikes_so_far}&as_of_when={est.as_of_when}"
        f"&dow={est.dow}&as_of_when={est.as_of_when}&closing_time={est.closing_time}"
    )
    url = f"{cfg.ESTIMATOR_URL_BASE}?{url_parms}"
    ##ut.squawk(f"{url=}")
    try:
        response = urllib.request.urlopen(url)
        data = response.read()
        decoded_data = data.decode("utf-8")
    except urllib.error.URLError:
        return ["URLError return"]

    return decoded_data.splitlines()


def _init_from_cgi() -> Estimator:
    """Read initialization parameters from CGI env var.

    CGI parameters: as at top of file.
        bikes_so_far, dow,as_of_when,closing_time

    """
    query_str = ut.untaint(os.environ.get("QUERY_STRING", ""))
    query_parms = urllib.parse.parse_qs(query_str)
    bikes_so_far = query_parms.get("bikes_so_far", [""])[0]
    dow = query_parms.get("dow", [""])[0]
    as_of_when = query_parms.get("as_of_when", [""])[0]
    closing_time = query_parms.get("closing_time", [""])[0]

    return Estimator(bikes_so_far, as_of_when, dow, closing_time)


def _init_from_args() -> Estimator:
    my_args = sys.argv[1:] + ["", "", "", "", "", "", "", ""]
    return Estimator(my_args[0], my_args[1], my_args[2], my_args[3])


if __name__ == "__main__":
    estimate: Estimator
    is_cgi = bool(os.environ.get("REQUEST_METHOD"))
    if is_cgi:
        print("Content-type: text/plain\n")
        estimate = _init_from_cgi()
    else:
        estimate = _init_from_args()

    if estimate.state != ERROR:
        estimate.guess()

    for line in estimate.result_msg():
        print(line)
