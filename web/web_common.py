#!/usr/bin/env python3
"""Common functions for GI scripts for TagTracker reports.

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

import sys
import os
import sqlite3
from dataclasses import dataclass, field
import copy
import urllib
from datetime import datetime, timedelta


from web.web_base_config import SITE_NAME
import web.web_base_config as wcfg

# from tt_conf import SITE_NAME
from common.tt_time import VTime
from common.tt_tag import TagID
import common.tt_dbutil as db
import common.tt_util as ut
from common.tt_daysummary import DayTotals
from common.get_version import get_version_info

# from common.tt_trackerday import TrackerDay
# from common.tt_daysummary import DaySummary, PeriodDetail, MomentDetail, DayTotals


# Set up debugging .. maybe
if "TAGTRACKER_DEBUG" in os.environ:
    import cgitb

    cgitb.enable()


WHAT_OVERVIEW = "Ov"
WHAT_BLOCKS = "Blk"
WHAT_OVERVIEW_DOW = "OvD"
WHAT_BLOCKS_DOW = "BlkD"
WHAT_ONE_DAY = "1D"
WHAT_ONE_DAY_FREQUENCIES = "1Q"
WHAT_DATA_ENTRY = "DE"
WHAT_DATAFILE = "DF"
WHAT_TAGS_LOST = "TL"
WHAT_TAG_HISTORY = "TH"
WHAT_DETAIL = "Dt"
WHAT_SUMMARY = "Sm"
WHAT_SUMMARY_FREQUENCIES = "SQ"
WHAT_AUDIT = "Au"
WHAT_DATERANGE = "PS"
WHAT_DATERANGE_FOREVER = "pF"
WHAT_DATERANGE_YEAR = "pY"
WHAT_DATERANGE_QUARTER = "pQ"
WHAT_DATERANGE_MONTH = "pM"
WHAT_DATERANGE_WEEK = "pW"
WHAT_DATERANGE_CUSTOM = "pC"
WHAT_ESTIMATE_VERBOSE="EstV"

# These constants are used to manage how report columns are sorted.
SORT_TAG = "tag"
SORT_DATE = "date"
SORT_TIME_IN = "time_in"
SORT_TIME_OUT = "time_out"
SORT_DAY = "day"
SORT_DURATION = "duration"
SORT_LEFTOVERS = "leftovers"
SORT_FULLNESS = "fullness"
SORT_PARKED = "parked"
SORT_OPEN = "open"
SORT_CLOSE = "close"
SORT_TEMPERATURE = "temperature"
SORT_PRECIPITATAION = "precipitation"

ORDER_FORWARD = "forward"
ORDER_REVERSE = "reverse"

# Special values related to 'pages_back' handling
NAV_NO_BUTTON = -1
NAV_MAIN_BUTTON = -2


class WebAuth:
    """Manage aspects of web/data authorization.

    I might want to ask these kinds of questions or store this data:
        Can this web user see this data-org's data?
        What is the name of this user-org?  Data-org?
        What 'where' clause can I use/add to filter what this user-org
        can see?

    For right now seems reasonable to limit to a single orgsite

    """

    def __init__(self):
        self.user_org_id: int = None
        self.user_org_handle: str = None
        self.user_org_name: str = None

        self.visible_org_ids: list = None

        self.visible_orgsite_ids: list = None
        self.visible_orgsite_handles: list = None
        self.visible_orgsite_names: list = None

        self.org_info: dict = None
        self.orgsite_info: dict = None

        pass

    def owner_org(self):
        pass

    def user_org(self):
        pass

    def orgsite_choices(self, user_org) -> list[int]:
        """Return list of orgsite choices visible to this user_org."""

    def orgsite_where(
        self, user_org_id, data_orgsite_id, table: str, standalone_clause: bool = False
    ) -> str:
        """Return 'WHERE ... or 'AND ... to filter what allowed to see.

        E.g. WHERE DAY.ORGISTE = id
        or AND VISIT.DAY_ID in (id,id.id) AND DAY.ORGSITE_ID IN (id,id id)

        Looks in ORG table to get list of data orgs this user_org can see.
        Create a list of orgsite ids this user can see.
        """


def test_dow_parameter(dow_parameter: str, list_ok: bool = False):
    """Check if dow_parameter is ok."""
    if list_ok:
        testme = dow_parameter.split(",")
    else:
        testme = dow_parameter
    for day in testme:
        if day not in [str(i) for i in range(1, 8)]:
            error_out(f"bad iso dow, need 1..7, not '{ut.untaint(dow_parameter)}'")


def titleize(title: str = "") -> str:
    """Puts SITE_NAME in front of title and makes it pretty."""
    name = SITE_NAME or "Bike Parking Service"
    if not title:
        return name
    return f"{SITE_NAME} {title}"


def called_by_self() -> bool:
    """Return True if this script was called by itself."""
    referer = os.environ.get("HTTP_REFERER")
    if not referer:
        return False
    base_url = referer.split("?", 1)[0]

    request_scheme = os.environ.get("REQUEST_SCHEME")
    http_host = os.environ.get("HTTP_HOST")
    script_name = os.environ.get("SCRIPT_NAME")
    expected_url = f"{request_scheme}://{http_host}{script_name}"

    return expected_url == base_url


def main_page_button() -> str:
    """Make a button to take a person to the main page."""
    target = selfref()
    button = f"<button onclick=window.location.href='{target}';>Main</button>"
    return button


def back_button(pages_back: int) -> str:
    """Make the 'back' button."""
    return f"<button onclick='goBack({pages_back})'>Back</button>"


def main_and_back_buttons(pages_back: int) -> str:
    """Make a button that is  the main_page_button(), back_button(), or nothing."""
    if pages_back == NAV_MAIN_BUTTON:
        return main_page_button()
    if pages_back == NAV_NO_BUTTON:
        return ""
    if called_by_self() and pages_back > 0:
        return back_button(pages_back)
    else:
        return main_page_button()

def increment_pages_back(pages_back:int) -> int:
    """Increments pages_back but without altering any
    of the pages_back magic values
    """
    if pages_back in (NAV_MAIN_BUTTON,NAV_NO_BUTTON):
        return pages_back
    else:
        return pages_back + 1

def resolve_date_range(
    ttdb: sqlite3.Connection,
    *,
    orgsite_id: int = 1,
    start_date: str = "",
    end_date: str = "",
    today: str = "today",
    db_limits=None,
) -> tuple[str, str, str, str]:
    """Return effective and default date ranges for reports.

    The default range spans from max(earliest day in DB, one year ago) to today (or
    the latest day in DB if earlier). Any provided start/end dates are normalised,
    clamped to available data, and ensured to remain in-order.
    """

    today_str = ut.date_str(today) if today else ""
    if not today_str:
        today_str = datetime.today().strftime("%Y-%m-%d")

    year_ago = (
        datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=365)
    ).strftime("%Y-%m-%d")

    if db_limits is None:
        db_start, db_end = db.fetch_date_range_limits(
            ttdb,
            orgsite_id=orgsite_id,
        )
    else:
        db_start, db_end = db_limits

    default_end_candidates = [today_str]
    if db_end:
        default_end_candidates.append(db_end)
    default_end = min(default_end_candidates)

    default_start_candidates = [year_ago]
    if db_start:
        default_start_candidates.append(db_start)
    default_start = max(default_start_candidates)

    if default_start > default_end:
        default_start = default_end

    requested_start = ut.date_str(start_date) if start_date else ""
    requested_end = ut.date_str(end_date) if end_date else ""

    resolved_start = requested_start or default_start
    resolved_end = requested_end or default_end

    if db_start:
        resolved_start = max(resolved_start, db_start)
    if db_end:
        resolved_end = min(resolved_end, db_end)

    if resolved_start > resolved_end:
        resolved_start = resolved_end

    return resolved_start, resolved_end, default_start, default_end


class URLParameters:
    """All the things that get read from the URL query string.

    How the sorts works:
        it is a list of booleans that indicates sort direction
        for the indexed columns. True=='forward', False='reverse'.
        What forward/reverse mean, and which columns numbers
        correspond to which columns, is up to the routine that
        uses them.   If there's nothing in the URL than it is
        all 'True', is is any col not specified when constructing
        the URL.
    """

    _DEFAULT_SORT_COLUMN = "*"
    _EPOCH_DATE = datetime(1970, 1, 1)
    _ACTION_KEY = "A"
    _QTAG_KEY = "tg"
    _QDATE_KEY = "dt"
    _QDOW_KEY = "dw"
    _QTIME_KEY = "tm"
    _PAGES_BACK_KEY = "pg"
    _SORT_DIRECTIONS_KEY = "sd"
    _SORT_COLUMN_KEY = "sc"

    def __init__(
        self,
        action=None,
        qtag=None,
        qdate=None,
        qdow=None,
        qtime=None,
        pages_back=None,
        sort_directions=None,
        sort_column=None,
    ):
        self.action = action
        self.qtag = qtag
        self.qdate = qdate
        self.qdow = qdow
        self.qtime = qtime
        self.pages_back = pages_back
        self.sort_directions = sort_directions
        self.sort_column = sort_column

    def _fetch_query_string(self):
        query_string = ut.untaint(os.environ.get("QUERY_STRING", ""))
        query_params = urllib.parse.parse_qs(query_string)
        self.action = query_params.get("what", [WHAT_SUMMARY])[0]
        self.qtag = TagID(query_params.get("tag", [""])[0])
        self.qdate = ut.date_str(query_params.get("date", [""])[0])
        self.qtime = VTime(query_params.get("time", [""])[0])

        # dow_parameter = query_params.get("dow", [""])[0]
        # if dow_parameter and dow_parameter not in [str(i) for i in range(1, 8)]:
        #     cc.error_out(f"bad iso dow, need 1..7, not '{ut.untaint(dow_parameter)}'")
        # if not dow_parameter:
        #     # If no day of week, set it to today.
        #     dow_parameter = str(
        #         datetime.datetime.strptime(ut.date_str("today"), "%Y-%m-%d").strftime("%u")
        #     )
        # sort_by = query_params.get("sort", [""])[0]
        # sort_direction = query_params.get("dir", [""])[0]

        pages_back: str = query_params.get("back", "1")[0]
        self.pages_back: int = int(pages_back) if pages_back.isdigit() else 1

    def make_query_string(self) -> str:
        """Encode URLParameters into a string for URL."""

        def one_parameter(parmlist: list, key: str, value):
            if value is not None:
                parmlist.append(f"{key}={value}")

        parms = []
        one_parameter(parms, self._ACTION_KEY, self.action)
        one_parameter(parms, self._QDATE_KEY, self.encode_date(self.qdate))
        one_parameter(parms, self._QTIME_KEY, self.qtime)
        one_parameter(parms, self._QTAG_KEY, self.qtag)
        one_parameter(parms, self._QDOW_KEY, self.qdow)
        one_parameter(parms, self._SORT_COLUMN_KEY, self.sort_column)  # might be 0
        one_parameter(
            parms, self._SORT_DIRECTIONS_KEY, self.sort_directions
        )  # might be 0
        one_parameter(parms, self._PAGES_BACK_KEY, self.pages_back)

        qstr = "?" + "&".join(parms) if parms else ""
        return qstr

    @classmethod
    def encode_date(cls, date_string):
        if date_string is None:
            return None
        try:
            days_since_epoch = (
                datetime.strptime(date_string, "%Y-%m-%d") - cls._EPOCH_DATE
            ).days
            return hex(days_since_epoch).lstrip("-0x")
        except ValueError:
            return f"Invalid date '{date_string}', expected YYYY-MM-DD."

    @classmethod
    def decode_date(cls, hex_string):
        if not hex_string:
            return None
        try:
            days_since_epoch = int(hex_string, 16)
            target_date = cls._EPOCH_DATE + timedelta(days=days_since_epoch)
            return target_date.strftime("%Y-%m-%d")
        except (ValueError, OverflowError):
            return f"Invalid hex date value '{hex_string}'."


def _resolve_script_path(script_name: str) -> str:
    """Return a sanitized script path for links within the same host."""

    current_script = ut.untaint(os.environ.get("SCRIPT_NAME", ""))
    if not script_name:
        return current_script

    clean_name = ut.untaint(script_name)
    if clean_name.startswith("/"):
        return clean_name

    if "/" not in current_script:
        return clean_name

    base_dir = current_script.rsplit("/", 1)[0]
    return f"{base_dir}/{clean_name}"


def _build_query_params(
    what: str = "",
    qdate: str = "",
    qtime: str = "",
    qtag: str = "",
    qdow: str = "",
    qsort: str = "",
    qdir: str = "",
    text_note: str = "",
    start_date: str = "",
    end_date: str = "",
    pages_back=None,
) -> str:
    """Create a query string fragment from the standard parameter set."""

    params = {
        "what": what,
        "date": qdate,
        "start_date": start_date,
        "end_date": end_date,
        "time": qtime,
        "tag": qtag,
        "dow": qdow,
        "sort": qsort,
        "dir": qdir,
        "text": text_note,
        # pages_back might legitimately be 0
        "back": pages_back if pages_back is not None else "",
    }

    filtered_params = {key: value for key, value in params.items() if value}
    if not filtered_params:
        return ""

    return "&".join(f"{key}={value}" for key, value in filtered_params.items())


def make_url(
    script_name: str,
    *,
    what: str = "",
    qdate: str = "",
    qtime: str = "",
    qtag: str = "",
    qdow: str = "",
    qsort: str = "",
    qdir: str = "",
    text_note: str = "",
    start_date: str = "",
    end_date: str = "",
    pages_back=None,
) -> str:
    """Return a URL for the given script on this host with the provided parameters."""

    target = _resolve_script_path(script_name)
    query = _build_query_params(
        what=what,
        qdate=qdate,
        qtime=qtime,
        qtag=qtag,
        qdow=qdow,
        qsort=qsort,
        qdir=qdir,
        text_note=text_note,
        start_date=start_date,
        end_date=end_date,
        pages_back=pages_back,
    )

    if not query:
        return target

    return f"{target}{ut.untaint('?' + query)}"


def selfref(
    what: str = "",
    qdate: str = "",
    qtime: str = "",
    qtag: str = "",
    qdow: str = "",
    qsort: str = "",
    qdir: str = "",
    text_note: str = "",
    start_date: str = "",
    end_date: str = "",
    pages_back=None,
) -> str:
    """Return a self-reference with the given parameters."""

    script_name = ut.untaint(os.environ.get("SCRIPT_NAME", ""))
    return make_url(
        script_name,
        what=what,
        qdate=qdate,
        qtime=qtime,
        qtag=qtag,
        qdow=qdow,
        qsort=qsort,
        qdir=qdir,
        text_note=text_note,
        start_date=start_date,
        end_date=end_date,
        pages_back=pages_back,
    )


def style() -> str:
    """Return a CSS stylesheet as a string."""
    style_str = """
        <style>
            html {
                font-family: sans-serif;
            }

            .general_table {
                border-collapse: collapse;
                border: 2px solid rgb(200, 200, 200);
                letter-spacing: 1px;
                font-size: 0.8rem;
            }

            .general_table td, .general_table th {
                border: 1px solid rgb(190, 190, 190);
                padding: 4px 6px;
                text-align: center; /* Center-align all td and th by default */
            }

            .general_table th {
                background: rgb(235, 235, 235);
            }

            .general_table td:first-child {
                text-align: left; /* Left-align the first column in each row */
            }

            .general_table tr:nth-child(even) td {
                background: rgb(250, 250, 250);
            }

            .general_table tr:nth-child(odd) td {
                background: rgb(245, 245, 245);
            }

            caption {
                padding: 10px;
            }
        </style>

        """
    return style_str


def error_out(msg: str = ""):
    if msg:
        print(msg)
    else:
        print("Bad or unknown parameter")
    sys.exit(1)


def show_help():
    print("<pre>\n")
    print("There is no help here. Read the code.")


def padval(val, length: int = 0) -> str:
    valstr = str(val)
    if length < len(valstr):
        length = len(valstr)
    pad = " " * (length - len(valstr))
    if isinstance(val, str):
        return f"{valstr}{pad}"
    else:
        return f"{pad}{valstr}"


def bad_date(bad_date_str: str = ""):
    """Print message about bad date & exit."""
    error_out(
        f"Bad date '{ut.untaint(bad_date_str)}'. "
        "Use YYYY-MM-DD or 'today' or 'yesterday'."
    )


# FIXME: Use PeriodDetail?
@dataclass
class SingleBlock:
    """Data about a single timeblock."""

    num_in: int = 0
    num_out: int = 0
    # activity: int = 0
    full: int = 0
    so_far: int = 0

    @property
    def activity(self) -> int:
        return self.num_in + self.num_out


# FIXME: Use DaysTotal (or whatever it's called?)
@dataclass
class BlocksSummary:
    """Summary of all blocks for a single day (or all days)."""

    total_num_in: int = 0
    max_num_in: int = 0
    total_num_out: int = 0
    max_num_out: int = 0
    total_activity: int = 0
    max_activity: int = 0
    ## max_full: int = 0 # Don't need this, it's max full in the days summary


_allblocks = {t: SingleBlock() for t in range(6 * 60, 24 * 60, 30)}


# # FIXME: surely use a DaysTotal or whatever tho DaysTotal will need stats.
@dataclass
class SingleDay:
    """Data about a single day."""

    date: str = ""
    dow: int = None
    valet_open: VTime = ""
    valet_close: VTime = ""
    total_bikes: int = 0
    regular_bikes: int = 0
    oversize_bikes: int = 0
    max_bikes: int = 0
    max_bikes_time: VTime = ""
    registrations: int = 0
    temperature: float = None
    precip: float = 0
    dusk: VTime = ""
    leftovers: int = 0  # as reported
    # leftovers_calculated: int = 0
    blocks: dict = field(default_factory=lambda: copy.deepcopy(_allblocks))
    min_stay = None
    max_stay = None
    mean_stay = None
    median_stay = None
    modes_stay = []
    modes_occurences = 0

    # @property
    # def leftovers_reported(self) -> int:
    #     return self.leftovers


def get_days_data(
    ttdb: sqlite3.Connection,
    min_date: str = "",
    max_date: str = "",
) -> list[DayTotals]:
    """Create the list of totals about a set of days."""

    orgsite_id = 1  # FIXME: hardcoded orgsite_id
    cursor = ttdb.cursor()
    day_ids = db.fetch_day_id_list(
        cursor=cursor, orgsite_id=orgsite_id, min_date=min_date, max_date=max_date
    )

    totals_list = []
    for day_id in day_ids:
        # day = DayTotals()
        day = db.fetch_day_totals(cursor=cursor, day_id=day_id)
        totals_list.append(day)
    return totals_list

    # where = ""
    # if min_date:
    #     where += f" DAY.date >= '{min_date}'"
    # if max_date:
    #     where += f"{' AND' if where else ''} DAY.date <= '{max_date}'"
    # where = f"WHERE{where}" if where else ""

    # sql = f"""
    #     SELECT
    #         DAY.date,
    #         DAY.weekday dow,
    #         DAY.time_open AS valet_open,
    #         DAY.time_closed AS valet_close,
    #         DAY.num_regular AS regular_bikes,
    #         DAY.num_oversize AS oversize_bikes,
    #         DAY.num_combined AS total_bikes,
    #         DAY.num_fullest_combined AS max_bikes,
    #         DAY.time_fullest_combined AS max_bikes_time,
    #         DAY.bikes_registered,
    #         DAY.precipitation AS precip,
    #         DAY.max_max_temperature AS temperature,
    #         DAY.num_leftover AS leftovers
    #     FROM DAY
    #     {where}
    #     GROUP BY DAY.date, DAY.time_open, DAY.time_closed, DAY.num_regular, DAY.num_oversize,
    #         DAY.num_combined, DAY.num_fullest_combined, DAY.time_fullest_combined, DAY.bikes_registered, DAY.precipitation,
    #         DAY.max_max_temperature, DAY.num_leftover;
    #     """

    # dbrows = db.db_fetch(ttdb, sql)
    # # There mught be nothing.
    # ##ut.squawk(f"{sql=}\n")
    # if not dbrows:
    #     return [SingleDay()]
    # # Look for properties in common (these are the ones we will copy over)
    # shared_properties = set(
    #     prop
    #     for prop in dbrows[0].__dict__.keys()
    #     if prop[0] != "_" and prop in SingleDay.__annotations__
    # )
    # days = []
    # for r in dbrows:
    #     # Copy any commmon properties
    #     d = SingleDay()
    #     for prop in shared_properties:
    #         setattr(d, prop, getattr(r, prop))
    #     # Fix up any that are to be VTimes
    #     d.valet_open = VTime(d.valet_open)
    #     d.valet_close = VTime(d.valet_close)
    #     d.max_bikes_time = VTime(d.max_bikes_time)
    #     d.dusk = VTime(d.dusk)

    #     days.append(d)
    # return days


def get_common_properties(obj1: object, obj2: object) -> list:
    """Return a list of callable properties common to the two objects (but not _*)."""
    common_properties = set(
        prop
        for prop in obj1.__dict__
        if not prop.startswith("_")
        and getattr(obj2, prop, None) is not None
        and not callable(getattr(obj1, prop))
    )
    return list(common_properties)


def copy_properties(
    source: object, target: object, common_properties: list = None
) -> None:
    """Copy common non-callable properties from source to target (but not _*).

    If common_properties exists, it will use that.  If not, it will figure
    them out.
    """
    if common_properties is None:
        common_properties = get_common_properties(source, target)

    for prop in common_properties:
        setattr(target, prop, getattr(source, prop))


def fetch_daily_visit_data(ttdb: sqlite3.Connection, in_or_out: str) -> list[db.DBRow]:
    sel = f"""
        select
            date,
            round(2*(julianday(time_{in_or_out})-julianday('00:15'))*24,0)/2 block,
            count(time_{in_or_out}) bikes_{in_or_out}
        from visit
        group by date,block;
    """
    return db.db_fetch(ttdb, sel)


def incorporate_blocks_data(ttdb: sqlite3.Connection, days: list[SingleDay]):
    """Fetch visit data to complete the days list.

    Calculates the blocks info for the days.
    """

    # Will need to be able to index into the days table by date
    days_dict = {d.date: d for d in days}
    # Fetch visits data
    visitrows_in = fetch_daily_visit_data(ttdb, in_or_out="in")
    visitrows_out = fetch_daily_visit_data(ttdb, in_or_out="out")

    # Intermediate dictionaries
    ins = {
        visitrow.date: {VTime(visitrow.block * 60): visitrow.bikes_in}
        for visitrow in visitrows_in
        if visitrow.date and visitrow.block and visitrow.bikes_in is not None
    }

    outs = {
        visitrow.date: {VTime(visitrow.block * 60): visitrow.bikes_out}
        for visitrow in visitrows_out
        if visitrow.date and visitrow.block and visitrow.bikes_out is not None
    }

    # Process data for each date
    for thisdate in sorted(days_dict.keys()):
        full_today, so_far_today = 0, 0

        # Iterate through blocks for the current date
        for block_key in sorted(days_dict[thisdate].blocks.keys()):
            thisblock = days_dict[thisdate].blocks[block_key]

            # Update block properties based on input and output data
            thisblock.num_in = ins[thisdate].get(block_key, 0)
            thisblock.num_out = outs.get(thisdate, {}).get(block_key, 0)

            # Update cumulative counters
            so_far_today += thisblock.num_in
            thisblock.so_far = so_far_today

            full_today += thisblock.num_in - thisblock.num_out
            thisblock.full = full_today


def get_blocks_summary(days: list[SingleDay]) -> BlocksSummary:
    """Find overall maximum values across all blocks."""
    summ = BlocksSummary()
    for day in days:
        for block in day.blocks.values():
            block: SingleBlock
            summ.total_num_in += block.num_in
            summ.total_num_out += block.num_out
            block_activity = block.num_in + block.num_out
            summ.max_num_in = max(summ.max_num_in, block.num_in)
            summ.max_num_out = max(summ.max_num_out, block.num_out)
            summ.total_activity += block.num_in + block_activity
            summ.max_activity = max(summ.max_activity, block_activity)

    return summ

def html_head(
    title: str = "TagTracker",
):
    print(
        f"""
        <html><head>
        <title>{title}</title>
        <meta name="format-detection" content="telephone=no"/>
        <meta charset='UTF-8'>
        {style()}
        <script>
          // (this fn courtesy of chatgpt)
          function goBack(pagesToGoBack = 1) {{
            window.history.go(-pagesToGoBack);
          }}
        </script>
        </head>"""
    )
    ##print(cc.style())
    print("<body>")


def webpage_footer(ttdb: sqlite3.Connection, elapsed_time):
    """Prints the footer for each webpage"""

    print("<pre>")

    if wcfg.DATA_OWNER:
        data_note = (
            wcfg.DATA_OWNER if isinstance(wcfg.DATA_OWNER, list) else [wcfg.DATA_OWNER]
        )
        for line in data_note:
            print(line)
        print()

    print( f"Elapsed time for query: {elapsed_time:.1f} seconds.")

    print(db.db_latest(ttdb))

    print(f"TagTracker version {get_version_info()}")


