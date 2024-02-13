#!/usr/bin/env python3
"""Load datafile records into TagTracker database.

Options:
    --force: reload given datafiles even if already loaded (default behaviour
            is to successfully load any given file only once, as identified
             by its file fingerprint (md5hash))
    --quiet: no output except error output (to stderr)
    --verbose: extra-chatty output

This should run on the tagtracker server.
Supersedes "tracker2db.py"

This is a script to update a persistent SQLite database in a configurable
directory with data from all available (by default) or specific TagTracker
data files.  It uses some modules that it shares in common with the TT client.

Before running this, the database will need to be created.
See "create_database.sql".

By default this avoids repeating a previously successful datafile load
by keeping a datafile_loads table in the database.  The --force option
will force reloading.

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
from dataclasses import dataclass, field
import subprocess
from datetime import datetime
import hashlib
from collections import defaultdict

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
STATUS_GOOD = "GOOD"  # File has not (yet) been rejected or had errors
STATUS_BAD = "BAD"  # File has errors
STATUS_SKIP_GOOD = "SKIP_PRIOR"  # Skip file because was loaded ok previously
STATUS_SKIP_LATER = "SKIP_TAIL"  # Skip file because another same-named is later
STATUS_SKIP_NEWER = "SKIP_NEWER"  # Skip file because another same-named is newer


# Names for tables and columns.s
# Table for logging datafile loads
TABLE_LOADS = "datafile_loads"
COL_FINGERPRINT = "fingerprint"
COL_DATAFILE = "filename"
COL_TIMESTAMP = "timestamp"
# (Also uses COL_DATE and COL_BATCH)

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

    @classmethod
    def num_files(cls, status: str = "") -> int:
        """Return count of files in a given status.

        status is a known status code, or "".
        If "", returns the total number of files."""
        if status:
            return len([f for f in cls.files.values() if f.status == status])
        return len(cls.files)


@dataclass
class FileInfo:
    name: str
    basename: str = ""
    status: str = STATUS_GOOD
    fingerprint: str = None
    timestamp: str = None
    errors: int = 0
    error_list: list = field(default_factory=list)

    def set_bad(self, error_msg: str = "Unspecified error", silent: bool = False):
        """Set a file's info to a fail state, emit error."""

        def print_first_line(msg: str):
            """Format for printing top line of error list."""
            print(f"{msg} [{self.name}]", file=sys.stderr)

        self.status = STATUS_BAD
        self.errors += 1
        self.error_list += [error_msg]
        if not silent:
            if isinstance(error_msg, list):
                print_first_line(error_msg[0] if error_msg else "")
                for line in error_msg[1:]:
                    print(line, file=sys.stderr)
            else:
                print_first_line(error_msg)


def create_logtable(dbconx: sqlite3.Connection):
    """Creates the load-logging table in the database."""
    if args.verbose:
        print(f"Assuring table {TABLE_LOADS} exists.")
    error_msg = sql_exec_and_error(
        f"""CREATE TABLE IF NOT EXISTS
        {TABLE_LOADS} (
            {COL_DATE}  TEXT PRIMARY KEY NOT NULL,
            {COL_DATAFILE} TEXT NOT NULL,
            {COL_TIMESTAMP} TEXT NOT NULL,
            {COL_FINGERPRINT} TEXT NOT NULL,
            {COL_BATCH} TEXT NOT NULL
        );""",
        dbconx,
    )
    if error_msg:
        Statuses.set_bad(f"    SQL error creating datafile_loads: {error_msg}")
        dbconx.close()
        sys.exit(1)


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
            print(f"    Error: {e}", file=sys.stderr)
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


def get_load_fingerprints(dbconx: sqlite3.Connection) -> list[str]:
    """Get a list of the fingerprints of files last loaded ok."""
    create_logtable(dbconx)
    rows = tt_dbutil.db_fetch(
        dbconx, f"SELECT {COL_FINGERPRINT} FROM {TABLE_LOADS}", ["fingerprint"]
    )
    fingerprints = [r.fingerprint for r in rows]
    return fingerprints


def get_file_timestamp(file_path):
    """Get a file's timestamp as an iso8601 string."""
    try:
        timestamp = os.path.getmtime(file_path)
        modified_time = datetime.fromtimestamp(timestamp)
        return modified_time.strftime("%Y-%m-%dT%H:%M:%S")
    except FileNotFoundError:
        print("    File not found {e}.", file=sys.stderr)
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
            msg = f"   Can not tell tag type for tag {tag}"
            Statuses.files[filename].set_bad(msg)
    row.total_parked = row.regular_parked + row.oversize_parked
    row.total_leftover = len(day.bikes_in) - len(day.bikes_out)
    if row.total_leftover < 0:
        msg = "    Total leftovers is negative"
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


def fetch_reg_from_db(dbconx: sqlite3.Connection, date: str) -> int:
    """Get any existing registration info from the DB; return int or None."""
    if args.verbose:
        print("   Fetching any existing bike registration info from DB.")
    rows = tt_dbutil.db_fetch(
        dbconx,
        f"SELECT {COL_REGISTRATIONS} FROM {TABLE_DAYS} WHERE DATE = '{date}'",
        ["registrations"],
    )
    if not rows:
        return None
    return rows[0].registrations


def calc_reg_value(day_summary: DayStats, dbconx: sqlite3.Connection) -> int:
    """Calculate what bike registrations count to use."""
    # Figure out what value to use for registrations.
    # This is yucky for legacy support reasons: before approx 2024-02
    # the count of registrations came from a separate day-end from, not
    # the datafile.  So this selects the existing value or the datafile
    # value, whichever is greater.

    # db_reg    df_reg      result
    # None      None        None
    # None      not None    df_reg
    # not None  None        db_reg
    # not None  not None    max(df_reg, db_reg)

    db_reg = fetch_reg_from_db(dbconx, day_summary.date)
    df_reg = day_summary.registrations
    winner = "nowhere"
    if db_reg is None and df_reg is None:
        result = "NULL"
    elif db_reg is None:
        result = df_reg
        winner = "datafile"
    elif df_reg is None:
        result = db_reg
        winner = "database"
    elif df_reg > db_reg:
        result = df_reg
        winner = "datafile"
    else:
        result = db_reg
        winner = "database"

    if args.verbose:
        print(f"   Using registration value {result} from {winner}.")

    return result


def day_summary_into_db(
    filename: str, day_summary: DayStats, batch: str, dbconx: sqlite3.Connection
) -> bool:
    """Load into the DAY table.  Return T or F to indicate success."""

    # Figure out what bike registrations count value to use.  (!!!!yuck)
    reg = calc_reg_value(day_summary, dbconx)

    # Insert/replace this day's summary info
    if args.verbose:
        print("   Adding day summary to database.")
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
                '{day_summary.date}',
                {day_summary.regular_parked},
                {day_summary.oversize_parked},
                {day_summary.total_parked},
                {day_summary.total_leftover},
                {day_summary.max_regular_num},
                '{day_summary.max_regular_time}',
                {day_summary.max_oversize_num},
                '{day_summary.max_oversize_time}',
                {day_summary.max_total_num},
                '{day_summary.max_total_time}',
                '{day_summary.time_open}',
                '{day_summary.time_close}',
                {day_summary.weekday},
                {reg},
                '{batch}'
            );""",
        dbconx,
    )
    # Did it work? (No error message means success.)
    if sql_error:
        Statuses.files[filename].set_bad(
            f"SQL error adding to {TABLE_DAYS}: {sql_error}"
        )
        return False

    return True


def day_visits_into_db(
    file_info: FileInfo,
    day: TrackerDay,
    day_summary: DayStats,
    batch: str,
    dbconx: sqlite3.Connection,
) -> bool:
    if args.verbose:
        print("   Deleting any existing visits info for this day from database.")
    sql_error = sql_exec_and_error(
        f"DELETE FROM {TABLE_VISITS} WHERE date = '{day_summary.date}'", dbconx
    )
    if sql_error:
        file_info.set_bad(f"Error deleting VISIT rows: {sql_error}")
        return False

    if args.verbose:
        print(f"   Adding {len(day.bikes_in)} visits to database.")
    for tag, time_in in day.bikes_in.items():
        time_in = VTime(time_in)

        # Insert VISIT rows one at a time
        if tag in day.bikes_out:
            time_out = VTime(day.bikes_out[tag])
            dur_end = time_out
        else:  # no check-out recorded
            dur_end = day_summary.time_close
            time_out = ""  # empty str for no time
        time_stay = calc_stay_length(time_in, dur_end)
        biketype = get_bike_type(tag, day)
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
                    '{day_summary.date}.{tag}',
                    '{day_summary.date}',
                    '{tag}',
                    '{biketype}',
                    '{time_in}',
                    '{time_out}',
                    '{time_stay}',
                    '{batch}');""",
            dbconx,
        )
        if sql_error:
            file_info.set_bad(f"Error inserting {TABLE_VISITS} tag {tag}: {sql_error}")
            return False
    return True


def fileload_results_into_db(
    file_info: FileInfo, day_summary: DayStats, batch: str, dbconx: sqlite3.Connection
) -> bool:
    """Update table that tracks load successes."""
    if args.verbose:
        print(f"   Updating fileload info for {day_summary.date} into database.")
    sql = f"""
        INSERT OR REPLACE INTO {TABLE_LOADS} (
            {COL_DATE},
            {COL_DATAFILE},
            {COL_TIMESTAMP},
            {COL_FINGERPRINT},
            {COL_BATCH}
        ) VALUES (
            '{day_summary.date}',
            '{file_info.name}',
            '{file_info.timestamp}',
            '{file_info.fingerprint}',
            '{batch}'
        ) """
    sql_error = sql_exec_and_error(sql, dbconx)
    if sql_error:
        file_info.set_bad(f"Error updating {TABLE_LOADS} table: {sql_error}")
        return False
    return True


def datafile_into_db(filename: str, batch, dbconx) -> str:
    """Record one datafile to the database, returns date.

    Reads the datafile, looking for errors.
    Calculates summary stats, loads DAY and VISIT tables.
    Saves the file info & fingerprint to LOAD_INFO table.

    Returns the date of the file's data if successful (else "")
    Status is also Statuses.files[filename], which is a FileInfo object.
    """

    file_info: FileInfo = Statuses.files[filename]

    if not os.path.isfile(filename):
        file_info.set_bad("File not found")
        return ""

    if args.verbose:
        print(f"Reading {filename}:")

    read_errors = []
    day = tt_datafile.read_datafile(f"{filename}", err_msgs=read_errors)
    if not day.date:
        msg = "Unable to read date from file. Skipping file."
        file_info.set_bad(msg)
        return ""
    if read_errors:
        msg = ["Errors reading datafile"] + read_errors
        file_info.set_bad(msg)
        return ""
    if args.verbose:
        print(
            f"   Date:{day.date}  Open:{day.opening_time}-{day.closing_time}"
            f"  Bikes:{len(day.bikes_in)} "
            f"Leftover:{len(day.bikes_in)-len(day.bikes_out)}  "
            f"Registrations:{day.registrations}"
        )

    day_summary = calc_day_stats(filename, day)

    sql_begin_transaction(dbconx)

    # Day summary
    if not day_summary_into_db(filename, day_summary, batch, dbconx):
        dbconx.rollback()
        return ""

    # Visits info
    if not day_visits_into_db(file_info, day, day_summary, batch, dbconx):
        dbconx.rollback()
        return ""

    # Successful load (pending commit), put it in the loads log
    if not fileload_results_into_db(file_info, day_summary, batch, dbconx):
        dbconx.rollback()
        return ""

    dbconx.commit()  # commit one datafile transaction

    if args.verbose:
        print(f"   Committed {day_summary.date}.")

    return day_summary.date


def sql_begin_transaction(dbconx: sqlite3.Connection):
    curs = dbconx.cursor()
    curs.execute("BEGIN;")


def sql_exec_and_error(sql_statement: str, dbconx) -> str:
    """Execute a SQL statement, returns error message (if any).

    Presumably there is no error if the return is empty.
    Counter-intuitively this means that this returns bool(False) if
    this succeeded.

    Not suitable (of course) for SELECT statements.
    """
    try:
        curs = dbconx.cursor()
        curs.execute(sql_statement)
    except sqlite3.Error as sqlite_err:
        print(f"SQLite error:{sqlite_err}", file=sys.stderr)
        return sqlite_err if sqlite_err else "Unspecified SQLite error"
    # Success
    return ""


def get_args() -> argparse.Namespace:
    """Get program arguments."""

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppresses all non-error output"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="provides most detailed output"
    )
    parser.add_argument(
        "-f", "--force", action="store_true", help="load even if previously loaded"
    )
    parser.add_argument(
        "-n",
        "--newest-only",
        action="store_true",
        help="if files have same basename, only consider the newest one",
    )
    parser.add_argument(
        "-t",
        "--tail-only",
        action="store_true",
        help="if files have same basename, only consider "
        "the one that is closer to the tail of of the file list",
    )
    parser.add_argument(
        "dataglob", type=str, nargs="+", help="Fileglob(s) of datafiles to load"
    )
    parser.add_argument("dbfile", type=str, help="SQLite3 database file")

    prog_args = parser.parse_args()

    if prog_args.verbose and prog_args.quiet:
        prog_args.quiet = False
        print("Arg --verbose set; ignoring arg --quiet.")

    if prog_args.tail_only and prog_args.newest_only:
        print(
            "Error: Can not use --newest-only and --tail-only together", file=sys.stderr
        )
        sys.exit(1)

    return prog_args


def find_datafiles(fileglob: list) -> list:
    """Return a list of files from a dataglob." """

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
        maybe_datafiles += globbed_files
    # Make paths absolute
    maybe_datafiles = convert_paths_to_absolute(maybe_datafiles)
    # Exclude exact duplicates but preserve the file order
    maybe_datafiles = dedup_filepaths(maybe_datafiles)

    return maybe_datafiles


def dedup_filepaths(filepaths: list[str]) -> list[str]:
    """Deduplicate a list of filepaths, removing dups and preserving order."""
    dedupped = []
    dups = []
    for f in filepaths:
        if f in dedupped:
            if f not in dups and not args.quiet:
                print(
                    f"Warning: filepath {f} given more than once, ignoring later instances.",
                    file=sys.stderr,
                )
            dups.append(f)
        else:
            dedupped.append(f)
    return dedupped


def convert_paths_to_absolute(files: list) -> list:
    """Convert a list of relative paths to absolute paths."""
    abs_paths = []
    for f in files:
        abs_paths.append(os.path.abspath(f))
    return abs_paths


def get_files_metadata(maybe_datafiles: list):
    """Gets metadata for the files, loads it into Statuses class."""
    for f in maybe_datafiles:
        f_info = FileInfo(f)
        Statuses.files[f] = f_info
        if not os.path.exists(f):
            f_info.set_bad("File not found")
            continue
        f_info.basename = os.path.basename(f)
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


def skip_non_tail_dups(filepath_list):
    """Sets FileInfo for some files based on their location in the list.

    file_list is an ordered list of filepaths.
    """
    base_list = [os.path.basename(f) for f in filepath_list]
    for i, base in enumerate(
        base_list[:-1]
    ):  # Iterate over all elements except the last one
        if (
            base in base_list[i + 1 :]
        ):  # Check if the item appears again in the subsequent portion of the list
            skip_path = filepath_list[i]
            # Set this file's status to skip
            Statuses.files[skip_path].status = STATUS_SKIP_LATER
    if args.verbose:
        print(
            f"{Statuses.num_files(STATUS_SKIP_LATER)} same-named files ignored "
            "because another is later in arg list."
        )


def skip_non_newest_dups():
    """Skips duplicate files that are not the newest."""

    def get_fileinfo_timestamp(fi: FileInfo) -> str:
        """FileInfo timestamp. (as a function so can use as key to max())."""
        return fi.timestamp

    # Find all the fileinfos associated with each basename
    bases = {}
    for fi in Statuses.files.items():
        fi: FileInfo
        base = fi.basename
        if base not in bases:
            bases[base] = [fi]
        else:
            bases[base].append(fi)
    for fi_list in bases.items():
        if len(fi_list) > 1:
            # Find newest file, skip the rest
            newest_stamp = max(fi_list, key=get_fileinfo_timestamp)
            for dup_fi in fi_list:
                dup_fi: FileInfo
                if dup_fi.timestamp != newest_stamp:
                    dup_fi.status = STATUS_SKIP_NEWER
    if args.verbose:
        print(
            f"{Statuses.num_files(STATUS_SKIP_NEWER)} same-named files ignored because another is newer."
        )


def print_summary(loaded_dates: dict[str:int]):
    """A chatty summary of what took place."""
    for info in Statuses.files.values():
        info: FileInfo
        info.errors = info.errors if info.errors else len(info.error_list)

    print()
    print(f"{Statuses.num_files():4d} files requested")
    print(f"{Statuses.num_files(STATUS_GOOD):4d} files loaded OK")
    print(
        f"{Statuses.num_files(STATUS_SKIP_LATER):4d} files ignored, file with same name later in file list"
    )
    print(
        f"{Statuses.num_files(STATUS_SKIP_NEWER):4d} files ignored, newer file with same name"
    )
    print(
        f"{Statuses.num_files(STATUS_SKIP_GOOD):4d} files ignored, previously loaded ok"
    )
    print(f"Files rejected: {Statuses.num_files(STATUS_BAD):4d}")
    if args.verbose:
        for f, finfo in sorted(Statuses.files.items()):
            finfo: FileInfo
            if finfo.status == STATUS_BAD:
                print(f"    {f}: {finfo.errors} errors")
    num_dup_dates = sum([x - 1 for d, x in loaded_dates.items() if d])
    if num_dup_dates:
        print(f"Dates for which more that one datafile loaded: {num_dup_dates}")
        if args.verbose:
            for date, count in sorted(loaded_dates.items()):
                if date and count > 1:
                    print(f"    {date}: {count} files")


def main():
    """Main routine."""

    Statuses.files = {}

    global args
    args = get_args()
    ordered_file_list = find_datafiles(args.dataglob)
    if not args.quiet:
        print(f"Load requested for {len(ordered_file_list)} files.")

    if args.verbose:
        print("Getting metadata for files.")
    get_files_metadata(ordered_file_list)

    database_file = args.dbfile
    if args.verbose:
        print(f"Connecting to database {database_file}.")
    dbconx = tt_dbutil.db_connect(database_file)
    if not dbconx:
        print(f"Error: unable to connect to db {database_file}", file=sys.stderr)
        dbconx.close()
        sys.exit(1)

    if args.tail_only:
        skip_non_tail_dups(ordered_file_list)

    if args.newest_only:
        skip_non_newest_dups()

    # Get a list of fingerprints of previous good loads.
    if args.verbose:
        print("Fetching fingerprints of previous datafile loads.")
    good_fingerprints = get_load_fingerprints(dbconx)

    # Decide which files to ignore becuase previously loaded ok
    for finfo in Statuses.files.values():
        finfo: FileInfo
        if (
            not args.force
            and finfo.status == STATUS_GOOD
            and finfo.fingerprint in good_fingerprints
        ):
            finfo.status = STATUS_SKIP_GOOD
    if not args.quiet:
        num_skipped = Statuses.num_files(STATUS_SKIP_GOOD)
        # ut.squawk(f"{num_skipped=},{args.force=},{args.quiet=}")
        if num_skipped:
            if args.force:
                print(f"Forcing reload of {num_skipped} previously loaded files.")
            else:
                print(f"Ignoring {num_skipped} previously loaded files.")
        num_bad = Statuses.num_files(STATUS_BAD)
        if num_bad:
            print(f"Ignoring {num_bad} files already known to be bad.")
        if num_skipped or num_bad:
            print(
                f"Attempting to load {Statuses.num_files(STATUS_GOOD)} remaining files."
            )

    num_good = Statuses.num_files(STATUS_GOOD)

    if num_good:
        if args.verbose:
            print("Assuring foreign key constraints are enabled.")
        sql_error = sql_exec_and_error("PRAGMA foreign_keys=ON;", dbconx)
        if sql_error:
            print(
                "Error: couldn't enable SQLite foreign key constraints", file=sys.stderr
            )
            dbconx.close()
            sys.exit(1)
        dbconx.commit()

        batch = Statuses.start_time[
            :-3
        ]  # For some reason batch does not include seconds
        if args.verbose:
            print(f"Batch ID is {batch}.")

    # Load the datafiles.
    dates_loaded_ok = defaultdict(int)
    for file_name in sorted(
        [f.name for f in Statuses.files.values() if f.status == STATUS_GOOD]
    ):
        this_date = datafile_into_db(file_name, batch, dbconx)
        dates_loaded_ok[this_date] += 1

    if args.verbose:
        print("Closing database connection.")
    dbconx.close()

    if not args.quiet:
        print_summary(dates_loaded_ok)

    if Statuses.errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
