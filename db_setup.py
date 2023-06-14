"""TagTracker by Julias Hocking.

SQL table names and script for creating db and tables.

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

import os
import re
import sqlite3

import tt_conf as cfg

# Path for the database to be put into
DB_FILEPATH = os.path.join(cfg.REPORTS_FOLDER, cfg.DB_FILENAME)

# regex for retrieving date from filename if it isn't explicit (older files)
DATE_RE = r"2[0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]"

# Regex for recognizing datafile names
DATAFILE_RE = re.compile(f"({cfg.DATA_BASENAME})*"
                         r"[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]\.dat$")

# Names for tables and columns.
# Table of individual bike visits
TABLE_VISITS = "visit"
COL_ID = "id" # text date.tag PK
COL_DATE = "date"
COL_TAG = "tag"
COL_BIKETYPE = "type"
COL_TIME_IN = "time_in"
COL_TIME_OUT = "time_out"
COL_DURATION = "duration"
COL_BATCH = "batch"
COL_LEFTOVER = "leftover"
COL_NOTES = "notes"

# Table of day summaries
TABLE_DAYS = "day"
#COL_DATE name reused - text date PK
COL_REGULAR = "parked_regular" # int count
COL_OVERSIZE = "parked_oversize" # int count
COL_TOTAL = "parked_total" # int sum of 2 above
COL_TOTAL_LEFTOVER = "bikes_leftover" # int count
COL_MAX_REGULAR = "max_reg" # int count of max regular bikes
COL_MAX_REGULAR_TIME = "time_max_reg" # HHMM time
COL_MAX_OVERSIZE = "max_over" # int count of max oversize bikes
COL_MAX_OVERSIZE_TIME = "time_max_over" # HHMM time
COL_MAX_TOTAL = "max_total" # int sum of 2 above
COL_MAX_TOTAL_TIME = "time_max_total" # HHMM
COL_TIME_OPEN = "opened" # HHMM opening time
COL_TIME_CLOSE = "closed" # HHMM closing time
COL_DAY_OF_WEEK = "weekday_Mon_Sun" # 0-6 day of the week
COL_PERCIP_MM = "precip" # mm precipitation - prob bulk from Env. Can. data
COL_TEMP_10AM = "temp_10am" # temp at 10AM - same
COL_SUNSET = "sunset" # HHMM time at sunset - same
COL_EVENT = "event" # text NULL or short name of event happening nearby
COL_EVENT_PROX = "event_prox_km" # est. num of km to event
COL_REGISTRATIONS = "registrations" # num of 529 registrations recorded
#COL_NOTES name reused

def create_connection(db_file) -> sqlite3.Connection:
    """Create a database connection to a SQLite database.
    
    This will create a new .db database file if none yet exists at the named
    path."""
    connection = None
    try:
        connection = sqlite3.connect(db_file)
        print(sqlite3.version)
    except sqlite3.Error as sqlite_err:
        print("sqlite ERROR in create_connection() -- ", sqlite_err)
    return connection

def create_visits_table() -> None:
    """Create table for individual visit data."""
    try:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE_VISITS} (
                    {COL_ID}            TEXT PRIMARY_KEY UNIQUE,
                    {COL_DATE}          TEXT NOT NULL,
                    {COL_TAG}           TEXT NOT NULL,
                    {COL_BIKETYPE}      TEXT NOT NULL,
                    {COL_TIME_IN}       TEXT NOT NULL,
                    {COL_TIME_OUT}      TEXT,
                    {COL_DURATION}      TEXT,
                    {COL_LEFTOVER}      TEXT,
                    {COL_NOTES}         TEXT,
                    {COL_BATCH}         TEXT NOT NULL);""")
    except sqlite3.Error as sqlite_err:
        print('sqlite ERROR in while creating {TABLE_DAYS}: ', sqlite_err)

def create_days_table() -> None:
    """Create table for daily summaries of visit data."""
    try:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE_DAYS} (
                    {COL_DATE}              TEXT PRIMARY_KEY UNIQUE,
                    {COL_REGULAR}           INTEGER,
                    {COL_OVERSIZE}          INTEGER,
                    {COL_TOTAL}             INTEGER,
                    {COL_TOTAL_LEFTOVER}    INTEGER,
                    {COL_MAX_REGULAR}       INTEGER,
                    {COL_MAX_REGULAR_TIME}  TEXT,
                    {COL_MAX_OVERSIZE}      INTEGER,
                    {COL_MAX_OVERSIZE_TIME} TEXT,
                    {COL_MAX_TOTAL}         INTEGER,
                    {COL_MAX_TOTAL_TIME}    TEXT,
                    {COL_TIME_OPEN}         TEXT,
                    {COL_TIME_CLOSE}        TEXT,
                    {COL_DAY_OF_WEEK}       INTEGER NOT NULL,
                    {COL_PERCIP_MM}         NUMERIC,
                    {COL_TEMP_10AM}         NUMERIC,
                    {COL_SUNSET}            TEXT,
                    {COL_EVENT}             TEXT,
                    {COL_EVENT_PROX}        NUMERIC,
                    {COL_REGISTRATIONS}     NUMERIC,
                    {COL_NOTES}             TEXT);""")
    except sqlite3.Error as sqlite_err:
        print(f"sqlite ERROR while creating {TABLE_DAYS} table: ", sqlite_err)

if __name__ == "__main__":
    conn = create_connection(DB_FILEPATH)
    if conn:
        create_visits_table()
        create_days_table()
    else:
        print("Error trying to create tables - no database connection made")
