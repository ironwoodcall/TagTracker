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
from common.tt_trackerday import OldTrackerDay
from common.tt_tag import TagID
from common.tt_time import VTime


# FIXME Also make a class for BLOCK. And a routine to load them all from the DB
# for a given date & orgsite_id.

# FIXME use VisitDetail instead?
class VisitRow:
    def __init__(self):
        self.tag = TagID()
        self.time_in = VTime()
        self.time_out = VTime()
        self.duration = VTime()
        self.checked_out = False


# FIXME use DayDetail instead, or make a subclass of it. Or maybe not.
class DayRow:
    def __init__(self):
        self.date = ""
        self.parked_regular = 0
        self.parked_oversize = 0
        self.parked_total = 0
        self.leftover = 0
        self.max_reg = 0
        self.time_max_reg = 0
        self.max_over = 0
        self.time_max_over = VTime("")
        self.max_total = 0
        self.time_max_total = VTime("")
        self.time_open = VTime("")
        self.time_closed = VTime("")
        self.weekday = None
        self.precip_mm = None
        self.temp = None
        self.sunset = VTime("")
        self.event = ""
        self.event_prox_km = None
        self.registrations = None
        self.notes = ""
        self.batch = ""

    def set_row(self, labels: list[str], vals: Iterable):
        for i, name in enumerate(labels):
            vars(self)[name] = vals[i]


class DBRow:
    """A generic class for holding database rows.

    In use, pylint will not be aware of the names of the attributes
    since they are created dynamically.
    """

    def __init__(self, labels: list[str], vals: Iterable):
        for i, name in enumerate(labels):
            setattr(self, name, vals[i])


def db_fetch(
    ttdb: sqlite3.Connection,
    select_statement: str,
    col_names: list[str] = None,
) -> list[DBRow]:
    """Fetch a select statement into a list of database rows.

    The col_names list converts the database column names into
    other names. E.g. ['fred','smorg'] will save the value of
    the first colun in attribute 'fred' and the 2nd in 'smorg'.
    Not sure what happens when
    the column name is something like 'count(tag)'

    """

    def flatten(raw_column_name: str) -> str:
        """Convert str into a name usable as a class attribute."""

        usable: str = "".join(
            [c for c in raw_column_name.lower() if c.isalnum() or c == "_"]
        )
        if usable and usable[0].isdigit():
            usable = f"_{usable}"
        return usable

    curs = ttdb.cursor()
    raw_rows = curs.execute(select_statement).fetchall()
    # Make sure we have a list of the target names for the columns(attributes)
    if not col_names:
        col_names = [flatten(description[0]) for description in curs.description]

    rows = [DBRow(col_names, r) for r in raw_rows]
    return rows


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


def db_tags_contexts( ttdb: sqlite3.Connection, whatdate: str, day:OldTrackerDay):
    """Fetch tags contexts from database into 'day' object."""

    def string_to_frozenset(string) -> frozenset:
        """Return a comma-separated str of TagID items as a frozenset of them."""
        tags = string.split(',')  # Split the string into a list of items
        return frozenset([TagID(t) for t in tags])   # Convert the list to a frozenset and return it

    rows = db_fetch(ttdb,
        f"SELECT regular,oversize,retired FROM taglist where date = '{whatdate}'"
    )
    # I expect one row back.
    if not rows:
        return
    # print(f"{rows[0].retired=}")
    day.regular = string_to_frozenset(rows[0].regular)
    day.oversize = string_to_frozenset(rows[0].oversize)
    day.retired = string_to_frozenset(rows[0].retired)

    # print(f"<pre>{day.regular=}</br>{day.oversize=}<br>{day.retired=}<br></pre>")

def db2day(ttdb: sqlite3.Connection, whatdate: str) -> OldTrackerDay:
    """Create one day's OldTrackerDay from the database."""
    # Do we have info about the day?  Need its open/close times
    curs = ttdb.cursor()
    rows = curs.execute(f"select time_open,time_closed,registrations from day where day.date = '{whatdate}'").fetchall()
    if not rows:
        return None
    day = OldTrackerDay()
    day.date = whatdate
    day.time_open = rows[0][0]
    day.time_closed = rows[0][1]
    day.registrations = rows[0][2]
    # Fetch any tags checked in or out
    curs = ttdb.cursor()
    rows = curs.execute(
        "select tag,time_in,time_out,type from visit "
        f"where date = '{whatdate}' "
        "order by time_in desc;"
    ).fetchall()
    oversize = set()
    regular = set()
    for row in rows:
        tag = TagID(row[0])
        time_in = VTime(row[1])
        time_out = VTime(row[2])

        still_in = not time_out
        if not tag or not time_in:
            continue
        day.bikes_in[tag] = time_in
        if time_out and not still_in:
            day.bikes_out[tag] = time_out
        # Tag type (regular/oversize)
        tag_type = row[3] if row[3] else day.guess_tag_type(tag)
        if tag_type == "R":
            regular.add(tag)
        elif tag_type == "O":
            oversize.add(tag)
    # Set the tag lists
    db_tags_contexts(ttdb,whatdate,day)
    if not day.regular:
        day.regular = frozenset(regular)
    if not day.oversize:
        day.oversize = frozenset(oversize)
    # Fake up a colour dictionary
    day.fill_colour_dict_gaps()
    return day


def db_connect(db_file) -> sqlite3.Connection:
    """Connect to (existing) SQLite database. Returns None if fails."""

    if not os.path.exists(db_file):
        print(f"Database file {db_file} not found")
        return None
    try:
        connection = sqlite3.connect(db_file)
        cursor = connection.cursor()
        tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
        cursor.close()
        if not tables:
            print(f"Database {db_file} is empty.")
            return None
    except (sqlite3.Error,sqlite3.DatabaseError)  as sqlite_err:
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
