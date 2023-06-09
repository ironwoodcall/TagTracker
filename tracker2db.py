#!/usr/bin/env python3
"""TagTracker by Julias Hocking.

Database updater for TagTracker suite.

This is a script to update a persistent SQLite database in a configurable
directory with data from all available (by default) or specific TagTracker
data files.
It pulls some functions and constants from tagtracker_config.py
and tracker_util.py.

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


import argparse
import calendar
import glob
import os
import re
import sqlite3
import sys
from typing import Union  # for type hints instead of (eg) int|str

import tt_util as ut
import tt_datafile as df
import tt_globals as tg

from tt_event import Event
from tt_time import VTime


# Names for tables and columns.s
# Table of individual bike visits
TABLE_VISITS = "visit"
COL_ID = "id"  # text date.tag PK
COL_DATE = "date"
COL_TAG = "tag"
COL_BIKETYPE = "type"
COL_TIME_IN = "time_in"
COL_TIME_OUT = "time_out"
COL_DURATION = "duration"
COL_NOTES = "notes"
COL_BATCH = "batch"

# Table of day summaries
TABLE_DAYS = "day"
# COL_DATE name reused - text date PK
COL_REGULAR = "parked_regular"  # int count
COL_OVERSIZE = "parked_oversize"  # int count
COL_TOTAL = "parked_total"  # int sum of 2 above
COL_TOTAL_LEFTOVER = "leftover"  # int count
COL_MAX_REGULAR = "max_reg"  # int count of max regular bikes
COL_MAX_REGULAR_TIME = "time_max_reg"  # HHMM time
COL_MAX_OVERSIZE = "max_over"  # int count of max oversize bikes
COL_MAX_OVERSIZE_TIME = "time_max_over"  # HHMM time
COL_MAX_TOTAL = "max_total"  # int sum of 2 above
COL_MAX_TOTAL_TIME = "time_max_total"  # HHMM
COL_TIME_OPEN = "time_open"  # HHMM opening time
COL_TIME_CLOSE = "time_closed"  # HHMM closing time
COL_DAY_OF_WEEK = "weekday"  # 0-6 day of the week
COL_PRECIP_MM = "precip_mm"  # mm (bulk pop from EnvCan dat)
COL_TEMP_10AM = "temp_10am"  # temp at 10AM - same
COL_SUNSET = "sunset"  # HHMM time at sunset - same
COL_EVENT = "event"  # brief name of nearby event
COL_EVENT_PROX = "event_prox_km"  # est. num of km to event
COL_REGISTRATIONS = "registrations"  # num of 529 registrations recorded
# COL_NOTES name reused
# COL_BATCH name reused

# Values for some text fields
REGULAR = "regular"
OVERSIZE = "oversize"


def create_connection(db_file) -> sqlite3.Connection:
    """Create a database connection to a SQLite database.

    This will create a new .db database file if none yet exists at the named
    path."""
    connection = None
    try:
        connection = sqlite3.connect(db_file)
        if args.verbose:
            print(f"SQLite version {sqlite3.version}")
    except sqlite3.Error as sqlite_err:
        print("Error (SQLite) trying to create_connection():", sqlite_err)
        sys.exit(1)
    return connection


def calc_duration(hhmm_in: str, hhmm_out: str) -> str:
    """Calculate a str duration from a str time in and out."""
    t_in = ut.time_int(hhmm_in)
    t_out = ut.time_int(hhmm_out)
    t_stay = t_out - t_in
    hhmm_stay = ut.time_str(t_stay)

    return hhmm_stay


def data_to_db(filename: str) -> None:
    """Record one datafile to the database.

    Read the datafile in question into a TrackerDay object with
    df.read_datafile()

    For the day, insert a row of day summary data into TABLE_DAYS

    Then calculate some things which might be based on it
    For each bike, record a row of visit data into TABLE_VISITS
    """

    def what_bike_type(tag: str) -> Union[str, None]:
        """Return the type 'Normal' or 'Oversize' of a tag.
        Based on each day's datafile"""
        if tag in regular_tags:
            return REGULAR
        elif tag in oversize_tags:
            return OVERSIZE
        else:
            print(
                f"Error: couldn't parse bike type for {tag} in {filename}. "
                "Exiting with error.",
                file=sys.stderr,
            )
            sys.exit(1)

    if not os.path.isfile(filename):
        print(f"Error: couldn't find file: {filename}", file=sys.stderr)
        return

    if args.verbose:
        print(f"\nWorking on {filename}")

    data = df.read_datafile(f"{filename}", err_msgs=[])

    date = data.date
    if not date:  # get from filename for old data formats (hopefully never)
        print(
            f"Error: unable to read valet date from file {filename}. "
            "Skipping this file",
            file=sys.stderr,
        )
        return

    if not data.bikes_in:  # if no visits to record, stop now
        print(f"No visits in {filename}")
        globals()["EMPTY_COUNT"] += 1
        return
    globals()["SUCCESS_COUNT"] += 1

    if data.regular and data.oversize:
        regular_tags = data.regular
        oversize_tags = data.oversize
        if args.verbose:
            print("Tags: datafile tag lists loaded")
    else:  # if no context
        print(
            f"Error: unable to read tags context from file {filename}. "
            "Skipping this file.",
            file=sys.stderr,
        )
        return

    # TABLE_DAYS handling
    # Simple counts
    regular_parked = 0
    oversize_parked = 0
    for tag in data.bikes_in.keys():
        bike_type = what_bike_type(tag)
        if bike_type == REGULAR:
            regular_parked += 1
        elif bike_type == OVERSIZE:
            oversize_parked += 1
    total_parked = regular_parked + oversize_parked
    total_leftover = len(data.bikes_in) - len(data.bikes_out)
    if total_leftover < 0:
        print(
            f"Error: calculated negative value ({total_leftover})"
            f" of leftover bikes for {date}. Skipping {filename}.",
            file=sys.stderr,
        )
        return

    # Highwater values
    events = Event.calc_events(data)
    max_regular_num = max([x.num_here_regular for x in events.values()])
    max_oversize_num = max([x.num_here_oversize for x in events.values()])
    max_total_num = max([x.num_here_total for x in events.values()])
    max_regular_time = None
    max_oversize_time = None
    max_total_time = None
    # Find the first time at which these took place
    for atime in sorted(events.keys()):
        if (
            events[atime].num_here_regular >= max_regular_num
            and not max_regular_time
        ):
            max_regular_time = atime
        if (
            events[atime].num_here_oversize >= max_oversize_num
            and not max_oversize_time
        ):
            max_oversize_time = atime
        if (
            events[atime].num_here_total >= max_total_num
            and not max_total_time
        ):
            max_total_time = atime

    # Open and close times
    if data.opening_time and data.closing_time:
        time_open = data.opening_time
        time_close = data.closing_time
    else:  # guess with bike check-ins
        time_open = data.earliest_event()
        time_close = data.latest_event()

    # Find int day of week
    date_bits = re.match(tg.DATE_FULL_RE, date)
    year = int(date_bits.group(1))
    month = int(date_bits.group(2))
    day = int(date_bits.group(3))
    weekday = 1 + calendar.weekday(year, month, day)
    if weekday == 7:  # awkward but should work
        weekday = 0

    if not sql_do(f"DELETE FROM {TABLE_DAYS} WHERE date = '{date}';"):
        print(
            f"Error: delete day summary failed for date '{date}'. "
            "Exiting with error.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not sql_do(
        f"""INSERT INTO {TABLE_DAYS} (
                {COL_DATE},
                {COL_REGULAR},
                {COL_OVERSIZE},
                {COL_TOTAL},
                {COL_TOTAL_LEFTOVER},
                {COL_MAX_REGULAR},
                {COL_MAX_REGULAR_TIME},
                {COL_MAX_OVERSIZE},
                {COL_MAX_OVERSIZE_TIME},
                {COL_MAX_TOTAL},
                {COL_MAX_TOTAL_TIME},
                {COL_TIME_OPEN},
                {COL_TIME_CLOSE},
                {COL_DAY_OF_WEEK},
                {COL_BATCH}
                ) VALUES (
                '{date}',
                {regular_parked},
                {oversize_parked},
                {total_parked},
                {total_leftover},
                {max_regular_num},
                '{max_regular_time}',
                {max_oversize_num},
                '{max_oversize_time}',
                {max_total_num},
                '{max_total_time}',
                '{time_open}',
                '{time_close}',
                {weekday},
                '{batch}'
                );"""
    ):
        print(
            f"Error: failed to insert day summary for {filename}. "
            "Exiting with error.",
            file=sys.stderr,
        )
        sys.exit(1)

    # TABLE_VISITS handling
    closing = select_closing_time(date)  # fetch checkout time for whole day
    sql_do(f"DELETE FROM {TABLE_VISITS} WHERE date = '{date}';")

    visit_commit_count = total_parked
    visit_fail_count = 0

    for tag, time_in in data.bikes_in.items():
        if tag in data.bikes_out.keys():
            time_out = data.bikes_out[tag]
            dur_end = time_out
            dur_end = time_out
        else:  # no check-out recorded
            if closing:
                dur_end = closing
                if args.verbose:
                    print(
                        f"(normal leftover): {tag} stay time found using "
                        f"closing time {closing} from table '{TABLE_DAYS}'"
                    )
            else:
                dur_end = data.latest_event()  # approx. as = to last event
                print(
                    f"WARN - datafile {filename} missing closing time: "
                    f"using latest event time for leftover with tag {tag}"
                )
            time_out = ""  # empty str for no time
        time_stay = calc_duration(time_in, dur_end)
        if not sql_do(
            f"""INSERT INTO {TABLE_VISITS} (
                    {COL_ID},
                    {COL_DATE},
                    {COL_TAG},
                    {COL_BIKETYPE},
                    {COL_TIME_IN},
                    {COL_TIME_OUT},
                    {COL_DURATION},
                    {COL_BATCH}
                    ) VALUES (
                    '{date}.{tag}',
                    '{date}',
                    '{tag}',
                    '{what_bike_type(tag)}',
                    '{time_in}',
                    '{time_out}',
                    '{time_stay}',
                    '{batch}');"""
        ):
            print(f"Error: failed to insert a stay for {tag}", file=sys.stderr)
            visit_commit_count -= 1
            visit_fail_count += 1
    try:
        conn.commit()  # commit one datafile transaction
        if not args.quiet:
            print(
                f" --> Committed records for {visit_commit_count} "
                f"visits on {date} ({visit_fail_count} failed)"
            )
    except sqlite3.Error as sqlite_err:
        print(f"Error (SQLite) committing for {filename}:", sqlite_err)


def select_closing_time(date: str) -> Union[VTime, bool]:
    """Return the closing time of a given date in TABLE_DAYS.

    - SELECT closing time from rows with matching dates (should be just 1)
    - If this yields no rows, return False.
    - If this yields 1 row, return the closing time as a str HHMM.
    - If this yields >1 row, raise error that the day has multiple records
    (shouldn't happen b/c of UNIQUE constraint on the date row, but in case)
    """
    curs = conn.cursor()
    rows = curs.execute(
        f"SELECT {COL_TIME_CLOSE} FROM {TABLE_DAYS} "
        f"WHERE {COL_DATE} == '{date}'"
    ).fetchall()
    num_rows = len(rows)
    if num_rows == 0:
        return False  # will now use last event instead
    elif num_rows == 1:
        return VTime(rows[0][0])  # needs double subscript apparently
    else:
        print(
            f"Error (database): finding closing time on date {date} in table "
            f"'{TABLE_DAYS}' returned multiple rows from query"
        )
        sys.exit(1)


def sql_do(sql_statement: str) -> bool:
    """Execute a SQL statement, or print the slite3 error."""
    try:
        curs = conn.cursor()
        curs.execute(sql_statement)
        return True
    except sqlite3.Error as sqlite_err:
        print("Error (SQLite) using sql_do():", sqlite_err)
        return False


def setup_parser() -> None:
    """Add arguments to the ArgumentParser."""
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_const",
        const=True,
        help="suppresses all non-error output",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_const",
        const=True,
        help="provides most detailed output",
    )
    parser.add_argument(
        "dataglob",
        type=str,
        nargs="+",
        help="glob(s) to select target datafiles",
    )
    parser.add_argument(
        "dbfile", type=str, help="path of destination SQLite3 database file"
    )


def find_datafiles(arguments: argparse.Namespace) -> list:
    """Use provided args to assemble a list of datafiles.

    Needs at least 1 of:
    - specific file to target
    - glob to search with in specified directory

    If provided both, returns the set union of all datafiles found.
    """
    targeted_datafiles = []
    for this_glob in arguments.dataglob:
        globbed_files = glob.glob(this_glob)  # glob glob glob
        if len(globbed_files) < 1:  # if still empty after globbing
            print(
                f"Error: no files found matching glob '{this_glob}'",
                file=sys.stderr,
            )
            sys.exit(1)
        targeted_datafiles = sorted(
            list(set().union(targeted_datafiles, globbed_files))
        )
    return targeted_datafiles


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    setup_parser()
    args = parser.parse_args()

    DB_FILEPATH = args.dbfile
    datafiles = find_datafiles(args)

    if args.verbose:
        print(f"Connecting to database at {DB_FILEPATH}...")
    conn = create_connection(DB_FILEPATH)

    if sql_do("PRAGMA foreign_keys=ON;"):
        if args.verbose:
            print("Successfully enabled SQLite foreign keys")
    else:
        print(
            "Error: couldn't enable SQLite use of foreign keys",
            file=sys.stderr,
        )
        sys.exit(1)

    date_today = ut.get_date()
    batch = f"{date_today}T{ut.get_time()}"
    if not args.quiet:
        print(f"Batch: {batch}")

    SUCCESS_COUNT = 0
    EMPTY_COUNT = 0

    for datafilename in datafiles:
        data_to_db(datafilename)

    conn.close()

    if not args.quiet:
        print(
            f"\n\nProcessed data from {SUCCESS_COUNT} datafiles "
            f"({EMPTY_COUNT} empty)."
        )
