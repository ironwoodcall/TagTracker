#!/usr/bin/env python3
"""Call the leaderboard (maximums) from the terminal.

Copyright (C) 2023-2025 Julias Hocking & Todd Glover

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
import tt_printer as pr


def get_leaderboard_via_url(category: str | None = None) -> list[str]:
    """Call leaderboard URL to get the maximums output."""
    if not cfg.LEADERBOARD_URL_BASE:
        return ["No leaderboard URL defined"]

    pr.iprint("Fetching maximums....")
    separator = "&" if "?" in cfg.LEADERBOARD_URL_BASE else "?"
    params = ["format=plain"]
    if category:
        params.append(f"category={category}")
    url = f"{cfg.LEADERBOARD_URL_BASE}{separator}" + "&".join(params)
    try:
        response = urllib.request.urlopen(url)
        data = response.read()
        decoded_data = data.decode("utf-8")
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", "") or getattr(e, "code", "") or ""
        return [f"URLError: {reason} ({e})", f"URL: {url}"]

    return decoded_data.splitlines()
