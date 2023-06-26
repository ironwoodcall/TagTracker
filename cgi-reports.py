#!/usr/bin/env python3
"""CGI script for TagTracker reports against consolidated database.

This expects environment var TAGTRACKER_CGI_PORT to indicate what
port this comes in on, if that's a concern



"""

import sqlite3

import os
import urllib.parse
import datetime

# from tt_globals import *
# import tt_conf
from tt_trackerday import TrackerDay
import tt_reports as rep
import tt_datafile as df
from tt_tag import TagID
from tt_time import VTime


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
        "select tag,time_in,time_out,leftover from visit "
        f"where date = '{whatdate}' "
        "order by time_in desc;"
    ).fetchall()
    for row in rows:
        tag = TagID(row[0])
        time_in = VTime(row[1])
        time_out = VTime(row[2])
        still_out = row[3] == "yes"
        if not tag or not time_in:
            continue
        day.bikes_in[tag] = time_in
        if time_out and not still_out:
            day.bikes_out[tag] = time_out
    # Fake up a colour dictionary
    day.make_fake_colour_dict()
    return day


def error_out(msg: str = ""):
    print("Content-type: text/plain\n\n\n")
    if msg:
        print(msg)
    else:
        print("Bad or unknown parameter")
    exit(1)


def show_help():
    print("Content-type: text/html\n\n\n")
    print("<html><body>")
    print("<pre>")
    print("recognized 'what' parameters:")
    print("  overall")
    print("  abandoned")
    print("  oneday&when=[date]")
    print("</pre></body></html>")


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


def padval(val, length: int = 0) -> str:
    valstr = str(val)
    if length < len(valstr):
        length = len(valstr)
    pad = " " * (length - len(valstr))
    if isinstance(val, str):
        return f"{valstr}{pad}"
    else:
        return f"{pad}{valstr}"


def report_overall(ttdb: sqlite3.Connection):
    print("Content-type: text/html\n\n\n")

    curs = ttdb.cursor()
    rows = curs.execute(
        "select date, parked_regular Regular, parked_oversize Oversize, parked_total Total, "
        "max_total fullest, leftover "
        "from day order by date desc"
    ).fetchall()
    names = [description[0].upper() for description in curs.description]
    lengths = [0 for _ in names]
    for i, v in enumerate(names):
        s = str(v)
        if len(s) > lengths[i]:
            lengths[i] = len(s)
    for row in rows:
        for i, v in enumerate(row):
            s = str(v)
            if len(s) > lengths[i]:
                lengths[i] = len(s)

    # print(f"{curs.description=}</br></br>")
    # print(f"{names=}</br></br>")
    print("<html><head><title>Daily valet overview</title></head><body>")
    print("<pre>")
    print("Daily valet overview")
    print("--------------------")
    print("Listed newest to oldest")
    print()
    for i, v in enumerate(names):
        print(f"{padval(v,lengths[i])} ", end="")
    print()

    for row in rows:
        for i, v in enumerate(row):
            print(f"{padval(v,lengths[i])} ", end="")
        print()
    print("</pre></body></html>")




def lost_tags(ttdb: sqlite3.Connection):
    too_many = 10
    curs = ttdb.cursor()
    rows = curs.execute(
        "select tag,date,time_in from visit "
        "where date not in (select date from day where leftover > 5) "
        "and leftover = 'yes' "
        "and date < strftime('%Y-%m-%d') "
        "order by date desc;"
    ).fetchall()

    print("Content-type: text/html\n\n\n")
    print("<html><head><title>Abandoned bikes</title></head><body>")
    print("<pre>")
    print("Tags of abandoned bikes")
    print("-----------------------")
    print("  - listed newest to oldest")
    print(f"  - excludes dates with more than {too_many} supposed leftovers")
    print()
    print("Tag    Last check-in")
    print("---    -------------")
    for row in rows:
        print(f"{padval(row[0],5)}  {padval(row[1],10)}  {padval(row[2],5)}")
    print("</pre></body></html>")


def latest_event(ttdb: sqlite3.Connection, whatday: str) -> str:
    curs = ttdb.cursor()
    rows = curs.execute(
        f"select max(time_in), max(time_out) from visit where date = '{whatday}' and leftover = 'no' "
    ).fetchall()
    if not rows:
        return VTime()
    max_in = rows[0][0]
    max_out = rows[0][1]
    max_in = max_in if max_in else ""
    max_out = max_out if max_out else ""
    if max_in > max_out:
        return VTime(max_in)
    else:
        return VTime(max_out)


class VisitRow:
    def __init__(self):
        self.tag = TagID()
        self.time_in = VTime()
        self.time_out = VTime()
        self.duration = VTime()
        self.leftover = False


def today(ttdb: sqlite3.Connection, whatday: str = ""):
    if whatday.lower() == "yesterday":
        # yesterday
        day = datetime.datetime.today() - datetime.timedelta(1)
        thisday = day.strftime("%Y-%m-%d")
    elif not whatday or whatday.lower() == "today":
        # today
        thisday = datetime.datetime.today().strftime("%Y-%m-%d")
    else:
        # possibly an actual date
        try:
            day = datetime.datetime.strptime(whatday, "%Y-%m-%d")
            thisday = day.strftime("%Y-%m-%d")
        except:
            error_out("Bad date. Use YYYY-MM-DD or 'today' or 'yesterday'.")

    curs = ttdb.cursor()
    rows = curs.execute(
        "select tag,time_in,time_out,duration,leftover from visit "
        f"where date = '{thisday}' "
        "order by time_in desc;"
    ).fetchall()

    visits = {}
    for row in rows:
        tag = TagID(row[0])
        if not tag:
            continue
        v: VisitRow = VisitRow()
        v.tag = tag
        v.time_in = VTime(row[1])
        v.time_out = VTime(row[2])
        v.duration = VTime(row[3])
        v.leftover = bool(row[4] == "yes")
        visits[tag] = v

    # Fix up visits
    for v in visits.values():
        if v.leftover:
            v.duration = VTime()
            v.time_out = VTime()

    print("Content-type: text/html\n\n\n")
    print(f"<html><head><title>Tags for {thisday}</title></head><body>")
    print("<pre>")
    print(f"Tags for {thisday}")
    print("-------------------")
    print(
        f"Latest recorded event this day is {latest_event(database,thisday).short}"
    )
    print()
    print("BIKE   --IN- -OUT-  DURTN")
    for tag in sorted(visits.keys()):
        v: VisitRow = visits[tag]
        print(
            f"{padval(tag,6)} {v.time_in.tidy} {v.time_out.tidy}  {v.duration.tidy}"
        )
    print("</pre></body></html>")


def datafile(ttdb: sqlite3.Connection, whatday: str = ""):
    """Print a reconstructed datafile for the given date."""
    if whatday.lower() == "yesterday":
        # yesterday
        day = datetime.datetime.today() - datetime.timedelta(1)
        thisday = day.strftime("%Y-%m-%d")
    elif not whatday or whatday.lower() == "today":
        # today
        thisday = datetime.datetime.today().strftime("%Y-%m-%d")
    else:
        # possibly an actual date
        try:
            day = datetime.datetime.strptime(whatday, "%Y-%m-%d")
            thisday = day.strftime("%Y-%m-%d")
        except:
            error_out("Bad date. Use YYYY-MM-DD or 'today' or 'yesterday'.")

    print("Content-type: text/plain\n")

    day = db2day(ttdb, thisday)
    print(f"# TagTracker datafile for {thisday}")
    print(
        f"# Reconstructed from database, on {datetime.datetime.today().strftime('%Y-%m-%d %H:%M')}"
    )
    print(f"{df.HEADER_VALET_DATE} {day.date}")
    print(f"{df.HEADER_VALET_OPENS} {day.opening_time}")
    print(f"{df.HEADER_VALET_CLOSES} {day.closing_time}")
    print(f"{df.HEADER_BIKES_IN}")
    for tag, atime in day.bikes_in.items():
        print(f"  {tag},{atime}")
    print(f"{df.HEADER_BIKES_OUT}")
    for tag, atime in day.bikes_out.items():
        print(f"  {tag},{atime}")
    print(f"{df.HEADER_REGULAR}")
    print(f"{df.HEADER_OVERSIZE}")
    print(f"{df.HEADER_RETIRED}")
    print(f"{df.HEADER_COLOURS}")
    for col, name in day.colour_letters.items():
        print(f"  {col},{name}")
    ##rep.audit_report(day,[])


# Parse query parameters from the URL if present
query_string = os.environ.get("QUERY_STRING", "")
query_params = urllib.parse.parse_qs(query_string)
what = query_params.get("what", [""])[0]
detail = query_params.get("detail", [""])[0]
when = query_params.get("when", [""])[0]

DBFILE = "/fs/sysbits/tagtracker/cityhall_bikevalet.db"

database = create_connection(DBFILE)
if not what:
    show_help()
elif what == "overall":
    report_overall(database)
elif what == "abandoned":
    lost_tags(database)
elif what == "oneday":
    today(database, when)
elif what == "datafile":
    datafile(database, when)
else:
    error_out()
    exit(1)
