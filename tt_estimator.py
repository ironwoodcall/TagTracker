#!/usr/bin/env python3
"""Estimate how many more bikes to expect.

Reads info from day-end-form (csv) or from other
sources (e.g. weather info from NRCan? tbd)

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
import numpy as np

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
import tt_conf as cfg
import tt_util as ut
from tt_time import VTime


class Estimator:
    def __init__(
        self, bikes_so_far: int, dow: int = None, as_of_when="", closing=""
    ) -> None:
        """Set up the inputs and results vars.

        This will make guesses about any missing inputs
        except the number of bikes so far.
        """
        # This says whether or not a good result is set.
        self.ok = False

        # These are inputs:
        if not dow:
            dow = ut.dow_int("today")
        self.dow = dow

        as_of_when = VTime(as_of_when)
        as_of_when = as_of_when if as_of_when else VTime("now")
        self.as_of_when = as_of_when

        self.bikes_so_far = bikes_so_far

        if not closing:
            closing = cfg.valet_hours(ut.date_str("today"))[1]
        self.closing = closing  # Closing time today

        # These are for the resulting estimate
        self.expected_min = None
        self.expected_max = None
        self.expected_median = None
        self.expected_mean = None
        self.data_points = None
        self.discarded_points = None

    @staticmethod
    def _doing_data_entry() -> bool:
        """Check whether using tagtracker data entry.

        Returns True if this is tagtracker.py
        """
        main_file = os.path.basename(ut.top_level_script())
        return bool(main_file == "tagtracker.py")

    @staticmethod
    def _discard_outliers(data: list[int]) -> list[int]:
        """Return list with numbers with low z scores."""
        Z_THRESHOLD = 2.5  # Seems about right?
        mean = np.mean(data)
        std_dev = np.std(data)
        z_scores = [(x - mean) / std_dev for x in data]

        # Exclude values that have z-scores greater than the threshold
        filtered_data = [
            data[i]
            for i in range(len(data))
            if abs(z_scores[i]) <= Z_THRESHOLD
        ]
        return filtered_data

    def database_fetch(self):
        """Set self result info from the database


        open db conx
        fetch from db, list of rows that are:
            date,time_in
            from visit
            where dow matches and closing time matches
            order by date,time_in

        for each date
            count bikes up to time
            if matches (rounded)
                count bikes after
                add to list

        find min and max
        discard outliers
        calculate mean and median of trimmed data


        """
        pass

        def short_message(self) -> None:
            """Return 'OK # # # #' string."""
            pass
        def long_message(self) -> None:
            """Return list of strings as long message."""
            msg = f"For day of week ... with closing time etc etc"

def url_fetch(
    bikes_so_far: int, dow: int = None, as_of_when="", closing=""
) -> Estimator:
    """Call estimator URL to get an Estimator object.

    This is presumably what one would call if the database
    is not on the same machine.
    """
    est = Estimator(bikes_so_far, dow, as_of_when, closing)
    if not cfg.ESTIMATOR_URL_BASE:
        return est
    url_parms = f"dow={est.dow}&as_of_when={est.as_of_when}&bikes_so_far={est.bikes_so_far}&closing={est.closing}&type=short"
    url = f"{cfg.ESTIMATOR_URL_BASE}?{url_parms}"

    try:
        response = urllib.request.urlopen(url)
        data = response.read()
        decoded_data = data.decode("utf-8")
    except urllib.error.URLError:
        return False

    bits = decoded_data.split()
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

if __name__ == "__main__":
    pass
    # If called as a cgi,
    #   pull args from env
    #   is_cgi = True
    # else
    #   args from command line
    #   is_cgi = False

    # If db file is not present, stop

    # est = Estimator(.....)
    # est.database_fetch()
    # if is_cgi:
    #   html header
    # if est.ok:
    #   if short:
    #       "OK # # # #"
    #   else:
    #       "blah blah blah" <-- prob a sep function
    # else:
    #   "error"
    # if is_cgi:
    #   end html