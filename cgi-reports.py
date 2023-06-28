#!/usr/bin/env python3
"""CGI script for TagTracker reports against consolidated database.

This expects environment var TAGTRACKER_CGI_PORT to indicate what
port this comes in on, if that's a concern

:

"""

import sqlite3

import os
import urllib.parse
import datetime
import re

from tt_globals import *

import tt_conf as cfg
from tt_trackerday import TrackerDay
import tt_reports as rep
import tt_datafile as df
from tt_tag import TagID
from tt_time import VTime


def untaint(tainted:str) -> str:
    """Remove any suspicious characters from a possibly tainted string."""
    return ''.join(c for c in tainted if c.isprintable())

def form(
    ttdb: sqlite3.Connection,
    title: str = "TagTracker",
    default_what: str = "",
    default_date: str = "",
    default_tag: str = "",
):
    latest_date = db_last_date(ttdb)
    if not default_date:
        default_date = latest_date

    choices = {
        "oneday": "Tags in/out on a particular day [specify Date]",
        "overall": "Overall",
        "abandoned": "Lost tag report",
        "last_use": "Last use of a tag             [specify TagID]",
        "datafile": "Recreate a day's datafile     [specify Date]",
        "audit": "* Audit report [specify Date]",
        "busyness": "* Report of one-day busyness [specify Date]",
        "chart": "* Chart of activities for one day [specify Date]",
        "busy-graph": "* Graph of activities for one day [specify Date]",
    }


    print(f"<html><head><title>{title}</title></head><body>")
    print("<h1>TagTracker reports</h1>")
    print(f"Database has information up to {latest_date}<br /><br />")
    print(
        f"""
    <form accept-charset="UTF-8" action="tt" autocomplete="off" method="GET">


    <label for="name">Report to create:</label>
    <select name="what" id="what">
""")
    for what,descr in choices.items():
        if what == default_what:
            print(f'<option value="{what}" selected="selected">{descr}</option>')
        else:
            print(f'<option value="{what}">{descr}</option>')
    print(f"""

    </select>
    <br />
          <i>Reports marked with (*) currently return incorrect information</i>
    <br /><br />
    Date: <input name="date" type="text" value="{default_date}" />
    <br />
    Tag: <input name="tag" type="text" value="{default_tag}" />
    <br />
    <br />
    <button type="submit" value="Submit">Create report</button>

    </form>
    <hr>
"""
    )


def db_last_date(ttdb: sqlite3.Connection) -> str:
    """Fetch the last date for which there is info in the database."""
    curs = ttdb.cursor()
    rows = curs.execute(
        "select date from visit order by date desc limit 1"
    ).fetchall()
    if not rows:
        return ""
    return rows[0][0]


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
    # Fake up regular/oversize lists
    day.make_fake_tag_lists()
    # Fake up a colour dictionary
    day.make_fake_colour_dict()
    return day


def error_out(msg: str = ""):
    if msg:
        print(msg)
    else:
        print("Bad or unknown parameter")
    exit(1)


def show_help():
    print("<pre>\n")
    print(
        f"""
Parameters

what        date     tag    description
----        ----            -----------
overall                     List a few stats about all days in database
abandoned                   List of all abandoned bikes
oneday      <date>          Info about one day
datafile    <date>          Reconstruct a datafile from the database
last_use             <tag>  Last time a particular tag was used

- Construct URLs thus: <server/cgi-bin/tt>?parameter=val&parameter=value...
  E.g. myserver.org/cgi-bin/tt?what=oneday&date=2023-04-29
- <date> can be YYYY-MM-DD, 'today', or 'yesterday'
      """
    )


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


def report_tag(ttdb: sqlite3.Connection, maybe_tag: MaybeTag) -> None:
    """Report last use of a tag."""

    tag = TagID(maybe_tag)
    if not tag:
        print(f"Not a tag: '{untaint(tag.original)}'")
        exit()
    # Fetch all info about this tag.
    (last_date, last_in, last_out, checked_out) = ("", "", "", False)
    curs = ttdb.cursor()
    rows = curs.execute(
        "select date,time_in,time_out,leftover "
        "from visit "
        f"where tag = '{tag}' "
        "order by date desc limit 1;"
    ).fetchall()
    if rows:
        last_date = rows[0][0]
        last_in = VTime(rows[0][1])
        last_out = VTime(rows[0][2])
        checked_out = rows[0][3] == "no"


    title = f"Last use of tag {tag.upper()}"
    print(f"<h1>{title}</h1>")
    ##print("-" * len(title))
    print()
    if not last_date:
        print(f"No record that {tag.upper()} ever used<br />")
    else:
        print(f"Last used {last_date}<br />")
        print(f"Bike in:  {last_in.tidy}<br />")
        if checked_out and last_out:
            print(f"Bike out: {last_out.tidy}<br />")
        else:
            print("Bike not checked out<br />")
    print("</body></html>")


def report_overall(ttdb: sqlite3.Connection):
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


def oneday(ttdb: sqlite3.Connection, whatday: str = ""):
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

    print("<pre>")
    if not visits:
        print(f"No activity recorded for {thisday}")
        exit()
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


def datafile(ttdb: sqlite3.Connection, date: str = ""):
    """Print a reconstructed datafile for the given date."""
    thisday = whatday(date)
    if not thisday:
        bad_date(date)

    print("<pre>")

    day = db2day(ttdb, thisday)
    print(f"# TagTracker datafile for {thisday}")
    print(
        f"# Reconstructed   on {datetime.datetime.today().strftime('%Y-%m-%d %H:%M')}"
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

def whatday(maybe_day:str="today") -> str:
    """Returns mayebday as a YYYY-MM-DD string."""
    if maybe_day.lower() == "yesterday":
        # yesterday
        day = datetime.datetime.today() - datetime.timedelta(1)
        thisday = day.strftime("%Y-%m-%d")
    elif maybe_day.lower() == "today":
        # today
        thisday = datetime.datetime.today().strftime("%Y-%m-%d")
    else:
        r = re.fullmatch(r"(\d\d\d\d)[-/]?(\d\d)[-/]?(\d\d)",maybe_day)
        if not r:
            return ""
        try:
            day = datetime.datetime.strptime(f"{r.group(1)}-{r.group(2)}-{r.group(3)}", "%Y-%m-%d")
            thisday = day.strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return thisday

def bad_date(bad_date:str=""):
    """Print message about bad date & exit."""
    error_out(f"Bad date '{untaint(bad_date)}'. "
              "Use YYYY-MM-DD or 'today' or 'yesterday'.")

def audit_report(ttdb:sqlite3.Connection,thisday:str,whattime:VTime):
    """Print audit report."""
    if not thisday:
        bad_date(thisday)
    print("<pre>")
    day = db2day(ttdb,thisday)
    rep.audit_report(day,[VTime(whattime)])


def one_day_chart(ttdb:sqlite3.Connection, date:str):
    """One-day chart."""
    thisday = whatday(date)
    if not thisday:
        bad_date(date)
    print("<pre>")
    rep.full_chart(db2day(ttdb,thisday),["now"])


def one_day_busy_graph(ttdb:sqlite3.Connection, date:str):
    """One-day chart."""
    thisday = whatday(date)
    if not thisday:
        bad_date(date)
    print("<pre>")
    rep.busy_graph(db2day(ttdb,thisday),["now"])


def busyness_report(ttdb:sqlite3.Connection, thisday:str, qtime:VTime):
    """One-day busy report."""
    if not thisday:
        bad_date(thisday)
    print("<pre>")
    rep.busyness_report(db2day(ttdb,thisday),[qtime])

#=================================================================
print("Content-type: text/html\n\n\n")

DBFILE = "/fs/sysbits/tagtracker/cityhall_bikevalet.db"
database = create_connection(DBFILE)

# Parse query parameters from the URL if present
query_string = untaint(os.environ.get("QUERY_STRING", ""))
query_params = urllib.parse.parse_qs(query_string)
what = query_params.get("what", [""])[0]
maybedate = query_params.get("date", [""])[0]
maybetime = query_params.get("time", [""])[0]
tag = query_params.get("tag", [""])[0]

# Date will be 'today' or 'yesterday' or ...
# Time of day will be 24:00 unless it's today (or specified)
qdate = whatday(maybedate)
if not maybetime:
    if qdate == whatday("today"):
        qtime = VTime("now")
    else:
        qtime = VTime("24:00")
else:
    qtime = VTime(maybetime)
if not qtime:
    error_out(f"Bad time: '{untaint(maybetime)}")
print(f"xxx {maybetime=};{maybedate=} ==> {qtime=}; {qdate=}")
form(database, default_what=what, default_date=maybedate, default_tag=tag)
if not what:
    exit()
if what == "last_use":
    report_tag(database, tag)
elif what == "overall":
    report_overall(database)
elif what == "abandoned":
    lost_tags(database)
elif what == "oneday":
    oneday(database, qdate)
elif what == "datafile":
    datafile(database, qdate)
elif what == "audit":
    audit_report(database,qdate,qtime)
elif what == "busyness":
    busyness_report(database,qdate,qtime)
elif what == "chart":
    one_day_chart(database,qdate)
elif what == "busy-graph":
    one_day_busy_graph(database,qdate)
else:
    error_out(f"Unknown request: {untaint(what)}")
    exit(1)
