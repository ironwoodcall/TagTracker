#!/usr/bin/env python3
"""Common functions for GI scripts for TagTracker reports.

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

import sys
import os

##from tt_globals import *

import tt_util as ut

WHAT_OVERVIEW = "overview"
WHAT_BLOCKS = "blocks"
WHAT_OVERVIEW_DOW = "overview_dow"
WHAT_BLOCKS_DOW = "blocks_dow"
WHAT_MISMATCH = "mismatch"
WHAT_ONE_DAY_TAGS = "one_day_tags"
WHAT_DATA_ENTRY = "data_entry"
WHAT_DATAFILE = "datafile"
WHAT_TAGS_LOST = "tags_lost"
WHAT_TAG_HISTORY = "tag_history"

# These constants are used to manage how report columns are sorted.
SORT_TAG = "tag"
SORT_DATE = "date"
SORT_TIME_IN = "time_in"
SORT_TIME_OUT = "time_out"
SORT_DAY = "day"
SORT_DURATION = "duration"
SORT_LEFTOVERS = "leftovers"
SORT_FULLNESS = "fullness"
SORT_PARKED = "parked"
SORT_OPEN = "open"
SORT_CLOSE = "close"

def selfref(
    what: str = "",
    qdate: str = "",
    qtime: str = "",
    qtag: str = "",
    qdow: str = "",
    qsort:str = "",
) -> str:
    """Return a self-reference with the given parameters."""

    me = ut.untaint(os.environ.get("SCRIPT_NAME", ""))
    parms = []
    if what:
        parms.append(f"what={what}")
    if qdate:
        parms.append(f"date={qdate}")
    if qtime:
        parms.append(f"time={qtime}")
    if qtag:
        parms.append(f"tag={qtag}")
    if qdow:
        parms.append(f"dow={qdow}")
    if qsort:
        parms.append(f"sort={qsort}")
    parms_str = f"?{'&'.join(parms)}" if parms else ""
    return f"{me}{ut.untaint(parms_str)}"


def style() -> str:
    """Return a CSS stylesheet as a string."""
    style_str = """
        <style>
            html {
                font-family: sans-serif;
            }

            table {
                border-collapse: collapse;
                border: 2px solid rgb(200, 200, 200);
                letter-spacing: 1px;
                font-size: 0.8rem;
            }

            td, th {
                border: 1px solid rgb(190, 190, 190);
                padding: 4px 6px;
                text-align: center; /* Center-align all td and th by default */
            }

            th {
                background-color: rgb(235, 235, 235);
            }

            td:first-child {
                text-align: left; /* Left-align the first column in each row */
            }

            tr:nth-child(even) td {
                background-color: rgb(250, 250, 250);
            }

            tr:nth-child(odd) td {
                background-color: rgb(245, 245, 245);
            }

            caption {
                padding: 10px;
            }
        </style>

        """
    return style_str


def error_out(msg: str = ""):
    if msg:
        print(msg)
    else:
        print("Bad or unknown parameter")
    sys.exit(1)


def show_help():
    print("<pre>\n")
    print("There is no help here. Read the code.")


def padval(val, length: int = 0) -> str:
    valstr = str(val)
    if length < len(valstr):
        length = len(valstr)
    pad = " " * (length - len(valstr))
    if isinstance(val, str):
        return f"{valstr}{pad}"
    else:
        return f"{pad}{valstr}"


def bad_date(bad_date_str: str = ""):
    """Print message about bad date & exit."""
    error_out(
        f"Bad date '{ut.untaint(bad_date_str)}'. "
        "Use YYYY-MM-DD or 'today' or 'yesterday'."
    )
