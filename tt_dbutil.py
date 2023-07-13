"""Database utilities for reporting from TagTracker database."""

import sqlite3
import sys
from typing import Tuple, Iterable
from tt_trackerday import TrackerDay
from tt_tag import TagID
from tt_time import VTime


class VisitRow:
    def __init__(self):
        self.tag = TagID()
        self.time_in = VTime()
        self.time_out = VTime()
        self.duration = VTime()
        self.checked_out = False


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
        self.temp_10am = None
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
            vars(self)[name] = vals[i]


def db_fetch(
    ttdb: sqlite3.Connection,
    select_statement: str,
    col_names: list[str] = None,
) -> list[DBRow]:
    """Fetch a select statement into a list of database rows.

    The col_names dict converts the database column names into
    other names. E.g. {'fred':'derf'} will convert any column
    returned from the SELECT that is called 'fred' into a
    DBRow attribute called 'derf'.  Not sure what happens when
    the column name is something like 'count(tag)'

    """

    def flatten(raw_column_name: str) -> str:
        """Convert str into a name usable as a class attribute."""

        usable: str = "".join([
            c for c in raw_column_name.lower() if c.isalnum() or c == "_"
        ])
        if usable and usable[0].isdigit():
            usable = f"_{usable}"
        return usable

    curs = ttdb.cursor()
    raw_rows = curs.execute(select_statement).fetchall()
    # Make sure we have a list of the target names for the columns(attributes)
    if not col_names:
        col_names = [
            flatten(description[0]) for description in curs.description
        ]

    rows = [DBRow(col_names, r) for r in raw_rows]
    return rows


def db_latest(
    ttdb: sqlite3.Connection, whatday: str = ""
) -> Tuple[str, VTime]:
    """Return (date,time) of latest event in database.

    If whatday is not null, return for that day, otherwise overall.
    """

    def one_col_max(db: sqlite3.Connection, inout: str, thisday: str) -> VTime:
        """Get the max time value of one column."""
        rows = (
            db.cursor()
            .execute(
                f"select max({inout}) from visit where date = '{thisday}'"
            )
            .fetchall()
        )
        if not rows:
            return VTime()
        return VTime(rows[0][0])

    # Determine the latest date unless one provided
    if not whatday:
        rows = (
            ttdb.cursor()
            .execute("select date from visit order by date desc limit 1")
            .fetchall()
        )
        if not rows:
            return ("", "")
        whatday = rows[0][0]
    # Determine the latest time on the given date.
    latest_time = VTime(
        max(
            one_col_max(ttdb, "time_in", whatday),
            one_col_max(ttdb, "time_out", whatday),
        )
    )
    return (whatday, latest_time)


def db_latest_date(ttdb: sqlite3.Connection) -> str:
    """Fetch the last date for which there is info in the database."""
    return db_latest(ttdb)[0]


def db_latest_time(ttdb: sqlite3.Connection, whatday: str) -> VTime:
    """Get latest time in db for a particular day."""
    return db_latest(ttdb, whatday=whatday)[1]


def db2day(ttdb: sqlite3.Connection, whatdate: str) -> TrackerDay:
    """Create one day's TrackerDay from the database."""
    # Do we have info about the day?  Need its open/close times
    curs = ttdb.cursor()
    rows = curs.execute(
        "select time_open,time_closed from day limit 1"
    ).fetchall()
    if not rows:
        return None
    day = TrackerDay()
    day.date = whatdate
    day.opening_time = rows[0][0]
    day.closing_time = rows[0][1]
    # Fetch any tags checked in or out
    curs = ttdb.cursor()
    rows = curs.execute(
        "select tag,time_in,time_out from visit "
        f"where date = '{whatdate}' "
        "order by time_in desc;"
    ).fetchall()
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
    # Fake up regular/oversize lists
    day.make_fake_tag_lists()
    # Fake up a colour dictionary
    day.make_fake_colour_dict()
    return day


def create_connection(db_file) -> sqlite3.Connection:
    """Create a database connection to a SQLite database.

    This will create a new .db database file if none yet exists at the named
    path."""
    connection = None
    try:
        connection = sqlite3.connect(db_file)
        ##print(sqlite3.version)
    except sqlite3.Error as sqlite_err:
        print("sqlite ERROR in create_connection() -- ", sqlite_err)
    return connection

def db_commit(db:sqlite3.Connection):
    """Just a database commit.  Only here for completeness."""
    db.commit()

def db_update(db:sqlite3.Connection,update_sql:str,commit:bool=True) -> bool:
    """Execute a SQL UPDATE statement.  T/F indicates success.

    (This could be any SQL statement, but the error checking and
    return is based on assumption it's an UPDATE)
    """
    try:
        db.cursor().execute(update_sql)
        if commit:
            db.commit()
    except (sqlite3.OperationalError,sqlite3.IntegrityError) as e:
        print(f"SQL error '{e}' for '{update_sql}'",file=sys.stdout)
        return False
    return True

