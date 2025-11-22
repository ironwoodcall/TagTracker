#!/usr/bin/env python3
"""
Load TagTracker datafiles into an SQLite database.

This script ingests one or more TagTracker datafiles, validates their contents,
and records day summaries, bike visits, and per-period block data into a
persistent SQLite database. It also maintains a log of previously loaded
files (with fingerprints) to avoid accidental duplicate loads.

Features:
    - Automatically calculates file fingerprints (md5) and timestamps.
    - Skips files already loaded successfully unless --force is given.
    - Handles duplicate filenames by keeping only the newest (--newest-only)
      or last-seen (--tail-only).
    - Inserts data into the following tables:
        * DAY (daily summary statistics)
        * VISIT (individual bike visits)
        * BLOCK (per-period visit counts)
        * DATALOADS (audit log of file loads)

Command-line options:
    --force        Reload datafiles even if already recorded
    --quiet        Suppress all normal output (errors still shown on stderr)
    --verbose      Print detailed progress information
    --newest-only  For files with the same basename, only load the newest one
    --tail-only    For files with the same basename, only load the last in the list
    --org          Organization handle (default: "no_org")

Arguments:
    dataglob       One or more file globs specifying the datafiles to load
    dbfile         Path to the SQLite database file

Requirements:
    - The SQLite database must already exist (see create_database.sql).
    - Database schema must include tables for DAY, VISIT, BLOCK, and DATALOADS.

Intended usage:
    Run on the TagTracker server to keep the central database updated from
    local or batch-exported datafiles.

Copyright (C) 2024 Todd Glover & Julias Hocking

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

# import tt_datafile
import database.tt_dbutil as db
from database.tt_dbutil import SQL_CRITICAL_ERRORS, SQL_MODERATE_ERRORS

# import tt_globals
import common.tt_util as ut
from common.tt_trackerday import TrackerDay, TrackerDayError
from common.tt_biketag import BikeTagError
from common.tt_bikevisit import BikeVisit

from common.tt_daysummary import DaySummary, PeriodDetail
from common.tt_time import VTime
from common.tt_constants import REGULAR, OVERSIZE, COMBINED

# Pre-declare this global for linting purposes.
args = None


# Default org_handle -- make this match default text in CREATE_DATABASE sql script
DEFAULT_ORG = "no_org"

# Values for good & bad status
STATUS_GOOD = "GOOD"  # File has not (yet) been rejected or had errors
STATUS_BAD = "BAD"  # File has errors
STATUS_SKIP_GOOD = "SKIP_PRIOR"  # Skip file because was loaded ok previously
STATUS_SKIP_LATER = "SKIP_TAIL"  # Skip file because another same-named is later
STATUS_SKIP_NEWER = "SKIP_NEWER"  # Skip file because another same-named is newer


# Names for tables and columns.s
# Table for logging datafile loads
TABLE_LOADS = "dataloads"
COL_DAYID = "day_id"
COL_FINGERPRINT = "datafile_fingerprint"
COL_DATAFILE = "datafile_name"
COL_TIMESTAMP = "datafile_timestamp"
COL_BATCH = "batch"


class DBError(Exception):
    pass


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

    # FIXME: probably want to do for only this organization's scope?

    cursor = dbconx.cursor()
    rows = cursor.execute(f"SELECT {COL_FINGERPRINT} FROM {TABLE_LOADS}").fetchall()
    fingerprints = [r[0] for r in rows]
    cursor.close()

    return fingerprints


def get_file_timestamp(file_path):
    """Get a file's timestamp as an iso8601 string."""
    try:
        timestamp = os.path.getmtime(file_path)
        modified_time = datetime.fromtimestamp(timestamp)
        return modified_time.strftime("%Y-%m-%dT%H:%M:%S")
    except FileNotFoundError as e:
        print(f"    File {file_path} not found {e}.", file=sys.stderr)
        return None


def fetch_existing_weather(
    cursor: sqlite3.Connection.cursor, date: str, orgsite_id: int
) -> tuple[float, float]:
    """Fetch any existing temp and precip data from the given day.

    This uses data and orgsite_id since day_id not known at time this is called."""
    if args.verbose:
        print(f"   Fetching existing weather (temp/precip) for {orgsite_id=}/'{date}'.")
    row = cursor.execute(
        f"SELECT max_temperature, precipitation FROM day WHERE orgsite_id = {orgsite_id} AND date = '{date}';"
    ).fetchone()

    if not row:
        return None, None

    return row[0], row[1]


# FIXME: use versions in tt_dbutil
def fetch_org_id(cursor: sqlite3.Connection.cursor, org_handle: str) -> int:
    """Fetch the org id."""
    org_handle = org_handle.strip().lower()
    if args.verbose:
        print(f"   Fetching org_id for '{org_handle}'.")
    row = cursor.execute(
        f"SELECT id FROM org WHERE org_handle = '{org_handle}';"
    ).fetchone()

    if not row:
        raise DBError(f"No match for org_handle '{org_handle}'.")

    this_id = row[0]
    if not isinstance(this_id, int):
        raise DBError(f"Not integer: org.id '{this_id}' (type {type(this_id)})")
    return this_id


# FIXME: separate making new into its own.  Use fetch_*() from tt_dbutil
def fetch_orgsite_id(
    cursor: sqlite3.Connection.cursor,
    site_handle: str,
    org_id: int,
    site_name: str = "",
    insert_new: bool = False,
) -> int:
    """Fetch the PK id from the orgsite table.

    If not found and insert_new, will create a new record."""

    site_handle = site_handle.strip().lower()
    if args.verbose:
        print(f"   Fetching orgsite_id for '{site_handle}', org_id {org_id}.")

    row = cursor.execute(
        f"SELECT id FROM orgsite WHERE site_handle = '{site_handle}' AND org_id = {org_id};",
    ).fetchone()
    if not row:
        if not insert_new:
            raise DBError(
                f"No match for site_handle '{site_handle}' with org_id {org_id}."
            )
        else:
            this_id = cursor.execute(
                "INSERT INTO orgsite (org_id,site_handle,site_name) VALUES (?,?,?)",
                (org_id, site_handle, site_name),
            ).lastrowid
            return this_id

    this_id = row[0]
    if not isinstance(this_id, int):
        raise DBError(f"Not integer: orgsite.id '{this_id}' (type {type(this_id)})")
    return this_id


def fetch_day_id(
    cursor: sqlite3.Connection.cursor, date: str, orgsite_id: int, null_ok: bool = True
) -> int:
    """Fetch the DAY id for this date/site.

    If null_ok, then it's ok if no matching record; otherwise a DBError."""
    if args.verbose:
        print(f"   Fetching day_id for {orgsite_id=}/'{date}'.")
    row = cursor.execute(
        f"SELECT id FROM day WHERE orgsite_id = {orgsite_id} AND date = '{date}';"
    ).fetchone()

    if not row:
        if null_ok:
            return None
        raise DBError(f"No match for {orgsite_id=}/{date=}.")

    this_id = row[0]
    if not isinstance(this_id, int):
        raise DBError(f"Not integer: day.id '{this_id}' (type {type(this_id)})")

    return this_id


def insert_new_orgsite(
    cursor: sqlite3.Connection.cursor,
    org_id: int,
    site_handle: str,
    site_name: str = "",
) -> int:
    """Insert new org/site into orgsite table, returns orgsite_id."""
    this_id = cursor.execute(
        "INSERT INTO orgsite (org_id,site_handle,site_name) VALUES (?,?,?)",
        (org_id, site_handle, site_name),
    ).lastrowid
    return this_id


def delete_one_day_data(cursor: sqlite3.Connection.cursor, date: str, orgsite_id: int):
    """Delete one complete day's data from all tables."""

    day_id = db.fetch_day_id(cursor=cursor, date=date, maybe_orgsite_id=orgsite_id)

    if args.verbose:
        print(f"   Deleting records for '{orgsite_id=}'/'{date}'.")

    if day_id is not None:
        cursor.execute(f"DELETE FROM VISIT WHERE day_id = {day_id}")
        cursor.execute(f"DELETE FROM BLOCK WHERE day_id = {day_id}")
        cursor.execute(f"DELETE FROM DATALOADS WHERE day_id = {day_id}")
        cursor.execute(f"DELETE FROM DAY WHERE id = {day_id}")
def insert_into_day(
    orgsite_id: int,
    td: TrackerDay,
    summary: DaySummary,
    batch_id: str,
    cursor: sqlite3.Connection.cursor,
) -> int:
    """Load into the DAY table.  Returns the rowid of the record inserted. None if failed."""

    # This requires some fancy footwork in order to preserve any existing
    # environmental values (rain, temp, sunset)
    # since the INSERT OR REPLACE really does do a REPLACE, meaning
    # that (unlike an update), any columns not specifcally names are
    # set to their default values

    # Insert/replace this day's summary info.
    # Have to delete and replace since doing an INSERT OR REPLACE
    # changes the PK id.  So *could* turn constraints off, update the
    # FKs, then turn back on, but this seems simpler since will be adding
    # new VISIT and BLOCK data anyway.  The cost is that must cache the
    # environmental data (temperature and precipitation).

    # Fetch current temp and precip
    existing_temp, existing_precip = fetch_existing_weather(
        cursor=cursor, date=td.date, orgsite_id=orgsite_id
    )

    # Delete existing data for this day
    delete_one_day_data(cursor=cursor, date=td.date, orgsite_id=orgsite_id)

    if args.verbose:
        print("   Adding day summary to database.")

    # Save to DAY table
    cursor.execute(
        """
        INSERT INTO DAY (
            orgsite_id,
            date,
            time_open,
            time_closed,
            weekday,

            num_parked_regular,
            num_parked_oversize,
            num_parked_combined,

            num_remaining_regular,
            num_remaining_oversize,
            num_remaining_combined,

            num_fullest_regular,
            num_fullest_oversize,
            num_fullest_combined,

            time_fullest_regular,
            time_fullest_oversize,
            time_fullest_combined,

            bikes_registered,
            batch,

            max_temperature,
            precipitation
        )
        VALUES (
            ?,?,?,?,?,
            ?,?,?,    ?,?,?,   ?,?,?,   ?,?,?,
            ?,?,
            ?,?
        )
    """,
        (
            # td.org_id,  # Add org_id to TrackerDay class
            # td.site_id,  # Add site_id to TrackerDay class
            orgsite_id,
            summary.whole_day.date,
            summary.whole_day.time_open,
            summary.whole_day.time_closed,
            ut.dow_int(td.date),
            summary.whole_day.num_parked_regular,
            summary.whole_day.num_parked_oversize,
            summary.whole_day.num_parked_combined,
            summary.whole_day.num_remaining_regular,
            summary.whole_day.num_remaining_oversize,
            summary.whole_day.num_remaining_combined,
            summary.whole_day.num_fullest_regular,
            summary.whole_day.num_fullest_oversize,
            summary.whole_day.num_fullest_combined,
            summary.whole_day.time_fullest_regular,
            summary.whole_day.time_fullest_oversize,
            summary.whole_day.time_fullest_combined,
            td.registrations.num_registrations,
            batch_id,
            existing_temp,
            existing_precip,
        ),
    )

    day_id = cursor.lastrowid

    return day_id




def insert_into_visit(
    day: TrackerDay,
    cursor: sqlite3.Connection.cursor,
    day_id: int,
) -> bool:
    """Load this day's visits into the database."""
    # if args.verbose:
    #     print("   Deleting any existing visits info for this day from database.")
    # sql_error = sql_exec_and_error(
    #     f"DELETE FROM {TABLE_VISITS} WHERE date = '{day_totals.date}'", dbconx
    # )
    # if sql_error:
    #     file_info.set_bad(f"Error deleting VISIT rows: {sql_error}")
    #     return False

    if args.verbose:
        print(f"   Adding {len(day.all_visits())} visits to database.")

    for visit in day.all_visits():
        visit: BikeVisit
        if not visit.time_in:
            continue
        biketype = "R" if day.biketags[visit.tagid].bike_type == REGULAR else "O"

        time_in_text = str(visit.time_in) if visit.time_in else "00:00"
        time_out_text = str(visit.time_out) if visit.time_out else ""

        # Save to VISIT table
        cursor.execute(
            """
            INSERT INTO VISIT (
                day_id,
                time_in,
                time_out,
                duration,
                bike_type,
                bike_id
            )

            VALUES (?,?,?,?,?,?)
        """,
            (
                day_id,
                time_in_text,
                time_out_text,
                visit.duration(day.time_closed, is_close_of_business=True),
                biketype,
                visit.tagid,
            ),
        )
    return True


def insert_into_block(
    summary: DaySummary,
    cursor: sqlite3.Connection.cursor,
    day_id: int,
) -> bool:
    """Load this day's block data into the database."""

    if args.verbose:
        print(f"   Adding {len(summary.blocks)} data blocks to database.")

    for block in summary.blocks.values():
        block: PeriodDetail
        # Save to BLOCK table
        cursor.execute(
            """
            INSERT INTO block (

                day_id,
                time_start,

                num_incoming_regular,
                num_incoming_oversize,
                num_incoming_combined,

                num_outgoing_regular,
                num_outgoing_oversize,
                num_outgoing_combined,

                num_on_hand_regular,
                num_on_hand_oversize,
                num_on_hand_combined,

                num_fullest_regular,
                num_fullest_oversize,
                num_fullest_combined,

                time_fullest_regular,
                time_fullest_oversize,
                time_fullest_combined


            )

            VALUES (?,?,  ?,?,?,  ?,?,?,  ?,?,?,  ?,?,?, ?,?,?)
        """,
            (
                day_id,
                block.time_start,
                block.num_incoming[REGULAR],
                block.num_incoming[OVERSIZE],
                block.num_incoming[COMBINED],
                block.num_outgoing[REGULAR],
                block.num_outgoing[OVERSIZE],
                block.num_outgoing[COMBINED],
                block.num_on_hand[REGULAR],
                block.num_on_hand[OVERSIZE],
                block.num_on_hand[COMBINED],
                block.num_fullest[REGULAR],
                block.num_fullest[OVERSIZE],
                block.num_fullest[COMBINED],
                block.time_fullest[REGULAR],
                block.time_fullest[OVERSIZE],
                block.time_fullest[COMBINED],
            ),
        )
    return True


def insert_into_dataloads(
    file_info: FileInfo, day_id: int, batch: str, dbconx: sqlite3.Connection
) -> bool:
    """Update table that tracks load successes."""
    if args.verbose:
        print(f"   Updating fileload info for {file_info.basename} into database.")
    sql = f"""
        INSERT OR REPLACE INTO {TABLE_LOADS} (
            {COL_DAYID},
            {COL_DATAFILE},
            {COL_TIMESTAMP},
            {COL_FINGERPRINT},
            {COL_BATCH}
        ) VALUES (
            '{day_id}',
            '{file_info.name}',
            '{file_info.timestamp}',
            '{file_info.fingerprint}',
            '{batch}'
        ) """
    cursor = dbconx.cursor()
    try:
        cursor.execute(sql)
    except tuple(SQL_MODERATE_ERRORS) as e:
        print(f"Non-fatal error occurred: {e}")
        return False
    except tuple(SQL_CRITICAL_ERRORS) as e:
        print(f"Fatal error occurred: {e}")
        raise
    finally:
        cursor.close()

    return True


def _sanitize_day_visits(day: TrackerDay) -> list[str]:
    """Attempt to repair or drop problematic visits instead of rejecting a file."""

    notes = []
    for tagid, biketag in day.biketags.items():
        if not biketag.visits:
            continue

        visits_sorted = sorted(
            biketag.visits,
            key=lambda visit: (
                visit.time_in.num if visit.time_in else -1,
                getattr(visit, "seq", 0),
            ),
        )

        cleaned_visits = []
        last_end: VTime | None = None
        for index, visit in enumerate(visits_sorted, start=1):
            label = f"{tagid}:{index}"

            if not visit.time_in:
                notes.append(f"Removed {label} because it is missing a check-in time.")
                continue

            if visit.time_out and visit.time_in > visit.time_out:
                notes.append(
                    f"Adjusted {label} checkout from {visit.time_out} to {visit.time_in}."
                )
                visit.time_out = VTime(visit.time_in)

            if last_end and visit.time_in < last_end:
                if visit.time_out and visit.time_out <= last_end:
                    notes.append(
                        f"Removed {label} because it ended before the prior visit's checkout."
                    )
                    continue

                adjusted_start = VTime(last_end)
                notes.append(
                    f"Shifted {label} check-in from {visit.time_in} to {adjusted_start} to avoid overlap."
                )
                visit.time_in = adjusted_start

            cleaned_visits.append(visit)
            last_end = visit.time_out if visit.time_out else visit.time_in

        unfinished = [v for v in cleaned_visits if not v.time_out]
        if len(unfinished) > 1:
            for extra in unfinished[:-1]:
                notes.append(
                    f"Removed {tagid} visit starting {extra.time_in} lacking checkout before the final visit."
                )
                cleaned_visits.remove(extra)

        if unfinished:
            last_unfinished = unfinished[-1]
            if last_unfinished in cleaned_visits:
                last_index = cleaned_visits.index(last_unfinished)
                if last_index != len(cleaned_visits) - 1:
                    notes.append(
                        f"Removed {tagid} visit starting {last_unfinished.time_in} without checkout because another visit follows."
                    )
                    cleaned_visits.pop(last_index)

        if len(cleaned_visits) != len(biketag.visits):
            notes.append(
                f"{tagid}: retained {len(cleaned_visits)} of {len(biketag.visits)} visits after repair."
            )

        biketag.visits = cleaned_visits

        if biketag.status != biketag.RETIRED:
            if not biketag.visits:
                biketag.status = biketag.UNUSED
            elif biketag.visits[-1].time_out:
                biketag.status = biketag.DONE
            else:
                biketag.status = biketag.IN_USE

    return notes


def read_datafile(filename: str) -> tuple[TrackerDay, DaySummary]:
    """Read and prepare one filename into TrackerDay & DaySummary obects."""
    file_info: FileInfo = Statuses.files[filename]

    if not os.path.isfile(filename):
        file_info.set_bad("File not found")
        return None, None

    if args.verbose:
        print(f"Reading {filename}:")

    try:
        day = TrackerDay.load_from_file(filename)
    except (TrackerDayError, BikeTagError) as e:
        msg = f"Error reading file {filename=}: {e}. Skipping file."
        file_info.set_bad(msg)
        # print(msg)
        return None, None

    lint_msgs = day.lint_check(strict_datetimes=True, allow_quick_checkout=True)
    if lint_msgs:
        repair_notes = _sanitize_day_visits(day)
        if repair_notes:
            file_info.error_list.extend([f"AUTO-REPAIR: {note}" for note in repair_notes])
            if args.verbose:
                print(f"   Auto-repaired visits in {filename}:")
                for note in repair_notes:
                    print(f"      {note}")
        lint_msgs = day.lint_check(strict_datetimes=True, allow_quick_checkout=True)
        if lint_msgs:
            msg = [f"Errors reading datafile {filename}:"] + lint_msgs
            file_info.set_bad(msg)
            return None, None

    day_summary = DaySummary(day=day, as_of_when="24:00")
    return day, day_summary


def one_datafile_into_db(filename: str, batch, dbconx) -> str:
    """Record one datafile to the database, returns date.

    Reads the datafile, looking for errors.
    Calculates summary stats, tables.
    Saves the file info & fingerprint to LOAD_INFO table.

    Returns the date of the file's data if successful (else "")
    Status is also Statuses.files[filename], which is a FileInfo object.

    This should create then destroy a cursor, which means rollback or commit.
    """

    day, day_summary = read_datafile(filename=filename)
    if day is None or day_summary is None:
        return None

    # Datafile fully loaded, now start db stuff
    cursor = sql_begin_transaction(dbconx=dbconx)
    if args.verbose:
        print("   Fetching org and orgsize ids")
    org_id = db.fetch_org_id(cursor=cursor, org_handle=args.org)
    if org_id is None:
        raise DBError(f"No org matches {args.org_handle}")
    orgsite_id = db.fetch_orgsite_id(
        cursor=cursor, site_handle=day.site_handle, maybe_org_id=org_id, null_ok=True
    )
    if orgsite_id is None:
        if args.verbose:
            print(f"  Adding new orgsite {args.org=},{day.site_handle=}")
        orgsite_id = insert_new_orgsite(
            cursor=cursor,
            org_id=org_id,
            site_handle=day.site_handle,
            site_name=day.site_name,
        )

    if args.verbose:
        print(
            f"   Date:{day.date}  Open:{day.time_open}-{day.time_closed}"
            f"  Visits:{day_summary.whole_day.num_parked_combined}  "
            f"Leftover:{day_summary.whole_day.num_remaining_combined}  "
            f"Registrations:{day.registrations.num_registrations}"
        )

    # Save data to database
    try:

        day_id = insert_into_day(
            td=day,
            summary=day_summary,
            orgsite_id=orgsite_id,
            batch_id=batch,
            cursor=cursor,
        )
        insert_into_visit(
            day=day,
            cursor=cursor,
            day_id=day_id,
        )
        insert_into_block(
            summary=day_summary,
            cursor=cursor,
            day_id=day_id,
        )
        # day_tags_context_into_db(file_info, day, day_totals, batch, dbconx)
        # day_blocks_into_db()

        insert_into_dataloads(
            Statuses.files[filename], day_id=day_id, batch=batch, dbconx=dbconx
        )

    except (sqlite3.Error, DBError) as err:
        print(f"Error:{err}", file=sys.stderr)
        dbconx.rollback()
        return ""

    finally:
        cursor.close()

    dbconx.commit()  # commit as one datafile transaction

    if args.verbose:
        print(
            f"   Committed {day_summary.whole_day.num_parked_combined} visits for {day.date}."
        )

    return day.date


def sql_begin_transaction(dbconx: sqlite3.Connection) -> sqlite3.Connection.cursor:
    curs = dbconx.cursor()
    curs.execute("BEGIN;")
    return curs


def sql_exec_and_error(sql_statement: str, dbconx) -> int:
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
        "the one that is closer to the tail of the file list",
    )
    parser.add_argument(
        "-o",
        "--org",
        type=str,
        default=DEFAULT_ORG,
        help=f"Organization org_handle (default: '{DEFAULT_ORG}')",
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
            "Error: Cannot use --newest-only and --tail-only together", file=sys.stderr
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
            f_info.set_bad("Cannot read md5sum")
            continue
        f_info.timestamp = get_file_timestamp(f)
        if not f_info.timestamp:
            f_info.set_bad("Cannot read timestamp")
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
    for fi in Statuses.files.values():
        fi: FileInfo
        base = fi.basename
        if base not in bases:
            bases[base] = [fi]
        else:
            bases[base].append(fi)
    for fi_list in bases.values():
        if len(fi_list) > 1:
            # Find newest file, skip the rest
            newest_stamp = max(fi_list, key=get_fileinfo_timestamp)
            for dup_fi in fi_list:
                dup_fi: FileInfo
                if dup_fi.timestamp != newest_stamp.timestamp:
                    dup_fi.status = STATUS_SKIP_NEWER
    if args.verbose:
        print(
            f"{Statuses.num_files(STATUS_SKIP_NEWER)} same-named files ignored because another is newer."
        )


def print_summary():
    """A chatty summary of what took place."""
    for info in Statuses.files.values():
        info: FileInfo
        info.errors = info.errors if info.errors else len(info.error_list)

    print()
    print(f"{Statuses.num_files():4d} files requested")
    print(f"{Statuses.num_files(STATUS_GOOD):4d} files loaded OK")
    print(
        f"{Statuses.num_files(STATUS_SKIP_LATER):4d} files ignored, a file with same name is later in file list"
    )
    print(
        f"{Statuses.num_files(STATUS_SKIP_NEWER):4d} files ignored, a file with same name is newer"
    )
    print(
        f"{Statuses.num_files(STATUS_SKIP_GOOD):4d} files ignored, previously loaded ok"
    )
    print(f"{Statuses.num_files(STATUS_BAD):4d} files not loaded because of errors")
    if args.verbose:
        for f, finfo in sorted(Statuses.files.items()):
            finfo: FileInfo
            if finfo.status == STATUS_BAD:
                print(f"    {f}: {finfo.errors} errors")


def main():
    """Main routine."""

    Statuses.files = {}

    global args  # pylint:disable=global-statement
    args = get_args()
    ordered_file_list = find_datafiles(args.dataglob)
    if not args.quiet:
        print(f"Load requested for {len(ordered_file_list)} files.")

    if args.verbose:
        print("Calculating metadata of datafiles.")
    get_files_metadata(ordered_file_list)

    database_file = args.dbfile
    if args.verbose:
        print(f"Connecting to database {database_file}.")
    dbconx = db.db_connect(database_file)
    if not dbconx:
        print(f"Error: unable to connect to db {database_file}", file=sys.stderr)
        try:
            dbconx.close()
        except Exception as e:
            print(f"Error {e}")
        sys.exit(1)

    if args.tail_only:
        skip_non_tail_dups(ordered_file_list)

    if args.newest_only:
        skip_non_newest_dups()

    # Get a list of fingerprints of previous good loads.
    if args.verbose:
        print("Fetching fingerprints of previous datafile loads.")
    try:
        good_fingerprints = get_load_fingerprints(dbconx=dbconx)
    except tuple(SQL_MODERATE_ERRORS + SQL_CRITICAL_ERRORS) as e:
        print(f"SQL error: {e}", file=sys.stderr)
        sys.exit(1)

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
        try:
            cursor = dbconx.cursor()
            cursor.execute("PRAGMA foreign_keys=ON;")
            dbconx.commit()
        except tuple(SQL_MODERATE_ERRORS) as e:
            print(f"SQL error: {e}", file=sys.stderr)
            sys.exit(1)
        except tuple(SQL_CRITICAL_ERRORS) as e:
            print(f"Serious SQL error occurred: {e}", file=sys.stderr)
            raise
        finally:
            cursor.close()

        batch = Statuses.start_time[
            :-3
        ]  # For some reason batch does not include seconds
        if args.verbose:
            print(f"Batch ID is {batch}.")

    # Load the datafiles.
    for file_name in sorted(
        [f.name for f in Statuses.files.values() if f.status == STATUS_GOOD]
    ):
        try:
            one_datafile_into_db(file_name, batch, dbconx)

        except tuple(SQL_MODERATE_ERRORS) as e:
            print(f"SQL error: {e}")
            continue
        except tuple(SQL_CRITICAL_ERRORS) as e:
            print(f"Serious SQL error occurred: {e}")
            raise

    if args.verbose:
        print("Closing database connection.")
    dbconx.close()

    if not args.quiet:
        print_summary()

    if Statuses.errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
