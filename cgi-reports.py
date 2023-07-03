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

import tt_dbutil as db
import tt_conf as cfg
from tt_trackerday import TrackerDay
import tt_reports as rep
import tt_datafile as df
from tt_tag import TagID
from tt_time import VTime
import tt_util as ut

##from zotto import print
##import zotto


def untaint(tainted: str) -> str:
    """Remove any suspicious characters from a possibly tainted string."""
    return "".join(c for c in tainted if c.isprintable())


def selfref(
    what: str = "",
    qdate: str = "",
    qtime: str = "",
    qtag: str = "",
) -> str:
    """Return a self-reference with the given parameters."""

    me = untaint(os.environ.get("SCRIPT_NAME", ""))
    parms = []
    if what:
        parms.append(f"what={what}")
    if qdate:
        parms.append(f"date={qdate}")
    if qtime:
        parms.append(f"time={qtime}")
    if qtag:
        parms.append(f"tag={qtag}")
    parms_str = f"?{'&'.join(parms)}" if parms else ""
    return f"{me}{untaint(parms_str)}"


def style() -> str:
    """Return a CSS stylesheet as a string."""
    return """
        <style>
            html {
        font-family: sans-serif;
        }

        table {
        border-collapse: collapse;
        border: 2px solid rgb(200,200,200);
        letter-spacing: 1px;
        font-size: 0.8rem;
        }

        td, th {
        border: 1px solid rgb(190,190,190);
        padding: 5px 15px;
        }

        th {
        background-color: rgb(235,235,235);
        }

        td {
        text-align: right;
        }

        tr:nth-child(even) td {
        background-color: rgb(250,250,250);
        }

        tr:nth-child(odd) td {
        background-color: rgb(245,245,245);
        }

        caption {
        padding: 10px;
        }
        </style>
    """


def form(
    ttdb: sqlite3.Connection,
    title: str = "TagTracker",
    default_what: str = "overview",
    default_date: str = "",
    default_tag: str = "",
):
    (latest_date, latest_time) = db.db_latest(ttdb)
    if not default_date:
        default_date = latest_date

    choices = {
        "overview": "Overview",
        "abandoned": "Lost tags report",
        "last_use": "Tag history (for one tag)     [specify TagID]",
        "one_day_tags": "Tags in/out on a particular day [specify Date]",
        "datafile": "Recreate a day's datafile     [specify Date]",
        "audit": "* Audit report [specify Date]",
        "busyness": "* Report of one-day busyness [specify Date]",
        "chart": "* Chart of activities for one day [specify Date]",
        "busy-graph": "* Graph of activities for one day [specify Date]",
    }

    print(f"<html><head><title>{title}</title></head>")
    print(style())
    print("<body>")
    print("<h2>TagTracker reports</h2>")
    print(
        f"Most recent time recorded in database is {latest_time.short} on {latest_date}<br /><br />"
    )
    print(
        f"""
    <form accept-charset="UTF-8" action="tt" autocomplete="off" method="GET">


    <label for="name">Report to create:</label>
    <select name="what" id="what">
"""
    )
    for what, descr in choices.items():
        if what == default_what:
            print(
                f'<option value="{what}" selected="selected">{descr}</option>'
            )
        else:
            print(f'<option value="{what}">{descr}</option>')
    print(
        f"""

    </select>
    <br />
          <i>Treat information from reports marked (*) with extra caution</i>
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
overview                     List a few stats about all days in database
abandoned                   List of all abandoned bikes
one_day_tags      <date>          Info about one day
datafile    <date>          Reconstruct a datafile from the database
last_use             <tag>  Last time a particular tag was used

- Construct URLs thus: <server/cgi-bin/tt>?parameter=val&parameter=value...
  E.g. myserver.org/cgi-bin/tt?what=one_day_tags&date=2023-04-29
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


def one_tag_history_report(
    ttdb: sqlite3.Connection, maybe_tag: MaybeTag
) -> None:
    """Report a tag's history."""

    tag = TagID(maybe_tag)
    if not tag:
        print(f"Not a tag: '{untaint(tag.original)}'")
        exit()
    # Fetch all info about this tag.
    (last_date, last_in, last_out) = ("", "", "")
    curs = ttdb.cursor()
    rows = curs.execute(
        "select date,time_in,time_out "
        "from visit "
        f"where tag = '{tag.lower()}' "
        "order by date desc;"
    ).fetchall()

    print(f"<h1>History of tag {tag.upper()}</h1>")
    print(
        f"<h3>This tag has been used {len(rows)} time{ut.plural(len(rows))}</h3>"
    )
    print()
    if not rows:
        print(f"No record that {tag.upper()} ever used<br />")
    else:
        print("<table>")
        print("<style>td {text-align: right;}</style>")
        print("<tr><th>Date</th><th>BikeIn</th><th>BikeOut</th></tr>")
        for row in rows:
            out = VTime(row[2]).tidy if row[2] else "     "
            linkdate = row[0]
            link = selfref(what="one_day_tags", qdate=linkdate)
            print(
                f"<tr><td>"
                f"<a href='{link}'>{row[0]}</a>"
                "</td>"
                f"<td>{VTime(row[1]).tidy}</td><td>{out}</td></tr>"
            )
        print("</table>")
    print("</body></html>")


def overview_report(ttdb: sqlite3.Connection):
    """Print new version of the all-days defauilt report."""
    sel = (
        "select date, time_open, time_closed, "
        "parked_regular, parked_oversize, parked_total, leftover, "
        "max_total "
        "from day order by date desc"
    )
    cnames = [
        "date",
        "opened",
        "closed",
        "reg",
        "ovr",
        "ttl",
        "extra",
        "most_bikes",
    ]
    dbrows = db.db_fetch(ttdb, sel, cnames)
    max_parked = 0
    max_parked_date = ""
    max_full = 0
    max_full_date = ""
    max_left = 0
    max_left_date = ""
    for r in dbrows:
        if r.ttl > max_parked:
            max_parked = r.ttl
            max_parked_date = r.date
        if r.most_bikes > max_full:
            max_full = r.most_bikes
            max_full_date = r.date
        if r.extra > max_left:
            max_left = r.extra
            max_left_date = r.date
    max_parked_factor = 255 / (max_parked*max_parked)
    max_full_factor = 255 / (max_full*max_full)
    max_left_factor = 255 / min(max_left, 5)

    print("<h1>Daily valet overview</h1>")
    print(f"<p><b>Most bikes parked:</b> {max_parked}, on {max_parked_date}<br />")
    print(f"<b>Valet was fullest:</b> {max_full} bikes, on {max_full_date}</p>")
    print("<p></p>")
    print("<p>Listed newest to oldest</p>")

    print("<table>")
    print("<style>td {text-align: right;}</style>")
    print(
        # "<colgroup>"
        # "<col>"
        #'<col span=2 style="background-color:#DCC48E; border:4px solid #C1437A;">'
        #'<col span=2 style=background-color:#97DB9A;>'
        #'<col style="width:42px;">'
        #'<col style="background-color:#97DB9A;">'
        #'<col style="background-color:#DCC48E; border:4px solid #C1437A;">'
        #'<col span="2" style="width:42px;">'
        #'</colgroup>'
        "<tr>"
        "<th rowspan=2>Date</th>"
        "<th colspan=2>Valet Hours</th>"
        "<th colspan=3>Bike Parked</th>"
        "<th rowspan=2>Bikes<br />Left at<br />Valet</th>"
        "<th rowspan=2>Most<br />Bikes<br />at Once</th>"
        "</tr>"
    )
    print(
        "<tr>"
        # "<th>Date</th>"
        "<th>Open</th><th>Close</th>"
        "<th>Rglr</th><th>Ovrsz</th><th>Total</th>"
        # "<th>Left</th>"
        # "<th>Fullest</th>"
        "</tr>"
    )
    for row in dbrows:
        date_link = selfref(what="one_day_tags", qdate=row.date)
        max_parked_col = max(0, 255 - int(row.ttl * row.ttl * max_parked_factor))
        max_full_col = max(0, 255 - int(row.most_bikes*row.most_bikes * max_full_factor))
        max_left_col = max(0, min(255 - int(row.extra * max_left_factor),255))

        print(
            f"<tr>"
            f"<td><a href='{date_link}'>{row.date}</a></td>"
            f"<td>{row.opened}</td><td>{row.closed}</td>"
            f"<td>{row.reg}</td><td>{row.ovr}</td><td style='background-color: rgb({max_parked_col},255,{max_parked_col})'>{row.ttl}</td>"
            f"<td style='background-color: rgb(255,{max_left_col},{max_left_col})'>{row.extra}</td>"
            f"<td style='background-color: rgb({max_full_col},255,{max_full_col})'>{row.most_bikes}</td>"
            "</tr>"
        )
    print(" </table>")


def lost_tags(ttdb: sqlite3.Connection):
    too_many = 10
    curs = ttdb.cursor()
    rows = curs.execute(
        "select tag,date,time_in from visit "
        f"where date not in (select date from day where leftover > {too_many}) "
        'and (time_out is null or time_out = "")'
        # "and date < strftime('%Y-%m-%d') "
        "order by date desc;"
    ).fetchall()

    # print("<pre>")
    print("<h1>Tags of abandoned bikes</h1>")
    print("<ul>")
    print("<li>Listed newest to oldest</li>")
    print(
        f"<li>Excludes dates with more than {too_many} supposed leftovers</li>"
    )
    print(
        "<li>Tags might have been returned to use after the dates listed</li>"
    )
    print("</ul>")

    print("<table>")
    print("<style>td {text-align: left;}</style>")
    print("<tr><th>Tag</th><th>Last check-in</th></tr>")
    for row in rows:
        tag = TagID(row[0])
        in_date = row[1]
        in_time = row[2]
        tag_link = selfref(what="last_use", qtag=tag)
        date_link = selfref(what="one_day_tags", qdate=in_date)

        print(
            f"<tr><td>"
            f"<a href='{tag_link}'>{tag.cased}</a>"
            "</td>"
            f"<td><a href='{date_link}'>{in_date}</a> {in_time}</td></tr>"
        )
    print(" </table>")


def one_day_tags_report(ttdb: sqlite3.Connection, whatday: str = ""):
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
        except ValueError:
            error_out("Bad date. Use YYYY-MM-DD or 'today' or 'yesterday'.")

    rows = (
        ttdb.cursor()
        .execute(
            "select tag,time_in,time_out,duration from visit "
            f"where date = '{thisday}' "
            "order by time_in desc;"
        )
        .fetchall()
    )

    visits = {}
    for row in rows:
        tag = TagID(row[0])
        if not tag:
            continue
        v: db.VisitRow = db.VisitRow()
        v.tag = tag
        v.time_in = VTime(row[1])
        v.time_out = VTime(row[2])
        v.duration = VTime(row[3])
        visits[tag] = v

    print("<pre>")
    if not visits:
        print(f"No activity recorded for {thisday}")
        exit()
    print(f"Tags for {thisday}")
    print("-------------------")
    print(
        f"- Latest recorded event this day is {db.db_latest_time(database,thisday).short}"
    )
    print(
        "- Where no check-out time exists, duration is estimated\n  assuming bike is at valet until the end of the day"
    )
    print()
    print("BIKE   --IN- -OUT-  DURTN")
    for tag in sorted(visits.keys()):
        v: db.VisitRow = visits[tag]
        print(
            f"{padval(tag,6)} {padval(v.time_in.tidy,5)} {padval(v.time_out.tidy,5)}  {v.duration.tidy}"
        )
    print("</pre></body></html>")


def datafile(ttdb: sqlite3.Connection, date: str = ""):
    """Print a reconstructed datafile for the given date."""
    thisday = whatday(date)
    if not thisday:
        bad_date(date)

    print("<pre>")

    day = db.db2day(ttdb, thisday)
    print(f"# TagTracker datafile for {thisday}")
    print(
        f"# Reconstructed   on {datetime.datetime.today().strftime('%Y-%m-%d %H:%M')}"
    )
    print(f"{df.HEADER_VALET_DATE} {day.date}")
    print(f"{df.HEADER_VALET_OPENS} {day.opening_time}")
    print(f"{df.HEADER_VALET_CLOSES} {day.closing_time}")
    print(f"{df.HEADER_BIKES_IN}")
    for tag, atime in day.bikes_in.items():
        print(f"  {tag.lower()},{atime}")
    print(f"{df.HEADER_BIKES_OUT}")
    for tag, atime in day.bikes_out.items():
        print(f"  {tag.lower()},{atime}")
    print(f"{df.HEADER_REGULAR}")
    print(f"{df.HEADER_OVERSIZE}")
    print(f"{df.HEADER_RETIRED}")
    print(f"{df.HEADER_COLOURS}")
    for col, name in day.colour_letters.items():
        print(f"  {col},{name}")


def whatday(maybe_day: str = "today") -> str:
    """Returns mayebday as a YYYY-MM-DD string."""
    if maybe_day.lower() == "yesterday":
        # yesterday
        day = datetime.datetime.today() - datetime.timedelta(1)
        thisday = day.strftime("%Y-%m-%d")
    elif maybe_day.lower() == "today":
        # today
        thisday = datetime.datetime.today().strftime("%Y-%m-%d")
    else:
        r = re.fullmatch(r"(\d\d\d\d)[-/]?(\d\d)[-/]?(\d\d)", maybe_day)
        if not r:
            return ""
        try:
            day = datetime.datetime.strptime(
                f"{r.group(1)}-{r.group(2)}-{r.group(3)}", "%Y-%m-%d"
            )
            thisday = day.strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return thisday


def bad_date(bad_date: str = ""):
    """Print message about bad date & exit."""
    error_out(
        f"Bad date '{untaint(bad_date)}'. "
        "Use YYYY-MM-DD or 'today' or 'yesterday'."
    )


def audit_report(ttdb: sqlite3.Connection, thisday: str, whattime: VTime):
    """Print audit report."""
    if not thisday:
        bad_date(thisday)
    print("<pre>")
    day = db.db2day(ttdb, thisday)
    rep.audit_report(day, [VTime(whattime)])


def one_day_chart(ttdb: sqlite3.Connection, date: str):
    """One-day chart."""
    thisday = whatday(date)
    if not thisday:
        bad_date(date)
    print("<pre>")
    rep.full_chart(db.db2day(ttdb, thisday), ["now"])


def one_day_busy_graph(ttdb: sqlite3.Connection, date: str):
    """One-day chart."""
    thisday = whatday(date)
    if not thisday:
        bad_date(date)
    print("<pre>")
    rep.busy_graph(db.db2day(ttdb, thisday), ["now"])


def busyness_report(ttdb: sqlite3.Connection, thisday: str, qtime: VTime):
    """One-day busy report."""
    if not thisday:
        bad_date(thisday)
    print("<pre>")
    rep.busyness_report(db.db2day(ttdb, thisday), [qtime])


# =================================================================
print("Content-type: text/html\n\n\n")

TagID.uc(cfg.TAGS_UPPERCASE)

DBFILE = "/fs/sysbits/tagtracker/proddata/cityhall_bikevalet.db"
database = create_connection(DBFILE)

# Parse query parameters from the URL if present
query_string = untaint(os.environ.get("QUERY_STRING", ""))
print("<pre>")
print(f"export QUERY_STRING='{query_string}'")
print(f"export SERVER_PORT={os.environ.get('SERVER_PORT')}")
print("</pre>")
query_params = urllib.parse.parse_qs(query_string)
what = query_params.get("what", [""])[0]
what = what if what else "overview"
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
form(database, default_what=what, default_date=maybedate, default_tag=tag)
if not what:
    exit()
if what == "last_use":
    one_tag_history_report(database, tag)
elif what == "overview":
    overview_report(database)
elif what == "abandoned":
    lost_tags(database)
elif what == "one_day_tags":
    one_day_tags_report(database, qdate)
elif what == "datafile":
    datafile(database, qdate)
elif what == "audit":
    audit_report(database, qdate, qtime)
elif what == "busyness":
    busyness_report(database, qdate, qtime)
elif what == "chart":
    one_day_chart(database, qdate)
elif what == "busy-graph":
    one_day_busy_graph(database, qdate)
else:
    error_out(f"Unknown request: {untaint(what)}")
    exit(1)
