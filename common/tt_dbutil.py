"""Database utilities for reporting from TagTracker database.

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

import sqlite3
import sys
import os
from typing import Iterable

# from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean, median

from common.tt_trackerday import TrackerDay
from common.tt_daysummary import DaySummary, DayTotals, PeriodDetail
from common.tt_tag import TagID
from common.tt_time import VTime
from common.tt_constants import TagTrackerError
from common.tt_biketag import BikeTag
from common.tt_bikevisit import BikeVisit
import common.tt_util as ut
import common.tt_constants as k


# These errors will mean a rollback but keep going
SQL_MODERATE_ERRORS = [
    sqlite3.IntegrityError,
    sqlite3.OperationalError,
    sqlite3.DatabaseError,
    sqlite3.Warning,
]

# These errors are big & bad and mean we should error exit
SQL_CRITICAL_ERRORS = [
    sqlite3.ProgrammingError,
    sqlite3.InterfaceError,
    sqlite3.DataError,
    sqlite3.InternalError,
]


class DBRow:
    """A generic class for holding database rows.

    In use, pylint will not be aware of the names of the attributes
    since they are created dynamically.
    """

    def __init__(self, labels: list[str], vals: Iterable):
        for i, name in enumerate(labels):
            setattr(self, name, vals[i])


def fetch_org_id(cursor: sqlite3.Connection.cursor, org_handle: str) -> int:
    """Fetch the org id."""
    org_handle = org_handle.strip().lower()
    row = cursor.execute(
        f"SELECT id FROM org WHERE org_handle = '{org_handle}';"
    ).fetchone()

    if not row:
        raise TagTrackerError(f"No match for org_handle '{org_handle}'.")

    this_id = row[0]
    if not isinstance(this_id, int):
        raise TagTrackerError(f"Not integer: org.id '{this_id}' (type {type(this_id)})")
    return this_id


def fetch_orgsite_id(
    cursor: sqlite3.Connection.cursor,
    site_handle: str,
    maybe_org_id: int = None,
    maybe_org_handle: str = None,
    null_ok: bool = False,
) -> int:
    """Fetch the PK id from the orgsite table.

    Will fetch for site_handle (always needed) and
    *either* org_id:int or org_handle:str, as org_handle_or_id.

    """

    # Check if exactly one of maybe_org_id or maybe_org_handle is provided
    if (maybe_org_id is None) == (maybe_org_handle is None):
        raise TagTrackerError("wrong arguments to function fetch_orgsite_id")

    if maybe_org_id is None:
        org_id = fetch_org_id(cursor=cursor, org_handle=maybe_org_handle)
    else:
        org_id = maybe_org_id

    row = cursor.execute(
        f"SELECT id FROM orgsite WHERE site_handle = '{site_handle}' AND org_id = {org_id};",
    ).fetchone()
    if not row:
        if null_ok:
            return None
        else:
            raise TagTrackerError(
                f"No match for site_handle '{site_handle}' with org_id {org_id}."
            )

    this_id = row[0]
    if not isinstance(this_id, int):
        raise TagTrackerError(
            f"Not integer: orgsite.id '{this_id}' (type {type(this_id)})"
        )
    return this_id


def fetch_day_id(
    cursor: sqlite3.Connection.cursor,
    date: str,
    maybe_orgsite_id: int = None,
    maybe_site_handle: str = None,
    maybe_org_id: int = None,
    maybe_org_handle: str = None,
    null_ok: bool = True,
) -> int:
    """Fetch the DAY id for this date/site.

    Always needs date.  Can take:
        orgsite_id (an int) or
        site_handle and (org_id or org_handle)

    If null_ok, then it's ok if no matching record; otherwise a DBError.
    """

    # Condition checks for having usable PK/FK args
    condition_have_orgsite_id = (
        maybe_orgsite_id is not None
        and maybe_site_handle is None
        and maybe_org_id is None
        and maybe_org_handle is None
    )

    condition_have_site_handle_and_org_handle = (
        maybe_orgsite_id is None
        and maybe_site_handle is not None
        and maybe_org_id is None
        and maybe_org_handle is not None
    )

    condition_have_site_handle_and_org_id = (
        maybe_orgsite_id is None
        and maybe_site_handle is not None
        and maybe_org_id is not None
        and maybe_org_handle is None
    )

    # Ensure exactly one condition is true
    conditions_met = sum(
        [
            condition_have_orgsite_id,
            condition_have_site_handle_and_org_id,
            condition_have_site_handle_and_org_handle,
        ]
    )
    if conditions_met != 1:
        raise TagTrackerError("Wrong arguments to function")

    if maybe_orgsite_id is None:
        orgsite_id = fetch_orgsite_id(
            cursor == cursor,
            site_handle=maybe_site_handle,
            maybe_org_id=maybe_org_id,
            maybe_org_handle=maybe_org_handle,
        )
    else:
        orgsite_id = maybe_orgsite_id

    row = cursor.execute(
        f"SELECT id FROM day WHERE orgsite_id = {orgsite_id} AND date = '{date}';"
    ).fetchone()

    if not row:
        if null_ok:
            return None
        raise TagTrackerError(f"No DB match for {orgsite_id=}/{date=}.")

    this_id = row[0]
    if not isinstance(this_id, int):
        raise TagTrackerError(f"Not integer: day.id '{this_id}' (type {type(this_id)})")

    return this_id


def fetch_day_id_list(
    cursor: sqlite3.Connection.cursor,
    orgsite_id: int,
    min_date: str = "",
    max_date: str = "",
) -> list[int]:
    """Fetch a list of day_id vals for this orgsite_id & date range."""

    min_date = min_date or "0000-00-00"
    max_date = max_date or ut.date_str("today")

    rows = cursor.execute(
        "select id from day where orgsite_id = ? and date >= ? and date <= ?;",
        (orgsite_id, min_date, max_date),
    ).fetchall()
    return [row[0] for row in rows if row[0]]


def db_fetch(
    conn_or_cursor,  #: sqlite3.Connection | sqlite3.Connection.cursor,
    select_statement: str,
    col_names: list[str] = None,
) -> list[DBRow]:
    """
    Fetch a select statement into a list of database rows.

    The col_names list converts the database column names into
    other names. E.g., ['fred', 'smorg'] will save the value of
    the first column in attribute 'fred' and the second in 'smorg'.
    """

    def flatten(raw_column_name: str) -> str:
        """Convert a string into a name usable as a class attribute."""
        usable = "".join(
            [c for c in raw_column_name.lower() if c.isalnum() or c == "_"]
        )
        if usable and usable[0].isdigit():
            usable = f"_{usable}"
        return usable

    # Determine if the input is a connection or a cursor
    if isinstance(conn_or_cursor, sqlite3.Connection):
        curs = conn_or_cursor.cursor()
        should_close_cursor = True
    else:
        curs = conn_or_cursor
        should_close_cursor = False

    # Execute the query and fetch all rows
    raw_rows = curs.execute(select_statement).fetchall()

    # Generate column names if not provided
    if col_names is None:
        col_names = [flatten(description[0]) for description in curs.description]

    # Close the cursor if it was created in this function
    if should_close_cursor:
        curs.close()

    # Create and return a list of DBRow objects
    rows = [DBRow(col_names, r) for r in raw_rows]
    return rows


# def db_fetch(
#     conn_or_cursor: sqlite3.Connection|sqlite3.Connection.cursor,
#     select_statement: str,
#     col_names: list[str] = None,
# ) -> list[DBRow]:
#     """Fetch a select statement into a list of database rows.

#     The col_names list converts the database column names into
#     other names. E.g. ['fred','smorg'] will save the value of
#     the first colun in attribute 'fred' and the 2nd in 'smorg'.
#     Not sure what happens when
#     the column name is something like 'count(tag)'

#     """

#     def flatten(raw_column_name: str) -> str:
#         """Convert str into a name usable as a class attribute."""

#         usable: str = "".join(
#             [c for c in raw_column_name.lower() if c.isalnum() or c == "_"]
#         )
#         if usable and usable[0].isdigit():
#             usable = f"_{usable}"
#         return usable

#     if isinstance(conn_or_cursor,sqlite3.Connection):
#         curs = conn_or_cursor.cursor()
#     else:
#         curs = conn_or_cursor

#     raw_rows = curs.execute(select_statement).fetchall()
#     # Make sure we have a list of the target names for the columns(attributes)
#     if not col_names:
#         col_names = [flatten(description[0]) for description in curs.description]

#     if isinstance(conn_or_cursor,sqlite3.Connection):
#         curs.close()


#     rows = [DBRow(col_names, r) for r in raw_rows]
#     return rows


def db_latest(ttdb: sqlite3.Connection) -> str:
    """Return str describing latest db update date/time."""

    latest_event = db_fetch(
        ttdb,
        """
        SELECT DAY.DATE || 'T' || MAX(MAX(TIME_IN), MAX(TIME_OUT))
            AS latest
        FROM VISIT,DAY
        WHERE VISIT.DAY_ID = DAY.ID
        GROUP BY DATE
        ORDER BY DATE DESC
        LIMIT 1;
        """,
    )[0].latest
    latest_load = db_fetch(
        ttdb,
        "SELECT MAX(BATCH) AS latest FROM  DAY",
    )[0].latest

    return f"Latest DB: load={latest_load}; event={latest_event}"


# def db_tags_contexts(ttdb: sqlite3.Connection, whatdate: str, day: TrackerDay):
#     """Fetch tags contexts from database into 'day' object."""

#     def string_to_frozenset(string) -> frozenset:
#         """Return a comma-separated str of TagID items as a frozenset of them."""
#         tags = string.split(",")  # Split the string into a list of items
#         return frozenset(
#             [TagID(t) for t in tags]
#         )  # Convert the list to a frozenset and return it

#     rows = db_fetch(
#         ttdb, f"SELECT regular,oversize,retired FROM taglist where date = '{whatdate}'"
#     )
#     # I expect one row back.
#     if not rows:
#         return
#     # print(f"{rows[0].retired=}")
#     day.regular = string_to_frozenset(rows[0].regular)
#     day.oversize = string_to_frozenset(rows[0].oversize)
#     day.retired = string_to_frozenset(rows[0].retired)


def fetch_day_totals(cursor: sqlite3.Cursor, day_id: int) -> DayTotals:
    """Fetch the full DayTotals -- essentially a single DAY row."""

    column_names = [
        "date",
        "time_open",
        "time_closed",
        "weekday",
        "num_parked_regular",
        "num_parked_oversize",
        "num_parked_combined",
        "num_remaining_regular",
        "num_remaining_oversize",
        "num_remaining_combined",
        "num_fullest_regular",
        "num_fullest_oversize",
        "num_fullest_combined",
        "time_fullest_regular",
        "time_fullest_oversize",
        "time_fullest_combined",
        "bikes_registered",
        "max_temperature",
        "precipitation",
    ]

    row = cursor.execute(
        f"SELECT {', '.join(column_names)} FROM day WHERE id = ?", (day_id,)
    ).fetchone()

    if not row:
        raise TagTrackerError(f"No day data for day_id={day_id}")

    # Horrifying dark magic to assign the db values to the DayTotals object
    totals = DayTotals(**dict(zip(column_names, row)))

    totals.time_open = VTime(totals.time_open)
    totals.time_closed = VTime(totals.time_closed)
    totals.time_fullest_regular = VTime(totals.time_fullest_regular)
    totals.time_fullest_oversize = VTime(totals.time_fullest_oversize)
    totals.time_fullest_combined = VTime(totals.time_fullest_combined)

    # FIXME (maybe) - this object does not have its site_handle or org_handle assigned

    return totals


def fetch_day_blocks(
    cursor: sqlite3.Connection.cursor, day_id: int
) -> dict[VTime, PeriodDetail]:
    """Fetch the full blocks dict for this day."""

    column_names = [
        "time_start",
        "num_incoming_regular",
        "num_incoming_oversize",
        "num_incoming_combined",
        "num_outgoing_regular",
        "num_outgoing_oversize",
        "num_outgoing_combined",
        "num_on_hand_regular",
        "num_on_hand_oversize",
        "num_on_hand_combined",
        "num_fullest_regular",
        "num_fullest_oversize",
        "num_fullest_combined",
        "time_fullest_regular",
        "time_fullest_oversize",
        "time_fullest_combined",
    ]

    rows = cursor.execute(
        f"SELECT {', '.join(column_names)} FROM block WHERE day_id = ?", (day_id,)
    ).fetchall()

    if not rows:
        raise TagTrackerError(f"No blocks data for day_id={day_id}")

    blocks = {}
    for row in rows:
        t = VTime(row[0])
        b = PeriodDetail(time_start=t)
        b.num_incoming[k.REGULAR] = row[1]
        b.num_incoming[k.OVERSIZE] = row[2]
        b.num_incoming[k.COMBINED] = row[3]

        b.num_outgoing[k.REGULAR] = row[4]
        b.num_outgoing[k.OVERSIZE] = row[5]
        b.num_outgoing[k.COMBINED] = row[6]

        b.num_on_hand[k.REGULAR] = row[7]
        b.num_on_hand[k.OVERSIZE] = row[8]
        b.num_on_hand[k.COMBINED] = row[9]

        b.num_fullest[k.REGULAR] = row[10]
        b.num_fullest[k.OVERSIZE] = row[11]
        b.num_fullest[k.COMBINED] = row[12]

        b.time_fullest[k.REGULAR] = VTime(row[13])
        b.time_fullest[k.OVERSIZE] = VTime(row[14])
        b.time_fullest[k.COMBINED] = VTime(row[15])

    return blocks


def fetch_day_summary(
    ttdb: sqlite3.Connection, whatdate: str, org_handle: str, site_handle: str
) -> DaySummary:
    """Recreate much of a DaySummary from the database.

    Does not recreate the moments of the day, just the DayTotals
    and the PeriodDetails (blocks{}).
    """

    curs = ttdb.cursor()

    day_id = fetch_day_id(
        cursor=curs,
        date=whatdate,
        maybe_org_handle=org_handle,
        maybe_site_handle=site_handle,
        null_ok=False,
    )
    if not day_id:
        print(f"No day_id matching {whatdate} {org_handle} {site_handle}")
        raise TagTrackerError("Unable to find day_id")

    day = DaySummary(whatdate)

    # Fetch the summary for this day
    day.whole_day = fetch_day_totals(cursor=curs, day_id=day_id)

    day.blocks = fetch_day_blocks(
        cursor=curs,
        day_id=day_id,
    )


def db2day(ttdb: sqlite3.Connection, day_id: int) -> TrackerDay:
    """Create one day's TrackerDay from the database."""
    # Do we have info about the day?  Need its open/close times
    curs = ttdb.cursor()
    row = curs.execute(
        "select date, time_open,time_closed,registrations "
        f"from day where day.id = {day_id}"
    ).fetchone()
    if not row:
        return None
    day = TrackerDay(filepath="")
    day.date = row[0]
    day.time_open = row[1]
    day.time_closed = row[2]
    day.registrations = row[3]

    # FIXME: does not set site_handle and site_name!!!

    # Fetch the visits, build the biketags from them
    rows = curs.execute(
        "select bike_id, time_in,time_out,bike_type from visit "
        "where day_id = ? order by time_in desc;",
        (day_id,),
    ).fetchall()
    curs.close()

    biketags: dict[VTime, BikeTag] = {}
    for row in rows:
        tagid = TagID(row[0])
        if row[3] == "R":
            bike_type = k.REGULAR
        elif row[3] == "O":
            bike_type = k.OVERSIZE
        else:
            bike_type = k.UNKNOWN
        if tagid in biketags:
            # FIXME: support a biketag with multiple bike_types
            if bike_type != biketags[tagid].bike_type:
                print(
                    f"FIXME: BikeTag {tagid} on {day_id=} has visits with different bike_type"
                )
        if tagid not in biketags:
            biketags[tagid] = BikeTag(tagid=tagid, bike_type=bike_type)
        visit = BikeVisit(tagid=tagid, time_in=row[1], time_out=row[2])
        biketags[tagid].visits.append(visit)
    # Set BikeTag's statuses (none will be RETIRED)
    for biketag in biketags.values():
        biketag: BikeTag
        if not biketag.visits:
            biketag.status = BikeTag.UNUSED
        elif biketag.visits[-1].time_out:
            biketag.status = BikeTag.DONE
        else:
            biketag.status = BikeTag.IN_USE

    day.determine_tagids_conformity()
    return day


@dataclass
class MultiDayTotals:
    """Summary data for multiple days."""

    total_parked_combined: int = 0
    total_parked_regular: int = 0
    total_parked_oversize: int = 0
    max_parked_combined: int = 0
    max_parked_combined_date: str = ""
    max_fullest_combined: int = 0
    max_fullest_combined_date: str = ""
    total_bikes_registered: int = 0
    max_bikes_registered: int = 0
    min_max_temperature: float = None
    max_max_temperature: float = None
    total_precipitation: float = 0
    max_precipitation: float = 0
    total_remaining_combined: int = 0
    max_remaining_combined: int = 0
    total_hours_open: float = 0
    total_days_open: int = 0
    total_visit_hours: float = 0
    visits_mean: str = ""
    visits_median: str = ""
    num_visit_modes_occurrences = 0
    visits_modes: list = field(default_factory=list)

    @staticmethod
    def fetch_from_db(
        conn: sqlite3.Connection,
        orgsite_id: int,
        start_date: str = "",
        end_date: str = "",
    ) -> "MultiDayTotals":

        start_date = start_date or "0000-00-00"
        end_date = end_date or "9999-99-99"

        totals = MultiDayTotals()

        # Query for combined aggregates from DAY
        query_combined = """
        SELECT
            SUM(num_parked_combined) AS total_parked_combined,
            SUM(num_parked_regular) AS total_parked_regular,
            SUM(num_parked_oversize) AS total_parked_oversize,
            SUM(bikes_registered) AS total_bikes_registered,
            MAX(bikes_registered) AS max_bikes_registered,
            MIN(max_temperature) AS min_max_temperature,
            MAX(max_temperature) AS max_max_temperature,
            SUM(precipitation) AS total_precipitation,
            MAX(precipitation) AS max_precipitation,
            SUM(num_remaining_combined) AS total_remaining_combined,
            MAX(num_remaining_combined) AS max_remaining_combined,
            SUM((julianday(time_closed) - julianday(time_open)) * 24) AS total_hours_open,
            COUNT(DISTINCT date) AS total_days_open
        FROM DAY
        WHERE orgsite_id = ? AND date BETWEEN ? AND ?;
        """

        # Query for max combined bikes
        query_max_combined_bikes = """
        SELECT
            num_parked_combined AS max_parked_combined,
            date AS max_parked_combined_date
        FROM DAY
        WHERE orgsite_id = ? AND date BETWEEN ? AND ?
        ORDER BY num_parked_combined DESC
        LIMIT 1;
        """

        # Query for max fullest combined
        query_max_fullest_combined = """
        SELECT
            num_fullest_combined AS max_fullest_combined,
            date AS max_fullest_combined_date
        FROM DAY
        WHERE orgsite_id = ? AND date BETWEEN ? AND ?
        ORDER BY num_fullest_combined DESC
        LIMIT 1;
        """

        # Query for total visit hours
        query_total_visit_hours = """
        SELECT
            SUM(duration) / 60.0 AS total_visit_hours
        FROM
            VISIT
        WHERE
            day_id IN (
                SELECT id FROM DAY
                WHERE orgsite_id = ?
                AND date BETWEEN ? AND ?
            );
        """

        # Query for individual visit durations
        query_visit_durations = """
        SELECT
            duration
        FROM
            VISIT
        WHERE
            day_id IN (
                SELECT id FROM DAY
                WHERE orgsite_id = ?
                AND date BETWEEN ? AND ?
            );
        """

        with conn:
            cursor = conn.cursor()

            # Execute combined query and set results to totals
            cursor.execute(query_combined, (orgsite_id, start_date, end_date))
            result = cursor.fetchone()
            (
                totals.total_parked_combined,
                totals.total_parked_regular,
                totals.total_parked_oversize,
                totals.total_bikes_registered,
                totals.max_bikes_registered,
                totals.min_max_temperature,
                totals.max_max_temperature,
                totals.total_precipitation,
                totals.max_precipitation,
                totals.total_remaining_combined,
                totals.max_remaining_combined,
                totals.total_hours_open,
                totals.total_days_open,
            ) = result

            # Execute max combined bikes query and set results to totals
            cursor.execute(query_max_combined_bikes, (orgsite_id, start_date, end_date))
            max_combined_bikes_result = cursor.fetchone()
            if max_combined_bikes_result:
                (
                    totals.max_parked_combined,
                    totals.max_parked_combined_date,
                ) = max_combined_bikes_result

            # Execute max fullest combined query and set results to totals
            cursor.execute(
                query_max_fullest_combined, (orgsite_id, start_date, end_date)
            )
            max_fullest_combined_result = cursor.fetchone()
            if max_fullest_combined_result:
                (
                    totals.max_fullest_combined,
                    totals.max_fullest_combined_date,
                ) = max_fullest_combined_result

            # Execute total visit hours query and set results to totals
            cursor.execute(query_total_visit_hours, (orgsite_id, start_date, end_date))
            total_visit_hours_result = cursor.fetchone()
            if total_visit_hours_result:
                totals.total_visit_hours = total_visit_hours_result[0]

            # Execute individual visit durations query and process results
            cursor.execute(query_visit_durations, (orgsite_id, start_date, end_date))
            visit_durations = [row[0] for row in cursor.fetchall()]

            # Calculate mean, median, and modes from visit_durations
            if visit_durations:
                totals.visits_mean = mean(visit_durations)
                totals.visits_median = median(visit_durations)
                totals.visits_modes, totals.num_visit_modes_occurrences = (
                    ut.calculate_visit_modes(visit_durations)
                )

        # Now 'totals' object has all the required data populated
        return totals


def db_connect(db_file) -> sqlite3.Connection:
    """Connect to (existing) SQLite database. Returns None if fails."""

    if not os.path.exists(db_file):
        print(f"Database file {db_file} not found")
        return None
    try:
        connection = sqlite3.connect(db_file)
        cursor = connection.cursor()
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
        cursor.close()
        if not tables:
            print(f"Database {db_file} is empty.")
            return None
    except (sqlite3.Error, sqlite3.DatabaseError) as sqlite_err:
        print(f"Sqlite ERROR: {sqlite_err}")
        return None

    return connection


def db_commit(db: sqlite3.Connection):
    """Just a database commit.  Only here for completeness."""
    db.commit()


def db_update(db: sqlite3.Connection, update_sql: str, commit: bool = True) -> bool:
    """Execute a SQL UPDATE statement.  T/F indicates success.

    (This could be any SQL statement, but the error checking and
    return is based on assumption it's an UPDATE)
    """
    try:
        db.cursor().execute(update_sql)
        if commit:
            db.commit()
    except (sqlite3.OperationalError, sqlite3.IntegrityError) as e:
        print(f"SQL error '{e}' for '{update_sql}'", file=sys.stdout)
        return False
    return True
