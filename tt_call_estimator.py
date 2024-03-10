#!/usr/bin/env python3
"""Call the estimator from the terminal.


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

import client_base_config as cfg
import tt_util as ut
from tt_time import VTime
import tt_trackerday


def get_estimate_via_url(
    day_data: tt_trackerday.TrackerDay,
    bikes_so_far: int,
    as_of_when="",
    dow: int = None,
    closing_time="",
) -> list[str]:
    """Call estimator URL to get the estimate.

    This is presumably what one would call if the database
    is not on the same machine.
    """
    if not bikes_so_far:
        bikes_so_far = len(day_data.bikes_in)
    if not as_of_when:
        as_of_when = VTime("now")
    if not dow:
        dow = ut.dow_int("today")
        if not closing_time:
            closing_time = day_data.closing_time

    if not cfg.ESTIMATOR_URL_BASE:
        return ["No estimator URL defined"]
    url_parms = (
        f"bikes_so_far={bikes_so_far}&as_of_when={as_of_when}"
        f"&dow={dow}&as_of_when={as_of_when}"
    )
    if closing_time:
        url_parms = f"{url_parms}&closing_time={closing_time}"

    url = f"{cfg.ESTIMATOR_URL_BASE}?{url_parms}"
    ##ut.squawk(f"{url=}")
    try:
        response = urllib.request.urlopen(url)
        data = response.read()
        decoded_data = data.decode("utf-8")
    except urllib.error.URLError:
        return ["URLError return"]

    return decoded_data.splitlines()
