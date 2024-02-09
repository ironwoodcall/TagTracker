#!/usr/bin/env python3
"""Load datafile records into TagTracker database.

This should run on the tagtracker server.

Supersedes "tracker2db.py"

This is a script to update a persistent SQLite database in a configurable
directory with data from all available (by default) or specific TagTracker
data files.  It uses some modules that it shares in common with the TT client.

Before running this, the database will need to be created.
See "create_database.sql".

Copyright (C) 2024 Julias Hocking, Todd Glover

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

import argparse
import calendar
import glob
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
import subprocess
from datetime import datetime

import tt_datafile
import tt_dbutil
import tt_globals
import tt_util as ut

from tt_event import Event
from tt_time import VTime

# Pre-declare this global for linting purposes.
program_args = None

# Values for good & bad status
STATUS_GOOD = "GOOD"
STATUS_BAD = "BAD"

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
COL_DAY_OF_WEEK = "weekday"  # ISO 8601-compliant 1-7 M-S
COL_PRECIP_MM = "precip_mm"  # mm (bulk pop from EnvCan dat)
COL_TEMP = "temp"
COL_SUNSET = "sunset"  # HHMM time at sunset - same
COL_EVENT = "event"  # brief name of nearby event
COL_EVENT_PROX = "event_prox_km"  # est. num of km to event
COL_REGISTRATIONS = "registrations"  # num of 529 registrations recorded
# COL_NOTES name reused
# COL_BATCH name reused

# Bike-type codes. Must match check constraint in code table TYPES.CODE
REGULAR = "R"
OVERSIZE = "O"


@dataclass
class Statuses:
    """Keep track of status of individual files & overall program."""

    start_time: str = ut.iso_timestamp()
    status: str = STATUS_GOOD
    errors: int = 0
    error_list: list = field(default_factory=list)
    files: dict = field(default_factory=dict)

    @classmethod
    def set_bad(cls,error_msg:str = "Unspecified error"):
        cls.status = STATUS_BAD
        cls.errors += 1
        cls.error_list += [error_msg]

@dataclass
class FileInfo:
    name: str
    status: str = STATUS_GOOD
    fingerprint: str = None
    timestamp: str = None
    errors: int = 0
    error_list: list = field(default_factory=list)

    def set_bad(self,error_msg:str = "Unspecified error"):
        self.status = STATUS_BAD
        self.errors += 1
        self.error_list += [error_msg]

def calc_duration(hhmm_in: str, hhmm_out: str) -> str:
    """Calculate a str duration from a str time in and out."""
    t_in = VTime(hhmm_in).num
    t_out = VTime(hhmm_out).num
    t_stay = t_out - t_in
    hhmm_stay = VTime(t_stay)

    return hhmm_stay


def get_file_fingerprint(file_path):
    """Get a file's fingerprint."""
    try:
        result = subprocess.run(
            ["md5sum", file_path], capture_output=True, text=True, check=True
        )
        md5sum_output = result.stdout.strip().split()[0]
        return md5sum_output
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def get_file_timestamp(file_path):
    """Get a file's timestamp as an iso8601 string."""
    try:
        timestamp = os.path.getmtime(file_path)
        modified_time = datetime.fromtimestamp(timestamp)
        return modified_time.strftime("%Y-%m-%dT%H:%M:%S")
    except FileNotFoundError:
        print("File not found {e}.", file=sys.stderr)
        return None


def data_to_db(filename: str, batch, conn) -> None:
    """Record one datafile to the database.

    Read the datafile in question into a TrackerDay object with
    df.read_datafile()

    For the day, UPDATE or INSERT a row of day summary data into TABLE_DAYS

    Then calculate some things which might be based on it
    for each bike, and record a row of visit data into TABLE_VISITS
    """

    def what_bike_type(tag: str) -> str:
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
        if program_args.verbose:
            print(f"Error: couldn't find file: {filename}", file=sys.stderr)
        Statuses.files[filename].set_bad("File not found")
        return

    if program_args.verbose:
        print(f"\nLoading {filename}:")

    data = tt_datafile.read_datafile(f"{filename}", err_msgs=[])
    date = data.date
    if not date:  # get from filename for old data formats (hopefully never)
        print(
            f"Error: unable to read valet date from file {filename}. "
            "Skipping this file",
            file=sys.stderr,
        )
        globals()["SKIP_COUNT"] += 1
        return

    if not data.bikes_in:  # if no visits to record, stop now
        print(f"No visits in {filename}")
        globals()["EMPTY_COUNT"] += 1
        return

    if data.regular and data.oversize:
        regular_tags = data.regular
        oversize_tags = data.oversize
        if program_args.verbose:
            print("Tags: datafile tag lists loaded")
    else:  # if no context
        print(
            f"Error: unable to read tags context from file {filename}. "
            "Skipping this file.",
            file=sys.stderr,
        )
        globals()["SKIP_COUNT"] += 1
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
        globals()["SKIP_COUNT"] += 1
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
        if events[atime].num_here_regular >= max_regular_num and not max_regular_time:
            max_regular_time = atime
        if (
            events[atime].num_here_oversize >= max_oversize_num
            and not max_oversize_time
        ):
            max_oversize_time = atime
        if events[atime].num_here_total >= max_total_num and not max_total_time:
            max_total_time = atime

    # Open and close times
    if data.opening_time and data.closing_time:
        time_open = data.opening_time
        time_close = data.closing_time
    else:  # guess with bike check-ins
        time_open = data.earliest_event()
        time_close = data.latest_event()
    if not time_close:
        print(
            f"Error - datafile {filename} missing closing time. " "Skipping datafile.",
            file=sys.stderr,
        )
        globals()["SKIP_COUNT"] += 1
        return

    # Find int day of week
    date_bits = re.match(tt_globals.DATE_FULL_RE, date)
    year = int(date_bits.group(1))
    month = int(date_bits.group(2))
    day = int(date_bits.group(3))
    weekday = 1 + calendar.weekday(year, month, day)  # ISO 8601 says 1-7 M-S

    if not sql_exec(  # First try to make a new row...
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
                );""",
        conn,
        quiet=True,
    ) and not sql_exec(  # Then try to update...
        f"""UPDATE {TABLE_DAYS} SET
                    {COL_REGULAR} = {regular_parked},
                    {COL_OVERSIZE} = {oversize_parked},
                    {COL_TOTAL} = {total_parked},
                    {COL_TOTAL_LEFTOVER} = {total_leftover},
                    {COL_MAX_REGULAR} = {max_regular_num},
                    {COL_MAX_REGULAR_TIME} = '{max_regular_time}',
                    {COL_MAX_OVERSIZE} = {max_oversize_num},
                    {COL_MAX_OVERSIZE_TIME} = '{max_oversize_time}',
                    {COL_MAX_TOTAL} = {max_total_num},
                    {COL_MAX_TOTAL_TIME} = '{max_total_time}',
                    {COL_TIME_OPEN} = '{time_open}',
                    {COL_TIME_CLOSE} = '{time_close}',
                    {COL_DAY_OF_WEEK} = {weekday},
                    {COL_BATCH} = '{batch}'
                    WHERE {COL_DATE} = '{date}'
                    ;""",
        conn,
    ):
        print(
            "Error: failed to INSERT or UPDATE " f"day summary for {filename}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # TABLE_VISITS handling

    visit_commit_count = total_parked
    visit_fail_count = 0
    sql_exec(f"DELETE FROM {TABLE_VISITS} WHERE date = '{date}';", conn)

    for tag, time_in in data.bikes_in.items():
        time_in = VTime(time_in)
        if time_in > time_close:  # both should be VTime
            print(
                f"Error: visit {tag} in {filename} has check-in ({time_in})"
                f" after closing time ({time_close}). Visit not recorded.",
                file=sys.stderr,
            )
            continue

        if tag in data.bikes_out.keys():
            time_out = VTime(data.bikes_out[tag])
            dur_end = time_out
        else:  # no check-out recorded
            dur_end = time_close
            if program_args.verbose:
                print(
                    f"(normal leftover): {tag} stay time found using "
                    f"closing time {time_close} from table '{TABLE_DAYS}'"
                )
            time_out = ""  # empty str for no time
        time_stay = calc_duration(time_in, dur_end)
        biketype = what_bike_type(tag)
        if not sql_exec(
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
                    '{biketype}',
                    '{time_in}',
                    '{time_out}',
                    '{time_stay}',
                    '{batch}');""",
            conn,
        ):
            print(
                f"Error: failed to INSERT a stay for {tag}",
                file=sys.stderr,
            )
            visit_commit_count -= 1
            visit_fail_count += 1
    globals()["SUCCESS_COUNT"] += 1

    try:
        conn.commit()  # commit one datafile transaction
        if not program_args.quiet:
            print(
                f" --> Committed records for {visit_commit_count} "
                f"visits on {date} ({visit_fail_count} failed)"
            )
    except sqlite3.Error as sqlite_err:
        print(
            f"SQLite COMMIT error {sqlite_err} for {filename}",
            file=sys.stderr,
        )
        Statuses.files[filename].set_bad(f"SQLite COMMIT error {sqlite_err} for {filename}")
        return

# FIXME: make sql_exec return its error message; caller always decides from that
def sql_exec(sql_statement: str, conn, quiet: bool = False) -> bool:
    """Execute a SQL statement, ignoring any output.

    Not suitable (of course) for SELECT statements.
    Returns True on success or False on failure."""
    try:
        curs = conn.cursor()
        curs.execute(sql_statement)
        return True
    except sqlite3.Error as sqlite_err:
        if not quiet:
            print(f"SQLite error:{sqlite_err}", file=sys.stderr)
        return False


def setup_parser(parser) -> None:
    """Add arguments to the ArgumentParser."""
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppresses all non-error output",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="provides most detailed output",
    )
    parser.add_argument(
        "-l", "--log", action="store_true", help="output in logging format"
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

    # Custom logic to handle setting quiet and verbose based on log option
    def process_args(program_args):
        if program_args.log:
            program_args.quiet = True
            program_args.verbose = False
        return program_args

    parser.set_defaults(func=process_args)


def find_datafiles(arguments: argparse.Namespace) -> list:
    """Set a list of files from the supplied dataglob.

    Needs at least 1 of:
    - specific file to target
    - glob to search with in specified directory

    If provided both, returns the set union of all datafiles found.
    """
    maybe_datafiles = []
    for this_glob in arguments.dataglob:
        # print(f"{this_glob=}")

        globbed_files = glob.glob(this_glob)  # glob glob glob
        # print(f"{globbed_files=}")
        if len(globbed_files) < 1:  # if still empty after globbing
            print(
                f"Error: no files found matching glob '{this_glob}'",
                file=sys.stderr,
            )
            sys.exit(1)
        maybe_datafiles = sorted(list(set().union(maybe_datafiles, globbed_files)))

    for f in maybe_datafiles:
        f_info = FileInfo(f)
        Statuses.files[f] = f_info
        if not os.path.exists(f):
            f_info.set_bad("File not found")
            continue
        f_info.fingerprint = get_file_fingerprint(f)
        if not f_info.fingerprint:
            f_info.set_bad("Can not read file md5sum")
            continue
        f_info.timestamp = get_file_timestamp(f)
        if not f_info.timestamp:
            f_info.set_bad("Can not read file timestamp")
            continue

    ok_datafiles = [f for f in Statuses.files.keys() if Statuses.files[f].status == STATUS_GOOD]

    return ok_datafiles

def summary_exit():
    """Status info printout and exit."""
    # print("File,MD5Sum,Status,File_Timestamp,Load_Timestamp")
    total_file_errors = 0
    for name,info in Statuses.files.items():
        info: FileInfo
        info.errors = info.errors if info.errors else len(info.error_list)
        total_file_errors += info.errors
        if not program_args.quiet:
            print(
                f"{name}, {info.fingerprint}, {info.status}, {info.timestamp}, {Statuses.start_time}"
            )
    if not program_args.quiet:
        print(f"Total files: {len(Statuses.files)}")
        print(f"Total file errors: {total_file_errors}")
        print(f"Total program errors: {Statuses.errors}")
    if Statuses.errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":

    Statuses.files = {}

    parser = argparse.ArgumentParser()
    setup_parser(parser)
    program_args = parser.parse_args()

    DB_FILEPATH = program_args.dbfile
    datafiles = find_datafiles(program_args)

    summary_exit()  # FIXME

    if program_args.verbose:
        print(f"Connecting to database {DB_FILEPATH}...")
    conn = tt_dbutil.db_connect(DB_FILEPATH)
    if not conn:
        sys.exit(1)  # Error messages already taken care of in fn

    if sql_exec("PRAGMA foreign_keys=ON;", conn):
        if program_args.verbose:
            print("Enabled foreign key constraints.")
    else:
        print(
            "Error: couldn't enable SQLite use of foreign keys",
            file=sys.stderr,
        )
        sys.exit(1)

    batch = Statuses.start_time
    if program_args.verbose:
        print(f"BatchID: {batch}")

    for datafilename in datafiles:
        data_to_db(datafilename, batch, conn)

    conn.close()

    SUCCESS_COUNT = len([x for x in Statuses.files if x.status == STATUS_GOOD])
    FAIL_COUNT = len(Statuses.files) - SUCCESS_COUNT
    summary_exit()

    if not program_args.quiet:
        print(
            f"\n\nLoaded {SUCCESS_COUNT} datafiles; {FAIL_COUNT} did not load."
        )
