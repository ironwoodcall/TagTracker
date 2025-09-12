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
from typing import Optional

import client_base_config as cfg
import common.tt_util as ut
from common.tt_time import VTime
import common.tt_trackerday as tt_trackerday


def get_estimate_via_url(
    day: tt_trackerday.TrackerDay,
    bikes_so_far: Optional[int] = None,
    opening_time: str = "",
    closing_time: str = "",
    max_bikes_today: str = "",
    max_bikes_time_today: str = "",
    estimation_type: str = "current",
) -> list[str]:
    """Call estimator URL (new API) to get the estimate.

    New API assumes: today, as of now. Parameters sent:
      opening_time, closing_time, bikes_so_far, [max_bikes_today], [max_bikes_time_today]
    """
    now = VTime("now")
    if bikes_so_far is None:
        bikes_so_far, _, _ = day.num_bikes_parked(now)

    # Default opening/closing from today's TrackerDay if not provided
    opening_time = opening_time or str(day.time_open)
    closing_time = closing_time or str(day.time_closed)

    if not cfg.ESTIMATOR_URL_BASE:
        return ["No estimator URL defined"]

    parts = [
        f"bikes_so_far={bikes_so_far}",
        f"opening_time={opening_time}",
        f"closing_time={closing_time}",
    ]
    if max_bikes_today:
        parts.append(f"max_bikes_today={max_bikes_today}")
    if max_bikes_time_today:
        parts.append(f"max_bikes_time_today={max_bikes_time_today}")
    if estimation_type:
        parts.append(f"estimation_type={estimation_type}")

    url = f"{cfg.ESTIMATOR_URL_BASE}?" + "&".join(parts)
    ##ut.squawk(f"{url=}")
    try:
        response = urllib.request.urlopen(url)
        data = response.read()
        decoded_data = data.decode("utf-8")
    except urllib.error.URLError as e:
        # Return a more helpful message for troubleshooting connectivity/config
        reason = getattr(e, 'reason', '') or getattr(e, 'code', '') or ''
        return [f"URLError: {reason} ({e})", f"URL: {url}"]

    return decoded_data.splitlines()
