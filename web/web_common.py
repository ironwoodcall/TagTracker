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
from dataclasses import dataclass, field, fields
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

# Set up debugging .. maybe
if "TAGTRACKER_DEBUG" in os.environ:
    import cgitb

    cgitb.enable()


# Caution: the 'audit' CGI script hard-code sets its CGI query string
# with the parameter name and parameter value for the audit report.
# Changes made of those here need to be reflected in the CGI script.
WHAT_AUDIT = "Au"  # See note above.
WHAT_OVERVIEW = "Ov"
WHAT_BLOCKS = "Blk"
WHAT_OVERVIEW_DOW = "OvD"
WHAT_ONE_DAY = "1D"
WHAT_ONE_DAY_FREQUENCIES = "1Q"
WHAT_TAGS_LOST = "TL"
WHAT_TAG_HISTORY = "TH"
WHAT_DETAIL = "Dt"
WHAT_SUMMARY = "Sm"
WHAT_SUMMARY_FREQUENCIES = "SQ"
WHAT_COMPARE_RANGES = "Cmp"
WHAT_DATERANGE_DETAIL = "DDet"
WHAT_DATERANGE = "P"
WHAT_DATERANGE_FOREVER = "pF"
WHAT_DATERANGE_YEAR = "pY"
WHAT_DATERANGE_QUARTER = "pQ"
WHAT_DATERANGE_MONTH = "pM"
WHAT_DATERANGE_WEEK = "pW"
WHAT_DATERANGE_CUSTOM = "pC"
WHAT_ESTIMATE_VERBOSE = "EstV"
WHAT_DOWNLOAD_CSV = "d.v"
WHAT_DOWNLOAD_DB = "d.b"
WHAT_VALID_VALUES = {
    WHAT_OVERVIEW,
    WHAT_BLOCKS,
    WHAT_OVERVIEW_DOW,
    WHAT_ONE_DAY,
    WHAT_ONE_DAY_FREQUENCIES,
    WHAT_TAGS_LOST,
    WHAT_TAG_HISTORY,
    WHAT_DETAIL,
    WHAT_SUMMARY,
    WHAT_SUMMARY_FREQUENCIES,
    WHAT_AUDIT,
    WHAT_COMPARE_RANGES,
    WHAT_DATERANGE,
    # WHAT_DATERANGE_FOREVER,
    # WHAT_DATERANGE_YEAR,
    # WHAT_DATERANGE_QUARTER,
    # WHAT_DATERANGE_MONTH,
    # WHAT_DATERANGE_WEEK,
    # WHAT_DATERANGE_CUSTOM,
    WHAT_ESTIMATE_VERBOSE,
    WHAT_DOWNLOAD_CSV,
    WHAT_DOWNLOAD_DB,
    WHAT_DATERANGE_DETAIL,
}

# These constants are used to manage how report columns are sorted.
SORT_TAG = "tag"
SORT_DATE = "date"
SORT_TIME_IN = "ti"
SORT_TIME_OUT = "to"
SORT_DAY = "day"
SORT_DURATION = "dur"
SORT_LEFTOVERS = "left"
SORT_FULLNESS = "max"
SORT_PARKED = "parked"
SORT_OPEN = "open"
SORT_CLOSE = "close"
SORT_TEMPERATURE = "temp"
SORT_PRECIPITATAION = "precip"
SORT_VALID_VALUES = {
    SORT_TAG,
    SORT_DATE,
    SORT_TIME_IN,
    SORT_TIME_OUT,
    SORT_DAY,
    SORT_DURATION,
    SORT_LEFTOVERS,
    SORT_FULLNESS,
    SORT_PARKED,
    SORT_OPEN,
    SORT_CLOSE,
    SORT_TEMPERATURE,
    SORT_PRECIPITATAION,
}

ORDER_FORWARD = "down"
ORDER_REVERSE = "up"
ORDER_VALID_VALUES = {ORDER_FORWARD, ORDER_REVERSE}

# Special values related to 'pages_back' handling
NAV_NO_BUTTON = -1
NAV_MAIN_BUTTON = -2
NAV_VALID_VALUES = {NAV_NO_BUTTON, NAV_MAIN_BUTTON}


def error_out(msg: str = ""):
    """Give an error message and exit."""
    if msg:
        print(msg)
    else:
        print("Unspecified error condition.")
    print(f'<br><a href="{os.environ.get("SCRIPT_NAME", "")}">Go to main page</a>')

    sys.exit(1)


def test_dow_parameter(dow_parameter: str, list_ok: bool = True):
    """Check if dow_parameter is ok."""
    if list_ok:
        testme = dow_parameter.split(",")
    else:
        testme = dow_parameter
    for day in testme:
        if day not in [str(i) for i in range(1, 8)]:
            error_out(f"bad iso dow, need 1..7, not '{ut.untaint(dow_parameter)}'")


def titleize(title: str = "", subtitle: str = "") -> str:
    """Puts SITE_NAME in front of title and makes it pretty,
    including heading tags."""
    content = f"{SITE_NAME or 'Bike Parking Service'}"
    # Special case: if no title nor subtitle, just use site as h1
    if not title and not subtitle:
        return f"<h1>{content}</h1>"

    content = f"<h2>{content}</h2>"
    if title:
        content = f"{content}<h1>{title.capitalize()}</h1>"
    if subtitle:
        content = f"{content}<h2>{subtitle.capitalize()}</h2>"
    return content


def resolve_date_range(
    ttdb: sqlite3.Connection,
    *,
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


@dataclass
class ReportParameters:
    """A bundle containing all the reporting parameters (that would be in URL)."""

    # Caution: the 'audit' CGI script hard-code sets its CGI query string
    # with the parameter name and parameter value for the audit report.
    # Changes made of those here need to be reflected in the CGI script.
    what_report: str | None = field(default=None, metadata={"cgi": "what"})
    sched_open: VTime | None = field(default=None, metadata={"cgi": "sched_open"})
    sched_close: VTime | None = field(default=None, metadata={"cgi": "sched_close"})
    precipitation: float | None = field(default=None, metadata={"cgi": "precip"})
    temperature: float | None = field(default=None, metadata={"cgi": "temp"})
    start_date: str | None = field(default=None, metadata={"cgi": "start_date"})
    end_date: str | None = field(default=None, metadata={"cgi": "end_date"})
    dow: str | None = field(default=None, metadata={"cgi": "dow"})
    start_date2: str | None = field(default=None, metadata={"cgi": "start_date2"})
    end_date2: str | None = field(default=None, metadata={"cgi": "end_date2"})
    dow2: str | None = field(default=None, metadata={"cgi": "dow2"})
    sort_by: str | None = field(default=None, metadata={"cgi": "sort_by"})
    sort_direction: str | None = field(default=None, metadata={"cgi": "sort_direction"})
    tag: TagID | None = field(default=None, metadata={"cgi": "tag"})
    pages_back: int | None = field(default=None, metadata={"cgi": "pages_back"})

    @classmethod
    def _cgi_maps(cls) -> tuple[dict[str, str], dict[str, str]]:
        """Return (attr->cgi, cgi->attr) lookups for CGI serialization."""
        attr_to_cgi: dict[str, str] = {}
        cgi_to_attr: dict[str, str] = {}
        for param in fields(cls):
            cgi_name = param.metadata.get("cgi")
            if cgi_name:
                attr_to_cgi[param.name] = cgi_name
                cgi_to_attr[cgi_name] = param.name
        return attr_to_cgi, cgi_to_attr

    @classmethod
    def cgi_name(cls, attr_name: str) -> str:
        """Return the CGI parameter name for the given ReportParameters attribute."""
        attr_to_cgi, _ = cls._cgi_maps()
        if attr_name not in attr_to_cgi:
            raise AttributeError(f"Unknown ReportParameters field '{attr_name}'")
        return attr_to_cgi[attr_name]

    @classmethod
    def cgi_items(cls) -> tuple[tuple[str, str], ...]:
        """Return (cgi_name, attr_name) pairs for CGI-aware fields."""
        _, cgi_to_attr = cls._cgi_maps()
        return tuple(cgi_to_attr.items())

    def _set_as_what(self, property_name, maybe_value):
        """Assigns maybe_value to self.{property_name} if valid. Errors out if not."""
        if maybe_value not in WHAT_VALID_VALUES:
            error_out(f"Bad value for parameter {property_name}: '{maybe_value}'")
        # Assign 'maybe_value' to self's property called 'property_name'
        setattr(self, property_name, maybe_value)

    def _set_as_time(self, property_name, maybe_value):
        """Assigns maybe_value to self.{property_name} if valid. Errors out if not."""
        t = VTime(maybe_value)
        if not t:
            error_out(f"Bad time value for parameter {property_name}: '{maybe_value}'")
        # Assign 'maybe_value' to self's property called 'property_name'
        setattr(self, property_name, maybe_value)

    def _set_as_tagid(self, property_name, maybe_value):
        """Assigns maybe_value to self.{property_name} if valid. Errors out if not."""
        t = TagID(maybe_value)
        if not t:
            error_out(f"Bad tag value for parameter {property_name}: '{maybe_value}'")
        # Assign 'maybe_value' to self's property called 'property_name'
        setattr(self, property_name, maybe_value)

    def _set_as_date(self, property_name, maybe_value) -> bool:
        """Assigns maybe_value to self.{property_name} if valid date in YYYY-MM-DD format.
        Errors out and halts if invalid (e.g. wrong format, impossible date).
        """
        maybe_value = maybe_value.strip().lower()
        val = ut.date_str(maybe_value)
        if not val:
            error_out(
                f"Bad date value for parameter {property_name}: '{ut.untaint(maybe_value)}'"
            )
        setattr(self, property_name, maybe_value)

    def _set_as_float(self, property_name, maybe_value) -> bool:
        """Assigns maybe_value to self.{property_name} if valid float.
        Errors out and halts if invalid (does not represent a float).
        """
        # Normalize and check presence
        if maybe_value is None:
            error_out(f"Missing numeric value for parameter {property_name}")
        maybe_value = str(maybe_value).strip().lower()

        # Validate float
        try:
            val = float(maybe_value)
        except ValueError:
            error_out(
                f"Bad numeric value for parameter {property_name}: '{ut.untaint(maybe_value)}'"
            )

        # Assign validated float
        setattr(self, property_name, val)
        return True

    def _set_as_dow(self, property_name, maybe_value):
        """Assigns maybe_value to self.{property_name} if valid. Errors out if not.
        Recognizes:
            "1".."7" or a comma-delimited combination of those
            "weekday(s)" --> "1,2,3,4,5"
            "weekend(s)" --> "6,7"
            "", "all" --> "" (i.e. all days)
        On finish:
            'property_name' is set to "" or comma-delimited list of  ISO days of week;
            or (if error) then message has been given and has errored out.
        """

        val = ut.untaint((maybe_value or "").strip().lower())

        if val in ("weekday", "weekdays"):
            setattr(self, property_name, "1,2,3,4,5")
            return
        if val in ("weekend", "weekends"):
            setattr(self, property_name, "6,7")
            return

        # Allow empty string (means "no restriction")
        if val in ("", "all"):
            setattr(self, property_name, "")
            return

        # Check if it's a comma-separated list of ISO day numbers (1–7)
        parts = [p.strip() for p in val.split(",") if p.strip() != ""]
        if all(p.isdigit() and 1 <= int(p) <= 7 for p in parts):
            setattr(self, property_name, ",".join(parts))
            return

        # Not recognized as valid dow, error out
        error_out(f"Bad dow parameter for {property_name}: '{ut.untaint(maybe_value)}'")

    def _set_as_pages_back(self, property_name, maybe_value):
        """Assigns maybe_value to self.{property_name} if valid. Errors out if not.
        Recognizes:
            positive integer
            NAV_NO_BUTTON, NAV_MAIN_BUTTON (these are negative integer sentinels)
        On finish:
            'property_name' is set to maybe_value if valid; else errors out.
        """
        try:
            val = int(str(maybe_value).strip())
        except (ValueError, TypeError):
            error_out(
                f"Bad pages_back value for {property_name}: '{ut.untaint(maybe_value)}'"
            )

        if val >= 0 or val in NAV_VALID_VALUES:
            setattr(self, property_name, val)
            return

        error_out(
            f"Bad pages_back value for {property_name}: '{ut.untaint(str(maybe_value))}'"
        )

    def _set_as_sort_direction(self, property_name, maybe_value):
        """Tests if maybe_value is a valid sort direction (ORDER_FORWARD, ORDER_REVERSE).
        If valid, assigns to property_name.
        """
        val = str(maybe_value).strip()

        if val in ORDER_VALID_VALUES:
            setattr(self, property_name, val)
            return

        error_out(
            f"Bad sort direction for {property_name}: '{ut.untaint(maybe_value)}'"
        )

    def _set_as_sort_column(self, property_name, maybe_value):
        """Tests if maybe_value is a valid sort column (in set SORT_VALID_VALUES).
        If valid, assigns to property_name.
        """
        val = str(maybe_value).strip()

        if val in SORT_VALID_VALUES:
            setattr(self, property_name, val)
            return

        error_out(f"Bad sort column for {property_name}: '{ut.untaint(maybe_value)}'")

    _property_type_checks = {
        "what_report": _set_as_what,
        "sched_open": _set_as_time,
        "sched_close": _set_as_time,
        "start_date": _set_as_date,
        "end_date": _set_as_date,
        "dow": _set_as_dow,
        "start_date2": _set_as_date,
        "end_date2": _set_as_date,
        "dow2": _set_as_dow,
        "sort_by": _set_as_sort_column,
        "sort_direction": _set_as_sort_direction,
        "tag": _set_as_tagid,
        "pages_back": _set_as_pages_back,
        "precipitation": _set_as_float,
        "temperature": _set_as_float,
    }

    def __init__(
        self,
        # pylint:disable=unused-argument
        maybe_what_report: str = None,
        maybe_clock: VTime = None,
        maybe_start_date: str = None,
        maybe_end_date: str = None,
        maybe_dow: str = None,
        maybe_start_date2: str = None,
        maybe_end_date2: str = None,
        maybe_dow2: str = None,
        maybe_sort_by: str = None,
        maybe_sort_direction: str = None,
        maybe_tag: TagID = None,
        maybe_pages_back: int = None,
        # pylint:enable=unused-argument
    ):
        for arg_name, value in locals().items():
            if arg_name == "self" or not value:
                continue
            if not arg_name.startswith("maybe_"):
                continue
            property_name = arg_name[len("maybe_") :]
            self.set_property(property_name, value)

    def set_property(self, property_name, maybe_value):
        """Updates (or adds) property property_name to maybe_value.
        This is the place where the class asserts what properties require
         what kinds of checks (as date, as time, etc)."""
        if property_name not in self._property_type_checks:
            error_out(f"Call to set unrecognized property '{property_name}'")
        self._property_type_checks[property_name](self, property_name, maybe_value)

    def dump(self) -> str:
        """Return an HTML <pre> block listing property names and their values."""
        lines: list[str] = []
        for param in fields(self):
            lines.append(f"{param.name}: {getattr(self, param.name)!r}")
        return "<pre>\n" + "\n".join(lines) + "\n</pre>"


class CGIManager:
    """Owns interactions with CGI variables."""

    # Query parameter sanitizing
    SAFE_QUERY_CHRS = frozenset(
        " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:,-"
    )

    @classmethod
    def _validate_query_params(cls, query_parms: dict[str, list[str]]) -> None:
        """Ensure all provided query parameter values only contain allowed characters."""
        for key, values in query_parms.items():
            for value in values:
                if not value:
                    continue
                if any(char not in cls.SAFE_QUERY_CHRS for char in value):
                    error_out(
                        f"Invalid characters in parameter '{ut.untaint(str(key))}'"
                    )

    @classmethod
    def param_name(cls, property_name: str) -> str:
        """Return the CGI parameter name associated with ``property_name``."""
        return ReportParameters.cgi_name(property_name)

    @staticmethod
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

    @classmethod
    def cgi_to_params(cls) -> ReportParameters:
        param_dict = urllib.parse.parse_qs(os.environ.get("QUERY_STRING", ""))
        cls._validate_query_params(param_dict)

        params = ReportParameters()
        cgi_to_attr = dict(ReportParameters.cgi_items())

        for cgi_name, values in param_dict.items():
            if cgi_name not in cgi_to_attr:
                error_out(f"Unrecognized URL parameter '{cgi_name}'")

            target_property = cgi_to_attr[cgi_name]

            if not values:
                continue

            raw_value = values[0]
            if raw_value is None:
                continue
            value = raw_value.strip()
            if value == "":
                continue

            params.set_property(target_property, value)

        return params

    @classmethod
    def params_to_query_str(cls, params: ReportParameters) -> str:
        """Return the parameter string for an URL to the current script using
        the parameters in params."""
        mapping = cls.params_to_query_mapping(params)
        if not mapping:
            return ""

        segments = [f"{key}={value}" for key, value in mapping.items()]
        return f"?{'&'.join(segments)}"

    @classmethod
    def params_to_query_mapping(cls, params: ReportParameters) -> dict[str, str]:
        """Return a dict mapping CGI parameter names to their serialized values."""
        if params is None:
            return {}

        mapping: dict[str, str] = {}
        attr_to_cgi, _ = ReportParameters._cgi_maps()
        for attr_name, cgi_name in attr_to_cgi.items():
            value = getattr(params, attr_name, None)
            if value in (None, ""):
                continue
            mapping[cgi_name] = str(value)
        return mapping

    @classmethod
    def make_url(cls, script_name: str, params: ReportParameters) -> str:
        """Return a URL for the given script on this host with the provided parameters."""

        target = _resolve_script_path(script_name)
        query = CGIManager.params_to_query_str(params)
        return f"{target}{query}"

    @classmethod
    def selfref(
        cls,
        params: ReportParameters = None,
        *,
        what_report: str = "",
        sched_open: str = "",
        sched_close:str = "",
        precipitation:float|None = None,
        temperature:float|None = None,
        tag: str = "",
        dow: str = "",
        sort_by: str = "",
        sort_direction: str = "",
        start_date: str = "",
        end_date: str = "",
        start_date2: str = "",
        end_date2: str = "",
        dow2: str = "",
        pages_back: int | None = None,
    ) -> str:
        """Return a self-reference with the given parameters.

        If additional parameters are given, they will override the equivalent
        params properties; or if no params, a new ReportParameters will be
        created with those values.
        """

        if params is None:
            new_params = ReportParameters()
        else:
            new_params = copy.deepcopy(params)

        overrides = {
            "what_report": what_report,
            "sched_open": sched_open,
            "sched_close": sched_close,
            "precipitation": precipitation,
            "temperature": temperature,
            "tag": tag,
            "dow": dow,
            "sort_by": sort_by,
            "sort_direction": sort_direction,
            "start_date": start_date,
            "end_date": end_date,
            "start_date2": start_date2,
            "end_date2": end_date2,
            "dow2": dow2,
            "pages_back": pages_back,
        }

        for property_name, value in overrides.items():
            if value is None:
                continue
            if isinstance(value, str) and value == "":
                continue
            new_params.set_property(property_name, value)

        # Get the script name, return the new URL
        script_name = ut.untaint(os.environ.get("SCRIPT_NAME", ""))
        return cls.make_url(script_name, new_params)


def _resolve_script_path(script_name: str) -> str:
    """Return a sanitized script path for links within the same host."""

    # FIXME: move to CGIManager.
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
            /* Heavier bottom border — apply to row (<tr>) or cell (<td>) */
            .general_table tr.heavy-bottom td,
            .general_table td.heavy-bottom {
                border-bottom: 2px solid gray !important;
            }
            /* Heavier top border — apply to row (<tr>) or cell (<td>) */
            .general_table tr.heavy-top td,
            .general_table td.heavy-top {
                border-top: 2px solid gray !important;
            }
            /* Heavier right-hand border — apply to individual <td> or <th> */
            .general_table td.heavy-right,
            .general_table th.heavy-right {
                border-right: 2px solid gray !important;
            }
        </style>

        """
    return style_str


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

    print(f"Elapsed time for query: {elapsed_time:.1f} seconds.")

    print(db.db_latest(ttdb))

    print(f"TagTracker version {get_version_info()}")


def main_page_button() -> str:
    """Make a button to take a person to the main page."""
    target = CGIManager.selfref(None)
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
    if isinstance(pages_back, int) and pages_back > wcfg.MAX_PAGES_BACK:
        return main_page_button()
    if CGIManager.called_by_self() and pages_back > 0:
        return back_button(pages_back)
    else:
        return main_page_button()


def increment_pages_back(pages_back: int) -> int:
    """Increments pages_back but without altering any
    of the pages_back magic values
    """
    if pages_back in (NAV_MAIN_BUTTON, NAV_NO_BUTTON):
        return pages_back
    else:
        return pages_back + 1
