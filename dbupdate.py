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
import asyncio

import env_canada

import tt_dbutil as db
import tt_util as ut

# These constants are values for which records to update
ALL = chr(0x2192) + "TARGET_ALL"
EMPTY = chr(0x2192) + "TARGET_EMPTY"
ONEDATE = chr(0x2192) + "TARGET_ONEDATE"
# These constants are for values for what kind of input we have
DAY_END = chr(0x2192) + "source_csv"
WEATHER = chr(0x2192) + "SOURCE_WEATHER"


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
        rainfall: float = None,
    ) -> None:
        self.registrations = registrations
        self.abandoned = abandoned
        self.precip = precip
        self.temp = temp
        self.max_temp = max_temp
        self.min_temp = min_temp
        self.rainfall = rainfall

    def dump(self):
        return f"{self.registrations=}; {self.abandoned=}; {self.precip=}; {self.temp=}"


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
                return ""
        if want_num:
            try:
                return float(myval)
            except ValueError:
                return ""
        return myval

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
    day_end_file: str,
    target_changes: str,
    target_onedate: str,
    db_data: dict[str, NewVals],
) -> list[str]:
    """Get SQL statements of changes from day end form source."""

    new = read_day_end_vals(day_end_file)
    sqls = []
    for db in db_data:
        if target_changes == ONEDATE and target_onedate != db.date:
            continue

        if (
            (target_changes != EMPTY or not db.registrations)
            and db.date in new
            and new[db.date].registrations
        ):
            sqls.append(
                f"update day set registrations = {new[db.date].registrations} where date = '{db.date}';"
            )
        if (
            (target_changes != EMPTY or not db.leftover)
            and db.date in new
            and new[db.date].abandoned
        ):
            sqls.append(
                f"update day set leftover = {new[db.date].abandoned} where date = '{db.date}';"
            )
        if (
            (target_changes != EMPTY or not db.precip_mm)
            and db.date in new
            and new[db.date].precip
        ):
            sqls.append(
                f"update day set precip_10mm = {new[db.date].precip} where date = '{db.date}';"
            )
        if (
            (target_changes != EMPTY or not db.temp_10am)
            and db.date in new
            and new[db.date].temp
        ):
            sqls.append(
                f"update day set temp_10am = {new[db.date].temp} where date = '{db.date}';"
            )
    return sqls


def read_nrcan_data(source_csv: str) -> dict[str, NewVals]:
    """Get weather data from NRCan data file for given range of dates.

    https://api.weather.gc.ca/collections/climate-daily/items?datetime=2023-01-01%2000:00:00/2023-07-09%2000:00:00&STN_ID=51337&sortby=PROVINCE_CODE,STN_ID,LOCAL_DATE&f=csv&limit=150000&startindex=0
    7,8,9: y,m,d
    10 - mean temp
    14 - max temp
    16 - total precip
    18 - total rainfall
    30 - heating degree days"""

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
                return ""
        if want_num:
            try:
                return float(myval)
            except ValueError:
                return ""
        return myval

    results = {}
    with open(source_csv, "r", newline="", encoding="utf-8") as csvfile:
        for row in csv.reader(csvfile):
            thisdate = ut.date_str(f"{row[7]}-{row[8]:02d}-{row[9]:02d}")
            if not thisdate:
                continue
            results[thisdate] = NewVals(
                precip=oneval(row, 16, want_num=True),
                temp=oneval(row, 14, want_num=True),
            )
    return results


def get_nrcan_changes(
    source_csv: str,
    target_changes: str,
    target_onedate: str,
    db_data: dict[str, NewVals],
) -> list[str]:
    """Get SQL statements of changes from NRCan source."""

    if not db_data:
        return []
    new = read_nrcan_data(source_csv)
    sqls = []
    for db in db_data:
        if target_changes == ONEDATE and target_onedate != db.date:
            continue

        if (
            (target_changes != EMPTY or not db.precip_mm)
            and db.date in new
            and new[db.date].precip
        ):
            sqls.append(
                f"update day set precip_mm = {new[db.date].precip} where date = '{db.date}';"
            )
        if (
            (target_changes != EMPTY or not db.temp_10am)
            and db.date in new
            and new[db.date].temp
        ):
            sqls.append(
                f"update day set temp_10am = {new[db.date].temp} where date = '{db.date}';"
            )
    return sqls


class ProgArgs:
    """Program arguments.

    Attributes:
        database_file: filename of the database
        target_rows: EMPTY, ALL or ONEDATE
        target_onedate: a valid date string or "" (only if ONEDATE)
        data_source: WEATHER or DAY_END
        source_csv: filename of DAY_END csv file (if DAY_END)
    """

    def __init__(self):
        """Get all the program arguments."""
        args = self._parse_args()
        self.database_file = args.database_file
        self.day_end = args.day_end
        self.target_rows = ""
        self.target_onedate = ""
        if args.date:
            self.target_rows = ONEDATE
            self.target_onedate = ut.date_str(args.date)
            if not self.target_onedate:
                print(
                    "DATE must be YYYY-MM-DD, 'today' or 'yesterday'",
                    file=sys.stderr,
                )
                sys.exit(1)
        elif args.all:
            self.target_rows = ALL
        elif args.empty:
            self.target_rows = EMPTY
        self.data_source = ""
        self.source_csv = ""
        if args.weather:
            self.data_source = WEATHER
            self.source_csv = args.weather
        elif args.day_end:
            self.data_source = DAY_END
            self.source_csv = args.day_end
        if not self.target_rows or not self.data_source:
            print(
                "Unknown args supporting which rows to update or what source to use",
                file=sys.stderr,
            )
            sys.exit(1)

    def dump(self):
        """Print the contents of the object."""
        print(f"{self.data_source=}; {self.source_csv=}")
        print(f"{self.target_rows=}; {self.target_onedate=}")
        print(f"{self.database_file=}")

    @staticmethod
    def _parse_args() -> argparse.Namespace:
        """Collect command args into an argparse.Namespace."""
        parser = argparse.ArgumentParser(
            description="Update TagTracker database DAY table from non-TagTracker sources",
            epilog="Exactly one of [all,empty,date] and [day-end,weather] are required.\n",
        )
        parser.add_argument(
            "database_file",
            metavar="DATABASE_FILE",
            help="TagTracker database file to update",
        )
        target_rows = parser.add_mutually_exclusive_group(required=True)
        target_rows.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="Update all available attributes in all DAY rows with new data",
        )
        target_rows.add_argument(
            "--empty",
            action="store_true",
            default=False,
            help="Update any empty attributes in all DAY rows if there is new data",
        )
        target_rows.add_argument(
            "--date",
            help="Update all available attributes in the DAY row that matches DATE with new data",
        )
        data_source = parser.add_mutually_exclusive_group(required=True)
        data_source.add_argument(
            "--day-end",
            metavar="FILE",
            help="Read source data csv file of day-end-form gsheet data",
        )
        data_source.add_argument(
            "--weather",
            metavar="FILE",
            help="Read source data csv file of Environment Canada historic climate data",
        )
        return parser.parse_args()


args = ProgArgs()
args.dump()


if args.data_source != DAY_END:
    print(f"Not implemented {args.data_source}", file=sys.stderr)
    exit(1)


# Get existing database info
# FIXME: make test for existnece of file part of create_connection
if not os.path.exists(args.database_file):
    print(f"Database file {args.database_file} not found", file=sys.stderr)
    sys.exit(1)
database = db.create_connection(args.database_file)
existing_data = db.db_fetch(
    database,
    "select "
    "   date, registrations, leftover, precip_mm, temp_10am "
    "from day "
    "order by date",
)

if args.data_source == DAY_END:
    changes: list[str] = get_day_end_changes(
        args.source_csv,
        args.target_rows,
        args.target_onedate,
        existing_data,
    )
    for onesql in changes:
        print(f"   {onesql}")

if args.data_source == WEATHER:
    changes: list[str] = get_ec_changes(
        args.source_csv,
        args.target_rows,
        args.target_onedate,
        existing_data,
    )
