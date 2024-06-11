#!/usr/bin/env python3
"""Update existing records in TagTraker database.

Reads weather info weather info in csv file into db

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

# FIXME: this is ignorant about orgs, ids, geography of sites

import argparse
import csv

# import datetime
import sys
import sqlite3

import common.tt_dbutil as db
import common.tt_util as ut
from common.tt_time import VTime


class NewVals:
    """This tiny class is just for holding data from new source.

    NRCan will use some fields, day-end-form may use some fields.
    """

    def __init__(
        self,
        # registrations: int = None,
        # abandoned: int = None,
        precipitation: float = None,
        max_temperature: float = None,
        min_temperature: float = None,
        mean_temperature: float = None,
        rainfall: float = None,
        # sunset: str = None,
    ) -> None:
        # self.registrations = registrations
        # self.abandoned = abandoned
        self.precipitation = precipitation
        self.max_temperature = max_temperature
        self.min_temperature = min_temperature
        self.mean_temperature = mean_temperature
        self.rainfall = rainfall
        # self.sunset = sunset

    def dump(self):
        """Dump object contents. Mostly here for debug work."""
        return (
            f"{self.precipitation=}; "
            f"{self.max_temperature=}; {self.min_temperature=}; {self.mean_temperature=}"
        )


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


def read_wx_data(source_csv: str) -> dict[str, NewVals]:
    """Get weather data from NRCan data file for given range of dates.

    https://api.weather.gc.ca/collections/climate-daily/items?datetime=2023-01-01%2000:00:00/2023-07-09%2000:00:00&STN_ID=51337&sortby=PROVINCE_CODE,STN_ID,LOCAL_DATE&f=csv&limit=150000&startindex=0
    7,8,9: y,m,d
    10 - mean temp
    12 - min temp
    14 - max temp
    16 - total precip
    18 - total rainfall
    30 - heating degree days

    ANother(?) possible URL:
    YYJ: https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID=51337&Year=2023&Month=7&Day=1&time=&timeframe=2&submit=Download+Data
    UVic: https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID=6812&Year=2023&Month=7&Day=1&time=&timeframe=2&submit=Download+Data
    5,6,7: y,m,d
    9: max temp
    11: min temp
    13: mean temp
    23: precip

    """

    results = {}
    with open(source_csv, "r", newline="", encoding="utf-8") as csvfile:
        for row in csv.reader(csvfile):
            maybedate = f"{row[5]}-{('0'+row[6])[-2:]}-{('0'+row[7])[-2:]}"
            thisdate = ut.date_str(maybedate)
            if not thisdate:
                continue
            results[thisdate] = NewVals(
                precipitation=oneval(row, 23, want_num=True),
                # temp=oneval(row, 14, want_num=True),    # max
                min_temperature=oneval(row, 11, want_num=True),
                max_temperature=oneval(row, 9, want_num=True),
                mean_temperature=oneval(row, 13, want_num=True),
            )
    return results


def get_wx_changes(
    ttdb: sqlite3.Connection,
    source_csv: str,
    force: str,
    onedate: str,
) -> list[str]:
    """Get SQL statements of changes from NRCan source."""

    where = f" where date = '{onedate}' " if onedate else ""
    db_data = db.db_fetch(
        ttdb,
        "select "
        "   date, precipitation, max_temperature "
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
            (force or existing.precipitation is None)
            and existing.date in new
            and new[existing.date].precipitation is not None
        ):
            sqls.append(
                f"update day set precipitation = {new[existing.date].precipitation} "
                f"where date = '{existing.date}';"
            )
        if (
            (force or not existing.max_temperature)
            and existing.date in new
            and new[existing.date].max_temperature is not None
        ):
            sqls.append(
                f"update day set max_temperature = {new[existing.date].max_temperature} "
                f"where date = '{existing.date}';"
            )
    return sqls


# -------------------
# def read_sun_data(source_csv: str) -> dict[str, NewVals]:
#     """Get sunset data from NRCan data file for given range of dates.

#     Using whole-year text file produced from solar calculator at
#     https://nrc.canada.ca/en/research-development/products-services/software-applications/sun-calculator/

#     Fields of interest:
#         0: Data as "Mmm D YYYY"
#         5: sunset
#         6: civilian twilight
#         7: nautical twilight

#     """

#     MONTHS = { #pylint:disable=invalid-name
#         "Jan": "01",
#         "Feb": "02",
#         "Mar": "03",
#         "Apr": "04",
#         "May": "05",
#         "Jun": "06",
#         "Jul": "07",
#         "Aug": "08",
#         "Sep": "09",
#         "Oct": "10",
#         "Nov": "11",
#         "Dec": "12",
#     }

#     results = {}
#     with open(source_csv, "r", newline="", encoding="utf-8") as csvfile:
#         for row in csv.reader(csvfile):
#             if not row or not row[0]:
#                 if args.verbose:
#                     print(f"discarding sun csv row {row}")
#                 continue
#             # Break first element into date elements
#             datebits = row[0].split()
#             if len(datebits) != 3:
#                 if args.verbose:
#                     print(f"discarding bad date in sun csv row {row}")
#                 continue
#             maybedate = f"{datebits[2]}-{MONTHS[datebits[0]]}-{('0'+datebits[1])[-2:]}"
#             thisdate = ut.date_str(maybedate)
#             if not thisdate:
#                 continue
#             if args.verbose:
#                 print(f"have date: {thisdate}")
#             results[thisdate] = NewVals(
#                 sunset=VTime(oneval(row, 6)),
#             )
#         if args.verbose:
#             [ # pylint:disable=expression-not-assigned
#                 print(f"{d}: {s.sunset}") for d, s in results.items()
#             ]
#     return results


# def get_sun_changes(
#     ttdb: sqlite3.Connection,
#     source_csv: str,
#     force: str,
#     onedate: str,
# ) -> list[str]:
#     """Get SQL statements of changes from NRCan source."""

#     where = f" where date = '{onedate}' " if onedate else ""
#     db_data = db.db_fetch(
#         ttdb,
#         "select " "   date, sunset " "from day " f"{where}" "order by date",
#     )
#     if not db_data:
#         return []
#     if args.verbose:
#         for row in db_data:
#             print(f"{row.date=};{row.sunset=}")
#     new = read_sun_data(source_csv)

#     sqls = []
#     for existing in db_data:
#         if onedate and onedate != existing.date:
#             continue

#         if (
#             (force or existing.sunset is None)
#             and existing.date in new
#             and new[existing.date].sunset is not None
#         ):
#             sqls.append(
#                 f"update day set sunset = '{new[existing.date].sunset}' "
#                 f"where date = '{existing.date}';"
#             )
#     return sqls


# -------------------


class ProgArgs:
    """Program arguments.

    Attributes:
        database_file: filename of the database
        target_rows: EMPTY, ALL or ONEDATE
        onedate: a valid date string or "" (only if ONEDATE)
        weather_csv: filename of WEATHER csv file (if any, else "")
    """

    # REMOVED:   day_end_csv: filename of DAY END csv file (if any, else "")

    def __init__(self):
        """Get all the program arguments."""
        progargs = self._parse_args()
        self.verbose = progargs.verbose
        self.database_file = progargs.database_file
        # self.day_end = progargs.day_end
        self.force = progargs.force
        self.onedate = ""
        if progargs.date:
            # self.target_rows = ONEDATE
            self.onedate = ut.date_str(progargs.date)
            if not self.onedate:
                print(
                    "DATE must be YYYY-MM-DD, 'today' or 'yesterday'",
                    file=sys.stderr,
                )
                sys.exit(1)
        # elif args.all:
        #    self.target_rows = ALL
        # elif args.empty:
        #    self.target_rows = EMPTY
        self.weather_csv = progargs.weather if progargs.weather else ""
        self.sun_csv = progargs.sun if progargs.sun else ""
        # self.day_end_csv = progargs.day_end if progargs.day_end else ""
        # if not self.target_rows:
        #    print(
        #        "Unknown args supporting which rows to update",
        #        file=sys.stderr,
        #    )
        #    sys.exit(1)
        if not self.weather_csv and not self.sun_csv:
            print(
                "Must specify at least one of --weather --sun --day-end",
                file=sys.stderr,
            )
            sys.exit(1)

    def dump(self):
        """Print the contents of the object."""
        print(f"{self.weather_csv=}; ")
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
        # parser.add_argument(
        #     "--day-end",
        #     metavar="FILE",
        #     help="Read registrations/leftovers from csv file of day-end-form gsheet data",
        # )
        parser.add_argument("--verbose", action="store_true", default=False)
        return parser.parse_args()


args = ProgArgs()
if args.verbose:
    args.dump()

# Get existing database info
database = db.db_connect(args.database_file)
if not database:
    sys.exit(1)

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
        db.db_update(database, sql, commit=False)
    db.db_commit(database)

# sun_changes = []
# if args.sun_csv:
#     if args.verbose:
#         print("SUN\n")
#     sun_changes: list[str] = get_sun_changes(
#         database,
#         args.sun_csv,
#         args.force,
#         args.onedate,
#     )
#     for sql in sun_changes:
#         if args.verbose:
#             print(sql)
#         db.db_update(database, sql, commit=False)
#     db.db_commit(database)

# day_end_changes = []
# if args.day_end_csv:
#     if args.verbose:
#         print("\nDAY END\n")
#     day_end_changes: list[str] = get_day_end_changes(
#         database,
#         args.day_end_csv,
#         args.force,
#         args.onedate,
#     )
#     for sql in day_end_changes:
#         if args.verbose:
#             print(sql)
#         db.db_update(database, sql, commit=False)
#     db.db_commit(database)

print(f"Updated database '{args.database_file}':")
if args.weather_csv:
    print(f"   {len(weather_changes):3d} weather updates from '{args.weather_csv}'")
# if args.sun_csv:
#     print(f"   {len(sun_changes):3d} sun updates from '{args.sun_csv}'")
# if args.day_end_csv:
#     print(
#         f"   {len(day_end_changes):3d} day_end updates from '{args.day_end_csv}'"
#     )
