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
import glob
import os
import sqlite3
import sys
import csv
from dataclasses import dataclass, field
import subprocess
from datetime import datetime
import hashlib

import tt_datafile
import tt_dbutil

# import tt_globals
import tt_util as ut
from tt_trackerday import TrackerDay

from tt_event import Event
from tt_time import VTime

# Pre-declare this global for linting purposes.
args = None

# Values for good & bad status
STATUS_GOOD = "GOOD"
STATUS_BAD = "BAD"
STATUS_SKIP = "SKIP"  # File done GOOD previously

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
class DayStats:
    # Summary stats & such for one day.
    # This makes up most of a record for a DAY row,
    date: str
    regular_parked: int = 0
    oversize_parked: int = 0
    total_parked: int = 0
    total_leftover: int = 0
    max_regular_num: int = 0
    max_regular_time: VTime = ""
    max_oversize_num: int = 0
    max_oversize_time: VTime = ""
    max_total_num: int = 0
    max_total_time: VTime = ""
    time_open: VTime = ""
    time_close: VTime = ""
    weekday: int = None
    registrations: int = 0


@dataclass
class Statuses:
    """Keep track of status of individual files & overall program."""

    start_time: str = ut.iso_timestamp()
    status: str = STATUS_GOOD
    errors: int = 0
    error_list: list = field(default_factory=list)
    files: dict = field(default_factory=dict)

    @classmethod
    def set_bad(cls, error_msg: str = "Unspecified error", silent: bool = False):
        cls.status = STATUS_BAD
        cls.errors += 1
        cls.error_list += [error_msg]
        if not silent:
            print(error_msg, file=sys.stderr)


@dataclass
class FileInfo:
    name: str
    status: str = STATUS_GOOD
    fingerprint: str = None
    timestamp: str = None
    errors: int = 0
    error_list: list = field(default_factory=list)

    def set_bad(self, error_msg: str = "Unspecified error", silent: bool = False):
        self.status = STATUS_BAD
        self.errors += 1
        self.error_list += [error_msg]
        if not silent:
            print(f"{error_msg} [{self.name}]", file=sys.stderr)


def calc_stay_length(hhmm_in: str, hhmm_out: str) -> str:
    """Calculate a str duration from a str time in and out."""
    t_in = VTime(hhmm_in).num
    t_out = VTime(hhmm_out).num
    t_stay = t_out - t_in
    hhmm_stay = VTime(t_stay)

    return hhmm_stay


def is_linux() -> bool:
    """Check if running in linux."""
    system_platform = sys.platform
    return system_platform.startswith("linux")


def get_file_fingerprint(file_path):
    """Get a file's fingerprint."""

    def get_file_md5_linux(file_path):
        """Get an md5 digest by calling the system program."""
        try:
            result = subprocess.run(
                ["md5sum", file_path], capture_output=True, text=True, check=True
            )
            md5sum_output = result.stdout.strip().split()[0]
            return md5sum_output
        except subprocess.CalledProcessError as e:
            print(f"Error: {e}", file=sys.stderr)
            return None

    def get_file_md5_windows(file_path):
        """Calculate the MD5 checksum for a given file by reading the file.

        This one would be OS independent.
        """
        # Open the file in binary mode
        with open(file_path, "rb") as file:
            # Create an MD5 hash object
            md5_hash = hashlib.md5()
            # Read the file in chunks to avoid loading the entire file into memory
            for chunk in iter(lambda: file.read(4096), b""):
                # Update the hash object with the chunk
                md5_hash.update(chunk)
        # Get the hexadecimal digest of the hash
        md5_checksum = md5_hash.hexdigest()
        return md5_checksum

    # On linux, prefer calling the system md5sum program
    if is_linux():
        return get_file_md5_linux(file_path)
    else:
        return get_file_md5_windows(file_path)


def get_good_mp5s_list(logfile: str) -> list[str]:
    """Get a list of the MD5 of successful loads."""
    if not os.path.exists(logfile):
        raise FileNotFoundError(f"The logfile '{logfile}' does not exist.")
    if not os.access(logfile, os.W_OK):
        raise PermissionError(f"The logfile '{logfile}' is not writable.")

    good_values = []
    with open(logfile, "r", newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if len(row) >= 3 and row[2] == "GOOD":
                good_values.append(row[1])
    return good_values


def get_file_timestamp(file_path):
    """Get a file's timestamp as an iso8601 string."""
    try:
        timestamp = os.path.getmtime(file_path)
        modified_time = datetime.fromtimestamp(timestamp)
        return modified_time.strftime("%Y-%m-%dT%H:%M:%S")
    except FileNotFoundError:
        print("File not found {e}.", file=sys.stderr)
        return None


def get_bike_type(tag: str, day: TrackerDay) -> str:
    if tag in day.regular:
        return REGULAR
    elif tag in day.oversize:
        return OVERSIZE
    else:
        return ""


def calc_day_stats(filename: str, day: TrackerDay) -> DayStats:
    """Figure out the stats for a DAY row."""

    row = DayStats(day.date)
    row.registrations = day.registrations
    row.regular_parked = 0
    row.oversize_parked = 0
    for tag in day.bikes_in.keys():
        bike_type = get_bike_type(tag, day)
        if bike_type == REGULAR:
            row.regular_parked += 1
        elif bike_type == OVERSIZE:
            row.oversize_parked += 1
        else:
            msg = f"Can not tell tag type for tag {tag}"
            Statuses.files[filename].set_bad(msg)
    row.total_parked = row.regular_parked + row.oversize_parked
    row.total_leftover = len(day.bikes_in) - len(day.bikes_out)
    if row.total_leftover < 0:
        msg = "Total leftovers is negative"
        Statuses.files[filename].set_bad(msg)
        return None

    # Highwater values
    events = Event.calc_events(day)
    row.max_regular_num = max([x.num_here_regular for x in events.values()])
    row.max_oversize_num = max([x.num_here_oversize for x in events.values()])
    row.max_total_num = max([x.num_here_total for x in events.values()])
    row.max_regular_time = None
    row.max_oversize_time = None
    row.max_total_time = None
    # Find the first time at which these took place
    for atime in sorted(events.keys()):
        if (
            events[atime].num_here_regular >= row.max_regular_num
            and not row.max_regular_time
        ):
            row.max_regular_time = atime
        if (
            events[atime].num_here_oversize >= row.max_oversize_num
            and not row.max_oversize_time
        ):
            row.max_oversize_time = atime
        if events[atime].num_here_total >= row.max_total_num and not row.max_total_time:
            row.max_total_time = atime

    # Open and close times
    if day.opening_time and day.closing_time:
        row.time_open = day.opening_time
        row.time_close = day.closing_time
    else:  # guess with bike check-ins
        row.time_open = day.earliest_event()
        row.time_close = day.latest_event()
    if not row.time_close:
        msg = "Can not find or guess a closing time"
        Statuses.files[filename].set_bad(msg)
        return None

    # Find int day of week
    row.weekday = ut.dow_int(row.date)

    return row


def fetch_reg_from_db(conn: sqlite3.Connection, date: str) -> int:
    """Get any existing registration info from the DB; return int or None."""
    rows = tt_dbutil.db_fetch(
        conn,
        f"SELECT {COL_REGISTRATIONS} FROM {TABLE_DAYS} WHERE DATE = '{date}'",["registrations"]
    )
    if not rows:
        return None
    return rows[0].registrations

def day_into_db(
    filename: str, day_row: DayStats, batch: str, conn: sqlite3.Connection
) -> bool:

    # Figure out what value to use for registrations.
    # This is yucky for legacy support reasons: before approx 2024-02
    # the count of registrations came from a separate day-end from, not
    # the datafile.  So this selects the existing value or the datafile
    # value, whichever is greater.
    reg = fetch_reg_from_db(conn,day_row.date)
    if reg is None:
        reg = day_row.registrations
    reg = "NULL" if reg is None else reg

    # Insert/replace this day's summary info
    sql_error = sql_exec_and_error(
        f"""INSERT OR REPLACE INTO {TABLE_DAYS} (
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
                {COL_REGISTRATIONS},
                {COL_BATCH}
            ) VALUES (
                '{day_row.date}',
                {day_row.regular_parked},
                {day_row.oversize_parked},
                {day_row.total_parked},
                {day_row.total_leftover},
                {day_row.max_regular_num},
                '{day_row.max_regular_time}',
                {day_row.max_oversize_num},
                '{day_row.max_oversize_time}',
                {day_row.max_total_num},
                '{day_row.max_total_time}',
                '{day_row.time_open}',
                '{day_row.time_close}',
                {day_row.weekday},
                {reg},
                '{batch}'
            );""",
        conn,
        quiet=True,
    )
    # Did it work? (No error message means success.)
    if sql_error:
        Statuses.files[filename].set_bad(f"SQL error adding to DAY: {sql_error}")
        return False

    return True


def datafile_into_db(filename: str, batch, conn) -> None:
    """Record one datafile to the database.

    Read the datafile in question into a TrackerDay object with
    df.read_datafile()

    For the day, UPDATE or INSERT a row of day summary data into TABLE_DAYS

    Then calculate some things which might be based on it
    for each bike, and record a row of visit data into TABLE_VISITS
    """

    if not os.path.isfile(filename):
        Statuses.files[filename].set_bad("File not found")
        return

    if args.verbose:
        print(f"Reading {filename}:")

    data = tt_datafile.read_datafile(f"{filename}", err_msgs=[])
    date = data.date
    if not date:
        msg = "Unable to read date from file. Skipping file."
        Statuses.files[filename].set_bad(msg)
        return

    # if not data.bikes_in:  # if no visits to record, stop now
    #     print(f"No visits in {filename}")
    #     globals()["EMPTY_COUNT"] += 1
    #     return

    # # Check there's enough info to determine bike type
    # if data.regular and data.oversize:
    #     regular_tags = data.regular
    #     oversize_tags = data.oversize
    #     if args.verbose:
    #         print("Tags: datafile tag lists loaded")
    # else:  # if no bike-type context
    #     msg = "Can not read lists of regular & oversize tags"
    #     Statuses.files[filename].set_bad(msg)
    #     return

    day_row = calc_day_stats(filename, data)
    if not day_into_db(filename, day_row, batch, conn):
        return

    # Visits into the VISIT table

    sql_error = sql_exec_and_error(
        f"DELETE FROM {TABLE_VISITS} WHERE date = '{date}';", conn
    )
    if sql_error:
        Statuses.files[filename].set_bad(f"Error deleting VISIT rows: {sql_error}")
        return

    for tag, time_in in data.bikes_in.items():
        time_in = VTime(time_in)
        # if time_in > day_row.time_close:  # both should be VTime
        #     print(
        #         f"Error: visit {tag} in {filename} has check-in ({time_in})"
        #         f" after closing time ({day_row.time_close}). Visit not recorded.",
        #         file=sys.stderr,
        #     )
        #     continue

        # Insert VISIT rows one at a time
        if tag in data.bikes_out:
            time_out = VTime(data.bikes_out[tag])
            dur_end = time_out
        else:  # no check-out recorded
            dur_end = day_row.time_close
            time_out = ""  # empty str for no time
        time_stay = calc_stay_length(time_in, dur_end)
        biketype = get_bike_type(tag, data)
        sql_error = sql_exec_and_error(
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
        )
        if sql_error:
            Statuses.files[filename].set_bad(
                f"Error inserting VISIT tag {tag}: {sql_error}"
            )
            return

    try:
        conn.commit()  # commit one datafile transaction
    except sqlite3.Error as sqlite_err:
        Statuses.files[filename].set_bad(f"SQLite COMMIT error {sqlite_err}")
        return
    if args.verbose:
        print(f"    Committed {day_row.total_parked} visit records for {date}")


def sql_exec_and_error(sql_statement: str, conn, quiet: bool = False) -> str:
    """Execute a SQL statement, returns error message (if any).

    Presumably there is no error if the return is empty.
    Counter-intuitively this means that this returns bool(False) if
    this succeeded.

    Not suitable (of course) for SELECT statements.
    """
    try:
        curs = conn.cursor()
        curs.execute(sql_statement)
    except sqlite3.Error as sqlite_err:
        if not quiet:
            print(f"SQLite error:{sqlite_err}", file=sys.stderr)
        return sqlite_err if sqlite_err else "Unspecified SQLite error"
    # Success
    return ""


def get_args() -> argparse.Namespace:
    """Get program arguments."""

    parser = argparse.ArgumentParser()

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

    prog_args = parser.parse_args()
    return prog_args


def find_datafiles(fileglob: str) -> list:
    """Set a list of files from the supplied dataglob.

    Needs at least 1 of:
    - specific file to target
    - glob to search with in specified directory

    If provided both, returns the set union of all datafiles found.
    """
    maybe_datafiles = []
    for this_glob in fileglob:
        # print(f"{this_glob=}")

        globbed_files = glob.glob(this_glob)
        if len(globbed_files) < 1:
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
            f_info.set_bad("Can not read md5sum")
            continue
        f_info.timestamp = get_file_timestamp(f)
        if not f_info.timestamp:
            f_info.set_bad("Can not read timestamp")
            continue

    ok_datafiles = [
        f for f in Statuses.files if Statuses.files[f].status == STATUS_GOOD
    ]

    return ok_datafiles


def get_logfile_name(database_file: str) -> str:
    """Make a logfile name from a database name."""
    base_name, extension = os.path.splitext(database_file)

    if extension == "":
        logfile = base_name + ".log"
    elif extension == ".log":
        raise ValueError("Database file cannot have '.log' extension.")
    else:
        logfile = base_name + ".log"

    return logfile


def save_log_info(logfile: str):
    """Status info for logging."""
    with open(logfile, "a", encoding="utf-8") as file:
        for name, info in Statuses.files.items():
            if info.status == STATUS_SKIP:
                continue
            print(
                f"{name},{info.fingerprint},{info.status},{info.timestamp},{Statuses.start_time}",
                file=file,
            )


def print_summary():
    """A chatty summary of what took place."""
    total_file_errors = 0
    for info in Statuses.files.values():
        info: FileInfo
        info.errors = info.errors if info.errors else len(info.error_list)
        total_file_errors += info.errors

    print(f"Total files: {len(Statuses.files)}")
    print(f"Total file errors: {total_file_errors}")
    print(f"Total program errors: {Statuses.errors}")


def main():
    """Main routine."""

    Statuses.files = {}

    global args
    args = get_args()

    database_file = args.dbfile
    datafiles = find_datafiles(args.dataglob)
    if not args.quiet:
        print(f"Given {len(datafiles)} files to load.")

    # If logging, get a list of known 'good' MD5s
    logfile = get_logfile_name(database_file)
    good_md5s = get_good_mp5s_list(logfile)
    num_skipped = 0
    for finfo in Statuses.files.values():
        finfo: FileInfo
        if finfo.fingerprint in good_md5s:
            finfo.status = STATUS_SKIP
            num_skipped += 1
    if num_skipped and not args.quiet:
        print(f"Skipping {num_skipped} datafiles previously loaded ok")

    if args.verbose:
        print(f"Connecting to database {database_file}")
    conn = tt_dbutil.db_connect(database_file)
    if not conn:
        sys.exit(1)  # Error messages already taken care of in fn

    sql_error = sql_exec_and_error("PRAGMA foreign_keys=ON;", conn)
    if sql_error:
        print(
            "Error: couldn't enable SQLite use of foreign keys",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.verbose:
        print("Enabled foreign key constraints.")

    batch = Statuses.start_time[:-3]  # For some reason batch does not include seconds
    if args.verbose:
        print(f"BatchID is {batch}")

    for datafilename in datafiles:
        if Statuses.files[datafilename].status != STATUS_SKIP:
            datafile_into_db(datafilename, batch, conn)

    conn.close()

    if args.log:
        save_log_info(logfile)
    if not args.quiet:
        print_summary()

    if Statuses.errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
