#!/usr/bin/env python3
"""Estimate how many more bikes to expect.

New API (CGI or CLI):
    opening_time, closing_time, bikes_so_far, [max_bikes_today], [max_bikes_time_today]
    where
        opening_time: service opening time for today (HHMM or HH:MM)
        closing_time: service closing time for today (HHMM or HH:MM)
        bikes_so_far: bikes currently parked (as of now)
        max_bikes_today: optional, for future use (ignored if provided)
        max_bikes_time_today: optional, for future use (ignored if provided)

Assumptions for new API:
    - Estimation is for today, at "now".
    - Optional `estimation_type` query parameter routes behavior:
        * legacy  -> use Estimator_old (legacy interface)
        * current or missing -> use Estimator (new API)
        * verbose -> Estimator (same output for now; verbose not yet implemented)

Backward compatibility:
    - If new parameters are not provided, falls back to legacy params
      (bikes_so_far, as_of_when, dow, time_closed) and Estimator_old.

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
import json
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

    # Measure label strings (edit here to change table text)
    MEAS_ACTIVITY_TEMPLATE = "Activity, now to {end_time}"
    MEAS_FURTHER = "Further bikes in today"
    MEAS_TIME_MAX = "Time max bikes onsite"
    MEAS_MAX = "Max bikes onsite"

    def _activity_label(self, t_end: VTime) -> str:
        return self.MEAS_ACTIVITY_TEMPLATE.format(end_time=t_end.tidy)

    # Static cache for calibration JSON
    _CALIB_CACHE = None

    def __init__(
        self,
        bikes_so_far: str = "",
        opening_time: str = "",
        closing_time: str = "",
        max_bikes_today: str = "",
        max_bikes_time_today: str = "",
        # Back-compat keyword aliases from legacy callers
        time_open: str = "",
        time_closed: str = "",
        verbose: bool = False,
    ) -> None:
        self.state = INCOMPLETE
        self.error = ""
        self.database = None
        self.verbose = bool(verbose)

        DBFILE = wcfg.DB_FILENAME
        if not os.path.exists(DBFILE):
            self.error = "Database not found"
            self.state = ERROR
            return
        self.database = db.db_connect(DBFILE)

        # Inputs: bikes_so_far (defaults to count right now)
        if not bikes_so_far:
            bikes_so_far = self._bikes_right_now()
        bikes_so_far = str(bikes_so_far).strip()
        if not bikes_so_far.isdigit():
            self.error = "Missing or bad bikes_so_far parameter."
            self.state = ERROR
            return
        self.bikes_so_far = int(bikes_so_far)

        # New API assumes estimation is for "now"
        self.as_of_when = VTime("now")
        if not self.as_of_when:
            self.error = "Bad current time."
            self.state = ERROR
            return

        # Today context
        dow_date = ut.date_str("today")
        self.dow = ut.dow_int(dow_date)

        # Schedule: opening and closing time (from params or defaults)
        # Accept legacy keyword aliases if provided
        if not opening_time and time_open:
            opening_time = time_open
        if not closing_time and time_closed:
            closing_time = time_closed

        if not opening_time or not closing_time:
            default_open, default_close = tt_default_hours.get_default_hours(dow_date)
            opening_time = opening_time or default_open
            closing_time = closing_time or default_close

        # Final fallbacks if defaults are also missing
        if not opening_time:
            opening_time = "00:00"
        if not closing_time:
            # Assume service can run to end-of-day if unknown
            closing_time = "24:00"

        self.time_closed = VTime(closing_time)
        self.time_open = VTime(opening_time)

        # If still invalid, clamp to safe values for calculations
        if not self.time_open:
            self.time_open = VTime("00:00")
        if not self.time_closed:
            self.time_closed = VTime("24:00")

        # Data buffers
        self.similar_dates: list[str] = []
        self.befores: list[int] = []
        self.afters: list[int] = []
        # Configurable matching and trimming
        self.VARIANCE = getattr(wcfg, "EST_VARIANCE", 15)
        self.Z_CUTOFF = getattr(wcfg, "EST_Z_CUTOFF", 2.5)
        self.MATCH_OPEN_TOL = int(getattr(wcfg, "EST_MATCH_OPEN_TOL", 15))
        self.MATCH_CLOSE_TOL = int(getattr(wcfg, "EST_MATCH_CLOSE_TOL", 15))
        self._match_note = ""
        # Load calibration once if configured
        self._calib = None
        self._calib_bins = None
        self._calib_best = None
        self._calib_debug: list[str] = []
        self._maybe_load_calibration()
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

    def _time_bounds(self, base: VTime, tol_min: int) -> tuple[str, str]:
        base_num = base.num if base and base.num is not None else 0
        lo = max(0, base_num - max(0, int(tol_min)))
        hi = min(24 * 60, base_num + max(0, int(tol_min)))
        return VTime(lo), VTime(hi)

    def _sql_str(self, use_open: bool, use_close: bool) -> str:
        today = ut.date_str("today")
        where_parts = [
            f"D.orgsite_id = {self.orgsite_id}",
            f"D.date != '{today}'",
        ]
        if use_open:
            lo, hi = self._time_bounds(self.time_open, self.MATCH_OPEN_TOL)
            where_parts.append(f"D.time_open BETWEEN '{lo}' AND '{hi}'")
        if use_close:
            lo, hi = self._time_bounds(self.time_closed, self.MATCH_CLOSE_TOL)
            where_parts.append(f"D.time_closed BETWEEN '{lo}' AND '{hi}'")
        where_sql = " AND\n              ".join(where_parts)
        return f"""
            SELECT
                D.date,
                SUM(CASE WHEN V.time_in <= '{self.as_of_when}' THEN 1 ELSE 0 END) AS befores,
                SUM(CASE WHEN V.time_in > '{self.as_of_when}' THEN 1 ELSE 0 END) AS afters
            FROM DAY D
            JOIN VISIT V ON D.id = V.day_id
            WHERE {where_sql}
            GROUP BY D.date;
        """

    def _maybe_load_calibration(self) -> None:
        if Estimator._CALIB_CACHE is not None:
            self._calib = Estimator._CALIB_CACHE
            self._calib_debug.append("calibration: using cached JSON")
        else:
            path_cfg = getattr(wcfg, "EST_CALIBRATION_FILE", "")
            tried: list[tuple[str, bool, str]] = []  # (path, exists, note)
            candidates: list[str] = []
            if path_cfg:
                candidates.append(path_cfg)
                # If relative, also try relative to module directory
                if not os.path.isabs(path_cfg):
                    mod_dir = os.path.dirname(os.path.abspath(__file__))
                    candidates.append(os.path.abspath(path_cfg))
                    candidates.append(os.path.join(mod_dir, path_cfg))
            for p in candidates:
                exists = os.path.exists(p)
                tried.append((p, exists, "exists" if exists else "missing"))
                if not exists:
                    continue
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        Estimator._CALIB_CACHE = json.load(fh)
                        self._calib = Estimator._CALIB_CACHE
                        self._calib_debug.append(f"calibration: loaded '{p}'")
                        break
                except Exception as e:
                    self._calib_debug.append(f"calibration: failed to load '{p}': {e}")
            if not self._calib:
                if not path_cfg:
                    self._calib_debug.append("calibration: EST_CALIBRATION_FILE not set")
                else:
                    for pth, exi, note in tried:
                        self._calib_debug.append(f"calibration: tried '{pth}' -> {note}")
        # Parse bins for quick lookup
        if self._calib and isinstance(self._calib.get("time_bins", None), list):
            bins = []
            for s in self._calib["time_bins"]:
                try:
                    a, b = s.split("-", 1)
                    lo = float(a); hi = float(b)
                    bins.append((lo, hi, s))
                except Exception:
                    continue
            self._calib_bins = bins or None
            self._calib_best = self._calib.get("best_model", None)

    def _bin_label(self, frac_elapsed: float) -> str | None:
        if not self._calib_bins:
            return None
        f = max(0.0, min(1.0, float(frac_elapsed)))
        for lo, hi, lbl in self._calib_bins:
            if lo <= f < hi:
                return lbl
        return self._calib_bins[-1][2]

    def _calib_residual_band(self, model: str, measure: str, frac_elapsed: float) -> tuple[float, float] | None:
        if not self._calib:
            return None
        lbl = self._bin_label(frac_elapsed)
        try:
            ent = self._calib["residual_bands"][model][measure][lbl]
            q05 = ent.get("q05", None)
            q95 = ent.get("q95", None)
            if q05 is None or q95 is None:
                return None
            return float(q05), float(q95)
        except Exception:
            return None

    def _fetch_raw_data(self) -> None:
        # Try: match both opening and closing times within tolerance
        sql = self._sql_str(use_open=True, use_close=True)
        data_rows = db.db_fetch(self.database, sql, ["date", "before", "after"])
        if data_rows:
            self._match_note = "matched on open+close"
        # Backoff 1: match closing time only
        if not data_rows:
            sql = self._sql_str(use_open=False, use_close=True)
            data_rows = db.db_fetch(self.database, sql, ["date", "before", "after"])
            if data_rows:
                self._match_note = "matched on close only"
        # Backoff 2: no time constraints (orgsite only)
        if not data_rows:
            sql = self._sql_str(use_open=False, use_close=False)
            data_rows = db.db_fetch(self.database, sql, ["date", "before", "after"])
            if data_rows:
                self._match_note = "matched without time filters"
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

    @staticmethod
    def _peak_all_day_occupancy(visits: list[tuple[VTime, Optional[VTime]]]) -> tuple[int, VTime]:
        """Compute the maximum occupancy and when it occurs over the entire day.

        Uses all visit events (ins as +1, outs as -1) from the day's data
        without restricting to times after now. Assumes occupancy is zero
        before the first event of the day.
        """
        events: list[tuple[int, int]] = []
        for tin, tout in visits:
            if tin:
                events.append((int(VTime(tin).num), +1))
            if tout:
                events.append((int(VTime(tout).num), -1))
        if not events:
            return 0, VTime("00:00")
        events.sort(key=lambda x: (x[0], -x[1]))
        occ = 0
        peak = 0
        peak_time = VTime(events[0][0])
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

    def _band_scaled(self, base: int, n: int, frac_elapsed: float, kind: str) -> int:
        """Scale a base band width by day progress and sample size.

        - Earlier in the day -> wider margins; later -> tighter margins.
        - More matched days -> tighter margins (sqrt-law capped).
        Configurable via optional wcfg values:
            EST_BAND_N_REF, EST_BAND_MIN_SCALE, EST_BAND_MAX_SCALE
        """
        try:
            n_ref = int(getattr(wcfg, "EST_BAND_N_REF", 10))
        except Exception:
            n_ref = 10
        try:
            min_scale = float(getattr(wcfg, "EST_BAND_MIN_SCALE", 0.5))
            max_scale = float(getattr(wcfg, "EST_BAND_MAX_SCALE", 1.25))
        except Exception:
            min_scale, max_scale = 0.5, 1.25

        # Progress factor: 1.3 at open, 0.8 at close (linear)
        pf = 1.30 - 0.50 * max(0.0, min(1.0, frac_elapsed))
        # Sample-size factor: sqrt scaling around n_ref; capped to reasonable bounds
        nn = max(1, int(n))
        import math
        sf = math.sqrt(n_ref / nn)
        sf = max(0.70, min(1.15, sf))

        scale = max(min_scale, min(max_scale, pf * sf))
        return max(0, int(round(base * scale)))

    @staticmethod
    def _percentiles(values: list[int], p_lo: float = 0.05, p_hi: float = 0.95) -> tuple[int, int]:
        """Compute (low, high) empirical percentiles as integers without numpy."""
        vals = sorted(int(v) for v in values)
        n = len(vals)
        if n == 0:
            return None, None  # type: ignore[return-value]
        if n == 1:
            return vals[0], vals[0]
        def q_at(p: float) -> int:
            p = max(0.0, min(1.0, float(p)))
            pos = p * (n - 1)
            i = int(pos)
            frac = pos - i
            if i >= n - 1:
                return vals[-1]
            return int(round(vals[i] * (1 - frac) + vals[i + 1] * frac))
        return q_at(p_lo), q_at(p_hi)

    @staticmethod
    def _clamp01(x: float) -> float:
        return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

    def _smooth_conf(self, n: int, frac_elapsed: float, spread: float | None, denom: float | None, n_ref: int = 12) -> str:
        """Compute a smooth % confidence reflecting time, sample size, and variation.

        - Time-of-day factor pf grows linearly from 0.3 at open to 1.0 at close.
        - Sample-size factor nf grows with sqrt(n/n_ref), clipped to [0,1].
        - Variation factor vf = 1 - clamp(spread/denom), where denom is a
          scale for the measure (e.g., median or day span). If spread/denom
          is small, vf is near 1 (high confidence); if large, vf is near 0.
        Returns a percentage string like '82%'.
        """
        # Time-of-day
        pf = 0.30 + 0.70 * self._clamp01(frac_elapsed)
        # Sample size
        try:
            nf = (max(0, int(n)) / max(1, int(n_ref))) ** 0.5
        except Exception:
            nf = 0.0
        nf = self._clamp01(nf)
        # Variation
        if spread is None or denom is None or denom <= 0:
            vf = 0.5  # neutral if unknown
        else:
            vf = 1.0 - self._clamp01(float(spread) / float(denom))
        # Blend
        score = 100.0 * (0.40 * pf + 0.30 * nf + 0.30 * vf)
        score = max(0.0, min(100.0, score))
        return f"{int(round(score))}%"

    def guess(self) -> None:
        if self.state == ERROR:
            return
        # Fraction elapsed
        open_num = self.time_open.num if self.time_open and self.time_open.num is not None else 0
        close_num = (
            self.time_closed.num if self.time_closed and self.time_closed.num is not None else 24 * 60
        )
        # Ensure positive span
        if close_num <= open_num:
            close_num = max(open_num + 60, 24 * 60)
        total_span = max(1, close_num - open_num)
        frac_elapsed = max(0.0, min(1.0, (self.as_of_when.num - open_num) / total_span))

        # Matched dates by bikes_so_far window
        matched = self._matched_dates()
        n = len(matched)

        # Further-bikes (remainder): SM median if available
        remainder = None
        if self.simple_model.state == OK:
            remainder = self.simple_model.median
        if remainder is None:
            remainder = 0

        # Next-hour activity and Peak (whole-day) via matched-day visits
        nxh_acts: list[int] = []
        peaks: list[tuple[int, VTime]] = []
        for d in matched:
            vlist = self._visits_for_date(d)
            _b, _a, _outs_to_t, ins_nxh, outs_nxh = self._counts_for_time(vlist, self.as_of_when)
            nxh_acts.append(int(ins_nxh + outs_nxh))
            # Use whole-day peak for similar days (can occur before or after 'now')
            p, pt = self._peak_all_day_occupancy(vlist)
            peaks.append((int(p), pt))

        # Build activity/peak arrays for all similar dates (for alternate models)
        all_acts: list[int] = []
        all_peaks: list[int] = []
        all_ptimes: list[VTime] = []
        for d in self.similar_dates:
            vlist = self._visits_for_date(d)
            _b2, _a2, _outs2, ins2, outs2 = self._counts_for_time(vlist, self.as_of_when)
            all_acts.append(int(ins2 + outs2))
            p2, pt2 = self._peak_all_day_occupancy(vlist)
            all_peaks.append(int(p2))
            all_ptimes.append(pt2)

        nxh_activity = int(statistics.median(nxh_acts)) if nxh_acts else 0
        if peaks:
            peak_val = int(statistics.median([p for p, _ in peaks]))
            # Estimate time of peak as median time among those with max (rough proxy)
            times = [pt.num for _p, pt in peaks]
            peak_time = VTime(int(statistics.median(times)))
        else:
            peak_val = self.bikes_so_far
            peak_time = self.as_of_when

        # Confidence levels and dynamic bands
        level = self._confidence_level(n, frac_elapsed)
        rem_band = self._band_scaled(self._band(level, "remainder"), n, frac_elapsed, "remainder")
        act_band = self._band_scaled(self._band(level, "activity"), n, frac_elapsed, "activity")
        peak_band = self._band_scaled(self._band(level, "peak"), n, frac_elapsed, "peak")
        ptime_band = self._band_scaled(self._band(level, "peaktime"), n, frac_elapsed, "peaktime")

        # 90% ranges from matched samples (when available)
        rem_lo = rem_hi = None
        if getattr(self, 'simple_model', None) and self.simple_model.state == OK and self.simple_model.trimmed_afters:
            rem_lo, rem_hi = self._percentiles(self.simple_model.trimmed_afters, 0.05, 0.95)
        act_lo = act_hi = None
        if nxh_acts:
            act_lo, act_hi = self._percentiles(nxh_acts, 0.05, 0.95)
        pk_lo = pk_hi = None
        ptime_lo = ptime_hi = None
        if peaks:
            pvals = [int(p) for p, _ in peaks]
            ptmins = [int(pt.num) for _p, pt in peaks]
            pk_lo, pk_hi = self._percentiles(pvals, 0.05, 0.95)
            tlo, thi = self._percentiles(ptmins, 0.05, 0.95)
            ptime_lo, ptime_hi = VTime(tlo), VTime(thi)

        # Build table rows with added Range and %confidence columns, preserving existing text
        def rng_str(lo, hi, is_time=False):
            if lo is None or hi is None:
                return ""
            if is_time:
                return f"{lo.short}-{hi.short}"
            # Clamp lower bound of numeric ranges to 0 to avoid negatives
            try:
                lo_i = max(0, int(lo))
                hi_i = int(hi)
            except Exception:
                return ""
            return f"{lo_i}-{hi_i}"

        # Prepare per-measure smooth confidences reflecting variation
        # Remainder confidence: spread relative to center (use hi as scale if center small)
        rem_spread = (rem_hi - rem_lo) if (rem_lo is not None and rem_hi is not None) else None
        rem_scale = max(1.0, float(remainder), float(rem_hi or 0)) if rem_spread is not None else None
        conf_rem = self._smooth_conf(n, frac_elapsed, rem_spread, rem_scale)

        # Peak value confidence
        pk_spread = (pk_hi - pk_lo) if (pk_lo is not None and pk_hi is not None) else None
        pk_scale = max(1.0, float(peak_val), float(pk_hi or 0)) if pk_spread is not None else None
        conf_pk = self._smooth_conf(n, frac_elapsed, pk_spread, pk_scale)

        # Peak time confidence: minutes window relative to total span
        pt_spread = ((ptime_hi.num - ptime_lo.num) if (ptime_lo is not None and ptime_hi is not None) else None)
        pt_scale = float(total_span) if pt_spread is not None else None
        conf_pt = self._smooth_conf(n, frac_elapsed, pt_spread, pt_scale)

        # Next-hour activity confidence
        act_spread = (act_hi - act_lo) if (act_lo is not None and act_hi is not None) else None
        act_scale = max(1.0, float(nxh_activity), float(act_hi or 0)) if act_spread is not None else None
        conf_act = self._smooth_conf(n, frac_elapsed, act_spread, act_scale)

        # Build three tables: Simple (median), Linear Regression, Schedule-Only Recent
        t_end = VTime(min(self.as_of_when.num + 60, 24 * 60))
        # Apply calibration residual bands if available to build model-specific ranges and margins
        def _apply_calib(model_code: str, measure_code: str, point_val: int, base_band: int) -> tuple[str, int]:
            band = base_band
            rstr = ""
            calib = self._calib_residual_band(model_code, measure_code, frac_elapsed)
            if calib:
                q05, q95 = calib
                # Use symmetric margin as half-width (rounded)
                half = int(round(max(0.0, (q95 - q05) / 2.0)))
                band = max(base_band, half)
                rstr = rng_str(int(point_val + q05), int(point_val + q95), False)
            return rstr, band

        # Simple (SM)
        sm_act_rng, sm_act_band = _apply_calib("SM", "act", int(nxh_activity), act_band)
        sm_fut_rng, sm_fut_band = _apply_calib("SM", "fut", int(remainder), rem_band)
        sm_pk_rng, sm_pk_band = _apply_calib("SM", "peak", int(peak_val), peak_band)
        simple_rows = [
            (self._activity_label(t_end), f"{int(nxh_activity)}", f"+/- {sm_act_band}", sm_act_rng or rng_str(act_lo, act_hi, False), conf_act),
            (self.MEAS_FURTHER, f"{int(remainder)}", f"+/- {sm_fut_band} bikes", sm_fut_rng or rng_str(rem_lo, rem_hi, False), conf_rem),
            (self.MEAS_TIME_MAX, f"{peak_time.short}", f"+/- {ptime_band} minutes", rng_str(ptime_lo, ptime_hi, True), conf_pt),
            (self.MEAS_MAX, f"{int(peak_val)}", f"+/- {sm_pk_band} bikes", sm_pk_rng or rng_str(pk_lo, pk_hi, False), conf_pk),
        ]

        # Linear regression helpers
        def _linreg(xs: list[float], ys: list[float]):
            npts = len(xs)
            if npts < 2:
                return None
            sx = sum(xs); sy = sum(ys)
            sxx = sum(x*x for x in xs); sxy = sum(x*y for x, y in zip(xs, ys))
            denom = npts * sxx - sx * sx
            if denom == 0:
                return None
            a = (npts * sxy - sx * sy) / denom
            b = (sy - a * sx) / npts
            return a, b

        # Remainder via LR (befores->afters)
        lr_remainder = int(remainder)
        try:
            lr = LRModel()
            lr.calculate_model(list(zip(self.befores, self.afters)))
            lr.guess(self.bikes_so_far)
            if lr.state == OK and isinstance(lr.further_bikes, int):
                lr_remainder = int(lr.further_bikes)
        except Exception:
            pass
        # Activity via LR (befores->activity)
        lr_act_val = int(nxh_activity)
        coeff = _linreg([float(x) for x in self.befores], [float(y) for y in all_acts])
        if coeff:
            a, b = coeff
            lr_act_val = max(0, int(round(a * float(self.bikes_so_far) + b)))
        # Peak via LR (befores->peak)
        lr_peak_val = int(peak_val)
        coeff_p = _linreg([float(x) for x in self.befores], [float(y) for y in all_peaks])
        if coeff_p:
            ap, bp = coeff_p
            lr_peak_val = max(0, int(round(ap * float(self.bikes_so_far) + bp)))
        # LR residual-based ranges and bands
        def _resid_ranges(xs: list[int], ys: list[int], a_b):
            if not a_b:
                return None, None
            a, b = a_b
            resids = [int(y - (a * float(x) + b)) for x, y in zip(xs, ys)]
            if not resids:
                return None, None
            lo, hi = self._percentiles(resids, 0.05, 0.95)
            return int(lo), int(hi)

        # Remainder residuals
        rem_lo_res, rem_hi_res = _resid_ranges(self.befores, self.afters, _linreg([float(x) for x in self.befores], [float(y) for y in self.afters]))
        # Activity residuals
        act_lo_res, act_hi_res = _resid_ranges(self.befores, all_acts, coeff)
        # Peak residuals
        pk_lo_res, pk_hi_res = _resid_ranges(self.befores, all_peaks, coeff_p)

        # Compute LR 90% ranges by adding residual bounds to point predictions
        def _rng_from_res(point: int, lo_res, hi_res):
            if lo_res is None or hi_res is None:
                return ""
            return rng_str(point + lo_res, point + hi_res, False)

        # Scale bands per-model using range width ratios (clamped)
        def _scale_band(base: int, model_width: int | None, ref_width: int | None) -> int:
            if model_width is None or ref_width is None or ref_width <= 0:
                return base
            import math
            sf = math.sqrt(max(1, model_width) / max(1, ref_width))
            sf = max(0.5, min(2.0, sf))
            return int(round(base * sf))

        # Reference (simple) widths
        rem_w_ref = (rem_hi - rem_lo) if (rem_lo is not None and rem_hi is not None) else None
        act_w_ref = (act_hi - act_lo) if (act_lo is not None and act_hi is not None) else None
        pk_w_ref = (pk_hi - pk_lo) if (pk_lo is not None and pk_hi is not None) else None

        # LR widths
        rem_w_lr = ((rem_hi_res - rem_lo_res) if (rem_lo_res is not None and rem_hi_res is not None) else None)
        act_w_lr = ((act_hi_res - act_lo_res) if (act_lo_res is not None and act_hi_res is not None) else None)
        pk_w_lr = ((pk_hi_res - pk_lo_res) if (pk_lo_res is not None and pk_hi_res is not None) else None)

        # Model-specific bands and calibrated ranges for LR
        lr_act_rng, act_band_lr = _apply_calib("LR", "act", lr_act_val, _scale_band(act_band, act_w_lr, act_w_ref))
        lr_rem_rng, rem_band_lr = _apply_calib("LR", "fut", lr_remainder, _scale_band(rem_band, rem_w_lr, rem_w_ref))
        lr_pk_rng, pk_band_lr = _apply_calib("LR", "peak", lr_peak_val, _scale_band(peak_band, pk_w_lr, pk_w_ref))
        pt_band_lr = ptime_band  # keep same for time for now

        # Model-specific confidences
        conf_rem_lr = self._smooth_conf(len(self.befores), frac_elapsed, rem_w_lr, max(1.0, float(lr_remainder)))
        conf_act_lr = self._smooth_conf(len(self.befores), frac_elapsed, act_w_lr, max(1.0, float(lr_act_val)))
        conf_pk_lr = self._smooth_conf(len(self.befores), frac_elapsed, pk_w_lr, max(1.0, float(lr_peak_val)))
        conf_pt_lr = conf_pt

        lr_rows = [
            (self._activity_label(t_end), f"{lr_act_val}", f"+/- {act_band_lr}", lr_act_rng or _rng_from_res(lr_act_val, act_lo_res, act_hi_res), conf_act_lr),
            (self.MEAS_FURTHER, f"{lr_remainder}", f"+/- {rem_band_lr} bikes", lr_rem_rng or _rng_from_res(lr_remainder, rem_lo_res, rem_hi_res), conf_rem_lr),
            (self.MEAS_TIME_MAX, f"{peak_time.short}", f"+/- {pt_band_lr} minutes", rng_str(ptime_lo, ptime_hi, True), conf_pt_lr),
            (self.MEAS_MAX, f"{lr_peak_val}", f"+/- {pk_band_lr} bikes", lr_pk_rng or _rng_from_res(lr_peak_val, pk_lo_res, pk_hi_res), conf_pk_lr),
        ]

        # Schedule-only recent model (ignores bikes_so_far; uses recent N similar days)
        recent_n = int(getattr(wcfg, "EST_RECENT_DAYS", 30))
        # Map date -> after (remainder proxy)
        date_to_after = {d: int(self.afters[i]) for i, d in enumerate(self.similar_dates) if i < len(self.afters)}
        # Pick most recent similar dates
        rec_dates = sorted(self.similar_dates, reverse=True)[:recent_n]
        # Build lists for recent window
        rec_acts: list[int] = []
        rec_afters: list[int] = []
        rec_peaks: list[int] = []
        rec_ptimes: list[int] = []
        for d in rec_dates:
            vlist = self._visits_for_date(d)
            _b3, _a3, _o3, ins3, outs3 = self._counts_for_time(vlist, self.as_of_when)
            rec_acts.append(int(ins3 + outs3))
            # afters from pre-aggregated if available
            if d in date_to_after:
                rec_afters.append(int(date_to_after[d]))
            else:
                # fallback compute 'after' by counting ins after now
                _btmp, _atmp, *_ = self._counts_for_time(vlist, self.as_of_when)
                rec_afters.append(int(_atmp))
            p3, pt3 = self._peak_all_day_occupancy(vlist)
            rec_peaks.append(int(p3))
            rec_ptimes.append(int(pt3.num))

        # Predictions as medians over recent window
        import statistics as _st
        rec_act_val = int(_st.median(rec_acts)) if rec_acts else int(nxh_activity)
        rec_rem_val = int(_st.median(rec_afters)) if rec_afters else int(remainder)
        rec_peak_val = int(_st.median(rec_peaks)) if rec_peaks else int(peak_val)
        rec_ptime_val = VTime(int(_st.median(rec_ptimes))) if rec_ptimes else peak_time

        # Ranges over recents
        r_act_lo, r_act_hi = self._percentiles(rec_acts, 0.05, 0.95) if rec_acts else (None, None)
        r_rem_lo, r_rem_hi = self._percentiles(rec_afters, 0.05, 0.95) if rec_afters else (None, None)
        r_pk_lo, r_pk_hi = self._percentiles(rec_peaks, 0.05, 0.95) if rec_peaks else (None, None)
        _pt_lo, _pt_hi = self._percentiles(rec_ptimes, 0.05, 0.95) if rec_ptimes else (None, None)
        r_pt_lo, r_pt_hi = (VTime(_pt_lo), VTime(_pt_hi)) if (_pt_lo is not None and _pt_hi is not None) else (None, None)

        # Model-specific bands via width scaling
        r_act_w = (r_act_hi - r_act_lo) if (r_act_lo is not None and r_act_hi is not None) else None
        r_rem_w = (r_rem_hi - r_rem_lo) if (r_rem_lo is not None and r_rem_hi is not None) else None
        r_pk_w = (r_pk_hi - r_pk_lo) if (r_pk_lo is not None and r_pk_hi is not None) else None
        # Apply calibration to REC as well
        rec_act_rng, act_band_rec = _apply_calib("REC", "act", rec_act_val, _scale_band(act_band, r_act_w, act_w_ref))
        rec_rem_rng, rem_band_rec = _apply_calib("REC", "fut", rec_rem_val, _scale_band(rem_band, r_rem_w, rem_w_ref))
        rec_pk_rng, pk_band_rec = _apply_calib("REC", "peak", rec_peak_val, _scale_band(peak_band, r_pk_w, pk_w_ref))
        pt_band_rec = ptime_band

        # Confidences for recents (n = #recent dates used)
        conf_act_rec = self._smooth_conf(len(rec_dates), frac_elapsed, r_act_w, max(1.0, float(rec_act_val)))
        conf_rem_rec = self._smooth_conf(len(rec_dates), frac_elapsed, r_rem_w, max(1.0, float(rec_rem_val)))
        conf_pk_rec = self._smooth_conf(len(rec_dates), frac_elapsed, r_pk_w, max(1.0, float(rec_peak_val)))
        conf_pt_rec = conf_pt

        rec_rows = [
            (self._activity_label(t_end), f"{rec_act_val}", f"+/- {act_band_rec}", rec_act_rng or rng_str(r_act_lo, r_act_hi, False), conf_act_rec),
            (self.MEAS_FURTHER, f"{rec_rem_val}", f"+/- {rem_band_rec} bikes", rec_rem_rng or rng_str(r_rem_lo, r_rem_hi, False), conf_rem_rec),
            (self.MEAS_TIME_MAX, f"{rec_ptime_val.short}", f"+/- {pt_band_rec} minutes", rng_str(r_pt_lo, r_pt_hi, True), conf_pt_rec),
            (self.MEAS_MAX, f"{rec_peak_val}", f"+/- {pk_band_rec} bikes", rec_pk_rng or rng_str(r_pk_lo, r_pk_hi, False), conf_pk_rec),
        ]

        # Build a Mixed table choosing best per measure across models
        def _parse_conf(pct: str) -> int:
            try:
                return int(str(pct).strip().strip('%'))
            except Exception:
                return 0
        def _range_width(rng: str, is_time: bool) -> int:
            if not rng:
                return 10**9
            try:
                a, b = rng.split('-', 1)
                if is_time:
                    va = VTime(a.strip())
                    vb = VTime(b.strip())
                    if not va or not vb:
                        return 10**9
                    return max(0, int(vb.num) - int(va.num))
                return abs(int(str(b).strip()) - int(str(a).strip()))
            except Exception:
                return 10**9

        # Map measure title to index in consistent row lists
        # All lists are in identical order matching our desired display
        measures = [
            self._activity_label(t_end),
            self.MEAS_FURTHER,
            self.MEAS_TIME_MAX,
            self.MEAS_MAX,
        ]
        tables_by_model = {
            'SM': simple_rows,
            'LR': lr_rows,
            'REC': rec_rows,
        }
        mixed_rows: list[tuple[str, str, str, str, str]] = []
        mixed_models: list[str] = []
        selected_by_model: dict[str, set[int]] = {'SM': set(), 'LR': set(), 'REC': set()}
        for idx, title_txt in enumerate(measures):
            # Collect candidates (model, row)
            candidates = []
            for mdl_code, rows in tables_by_model.items():
                if idx >= len(rows):
                    continue
                r = rows[idx]
                # r = (measure, value, margin, range, conf)
                rng = r[3]
                is_time = (idx == 2)
                width = _range_width(rng, is_time)
                confv = _parse_conf(r[4])
                candidates.append((width, -confv, mdl_code, r))
            if not candidates:
                continue
            # Primary: minimal width; Secondary: highest confidence; Tertiary: use calibration best_model if exact tie
            candidates.sort()
            # If multiple with same width and conf, prefer calibration suggestion if available
            best = candidates[0]
            if self._calib_best and len(candidates) > 1:
                # figure measure key for calibration map
                meas_key = 'act' if idx == 0 else ('fut' if idx == 1 else ('peak' if idx == 3 else None))
                if meas_key:
                    lbl = self._bin_label(frac_elapsed)
                    pref = None
                    try:
                        pref = self._calib_best[meas_key][lbl]
                    except Exception:
                        pref = None
                    if pref:
                        # find first candidate matching pref among those tied on width/conf
                        w0, c0 = candidates[0][0], candidates[0][1]
                        for cand in candidates:
                            if cand[0] == w0 and cand[1] == c0 and cand[2] == pref:
                                best = cand; break
            mixed_rows.append(best[3])
            mixed_models.append(best[2])
            try:
                selected_by_model[best[2]].add(idx)
            except Exception:
                pass

        # Store tables for rendering (Mixed first)
        self.tables: list[tuple[str, list[tuple[str, str, str, str, str]]]] = [
            ("Estimation — Mixed (per best model)", mixed_rows),
            ("Estimation — Similar-Days Median", simple_rows),
            ("Estimation — Linear Regression", lr_rows),
            ("Estimation — Schedule-Only (Recent)", rec_rows),
        ]
        self._mixed_models = mixed_models
        self._selected_by_model = selected_by_model

        # Back-compat: expose min/max remainder used by callers expecting legacy API
        rem_min = max(0, int(remainder) - rem_band)
        rem_max = int(remainder) + rem_band
        self.min = rem_min
        self.max = rem_max
        self.state = OK

    def result_msg(self) -> list[str]:
        if self.state == ERROR:
            return [f"Can't estimate because: {self.error}"]
        if not getattr(self, 'tables', None):
            return ["No estimates available"]
        lines: list[str] = []

        if not self.verbose:
            # Default: show only Mixed with Model column; hide Error margin
            title_base, rows = self.tables[0]
            header = ["Measure", "Value", "Range (90%)", "% confidence", "Model"]
            # Prepare rows with model info
            mixed_rows_disp = []
            for i, r in enumerate(rows):
                model = (self._mixed_models[i] if hasattr(self, '_mixed_models') and i < len(self._mixed_models) else "")
                # r: (measure, value, margin, range, conf)
                mixed_rows_disp.append([r[0], r[1], r[3], r[4], model])
            widths = [max(len(str(r[i])) for r in ([header] + mixed_rows_disp)) for i in range(5)]
            def fmt_row5(r: list[str]) -> str:
                return (
                    f"{str(r[0]).ljust(widths[0])}  "
                    f"{str(r[1]).rjust(widths[1])}  "
                    f"{str(r[2]).ljust(widths[2])}  "
                    f"{str(r[3]).ljust(widths[3])}  "
                    f"{str(r[4]).ljust(widths[4])}"
                )
            title = f"{title_base} (as of {self.as_of_when.short})"
            lines += [title, fmt_row5(header), fmt_row5(["-"*widths[0], "-"*widths[1], "-"*widths[2], "-"*widths[3], "-"*widths[4]])]
            for r in mixed_rows_disp:
                lines.append(fmt_row5(r))
        else:
            # FULL: show model tables only (do not repeat Mixed), keep Error margin,
            # add '*' as far-right column for rows selected in Mixed.
            for title_base, rows in self.tables:
                # Skip Mixed table in FULL
                if title_base.startswith("Estimation — Mixed"):
                    continue
                header = ["Measure", "Value", "Error margin", "Range (90%)", "% confidence", ""]
                # Possibly mark measure with '*' if selected in Mixed
                title_code = None
                if title_base.endswith("Similar-Days Median"):
                    title_code = 'SM'
                elif title_base.endswith("Linear Regression"):
                    title_code = 'LR'
                elif title_base.endswith("Schedule-Only (Recent)"):
                    title_code = 'REC'
                # Build a preview of rows including mark column to size widths
                preview_rows = []
                for idx, (m, v, c, r90, pc) in enumerate(rows):
                    mark = ""
                    if title_code and hasattr(self, '_selected_by_model'):
                        try:
                            if idx in self._selected_by_model.get(title_code, set()):
                                mark = "*"
                        except Exception:
                            pass
                    # Mixed table rows are all selected
                    if title_base.endswith("per best model)"):
                        mark = "*"
                    preview_rows.append([m, v, c, r90, pc, mark])

                widths = [max(len(str(r[i])) for r in ([header] + preview_rows)) for i in range(6)]
                def fmt_row(r: list[str]) -> str:
                    return (
                        f"{str(r[0]).ljust(widths[0])}  "
                        f"{str(r[1]).rjust(widths[1])}  "
                        f"{str(r[2]).ljust(widths[2])}  "
                        f"{str(r[3]).ljust(widths[3])}  "
                        f"{str(r[4]).rjust(widths[4])}  "
                        f"{str(r[5]).rjust(widths[5])}"
                    )
                title = f"{title_base} (as of {self.as_of_when.short})"
                if lines and lines[-1] != "":
                    lines.append("")
                # Dashes row for 6 columns
                lines += [title, fmt_row(header), fmt_row(["-"*widths[0], "-"*widths[1], "-"*widths[2], "-"*widths[3], "-"*widths[4], "-"*widths[5]])]
                for row6 in preview_rows:
                    lines.append(fmt_row(row6))
        # Verbose details if requested
        if self.verbose:
            lines.append("")
            lines.append("Details")
            lines.append("-------")
            # Report calibration usage and breadcrumbs here (bottom)
            calib_msg = "Calibration JSON: used" if self._calib else "Calibration JSON: not used"
            lines.append(calib_msg)
            if self._calib_debug:
                for msg in self._calib_debug:
                    lines.append(f"  {msg}")
            lines.append(f"Bikes so far: {self.bikes_so_far}")
            lines.append(f"Open/Close: {self.time_open} - {self.time_closed}")
            open_num = self.time_open.num if self.time_open and self.time_open.num is not None else 0
            close_num = self.time_closed.num if self.time_closed and self.time_closed.num is not None else 24*60
            span = max(1, close_num - open_num)
            frac_elapsed = max(0.0, min(1.0, (self.as_of_when.num - open_num) / span))
            lines.append(f"Day progress: {int(frac_elapsed*100)}% (span {span} minutes)")
            lines.append(f"Similar-day rows: {len(self.similar_dates)} ({self._match_note})")
            lines.append(f"Match tolerance (VARIANCE): {self.VARIANCE}")
            lines.append(f"Outlier Z cutoff: {self.Z_CUTOFF}")
            if getattr(self, 'simple_model', None) and self.simple_model.state == OK:
                sm = self.simple_model
                lines.append("")
                lines.append("Simple model (similar days)")
                lines.append(f"  Points matched: {sm.num_points}")
                lines.append(f"  Discarded as outliers: {sm.num_discarded}")
                lines.append(f"  Min/Median/Mean/Max: {sm.min}/{sm.median}/{sm.mean}/{sm.max}")
            # Confidence
            matched = self._matched_dates()
            level = self._confidence_level(len(matched), frac_elapsed)
            lines.append("")
            lines.append(f"Confidence level: {level}")
            rb = self._band(level,'remainder'); ab = self._band(level,'activity'); pb = self._band(level,'peak'); tb = self._band(level,'peaktime')
            rbs = self._band_scaled(rb, len(matched), frac_elapsed, 'remainder')
            abs_ = self._band_scaled(ab, len(matched), frac_elapsed, 'activity')
            pbs = self._band_scaled(pb, len(matched), frac_elapsed, 'peak')
            tbs = self._band_scaled(tb, len(matched), frac_elapsed, 'peaktime')
            lines.append(
                f"Bands used (remainder/activity/peak/peaktime): {rbs}/{abs_}/{pbs}/{tbs}"
            )
            lines.append(
                f"Base bands (before scaling): {rb}/{ab}/{pb}/{tb}"
            )
        return lines


if __name__ == "__main__":
    # Prefer new-API parameters; fall back to old for compatibility
    def _init_from_cgi_new() -> Estimator:
        query_str = ut.untaint(os.environ.get("QUERY_STRING", ""))
        query_parms = urllib.parse.parse_qs(query_str)
        bikes_so_far = query_parms.get("bikes_so_far", [""])[0]
        opening_time = query_parms.get("opening_time", [""])[0]
        closing_time = query_parms.get("closing_time", [""])[0]
        max_bikes_today = query_parms.get("max_bikes_today", [""])[0]
        max_bikes_time_today = query_parms.get("max_bikes_time_today", [""])[0]
        est_type = (query_parms.get("estimation_type", [""])[0] or "").strip().lower()
        return Estimator(
            bikes_so_far=bikes_so_far,
            opening_time=opening_time,
            closing_time=closing_time,
            max_bikes_today=max_bikes_today,
            max_bikes_time_today=max_bikes_time_today,
            verbose=(est_type == "verbose"),
        )

    def _init_from_args_new() -> Estimator:
        my_args = sys.argv[1:] + ["", "", "", "", ""]
        return Estimator(
            bikes_so_far=my_args[0],
            opening_time=my_args[1],
            closing_time=my_args[2],
            max_bikes_today=my_args[3],
            max_bikes_time_today=my_args[4],
        )

    estimate_any = None
    is_cgi = bool(os.environ.get("REQUEST_METHOD"))
    if is_cgi:
        print("Content-type: text/plain\n")
        q = ut.untaint(os.environ.get("QUERY_STRING", ""))
        qd = urllib.parse.parse_qs(q)
        est_type = (qd.get("estimation_type", [""])[0] or "").strip().lower()
        if est_type == "legacy":
            estimate_any = _init_from_cgi_old()
        else:
            # 'current' (default) and 'verbose' both use the new estimator for now
            estimate_any = _init_from_cgi_new()
    else:
        # CLI defaults to new API
        estimate_any = _init_from_args_new()

    if estimate_any.state != ERROR:
        estimate_any.guess()

    for line in estimate_any.result_msg():
        print(line)
