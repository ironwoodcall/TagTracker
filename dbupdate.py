#!/bin/env python3
"""Update existing records in TagTraker database.

Reads info from day-end-form (csv) or from other
sources (e.g. weather info from NRCan? tbd)


dbupdate.py [--all | --empty --date DATE] [--day-end FILE] database_file
"""


import argparse
import csv
import datetime
import os
import sys
import sqlite3

import tt_dbutil as db
import tt_util as ut
from tt_time import VTime


class NewVals:
    """This tiny class is just for olding data from new source.

    NRCan will use some fields, day-end-form may use some fields.
    """

    def __init__(
        self,
        registrations: int = None,
        abandoned: int = None,
        precip: float = None,
        temp: float = None,
        max_temp: float = None,
        min_temp: float = None,
        mean_temp:float = None,
        rainfall: float = None,
        sunset:str = None,
    ) -> None:
        self.registrations = registrations
        self.abandoned = abandoned
        self.precip = precip
        self.temp = temp
        self.max_temp = max_temp
        self.min_temp = min_temp
        self.mean_temp = mean_temp
        self.rainfall = rainfall
        self.sunset = sunset

    def dump(self):
        return f"{self.registrations=}; {self.abandoned=}; {self.precip=}; {self.temp=}"

def oneval(
    thisrow: list,
    field: int,
    want_num: bool = False,
    want_int: bool = False,
) -> str | int | float | None:
    """Get item field from thisrow."""
    myval = (thisrow + [""] * 20)[field]
    if want_int:
        if myval.isdigit():
            return int(myval)
        else:
            return None
    if want_num:
        try:
            return float(myval)
        except ValueError:
            return None
    return myval

def read_day_end_vals(
    day_end_csv: str,
) -> dict[str, NewVals]:
    """Get data from day end form google sheet csv file.

    Sample lines:
        "Timestamp","Email Address","What Day?","Staff Name (who is filling this out)","Day","Opening Time","Closing Time","Bike Parking Time Average (Mean)","Regular Bikes Parked","Oversized Bikes Parked","Total Bikes Parked (Manual Count)","What cool, interesting, or weird things did you park today?","Project 529 Registrations Today","Weather description","Precipitation (https://www.victoriaweather.ca/datatime.php?field=raintotal&interval=1440&year=2022&month=7&day=20)","Temperature (#)","Day End Checklist: make sure to complete all tasks","How many abandoned bikes were there left? (#)","Notes, feedback, suggestions, comments?","Bike Parking Time (Median)","Bike Parking Time (Mode)","AM Bikes (#)","PM Bikes (#)","Stays under 1.5 Hours (#)","Stays between 1.5 and 5 hours (#)","Stays over 5 hours (#)","Maximum Time Parked","Minimum Time Parked","Total Tags Tracked (AM+PM bikes)","Precipitation (https://www.victoriaweather.ca/datatime.php?field=raintotal&interval=1440&year=2022&month=7&day=20)"
        "3/27/2023 17:52:42","","3/27/2023","todd","Monday","7:30:00 AM","6:00:00 PM","5:00:00","51","41","92","","4","clear light wind","0","11","Sandwich boards collected, Inventory completed, Abandoned bikes photographed and locked (if any), Abandoned bikes photos sent to coordinator (if any)","0","","4:00:00","3:00:00","56","30","0","67","23","10:30:00","0:30:00","86","","","","","","","",""
    Items of potential interest (0-based counting)
        0: m/d/yyyy hh:mm:ss timestamp
        2: m/dd/yyyy datestamp indicating date for the data <-- prone to error
        12: 529 registrations
        13: weather description
        14: precip (from https://www.victoriaweather.ca/datatime.php?field=raintotal&interval=1440&year=2022&month=7&day=20)
        15: temp (manually entered)
        17: abandoned bikes

    """

    def mdy2ymd(maybedate: str) -> str:
        """Convert "m/d/y h:m:s" string to ISO YYYY-MM-DD string (or "")."""
        datepart = (maybedate.split() + [""])[0]
        try:
            newdate = datetime.datetime.strptime(datepart, "%m/%d/%Y")
        except ValueError:
            return ""
        return newdate.strftime("%Y-%m-%d")

    results = {}
    with open(day_end_csv, "r", newline="", encoding="utf-8") as csvfile:
        dereader = csv.reader(csvfile)
        for row in dereader:
            thisdate = mdy2ymd(row[0])
            if not thisdate:
                continue
            results[thisdate] = NewVals(
                registrations=oneval(row, 12, want_int=True),
                abandoned=oneval(row, 17, want_int=True),
                precip=oneval(row, 14, want_num=True),
                temp=oneval(row, 15, want_num=True),
            )
    return results


def get_day_end_changes(
    ttdb:sqlite3.Connection,
    day_end_file: str,
    force: bool,
    onedate: str,
) -> list[str]:
    """Get SQL statements of changes from day end form source."""

    where = f" where date = '{onedate}' " if onedate else ""
    db_data = db.db_fetch(
        ttdb,
        "select "
        "   date, registrations, leftover, precip_mm, temp_10am "
        "from day "
        f"{where}"
        "order by date",
    )
    if not db_data:
        return []

    new = read_day_end_vals(day_end_file)
    sqls = []
    for existing in db_data:
        if onedate and onedate != existing.date:
            continue

        if (
            (force or existing.registrations is None)
            and existing.date in new
            and new[existing.date].registrations is not None
        ):
            sqls.append(
                f"update day set registrations = {new[existing.date].registrations} where date = '{existing.date}';"
            )
        if (
            (force or existing.leftover is None)
            and existing.date in new
            and new[existing.date].abandoned is not None
        ):
            sqls.append(
                f"update day set leftover = {new[existing.date].abandoned} where date = '{existing.date}';"
            )
    return sqls


def read_wx_data(source_csv: str) -> dict[str, NewVals]:
    """Get weather data from NRCan data file for given range of dates.

    https://api.weather.gc.ca/collections/climate-daily/items?datetime=2023-01-01%2000:00:00/2023-07-09%2000:00:00&STN_ID=51337&sortby=PROVINCE_CODE,STN_ID,LOCAL_DATE&f=csv&limit=150000&startindex=0
    7,8,9: y,m,d
    10 - mean temp
    12 - min temp
    14 - max temp
    16 - total precip
    18 - total rainfall
    30 - heating degree days"""


    results = {}
    with open(source_csv, "r", newline="", encoding="utf-8") as csvfile:
        for row in csv.reader(csvfile):
            maybedate = f"{row[7]}-{('0'+row[8])[-2:]}-{('0'+row[9])[-2:]}"
            thisdate = ut.date_str(maybedate)
            if not thisdate:
                continue
            results[thisdate] = NewVals(
                precip=oneval(row, 16, want_num=True),
                temp=oneval(row, 14, want_num=True),    # max
                min_temp=oneval(row,12,want_num=True),
                max_temp=oneval(row,14,want_num=True),
                mean_temp=oneval(row,10,want_num=True),
            )
    return results


def get_wx_changes(
    ttdb:sqlite3.Connection,
    source_csv: str,
    force: str,
    onedate: str,
) -> list[str]:
    """Get SQL statements of changes from NRCan source."""

    where = f" where date = '{onedate}' " if onedate else ""
    db_data = db.db_fetch(
        ttdb,
        "select "
        "   date, registrations, leftover, precip_mm, temp_10am "
        "from day "
        f"{where}"
        "order by date",
    )
    if not db_data:
        return []

    new = read_wx_data(source_csv)

    sqls = []
    for existing in db_data:
        if onedate and onedate != existing.date:
            continue

        if (
            (force or existing.precip_mm is None)
            and existing.date in new
            and new[existing.date].precip is not None
        ):
            sqls.append(
                f"update day set precip_mm = {new[existing.date].precip} where date = '{existing.date}';"
            )
        if (
            (force or not existing.temp_10am)
            and existing.date in new
            and new[existing.date].temp is not None
        ):
            sqls.append(
                f"update day set temp_10am = {new[existing.date].temp} where date = '{existing.date}';"
            )
    return sqls
#-------------------
def read_sun_data(source_csv: str) -> dict[str, NewVals]:
    """Get sunset data from NRCan data file for given range of dates.

    Using whole-year text file produced from solar calculator at
    https://nrc.canada.ca/en/research-development/products-services/software-applications/sun-calculator/

    Fields of interest:
        0: Data as "Mmm D YYYY"
        5: sunset
        6: civilian twilight
        7: nautical twilight

    """

    MONTHS={'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
            'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}

    results = {}
    with open(source_csv, "r", newline="", encoding="utf-8") as csvfile:
        for row in csv.reader(csvfile):
            if not row or not row[0]:
                if args.verbose:
                    print(f"discarding sun csv row {row}")
                    continue
            # Break first element into date elements
            datebits = row[0].split()
            if len(datebits) != 3:
                if args.verbose:
                    print(f"discarding bad date in sun csv row {row}")
                    continue
            maybedate = f"{datebits[2]}-{MONTHS[datebits[0]]}-{('0'+datebits[1])[-2:]}"
            thisdate = ut.date_str(maybedate)
            if not thisdate:
                continue
            if args.verbose:
                print(f"have date: {thisdate}")
            results[thisdate] = NewVals(
                sunset=VTime(oneval(row, 6)),
            )
        if args.verbose:
            [print(f"{d}: {s.sunset}") for d,s in results.items()]
    return results


def get_sun_changes(
    ttdb:sqlite3.Connection,
    source_csv: str,
    force: str,
    onedate: str,
) -> list[str]:
    """Get SQL statements of changes from NRCan source."""

    where = f" where date = '{onedate}' " if onedate else ""
    db_data = db.db_fetch(
        ttdb,
        "select "
        "   date, sunset "
        "from day "
        f"{where}"
        "order by date",
    )
    if not db_data:
        return []
    if args.verbose:
        for row in db_data:
            print(f"{row.date=};{row.sunset=}")
    new = read_sun_data(source_csv)

    sqls = []
    for existing in db_data:
        if onedate and onedate != existing.date:
            continue

        if (
            (force or existing.sunset is None)
            and existing.date in new
            and new[existing.date].sunset is not None
        ):
            sqls.append(
                f"update day set sunset = '{new[existing.date].sunset}' where date = '{existing.date}';"
            )
    return sqls


#-------------------

class ProgArgs:
    """Program arguments.

    Attributes:
        database_file: filename of the database
        target_rows: EMPTY, ALL or ONEDATE
        onedate: a valid date string or "" (only if ONEDATE)
        weather_csv: filename of WEATHER csv file (if any, else "")
        day_end_csv: filename of DAY END csv file (if any, else "")
    """

    def __init__(self):
        """Get all the program arguments."""
        progargs = self._parse_args()
        self.verbose = progargs.verbose
        self.database_file = progargs.database_file
        self.day_end = progargs.day_end
        self.force = progargs.force
        self.onedate = ""
        if progargs.date:
            #self.target_rows = ONEDATE
            self.onedate = ut.date_str(progargs.date)
            if not self.onedate:
                print(
                    "DATE must be YYYY-MM-DD, 'today' or 'yesterday'",
                    file=sys.stderr,
                )
                sys.exit(1)
        #elif args.all:
        #    self.target_rows = ALL
        #elif args.empty:
        #    self.target_rows = EMPTY
        self.weather_csv = progargs.weather if progargs.weather else ""
        self.sun_csv = progargs.sun if progargs.sun else ""
        self.day_end_csv = progargs.day_end if progargs.day_end else ""
        #if not self.target_rows:
        #    print(
        #        "Unknown args supporting which rows to update",
        #        file=sys.stderr,
        #    )
        #    sys.exit(1)
        if not self.weather_csv and not self.day_end_csv and not self.sun_csv:
            print(
                "Must specify at least one of --weather --sun --day-end",
                file=sys.stderr,
            )
            sys.exit(1)

    def dump(self):
        """Print the contents of the object."""
        print(f"{self.weather_csv=}; {self.day_end_csv=}")
        print(f"{self.force=}; {self.onedate=}")
        print(f"{self.database_file=}")

    @staticmethod
    def _parse_args() -> argparse.Namespace:
        """Collect command args into an argparse.Namespace."""
        parser = argparse.ArgumentParser(
            description="Update TagTracker database DAY table from non-TagTracker sources",
            epilog="",
        )
        parser.add_argument(
            "database_file",
            metavar="DATABASE_FILE",
            help="TagTracker database file to update",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Update all attributes (usually only updates empty attributes)",
        )
        parser.add_argument(
            "--date",
            help="Limit update to DAY row for date DATE",
        )
        parser.add_argument(
            "--weather",
            metavar="FILE",
            help="Read temp/precip from csv file of Environment Canada historic climate data",
        )
        parser.add_argument(
            "--sun",
            metavar="FILE",
            help="Read sunset times from csv file of NR Canada sunrise/sunset times",
        )
        parser.add_argument(
            "--day-end",
            metavar="FILE",
            help="Read registrations/leftovers from csv file of day-end-form gsheet data",
        )
        parser.add_argument( "--verbose",action="store_true",default=False)
        return parser.parse_args()

args = ProgArgs()
if args.verbose:
    args.dump()

# Get existing database info
# FIXME: make test for existnece of file part of create_connection
if not os.path.exists(args.database_file):
    print(f"Database file {args.database_file} not found", file=sys.stderr)
    sys.exit(1)
database = db.create_connection(args.database_file)

weather_changes = []
if args.weather_csv:
    if args.verbose:
        print("\nWEATHER\n")
    weather_changes: list[str] = get_wx_changes(
        database,
        args.weather_csv,
        args.force,
        args.onedate,
    )
    for sql in weather_changes:
        if args.verbose:
            print(sql)
        db.db_update(database,sql,commit=False)
    db.db_commit(database)

sun_changes = []
if args.sun_csv:
    if args.verbose:
        print("\SUN\n")
    sun_changes: list[str] = get_sun_changes(
        database,
        args.sun_csv,
        args.force,
        args.onedate,
    )
    for sql in sun_changes:
        if args.verbose:
            print(sql)
        db.db_update(database,sql,commit=False)
    db.db_commit(database)

day_end_changes = []
if args.day_end_csv:
    if args.verbose:
        print("\nDAY END\n")
    day_end_changes: list[str] = get_day_end_changes(
        database,
        args.day_end_csv,
        args.force,
        args.onedate,
    )
    for sql in day_end_changes:
        if args.verbose:
            print(sql)
        db.db_update(database,sql,commit=False)
    db.db_commit(database)

print(f"Updated database '{args.database_file}':")
if args.weather_csv:
    print(f"   {len(weather_changes):3d} weather updates from '{args.weather_csv}'")
if args.sun_csv:
    print(f"   {len(sun_changes):3d} sun updates from '{args.sun_csv}'")
if args.day_end_csv:
    print(f"   {len(day_end_changes):3d} day_end updates from '{args.day_end_csv}'")

