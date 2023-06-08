"""Database updater for TagTracker suite.

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


import glob
import re
import sys
import os
import sqlite3
import calendar
from typing import Union  # for type hints instead of (eg) int|str

import tt_conf as cfg
import tt_util as ut
import tt_datafile as df
import tt_globals as tg
import tt_event as ev


# Path for the database to be put into
DB_FILEPATH = os.path.join(cfg.DATA_FOLDER, r"test_database.db")

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
    """Create the table TABLE_VISITS if it doesn't exist yet."""
    if conn:
        try: #FIXME: try to add each column individually if it doesn't exist?
            # that way can update DB with new columns in future which will
            # probably be needed - likely more important for TABLE_DAYS
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
            print('sqlite ERROR in create_visits_table() -- ', sqlite_err)
    else:
        print("Error trying to create_visits_table(): no database connection")

def create_days_table() -> None:
    """Create the table TABLE_DAYS if it doesn't exist yet."""
    if conn:
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
            print('sqlite ERROR in create_days_table() -- ', sqlite_err)
    else:
        print("Error trying to create_days_table(): no database connection")

def duration(hhmm_in:str, hhmm_out:str) -> str:
    """Calculate a str duration from a str time in and out."""
    t_in = ut.time_int(hhmm_in)
    t_out = ut.time_int(hhmm_out)
    t_stay = t_out - t_in
    hhmm_stay = ut.time_str(t_stay)

    return hhmm_stay

def data_to_db(filename:str) -> None:
    """Record one datafile to the database.
    
    Read the datafile in question into a TrackerDay object with 
    df.read_datafile()
    
    For the day, insert a row of day summary data into TABLE_DAYS

    Then calculate some things which might be based on it
    For each bike, record a row of visit data into TABLE_VISITS
    """

    def what_bike_type(tag:str) -> Union[str,None]:
        """Return the type 'Normal' or 'Oversize' of a tag.
        Based on each day's datafile"""
        if tag in regular_tags:
            return 'Regular'
        elif tag in oversize_tags:
            return 'Oversize'
        else:
            print(f" Bike type parsing problem for {tag}")
            return None

    def weekday(date_str):
        """Return int 0-6 day of the week; Mon-Sun."""
        date_bits = re.match(tg.DATE_FULL_RE, date_str)
        year =  int(date_bits.group(1))
        month = int(date_bits.group(2))
        day =   int(date_bits.group(3))
        weekday = calendar.weekday(year, month, day)
        return weekday

    print(f"\nWorking on {filename}...")
    data = df.read_datafile(f"{filename}", err_msgs=[])

    if data.regular and data.oversize:
        print(" Tags: datafile tag lists loaded")
        regular_tags = data.regular
        oversize_tags = data.oversize
    else: # read tags.txt only if necessary
        print(f" Tags: using {cfg.TAG_CONFIG_FILE} as no tag info in datafile")
        tags_data = df.read_datafile(cfg.TAG_CONFIG_FILE, err_msgs=[])
        regular_tags = tags_data.regular
        oversize_tags = tags_data.oversize

    date = data.date
    if not date: # get from filename for old data formats
        date = re.search(DATE_RE, filename).group(0)
    # TABLE_DAYS handling
    # simple counts
    regular_parked = 0
    oversize_parked = 0
    for tag in data.bikes_in.keys():
        bike_type = what_bike_type(tag)
        if bike_type == 'Regular':
            regular_parked += 1
        elif bike_type == 'Oversize':
            oversize_parked += 1
    total_parked = regular_parked + oversize_parked
    total_leftover = len(data.bikes_in) - len(data.bikes_out)
    if total_leftover < 0:
        print(f"**WEIRD: negative leftovers calculated for {filename}")
    # highwater values
    events = ev.calc_events(data)
    max_regular_num = max([x.num_here_regular for x in events.values()])
    max_oversize_num = max([x.num_here_oversize for x in events.values()])
    max_total_num = max([x.num_here_total for x in events.values()])
    max_regular_time = None
    max_oversize_time = None
    max_total_time = None
    # Find the first time at which these took place
    for atime in sorted(events.keys()):
        if (events[atime].num_here_regular >= max_regular_num
                and not max_regular_time):
            max_regular_time = atime
        if (events[atime].num_here_oversize >= max_oversize_num
            and not max_oversize_time):
            max_oversize_time = atime
        if (events[atime].num_here_total >= max_total_num
                and not max_total_time):
            max_total_time = atime
    # open and close times
    if data.opening_time and data.closing_time:
        time_open = data.opening_time
        time_close = data.closing_time
    else: # guess with bike check-ins
        time_open = data.earliest_event()
        time_close = data.latest_event()
    # int day of week
    weekday = weekday(date)

    cmd_day_insert = f"""INSERT INTO {TABLE_DAYS} (
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
                    {COL_DAY_OF_WEEK}
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
                    {weekday}
                    );"""
    sql_do(f"DELETE FROM {TABLE_DAYS} WHERE date = '{date}';")
    sql_do(cmd_day_insert)

    # TABLE_VISITS handling
    if not data.bikes_in:
        print(f" No visits in {filename}")
        return None # if no visits to record, stop now

    closing = select_closing_time(date) # fetch checkout time for whole day
    sql_do(f"DELETE FROM {TABLE_VISITS} WHERE date = '{date}';")
    for tag, time in data.bikes_in.items():
        tag_name = tag
        time_in = time
        if tag_name in data.bikes_out.keys():
            time_out = data.bikes_out[tag]
            leftover = 'No'
        else: # no check-out recorded
            if closing:
                print(f" Leftover: using closing time {closing} recorded in "
                        f"'{TABLE_DAYS}' tabl for {tag}")
                time_out = closing
            else:
                print(f" Leftover: using latest event time for {tag}")
                time_out = data.latest_event() # approx. as = to last event
            leftover = "Yes"
        time_stay = duration(time_in, time_out)
        cmd_visit_insert = f"""INSERT INTO {TABLE_VISITS} (
                        {COL_ID},
                        {COL_DATE},
                        {COL_TAG},
                        {COL_BIKETYPE},
                        {COL_TIME_IN},
                        {COL_TIME_OUT},
                        {COL_DURATION},
                        {COL_LEFTOVER},
                        {COL_BATCH}
                        ) VALUES (
                        '{date}.{tag}',
                        '{date}',
                        '{tag}',
                        '{what_bike_type(tag)}',
                        '{time_in}',
                        '{time_out}',
                        '{time_stay}',
                        '{leftover}',
                        '{batch}');"""
        sql_do(cmd_visit_insert) # no notes added at this stage
    try:
        conn.commit() # commit one datafile transaction
        print(" Committed!")
    except sqlite3.Error as sqlite_err:
        print(f"ERR: SQL error trying to commit {filename} - {sqlite_err}")


def select_closing_time(date:str) -> Union[ut.Time, bool]:
    """Return the closing time of a given date in TABLE_DAYS.
    
    - SELECT closing time from rows with matching dates (should be just 1)
    - If this yields no rows, return False.
    - If this yields 1 row, return the closing time as a str HHMM.
    - If this yields >1 row, raise error that the day has multiple records
    (shouldn't happen b/c of UNIQUE constraint on the date row, but in case)"""
    curs = conn.cursor()
    rows = curs.execute(
        f"SELECT {COL_TIME_CLOSE} FROM {TABLE_DAYS} "
        f"WHERE {COL_DATE} == '{date}'"
        ).fetchall()
    num_rows = len(rows)
    if num_rows == 0:
        return False # will now use last event instead
    elif num_rows == 1:
        return rows[0][0] # needs double subscript apparently
    else:
        print(f" Database error: finding closing time on '{date}' in table "
              "'{TABLE_DAYS}' returned multiple rows -- duplicate records?")
        return False

def sql_do(sql_statement:str) -> None:
    """Execute a SQL statement, or print the slite3 error."""
    try:
        curs = conn.cursor()
        curs.execute(sql_statement)
    except sqlite3.Error as sqlite_err:
        print("sqlite ERROR using sql_do() -- ", sqlite_err)

if __name__ == "__main__":
    conn = create_connection(DB_FILEPATH)

    create_visits_table() # if none yet exists
    create_days_table() # if none yet exists

    batch = f"{ut.get_date()}-{ut.get_time()}"
    print(f"Batch / current time: '{batch}'")
    in_files = sys.argv[1:]
    if in_files:
        datafiles = in_files
    else: # if no filenames passed, grab everything in /data
        datafiles = [f"{cfg.DATA_FOLDER}/{filename}" for filename
                    in glob.glob('*.dat', root_dir=cfg.DATA_FOLDER)
                    if re.match(DATAFILE_RE, filename)]

    for datafilename in datafiles:
        data_to_db(datafilename)

    conn.close()

    print("\n\n\n")
    print(f"Processed {len(datafiles)} datafiles.")
    input("Press [Enter] to exit.")

#pylint: disable = pointless-string-statement
'''
Add checks for integrity - DB and datafiles(?)
- missing dates
- new data incoming that has many fewer records than what is already there
- unusual open/close times (which might indicate sloppy operators, 
or a corrupt file)
--- flag guessed open close times?
- days with identical data
- days with more than x bikes left at the end of the data entries
'''