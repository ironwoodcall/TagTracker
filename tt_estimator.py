#!/usr/bin/env python3
"""Estimate how many more bikes to expect.

Call (as itself) as:
    self    bikes_so_far, dow, as_of_when, closing_time
    where
        bikes_so_far: is how many bikes in by as_of_when (mandatory)
        dow: is ISO day of week (1=Mon..7=Su) or a YYYY-MM-DD date
            (default if missing or "": today)
        as_of_when: is the time for which the estimate is made, HH:MM, H:MM, HMM
            (default if missing or "": now)
        closing_time: HHMM of time the valet closes day of estimate
            (default if missing or "": will try to determine using config functions)
        result_type: 'long' or 'short'.
            'long' prints a multi-line response describing the result
            'short' prints a short result for parsing:
                "OK",mean,median,min,max,used_data,discarded_data
                where:
                    "OK" means succesful result. Anything else means
                        there was an error or there is no answer
                    min,max are the (un-trimmed) historic min and max
                        bikes-in counts for this set of parameters
                    mean,median: values computed from trimmed data
                    used_data: is the count of the list of historic values
                    discarded_data: is the count of values that were discarded
                        as being outliers
            (default:long)

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


SHORT = "short"
LONG = "long"


class Estimator:
    """Data and methods to estimate how many more bikes to expect."""

    def __init__(
        self,
        bikes_so_far="",
        dow="",
        as_of_when="",
        closing_time="",
        result_type="",
    ) -> None:
        """Set up the inputs and results vars.

        Inputs are thoroughly checked and default values figured out.


        This will make guesses about any missing inputs
        except the number of bikes so far.
        """
        # This stays False until a known ok result is set.
        self.ok = False
        # This stays empty unless set to an error message.
        self.message = ""  # Error message
        # These are inputs
        self.bikes_so_far = None
        self.dow = None
        self.as_of_when = None
        self.closing_time = None
        self.result_type = "long"  # Default is "long".
        # These are for the resulting estimate
        self.expected_mean = None
        self.expected_median = None
        self.expected_min = None
        self.expected_max = None
        self.data_points = None
        self.discarded_points = None

        # Now process the inputs from passed-in values.
        bikes_so_far = str(bikes_so_far).strip()
        if not bikes_so_far.isdigit():
            self.message = "Missing or bad bikes_so_far parameter."
            return
        self.bikes_so_far = int(bikes_so_far)

        dow = dow if dow else "today"
        if str(dow) in ["1", "2", "3", "4", "5", "6", "7"]:
            self.dow = int(dow)
        else:
            self.dow = ut.dow_int(dow)  # returns None if bad
        if not self.dow:
            self.message = "Bad dow parameter."
            return

        as_of_when = as_of_when if as_of_when else "now"
        self.as_of_when = VTime(as_of_when)
        if not self.as_of_when:
            self.message = "Bad as_of_when parameter."
            return

        if not closing_time:
            closing_time = cfg.valet_hours(ut.date_str("today"))[1]
        self.closing_time = VTime(closing_time)  # Closing time today
        if not self.closing_time:
            self.message = "Missing or bad closing_time parameter."
            return

        if result_type:
            self.result_type = result_type.lower().strip()
        if self.result_type not in [SHORT, LONG]:
            self.message = "Bad result_type parameter."
            return

    @staticmethod
    def _doing_data_entry() -> bool:
        """Check whether using tagtracker data entry.

        Returns True if this is tagtracker.py
        """
        main_file = os.path.basename(ut.top_level_script())
        return bool(main_file == "tagtracker.py")

    @staticmethod
    def _discard_outliers(data: list[int], z_cutoff: float) -> list[int]:
        """Return list of values with z <= z_cutoff."""
        # For 2 or fewer data points, the idea of outliers means nothing.
        if len(data) <= 2:
            return data
        # Make new list, discarding outliers.
        mean = statistics.mean(data)
        std_dev = statistics.stdev(data)
        z_scores = [(x - mean) / std_dev for x in data]
        filtered_data = [
            data[i] for i in range(len(data)) if abs(z_scores[i]) <= z_cutoff
        ]
        return filtered_data

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
               /* day.date AS date, */
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

    def database_fetch(self) -> None:
        """Set self result info from the database."""
        # Rounding for how close a historic bikes_so_far
        # is to the requested to be considered the same
        VARIANCE = 10  # pylint: disable=invalid-name
        # Z score at which to eliminate a data point an an outlier
        Z_CUTOFF = 2.5  # pylint: disable=invalid-name

        # Collect data from database
        # pylint: disable-next=invalid-name
        DBFILE = "../data/cityhall_bikevalet.db"
        if not os.path.exists(DBFILE):
            self.message = "Database not found"
            return

        database = db.db_connect(DBFILE)
        sql = self._sql_str()
        data_rows = db.db_fetch(database, sql, ["before", "after"])
        befores = [int(r.before) for r in data_rows]
        afters = [int(r.after) for r in data_rows]

        # Find data points that match our bikes-so-far
        # values within this dist are considered same
        data = []
        for i, bikes_so_far in enumerate(befores):
            if abs(bikes_so_far - self.bikes_so_far) <= VARIANCE:
                data.append(afters[i])
        self.data_points = len(data)

        # Discard outliers (z score > z cutodd)
        trimmed_data = self._discard_outliers(data, Z_CUTOFF)
        self.discarded_points = self.data_points - len(trimmed_data)

        # Check for no data.
        if not data:
            self.message = "No matching data"
            return

        # Calculate return value statistics
        # (Both data and trimmed_data now have length > 0)
        self.expected_min = min(trimmed_data)
        self.expected_max = max(trimmed_data)
        self.expected_mean = int(statistics.mean(trimmed_data))
        self.expected_median = int(statistics.median(trimmed_data))
        self.ok = True

    def short_result(self) -> str:
        """Return results as a minimalist string.

        An ok results will start with "OK" and be in the form:
            "OK",mean,median,min,max,#datapoint,#pointsdiscarded
        Anything not ok does *not* start with "OK,". It will
            likely have an error message.
        """
        if self.ok:
            return (
                "OK,"
                f"{self.expected_mean},{self.expected_median},"
                f"{self.expected_min},{self.expected_max},"
                f"{self.data_points},{self.discarded_points}"
            )
        return f"Bad: {self.message}"

    def long_result(self) -> list[str]:
        """Return list of strings as long message."""



        lines = []
        if not self.ok:
            lines.append(f"Can't estimate because: {self.message}")
            return lines

        if self.dow == 6:
            dayname = "Saturday"
        elif self.dow == 7:
            dayname = "Sunday"
        else:
            dayname = "weekday"

        mean_median = [self.expected_mean,self.expected_median]
        mean_median.sort()
        if mean_median[0] == mean_median[1]:
            mm_str = str(mean_median[0])
        else:
            mm_str = f"{mean_median[0]} or {mean_median[1]}"


        lines.append("How many more bikes?")
        lines.append("")
        if self.expected_max == self.expected_min:
            lines.append(f"Expect {self.expected_min} more bikes")
        else:
            lines.append(f"Expect {self.expected_min} to {self.expected_max} more bikes (best guess: {mm_str})")
        lines.append(f"on a {dayname} the valet closes at {self.closing_time}")
        lines.append(f"when there are {self.bikes_so_far} bikes parked by {self.as_of_when}.")
        lines.append("")
        if self.discarded_points:
            lines.append(f"This is based on {self.data_points} similar previous days ({self.discarded_points} discarded as outliers).")
        else:
            lines.append(f"This is based on {self.data_points} similar previous days.")

        return lines


def url_fetch(
    bikes_so_far: int, dow: int = None, as_of_when="", closing_time=""
) -> Estimator:
    """Call estimator URL to get an Estimator object.

    This is presumably what one would call if the database
    is not on the same machine.
    """
    est = Estimator(bikes_so_far, dow, as_of_when, closing_time)
    if not cfg.ESTIMATOR_URL_BASE:
        return est
    url_parms = (
        f"dow={est.dow}&as_of_when={est.as_of_when}"
        f"&bikes_so_far={est.bikes_so_far}&closing_time={est.closing_time}"
        f"&result_type={SHORT}"
    )
    url = f"{cfg.ESTIMATOR_URL_BASE}?{url_parms}"

    try:
        response = urllib.request.urlopen(url)
        data = response.read()
        decoded_data = data.decode("utf-8")
    except urllib.error.URLError:
        return False

    # Split on whitespace OR commas, ignoring multiples.
    bits = re.split(r"[,\s]+", decoded_data.strip())
    if len(bits) != 7 or bits[0] != "OK":
        return est
    bits = [int(x) for x in bits[1:] if x.isdigit()]
    if len(bits) != 6:
        return est

    est.expected_min = bits[0]
    est.expected_max = bits[1]
    est.expected_median = bits[2]
    est.expected_mean = bits[3]
    est.data_points = bits[4]
    est.discarded_points = bits[5]
    est.ok = True

    return est


def _init_from_cgi(query_str: str) -> Estimator:
    """Read initialization parameters from CGI env var.

    CGI parameters: as at top of file.
        bikes_so_far, dow,as_of_when,closing_time,result_type

    """
    query_parms = urllib.parse.parse_qs(query_str)
    bikes_so_far = query_parms.get("bikes_so_far", [""])[0]
    dow = query_parms.get("dow", [""])[0]
    as_of_when = query_parms.get("as_of_when", [""])[0]
    closing_time = query_parms.get("closing_time", [""])[0]
    result_type = query_parms.get("result_type", [""])[0]

    return Estimator(bikes_so_far, dow, as_of_when, closing_time, result_type)


def _init_from_args() -> Estimator:
    my_args = sys.argv[1:] + ["","","","","","","",""]
    return Estimator(
        my_args[0], my_args[1], my_args[2], my_args[3], my_args[4]
    )


if __name__ == "__main__":
    # If db file is not present, stop

    query_string = ut.untaint(os.environ.get("QUERY_STRING", ""))
    is_cgi = bool(query_string)

    estimate: Estimator
    if is_cgi:
        estimate = _init_from_cgi(query_string)
    else:
        estimate = _init_from_args()

    if not estimate.message:
        estimate.database_fetch()

    if is_cgi:
        print("Content-type: text/plain\n\n")
    if estimate.result_type == SHORT:
        print(estimate.short_result())
    else:
        for line in estimate.long_result():
            print(line)
