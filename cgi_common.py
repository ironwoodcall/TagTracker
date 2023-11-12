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
import sqlite3
from dataclasses import dataclass, field
import copy
import statistics

from tt_conf import SITE_NAME
from tt_time import VTime
import tt_dbutil as db
import tt_util as ut


WHAT_OVERVIEW = "Ov"
WHAT_BLOCKS = "Blk"
WHAT_OVERVIEW_DOW = "OvD"
WHAT_BLOCKS_DOW = "BlkD"
WHAT_MISMATCH = "MM"
WHAT_ONE_DAY = "1D"
WHAT_DATA_ENTRY = "DE"
WHAT_DATAFILE = "DF"
WHAT_TAGS_LOST = "TL"
WHAT_TAG_HISTORY = "TH"
WHAT_DETAIL = "Dt"
WHAT_SUMMARY = "Sm"

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
SORT_TEMPERATURE = "temperature"
SORT_PRECIPITATAION = "precipitation"

ORDER_FORWARD = "forward"
ORDER_REVERSE = "reverse"

def titleize( title:str="" ) -> str:
    """Puts SITE_NAME in front of title and makes it pretty."""
    name = SITE_NAME if SITE_NAME else "Valet"
    if not title:
        return name
    return f"{SITE_NAME} {title}"

def back_button(pages_back:int) -> str:
    """Make the 'back' button."""
    return (f"<button onclick='goBack({pages_back})'>Back</button>")


def selfref(
    what: str = "",
    qdate: str = "",
    qtime: str = "",
    qtag: str = "",
    qdow: str = "",
    qsort:str = "",
    qdir:str = "",
    pages_back = None
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
    if qdir:
        parms.append(f"dir={qdir}")
    if pages_back is not None:
        parms.append(f"back={pages_back}")
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


@dataclass
class SingleBlock:
    """Data about a single timeblock."""

    num_in: int = 0
    num_out: int = 0
    # activity: int = 0
    full: int = 0
    so_far: int = 0

    @property
    def activity(self) -> int:
        return self.num_in + self.num_out


@dataclass
class BlocksSummary:
    """Summary of all blocks for a single day (or all days)."""

    total_num_in: int = 0
    max_num_in: int = 0
    total_num_out: int = 0
    max_num_out: int = 0
    total_activity: int = 0
    max_activity: int = 0
    ## max_full: int = 0 # Don't need this, it's max full in the days summary


_allblocks = {t: SingleBlock() for t in range(6 * 60, 24 * 60, 30)}


@dataclass
class SingleDay:
    """Data about a single day."""

    date: str = ""
    dow: int = None
    valet_open: VTime = ""
    valet_close: VTime = ""
    total_bikes: int = 0
    regular_bikes: int = 0
    oversize_bikes: int = 0
    max_bikes: int = 0
    max_bikes_time: VTime = ""
    registrations: int = 0
    temperature: float = None
    precip: float = 0
    dusk: VTime = ""
    leftovers: int = 0  # as reported
    leftovers_calculated: int = 0
    blocks: dict = field(default_factory=lambda: copy.deepcopy(_allblocks))

    @property
    def leftovers_reported(self) -> int:
        return self.leftovers


@dataclass
class DaysSummary:
    """Summary data for all days."""

    total_total_bikes: int = 0
    total_regular_bikes: int = 0
    total_oversize_bikes: int = 0
    max_total_bikes: int = 0
    max_total_bikes_date: str = ""
    max_max_bikes: int = 0
    max_max_bikes_date: str = ""
    total_registrations: int = 0
    max_registrations: int = 0
    min_temperature: float = None
    max_temperature: float = None
    total_precip: float = 0
    max_precip: float = 0
    total_leftovers: int = 0
    max_leftovers: int = 0
    total_valet_hours: float = 0
    total_valet_days: int = 0
    total_visit_hours: float = 0
    visits_mean: str = ""
    visits_median: str = ""


def get_days_data(
    ttdb: sqlite3.Connection, min_date: str = "", max_date: str = ""
) -> list[SingleDay]:
    """Create the list of SingleDay data, some info loaded but not the block data.

    If min_date &/or max_date are present, will restrict dates to those

    Does not load:
        blocks
    """

    where = ""
    if min_date:
        where += f" DAY.date >= '{min_date}'"
    if max_date:
        where += f"{' AND' if where else ''} DAY.date <= '{max_date}'"
    where = f"WHERE{where}" if where else ""

    dbrows = db.db_fetch(
        ttdb,
        f"""
        SELECT
            DAY.date,
            DAY.weekday dow,
            DAY.time_open AS valet_open,
            DAY.time_closed AS valet_close,
            DAY.parked_regular AS regular_bikes,
            DAY.parked_oversize AS oversize_bikes,
            DAY.parked_total AS total_bikes,
            DAY.max_total AS max_bikes,
            DAY.time_max_total AS max_bikes_time,
            DAY.registrations,
            DAY.precip_mm AS precip,
            DAY.temp AS temperature,
            DAY.sunset AS dusk,
            DAY.leftover AS leftovers,
            COUNT(VISIT.date) AS leftovers_calculated
        FROM DAY
        LEFT JOIN VISIT ON DAY.date = VISIT.date AND VISIT.TIME_OUT = ""
        {where}
        GROUP BY DAY.date, DAY.time_open, DAY.time_closed, DAY.parked_regular, DAY.parked_oversize,
            DAY.parked_total, DAY.max_total, DAY.time_max_total, DAY.registrations, DAY.precip_mm,
            DAY.temp, DAY.sunset, DAY.leftover;
        """,
    )
    # Look for properties in common (these are the ones we will copy over)
    shared_properties = set(
        prop
        for prop in dbrows[0].__dict__.keys()
        if prop[0] != "_" and prop in SingleDay.__annotations__
    )
    days = []
    for r in dbrows:
        # Copy any commmon properties
        d = SingleDay()
        for prop in shared_properties:
            setattr(d, prop, getattr(r, prop))
        # Fix up any that are to be VTimes
        d.valet_open = VTime(d.valet_open)
        d.valet_close = VTime(d.valet_close)
        d.max_bikes_time = VTime(d.max_bikes_time)
        d.dusk = VTime(d.dusk)
        days.append(d)
    return days


def get_common_properties(obj1: object, obj2: object) -> list:
    """Return a list of callable properties common to the two objects (but not _*)."""
    common_properties = set(
        prop
        for prop in obj1.__dict__
        if not prop.startswith("_")
        and getattr(obj2, prop, None) is not None
        and not callable(getattr(obj1, prop))
    )
    return list(common_properties)


def copy_properties(
    source: object, target: object, common_properties: list = None
) -> None:
    """Copy common non-callable properties from source to target (but not _*).

    If common_properties exists, it will use that.  If not, it will figure
    them out.
    """
    if common_properties is None:
        common_properties = get_common_properties(source, target)

    for prop in common_properties:
        setattr(target, prop, getattr(source, prop))


def get_visit_stats(ttdb: sqlite3.Connection) -> tuple[float, VTime, VTime]:
    """Calculate stats for stay length.

    Returns:
        total visit hours: float
        mean: VTime
        median: VTime
    """
    visits = db.db_fetch(ttdb, "select duration from visit")
    durations = [VTime(v.duration).num for v in visits]
    ##durations = sorted([d for d in durations if d])
    num_visits = len(durations)
    total_duration = sum(durations)  # minutes
    if num_visits <= 0:
        return 0, "", ""
    mean = statistics.mean(durations)
    median = statistics.median(durations)

    return (total_duration / 60), VTime(mean).tidy, VTime(median).tidy


def get_season_summary_data(
    ttdb: sqlite3.Connection, season_dailies: list[SingleDay]
) -> DaysSummary:
    """Fetch whole-season data."""

    def set_obj_from_sql(database: sqlite3.Connection, sql_query: str, target: object):
        """Sets target's properties from row 0 of the return from SQL."""
        dbrows: list[db.DBRow] = db.db_fetch(database, sql_query)
        if not dbrows:
            return
        copy_properties(dbrows[0], target)

    summ = DaysSummary()
    set_obj_from_sql(
        ttdb,
        """
        select
            sum(parked_total) total_total_bikes,
            sum(parked_regular) total_regular_bikes,
            sum(parked_oversize) total_oversize_bikes,
            sum(registrations) total_registrations,
            max(registrations) max_registrations,
            min(temp) min_temperature,
            max(temp) max_temperature,
            sum(precip_mm) total_precip,
            max(precip_mm) max_precip,
            sum(leftover) total_leftovers,
            max(leftover) max_leftovers,
            count(date) total_valet_days
        from day;
        """,
        summ,
    )

    set_obj_from_sql(
        ttdb,
        """
            SELECT
                parked_total as max_total_bikes,
                date as max_total_bikes_date
            FROM day
            ORDER BY parked_total DESC, date ASC
            LIMIT 1;
        """,
        summ,
    )

    set_obj_from_sql(
        ttdb,
        """
            SELECT
                max_total as max_max_bikes,
                date as max_max_bikes_date
            FROM day
            ORDER BY max_total DESC, date ASC
            LIMIT 1;
        """,
        summ,
    )

    # Still need to calculate total_valet_hours
    summ.total_valet_hours = (
        sum([d.valet_close.num - d.valet_open.num for d in season_dailies]) / 60
    )

    # Stats about visits
    summ.total_visit_hours, summ.visits_mean, summ.visits_median = get_visit_stats(ttdb)

    return summ


def fetch_daily_visit_data(ttdb: sqlite3.Connection, in_or_out: str) -> list[db.DBRow]:
    sel = f"""
        select
            date,
            round(2*(julianday(time_{in_or_out})-julianday('00:15'))*24,0)/2 block,
            count(time_{in_or_out}) bikes_{in_or_out}
        from visit
        group by date,block;
    """
    return db.db_fetch(ttdb, sel)


def incorporate_blocks_data(ttdb: sqlite3.Connection, days: list[SingleDay]):
    """Fetch visit data to complete the days list.

    Calculates leftovers_calculated and the blocks info for the days.
    """

    # Will need to be able to index into the days table by date
    days_dict = {d.date: d for d in days}
    # Fetch visits data
    visitrows_in = fetch_daily_visit_data(ttdb, in_or_out="in")
    visitrows_out = fetch_daily_visit_data(ttdb, in_or_out="out")

    # Intermediate dictionaries
    ins = {
        visitrow.date: {VTime(visitrow.block * 60): visitrow.bikes_in}
        for visitrow in visitrows_in
        if visitrow.date and visitrow.block and visitrow.bikes_in is not None
    }

    outs = {
        visitrow.date: {VTime(visitrow.block * 60): visitrow.bikes_out}
        for visitrow in visitrows_out
        if visitrow.date and visitrow.block and visitrow.bikes_out is not None
    }

    # Process data for each date
    for thisdate in sorted(days_dict.keys()):
        full_today, so_far_today = 0, 0

        # Iterate through blocks for the current date
        for block_key in sorted(days_dict[thisdate].blocks.keys()):
            thisblock = days_dict[thisdate].blocks[block_key]

            # Update block properties based on input and output data
            thisblock.num_in = ins[thisdate].get(block_key, 0)
            thisblock.num_out = outs.get(thisdate, {}).get(block_key, 0)

            # Update cumulative counters
            so_far_today += thisblock.num_in
            thisblock.so_far = so_far_today

            full_today += thisblock.num_in - thisblock.num_out
            thisblock.full = full_today


def get_blocks_summary(days: list[SingleDay]) -> BlocksSummary:
    """Find overall maximum values across all blocks."""
    summ = BlocksSummary()
    for day in days:
        for block in day.blocks.values():
            block: SingleBlock
            summ.total_num_in += block.num_in
            summ.total_num_out += block.num_out
            block_activity = block.num_in + block.num_out
            summ.max_num_in = max(summ.max_num_in, block.num_in)
            summ.max_num_out = max(summ.max_num_out, block.num_out)
            summ.total_activity += block.num_in + block_activity
            summ.max_activity = max(summ.max_activity, block_activity)

    return summ

