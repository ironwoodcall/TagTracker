#!/usr/bin/env python3
"""Estimate how many more bikes to expect.

Call (as itself) as:
    self    bikes_so_far, as_of_when, dow, time_closed
    where
        bikes_so_far: is how many bikes in by as_of_when (mandatory)
        as_of_when: is the time for which the estimate is made, HH:MM, H:MM, HMM
            (default if missing or "": now)
        dow: ISO day of week (1=Mo..7=Su), YYYY-MM-DD, "today" or "yesterday"
            (default if missing or "": today)
        time_closed: HHMM of time the service closes day of estimate
            (default if missing or "": will try to determine using config functions)

Or call in a CGI script, and the parameters are read from QUERY_STRING.
The parameter names are the same as above.

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


import urllib.request
import os
import sys
import math
import statistics
from typing import Optional

sys.path.append("../")
sys.path.append("./")

# pylint: disable=wrong-import-position
import web_base_config as wcfg
import common.tt_util as ut
from common.tt_time import VTime
import common.tt_dbutil as db
import tt_default_hours

# import client_base_config as cfg
import web.web_estimator_rf as rf

# pylint: enable=wrong-import-position

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

        lines.append(f"    Expect {mm_str} more {ut.plural(self.median,'bike')}.")

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
            f"    {s}" for s in ut.line_wrapper(one_line, width=PRINT_WIDTH)
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

    # def calculate_nrmse(self):
    #     sum_squared_errors = sum(
    #         (y - (self.slope * x + self.intercept)) ** 2 for x, y in self.xy_data
    #     )
    #     rmse = math.sqrt(sum_squared_errors / self.num_points)

    #     range_y = max(y for _, y in self.xy_data) - min(y for _, y in self.xy_data)
    #     if range_y == 0:
    #         self.nmrse = "DIV/0"
    #     else:
    #         self.nrmse = rmse / range_y

    # def calculate_nmae(self):
    #     sum_absolute_errors = sum(
    #         abs(y - (self.slope * x + self.intercept)) for x, y in self.xy_data
    #     )
    #     range_y = max(y for _, y in self.xy_data) - min(y for _, y in self.xy_data)
    #     divisor = self.num_points * range_y
    #     if divisor == 0:
    #         self.nmae = "DIV/0"
    #     else:
    #         self.nmae = sum_absolute_errors / divisor

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
            self.r_squared = self.correlation_coefficient * self.correlation_coefficient
        except ZeroDivisionError:
            self.correlation_coefficient = "DIV/0"
            self.r_squared = "DIV/0"

        # self.calculate_nrmse()
        # self.calculate_nmae()

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
        # cc = _format_measure(self.correlation_coefficient)
        # rs = _format_measure(self.r_squared)

        lines = lines + [
            f"    Expect {self.further_bikes} more {ut.plural(self.further_bikes,'bike')}."
        ]

        lines.append(
            f"    Based on {self.num_points} "
            f"data {ut.plural(self.num_points,'point')} "
        )
        # nrmse_str = _format_measure(self.nrmse)
        # nmae_str = _format_measure(self.nmae)
        # if nmae_str == "?" and nrmse_str == "?":
        #     lines.append("    Model quality can not be calculated.")
        # else:
        #     lines.append(f"    NMAE {nmae_str}; NRMSE {nrmse_str} [lower is better].")

        return lines


class Estimator_old:
    """Data and methods to estimate how many more bikes to expect."""

    DBFILE = wcfg.DB_FILENAME

    orgsite_id = 1  # FIXME hardwired orgsite

    def __init__(
        self,
        bikes_so_far="",
        as_of_when="",
        dow_in="",
        time_closed="",
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

        # Min and Max from all the models
        self.min = None
        self.max = None

        # These are inputs
        self.bikes_so_far = None
        self.dow = None
        self.as_of_when = None
        self.time_closed = None
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
        DBFILE = wcfg.DB_FILENAME
        if not os.path.exists(DBFILE):
            self.error = "Database not found"
            self.state = ERROR
            return
        self.database = db.db_connect(DBFILE)

        # Now process the inputs from passed-in values.
        ##if not bikes_so_far and not as_of_when and not dow_in and not time_closed:
        if not bikes_so_far:
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
        if not time_closed:
            time_closed = tt_default_hours.get_default_hours(dow_date)[1]
        self.time_closed = VTime(time_closed)  # Closing time today
        if not self.time_closed:
            self.error = "Missing or bad time_closed parameter."
            self.state = ERROR
            return

    def _bikes_right_now(self) -> int:
        today = ut.date_str("today")
        cursor = self.database.cursor()
        day_id = db.fetch_day_id(
            cursor=cursor, date=today, maybe_orgsite_id=self.orgsite_id
        )
        if not day_id:
            print("no data matches this day")
            return None
        # ut.squawk(f"{day_id=}")
        rows = db.db_fetch(
            self.database,
            f"select count(time_in) from visit where day_id = {day_id} and time_in > ''",
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
            SELECT
                D.date,
                SUM(CASE WHEN V.time_in <= '{self.as_of_when}' THEN 1 ELSE 0 END) AS befores,
                SUM(CASE WHEN V.time_in > '{self.as_of_when}' THEN 1 ELSE 0 END) AS afters
            FROM
                DAY D
            JOIN
                VISIT V ON D.id = V.day_id
            WHERE
                D.orgsite_id = {self.orgsite_id}
                AND D.weekday IN {dow_set}
                AND D.date != '{today}'
                AND D.time_closed = '{self.time_closed}'
            GROUP BY
                D.date;
        """
        return sql

    def _fetch_raw_data(self) -> None:
        """Get raw data from the database into self.befores, self.afters."""
        # Collect data from database
        sql = self._sql_str()
        data_rows = db.db_fetch(self.database, sql, ["date", "before", "after"])
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

        # min and max of the guesses so far
        self.min = min(
            (
                v
                for v in [
                    self.simple_model.mean,
                    self.simple_model.median,
                    self.lr_model.further_bikes,
                ]
                if v is not None
            ),
            default=None,
        )
        self.max = max(
            (
                v
                for v in [
                    self.simple_model.mean,
                    self.simple_model.median,
                    self.lr_model.further_bikes,
                ]
                if v is not None
            ),
            default=None,
        )

        if rf.POSSIBLE:
            self.rf_model.create_model([], self.befores, self.afters)
            self.rf_model.guess(self.bikes_so_far)
            self.min = min(self.min, self.rf_model.further_bikes)
            self.max = max(self.max, self.rf_model.further_bikes)

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

        one_line = (
            f"Estimating for a typical {dayname} with {self.bikes_so_far} "
            f"{ut.plural(self.bikes_so_far,'bike')} parked by {self.as_of_when.short}, "
            f"closing at {self.time_closed}:"
        )
        lines = [s for s in ut.line_wrapper(one_line, width=PRINT_WIDTH)]

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
        prediction_str = "?"
        if predictions:
            min_day_total = min(predictions) + self.bikes_so_far
            max_day_total = max(predictions) + self.bikes_so_far
            if min_day_total == max_day_total:
                prediction_str = str(min_day_total)
            else:
                prediction_str = f"{min_day_total} to {max_day_total}"

        lines = [
            "How many more bikes?",
            "",
            f"Expect a total of {prediction_str} bikes for the day.",
            "",
        ] + lines

        one_line = (
            "Estimation performed at "
            f"{VTime('now').short} on {ut.date_str('now',long_date=True)}."
        )
        if self.as_of_when < "12:30":
            one_line = f"{one_line}  Estimates early in the day may be of low quality."
        lines = lines + [""] + [s for s in ut.line_wrapper(one_line, width=PRINT_WIDTH)]

        return lines


def _init_from_cgi_old() -> Estimator_old:
    """Read initialization parameters from CGI env var.

    CGI parameters: as at top of file.
        bikes_so_far, dow,as_of_when,time_closed

    """
    query_str = ut.untaint(os.environ.get("QUERY_STRING", ""))
    query_parms = urllib.parse.parse_qs(query_str)
    bikes_so_far = query_parms.get("bikes_so_far", [""])[0]
    dow = query_parms.get("dow", [""])[0]
    as_of_when = query_parms.get("as_of_when", [""])[0]
    time_closed = query_parms.get("time_closed", [""])[0]

    return Estimator_old(bikes_so_far, as_of_when, dow, time_closed)


def _init_from_args_old() -> Estimator_old:
    my_args = sys.argv[1:] + ["", "", "", "", "", "", "", ""]
    return Estimator_old(my_args[0], my_args[1], my_args[2], my_args[3])


# New estimator that provides a concise estimation table
class Estimator:
    """New estimator producing a compact table of key metrics and confidence.

    Outputs four items:
      - Further bikes today (remainder)
      - Max full today (count)
      - Max full today time (HH:MM)
      - Events in the next hour (ins+outs)
    """

    orgsite_id = 1  # FIXME: hardwired orgsite (kept consistent with old)

    def __init__(
        self,
        bikes_so_far: str = "",
        as_of_when: str = "",
        dow_in: str = "",
        time_closed: str = "",
    ) -> None:
        self.state = INCOMPLETE
        self.error = ""
        self.database = None

        DBFILE = wcfg.DB_FILENAME
        if not os.path.exists(DBFILE):
            self.error = "Database not found"
            self.state = ERROR
            return
        self.database = db.db_connect(DBFILE)

        # Inputs
        if not bikes_so_far:
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

        dow_in = dow_in if dow_in else "today"
        maybe_dow = ut.dow_int(dow_in)
        if maybe_dow:
            self.dow = maybe_dow
            dow_date = ut.most_recent_dow(self.dow)
        else:
            dow_date = ut.date_str(dow_in)
            if dow_date:
                self.dow = ut.dow_int(dow_date)
            else:
                self.error = "Bad dow parameter."
                self.state = ERROR
                return

        # Schedule
        if not time_closed:
            time_closed = tt_default_hours.get_default_hours(dow_date)[1]
        self.time_closed = VTime(time_closed)
        if not self.time_closed:
            self.error = "Missing or bad time_closed parameter."
            self.state = ERROR
            return
        # Open time (for fraction elapsed and day-shape logic)
        self.time_open = VTime(tt_default_hours.get_default_hours(dow_date)[0])

        # Data buffers
        self.similar_dates: list[str] = []
        self.befores: list[int] = []
        self.afters: list[int] = []
        # Configurable matching and trimming
        self.VARIANCE = getattr(wcfg, "EST_VARIANCE", 15)
        self.Z_CUTOFF = getattr(wcfg, "EST_Z_CUTOFF", 2.5)
        self._fetch_raw_data()
        if self.state == ERROR:
            return

        # Build SimpleModel for remainder
        self.simple_model = SimpleModel()
        self.simple_model.create_model(
            self.similar_dates, self.befores, self.afters, self.VARIANCE, self.Z_CUTOFF
        )
        self.simple_model.guess(self.bikes_so_far)

        self.table_rows: list[tuple[str, str, str]] = []

    def _bikes_right_now(self) -> int:
        today = ut.date_str("today")
        cursor = self.database.cursor()
        day_id = db.fetch_day_id(cursor=cursor, date=today, maybe_orgsite_id=self.orgsite_id)
        if not day_id:
            return 0
        rows = db.db_fetch(
            self.database,
            f"select count(time_in) as cnt from visit where day_id = {day_id} and time_in > ''",
            ["cnt"],
        )
        return int(rows[0].cnt) if rows else 0

    def _sql_str(self) -> str:
        if self.dow in [6, 7]:
            dow_set = f"({self.dow})"
        else:
            dow_set = "(1,2,3,4,5)"
        today = ut.date_str("today")
        return f"""
            SELECT
                D.date,
                SUM(CASE WHEN V.time_in <= '{self.as_of_when}' THEN 1 ELSE 0 END) AS befores,
                SUM(CASE WHEN V.time_in > '{self.as_of_when}' THEN 1 ELSE 0 END) AS afters
            FROM DAY D
            JOIN VISIT V ON D.id = V.day_id
            WHERE D.orgsite_id = {self.orgsite_id}
              AND D.weekday IN {dow_set}
              AND D.date != '{today}'
              AND D.time_closed = '{self.time_closed}'
            GROUP BY D.date;
        """

    def _fetch_raw_data(self) -> None:
        sql = self._sql_str()
        data_rows = db.db_fetch(self.database, sql, ["date", "before", "after"])
        if not data_rows:
            self.error = "no data returned from database."
            self.state = ERROR
            return
        self.befores = [int(r.before) for r in data_rows]
        self.afters = [int(r.after) for r in data_rows]
        self.similar_dates = [r.date for r in data_rows]

    def _matched_dates(self) -> list[str]:
        out: list[str] = []
        for i, b in enumerate(self.befores):
            if abs(int(b) - int(self.bikes_so_far)) <= self.VARIANCE:
                out.append(self.similar_dates[i])
        return out

    def _visits_for_date(self, date_str: str) -> list[tuple[VTime, Optional[VTime]]]:
        day_id = db.fetch_day_id(cursor=self.database.cursor(), date=date_str, maybe_orgsite_id=self.orgsite_id)
        if not day_id:
            return []
        rows = db.db_fetch(
            self.database,
            f"SELECT time_in, time_out FROM VISIT WHERE day_id = {day_id} ORDER BY time_in",
            ["time_in", "time_out"],
        )
        out = []
        for r in rows:
            tin = VTime(r.time_in)
            tout = VTime(r.time_out) if r.time_out else None
            out.append((tin, tout))
        return out

    @staticmethod
    def _counts_for_time(visits: list[tuple[VTime, Optional[VTime]]], t: VTime) -> tuple[int, int, int, int, int]:
        t_end = VTime(min(t.num + 60, 24 * 60))
        before_ins = sum(1 for tin, _ in visits if tin and tin <= t)
        after_ins = sum(1 for tin, _ in visits if tin and tin > t)
        outs_up_to_t = sum(1 for _, tout in visits if tout and tout <= t)
        ins_next = sum(1 for tin, _ in visits if tin and t < tin <= t_end)
        outs_next = sum(1 for _, tout in visits if tout and t < tout <= t_end)
        return before_ins, after_ins, outs_up_to_t, ins_next, outs_next

    @staticmethod
    def _peak_future_occupancy(visits: list[tuple[VTime, Optional[VTime]]], t: VTime, close: VTime) -> tuple[int, VTime]:
        occ_now = sum(1 for tin, _ in visits if tin and tin <= t) - sum(1 for _, tout in visits if tout and tout <= t)
        events: list[tuple[int, int]] = []
        for tin, tout in visits:
            if tin and t < tin <= close:
                events.append((int(VTime(tin).num), +1))
            if tout and t < tout <= close:
                events.append((int(VTime(tout).num), -1))
        events.sort(key=lambda x: (x[0], -x[1]))
        peak = occ_now
        peak_time = t
        occ = occ_now
        for tm, delta in events:
            occ += delta
            if occ > peak:
                peak = occ
                peak_time = VTime(tm)
        return peak, peak_time

    def _confidence_level(self, n: int, frac_elapsed: float) -> str:
        cfg = getattr(wcfg, "EST_CONF_THRESHOLDS", None)
        high = {"min_n": 12, "min_frac": 0.4}
        med = {"min_n": 8, "min_frac": 0.2}
        if isinstance(cfg, dict):
            high = cfg.get("High", high)
            med = cfg.get("Medium", med)
        if n >= int(high.get("min_n", 12)) and frac_elapsed >= float(high.get("min_frac", 0.4)):
            return "High"
        if n >= int(med.get("min_n", 8)) and frac_elapsed >= float(med.get("min_frac", 0.2)):
            return "Medium"
        return "Low"

    def _band(self, level: str, kind: str) -> int:
        # kind in {remainder, activity, peak, peaktime}
        bands = getattr(wcfg, "EST_BANDS", None)
        default = {
            "remainder": {"High": 10, "Medium": 18, "Low": 30},
            "activity": {"High": 8, "Medium": 12, "Low": 16},
            "peak": {"High": 10, "Medium": 15, "Low": 25},
            "peaktime": {"High": 20, "Medium": 30, "Low": 60},
        }
        table = default.get(kind, {})
        if isinstance(bands, dict):
            table = bands.get(kind, table)
        return int(table.get(level, 0) or 0)

    def guess(self) -> None:
        if self.state == ERROR:
            return
        # Fraction elapsed
        total_span = max(1, self.time_closed.num - self.time_open.num)
        frac_elapsed = max(0.0, min(1.0, (self.as_of_when.num - self.time_open.num) / total_span))

        # Matched dates by bikes_so_far window
        matched = self._matched_dates()
        n = len(matched)

        # Further-bikes (remainder): SM median if available
        remainder = None
        if self.simple_model.state == OK:
            remainder = self.simple_model.median
        if remainder is None:
            remainder = 0

        # Next-hour activity and Peak-future via matched-day visits
        nxh_acts: list[int] = []
        peaks: list[tuple[int, VTime]] = []
        for d in matched:
            vlist = self._visits_for_date(d)
            _b, _a, _outs_to_t, ins_nxh, outs_nxh = self._counts_for_time(vlist, self.as_of_when)
            nxh_acts.append(int(ins_nxh + outs_nxh))
            p, pt = self._peak_future_occupancy(vlist, self.as_of_when, self.time_closed)
            peaks.append((int(p), pt))

        nxh_activity = int(statistics.median(nxh_acts)) if nxh_acts else 0
        if peaks:
            peak_val = int(statistics.median([p for p, _ in peaks]))
            # Estimate time of peak as median time among those with max (rough proxy)
            times = [pt.num for _p, pt in peaks]
            peak_time = VTime(int(statistics.median(times)))
        else:
            peak_val = self.bikes_so_far
            peak_time = self.as_of_when

        # Confidence levels and bands
        level = self._confidence_level(n, frac_elapsed)
        rem_band = self._band(level, "remainder")
        act_band = self._band(level, "activity")
        peak_band = self._band(level, "peak")
        ptime_band = self._band(level, "peaktime")

        # Build table rows
        self.table_rows = [
            ("Further bikes today", f"{int(remainder)}", f"±{rem_band} bikes"),
            ("Max full today", f"{int(peak_val)}", f"±{peak_band} bikes"),
            ("Max full today time", f"{peak_time.short}", f"±{ptime_band} minutes"),
            ("Events in the next hour", f"{int(nxh_activity)}", f"±{act_band}"),
        ]
        self.state = OK

    def result_msg(self) -> list[str]:
        if self.state == ERROR:
            return [f"Can't estimate because: {self.error}"]
        if not self.table_rows:
            return ["No estimates available"]
        # Render a simple aligned table
        header = ["Measure", "Value", "Confidence"]
        widths = [max(len(r[i]) for r in ([header] + self.table_rows)) for i in range(3)]
        def fmt_row(r: list[str]) -> str:
            return f"{r[0].ljust(widths[0])}  {r[1].rjust(widths[1])}  {r[2].ljust(widths[2])}"
        lines = [fmt_row(header), fmt_row(["-"*widths[0], "-"*widths[1], "-"*widths[2]])]
        for m, v, c in self.table_rows:
            lines.append(fmt_row([m, v, c]))
        return lines


if __name__ == "__main__":
    # Backward-compatible CLI/CGI runner for the old estimator
    estimate: Estimator_old
    is_cgi = bool(os.environ.get("REQUEST_METHOD"))
    if is_cgi:
        print("Content-type: text/plain\n")
        estimate = _init_from_cgi_old()
    else:
        estimate = _init_from_args_old()

    if estimate.state != ERROR:
        estimate.guess()

    for line in estimate.result_msg():
        print(line)
