#!/usr/bin/env python3

"""TagTracker by Julias Hocking.

For a given date, find its default hours of operation.

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

from datetime import datetime
from client_base_config import SEASON_HOURS,SPECIAL_HOURS
from tt_constants import MaybeDate

def get_default_hours(date_str:MaybeDate) -> tuple[str,str]:
    """Look for opening/closing hours for this date.

    Reads data structures SEASON_HOURS and SPECIAL_HOURS from
    client config file.

    If no match or string isbad, returns "","".
    """
    # Find the day of the week (& test for a badly formed date string).
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        iso_day = date.isoweekday() #1=Mo,7=Su
    except ValueError:
        return "",""
    # First see if this is listed as a special day.
    for special_date, hours in SPECIAL_HOURS.items():
        if date_str == special_date:
            return tuple(hours)
    # Now look for a set of hours for this day within a date range.
    for i in range(0, len(SEASON_HOURS), 2):
        start_date = datetime.strptime(SEASON_HOURS[i][0], '%Y-%m-%d')
        end_date = datetime.strptime(SEASON_HOURS[i][1], '%Y-%m-%d')
        if start_date <= date <= end_date:
            hours_map = SEASON_HOURS[i + 1]
            if iso_day in hours_map:
                return tuple(hours_map[iso_day])
    # No match
    return "", ""

