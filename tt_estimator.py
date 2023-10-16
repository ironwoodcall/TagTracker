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

import urllib.request
import os
import sys
import math
import statistics

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
import tt_conf as cfg
import tt_util as ut
from tt_time import VTime
import tt_dbutil as db
import tt_estimator_rf as rf

# These are model states
INCOMPLETE = "incomplete"  # initialized but not ready to use
READY = "ready"  # model is ready to use
OK = "ok"  # model has been used to create a guess OK
ERROR = "error"  # the model is unusable, in an error state

PRINT_WIDTH = 47


def _format_measure(m):
    """Format a regression measure as a string."""
    if m is None or m != m or not isinstance(m, (float, int)):
        return "?"
    return f"{m:.2f}"


class SimpleModel:
    """A simple model using mean & median for similar days."""

    def __init__(self) -> None:
        self.raw_befores = None
        self.raw_afters = None
        self.raw_dates = []
        self.match_tolerance = None
        self.matched_afters = []
        self.matched_dates = []
        self.num_points = None
        self.trim_tolerance = None
        self.trimmed_afters = []
        self.discarded_afters = []
        self.discarded_dates = []
        self.num_discarded = None

        self.min = None
        self.max = None
        self.mean = None
        self.median = None

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
        dates: list[str],
        befores: list[int],
        afters: list[int],
        tolerance: float,
        z_threshold: float,
    ):
        if self.state == ERROR:
            return
        self.raw_dates = dates
        self.raw_befores = befores
        self.raw_afters = afters
        self.match_tolerance = tolerance
        self.trim_tolerance = z_threshold
        self.state = READY

    def guess(self, bikes_so_far: int):
        """Calculate results for our simple mean & median) model."""
        if self.state == ERROR:
            return
        if self.state not in [READY, OK]:
            self.state = ERROR
            self.error = "can not guess, model not in ready state."
            return

        # Find data points that match our bikes-so-far
        # values within this dist are considered same
        self.matched_afters = []
        for i, this_bikes_so_far in enumerate(self.raw_befores):
            if abs(bikes_so_far - this_bikes_so_far) <= self.match_tolerance:
                self.matched_afters.append(self.raw_afters[i])
        self.num_points = len(self.matched_afters)

        # Discard outliers (z score > z cutodd)
        self._discard_outliers()

        # Check for no data.
        if not self.matched_afters:
            self.error = "no similar dates"
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

        lines = ["Using a model that averages roughly similar dates:"]
        if self.state != OK:
            lines += [f"    Can't estimate because: {self.error}"]
            return lines

        mean_median = [self.mean, self.median]
        mean_median.sort()
        if mean_median[0] == mean_median[1]:
            mm_str = f"{mean_median[0]}"
        else:
            mm_str = f"{mean_median[0]} [median] or {mean_median[1]} [mean]"

        lines.append(
            f"    Expect {mm_str} more {ut.plural(self.median,'bike')}."
        )

        one_line = (
            f"Based on {self.num_points} similar previous "
            f"{ut.plural(self.num_points,'day')}"
        )
        if self.num_discarded:
            one_line = (
                f"{one_line} ({self.num_discarded} "
                f"{ut.plural(self.num_discarded,'outlier')} discarded)"
            )
        one_line = f"{one_line}."
        lines = lines + [
            f"    {s}" for s in ut.line_splitter(one_line, width=PRINT_WIDTH)
        ]

        return lines


class LRModel:
    """A linear regression model using least squares."""

    def __init__(self):
        self.state = INCOMPLETE
        self.error = None
        self.xy_data = None
        self.num_points = None
        self.slope = None
        self.intercept = None
        self.r_squared = None
        self.correlation_coefficient = None
        self.nmae = None
        self.nrmse = None

        self.further_bikes = None

    def calculate_nrmse(self):
        sum_squared_errors = sum(
            (y - (self.slope * x + self.intercept)) ** 2
            for x, y in self.xy_data
        )
        rmse = math.sqrt(sum_squared_errors / self.num_points)

        range_y = max(y for _, y in self.xy_data) - min(
            y for _, y in self.xy_data
        )
        if range_y == 0:
            self.nmrse = "DIV/0"
        else:
            self.nrmse = rmse / range_y

    def calculate_nmae(self):
        sum_absolute_errors = sum(
            abs(y - (self.slope * x + self.intercept)) for x, y in self.xy_data
        )
        range_y = max(y for _, y in self.xy_data) - min(
            y for _, y in self.xy_data
        )
        divisor = self.num_points * range_y
        if divisor == 0:
            self.nmae = "DIV/0"
        else:
            self.nmae = sum_absolute_errors / divisor

    def calculate_model(self, xy_data):
        if self.state == ERROR:
            return

        self.xy_data = xy_data
        self.num_points = len(xy_data)
        if self.num_points < 2:
            self.error = "not enough data points"
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
            self.error = "DIV/0 in slope calculation."
            self.state = ERROR
            return
        self.intercept = mean_y - self.slope * mean_x

        # Calculate the correlation coefficient (r) and goodness of fit (R^2)
        sum_diff_prod = sum((x - mean_x) * (y - mean_y) for x, y in xy_data)
        sum_x_diff_squared = sum((x - mean_x) ** 2 for x, _ in xy_data)
        sum_y_diff_squared = sum((y - mean_y) ** 2 for _, y in xy_data)
        try:
            self.correlation_coefficient = sum_diff_prod / (
                math.sqrt(sum_x_diff_squared) * math.sqrt(sum_y_diff_squared)
            )
            self.r_squared = (
                self.correlation_coefficient * self.correlation_coefficient
            )
        except ZeroDivisionError:
            self.correlation_coefficient = "DIV/0"
            self.r_squared = "DIV/0"

        self.calculate_nrmse()
        self.calculate_nmae()

        self.state = READY

    def guess(self, x: float) -> float:
        # Predict y based on the linear regression equation
        if self.state == ERROR:
            return
        if self.state not in [READY, OK]:
            self.state = ERROR
            self.error = "model not ready, can not guess"
            return
        self.further_bikes = round(self.slope * x + self.intercept)
        self.state = OK
        return

    def result_msg(self) -> list[str]:
        """Return list of strings as long message."""

        lines = ["Using a linear regression model:"]
        if self.state != OK:
            lines.append(f"    Can't estimate because: {self.error}")
            return lines
        cc = _format_measure(self.correlation_coefficient)
        rs = _format_measure(self.r_squared)

        lines = lines + [
            f"    Expect {self.further_bikes} more {ut.plural(self.further_bikes,'bike')}."
        ]

        lines.append(
            f"    Based on {self.num_points} "
            f"data {ut.plural(self.num_points,'point')} "
        )
        nrmse_str = _format_measure(self.nrmse)
        nmae_str = _format_measure(self.nmae)
        if nmae_str == "?" and nrmse_str == "?":
            lines.append("    Model quality can not be calculated.")
        else:
            lines.append(
                f"    NMAE {nmae_str}; NRMSE {nrmse_str} [lower is better]."
            )

        return lines


class Estimator:
    """Data and methods to estimate how many more bikes to expect."""

    DBFILE = cfg.DB_FILENAME

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
        self.similar_dates = []
        self.befores = []
        self.afters = []
        # These are for the resulting 'simple model' estimate
        self.simple_model = SimpleModel()
        # This is for the linear regression model
        self.lr_model = LRModel()
        # This for the random forest estimate
        self.rf_model = rf.RandomForestRegressorModel()

        # pylint: disable-next=invalid-name
        DBFILE = cfg.DB_FILENAME
        if not os.path.exists(DBFILE):
            self.error = "Database not found"
            self.state = ERROR
            return
        self.database = db.db_connect(DBFILE)

        # Now process the inputs from passed-in values.
        if (
            not bikes_so_far
            and not as_of_when
            and not dow_in
            and not closing_time
        ):
            bikes_so_far = self._bikes_right_now()

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

    def _bikes_right_now(self) -> int:
        today = ut.date_str("today")
        rows = db.db_fetch(
            self.database,
            f"select count(date) from visit where date = '{today}' and time_in > ''",
            ["count"],
        )
        if not rows:
            return None
        return rows[0].count

    def _sql_str(self) -> str:
        """Build SQL query."""
        if self.dow in [6, 7]:
            dow_set = f"({self.dow})"
        else:
            dow_set = "(1,2,3,4,5)"
        today = ut.date_str("today")
        sql = f"""
            WITH all_dates AS (
                SELECT DISTINCT date
                FROM visit
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
                AND day.date != "{today}"
            ORDER BY
                day.date;
        """
        return sql

    def _fetch_raw_data(self) -> None:
        """Get raw data from the database into self.befores, self.afters."""
        # Collect data from database
        sql = self._sql_str()
        data_rows = db.db_fetch(
            self.database, sql, ["date", "before", "after"]
        )
        if not data_rows:
            self.error = "no data returned from database."
            self.state = ERROR
            return

        self.befores = [int(r.before) for r in data_rows]
        self.afters = [int(r.after) for r in data_rows]
        self.similar_dates = [r.date for r in data_rows]

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
            self.similar_dates, self.befores, self.afters, VARIANCE, Z_CUTOFF
        )
        self.simple_model.guess(self.bikes_so_far)

        # Calculate using linear regression.
        self.lr_model.calculate_model(list(zip(self.befores, self.afters)))
        self.lr_model.guess(self.bikes_so_far)

        if rf.POSSIBLE:
            self.rf_model.create_model([], self.befores, self.afters)
            self.rf_model.guess(self.bikes_so_far)

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

        one_line = (
            f"Estimating for a typical {dayname} with {self.bikes_so_far} "
            f"{ut.plural(self.bikes_so_far,'bike')} parked by {self.as_of_when.short}, "
            f"closing at {self.closing_time}:"
        )
        lines = (
            lines
            + [""]
            + [s for s in ut.line_splitter(one_line, width=PRINT_WIDTH)]
        )

        predictions = []
        lines += [""] + self.simple_model.result_msg()
        if self.simple_model.state == OK:
            predictions += [self.simple_model.mean, self.simple_model.median]
        lines += [""] + self.lr_model.result_msg()
        if self.lr_model.state == OK:
            predictions += [self.lr_model.further_bikes]
        if rf.POSSIBLE:
            lines += [""] + self.rf_model.result_msg()
            if self.rf_model.state == rf.OK:
                predictions += [self.rf_model.further_bikes]
        # Find day-total expectation

        if predictions:
            min_day_total = min(predictions) + self.bikes_so_far
            max_day_total = max(predictions) + self.bikes_so_far
            if min_day_total == max_day_total:
                prediction_str = str(min_day_total)
            else:
                prediction_str = f"{min_day_total} to {max_day_total}"

        one_line = (
            f"From these models, "
            f"expect a total of {prediction_str} bikes for the day."
        )
        one_line = (
            f"{one_line}  Estimation performed at "
            f"{VTime('now').short} on {ut.date_str('now',long_date=True)}."
        )
        if self.as_of_when < "12:30":
            one_line = f"{one_line}  Estimates early in the day may be of low quality."
        lines = (
            lines
            + [""]
            + [s for s in ut.line_splitter(one_line, width=PRINT_WIDTH)]
        )

        return lines


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
