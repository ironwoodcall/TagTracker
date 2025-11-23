#!/usr/bin/env python3
"""Scan hours to see if they seem correct."""

import sys
import database.tt_dbutil as db
from web.web_base_config import DB_FILENAME
import common.tt_util as ut

sys.path.append("../")

dbfile = DB_FILENAME

database = db.db_connect(dbfile)
if not database:
    sys.exit(1)
vhours = db.db_fetch(
    database, "select date,time_open,time_closed from day order by date"
)

# If want to run this then need to fix up its call to (superseded) valet_hours.
def valet_hours(date:str):
    print("This script needs to get updated to use newer definitions of dates")
    sys.exit(1)
    return None,None


print("Mismatches between actual and exected operating hours.")
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
            f"{onedate.date} {ut.date_str(onedate.date,dow_str_len=3)}  "
            f"{actual_open}-{actual_close}  "
            f"{expected_open}-{expected_close}  "
            f"{nomatch}"
        )
