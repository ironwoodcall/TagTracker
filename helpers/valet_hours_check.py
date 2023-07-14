#!/usr/bin/env python3
"""Scan valet hours to see if they seem correct."""

import sys
sys.path.append("../")
import tt_dbutil as db
from tt_conf import valet_hours
from tt_util import date_str

dbfile = "/fs/sysbits/tagtracker/dev/data/cityhall_bikevalet.db"

database = db.create_connection(dbfile)
vhours = db.db_fetch(
    database, "select date,time_open,time_closed from day order by date"
)
print("Mismatches between actual and exected valet hours.")
print(f"Database: {dbfile}")
print()
print("Date            Actual(DB)   Expected")
for onedate in vhours:
    (expected_open, expected_close) = valet_hours(onedate.date)
    actual_open = onedate.time_open
    actual_close = onedate.time_closed
    nomatch = ""
    if actual_open != expected_open:
        nomatch = "OPEN"
    if actual_close != expected_close:
        nomatch = "BOTH" if nomatch else "CLOSE"
    if nomatch:
        print(
            f"{onedate.date} {date_str(onedate.date,dow_str_len=3)}  "
            f"{actual_open}-{actual_close}  "
            f"{expected_open}-{expected_close}  "
            f"{nomatch}"
        )
