"""TagTracker by Julias Hocking.

Global constants for use through most or all the TagTracker modules.
These are meant to be wildcard-imported.

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

import re
from tt_colours import Style, Fore, Back

# Type aliases only to improve readability and IDE linting
MaybeTag = str
MaybeTime = str
MaybeDate = str


# Constants to use as dictionary keys.

TAG = chr(0x2192) + "TAGID"
BIKE_IN = chr(0x2192) + "bike_in"
BIKE_OUT = chr(0x2192) + "bike_out"
INOUT = chr(0x2192) + "inout"
NOTES = chr(0x2192) + "notes"
REGULAR = chr(0x2192) + "REGULAR"
OVERSIZE = chr(0x2192) + "OVERSIZE"
MIXED = chr(0x2192) + "MIXED"
COMBINED = chr(0x2192) + "COMBINED"
RETIRED = chr(0x2192) + "RETIRED"
USABLE = chr(0x2192) + "USABLE"
TOTAL = chr(0x2192) + "total"
COUNT = chr(0x2192) + "count"
TIME = chr(0x2192) + "time"
IGNORE = chr(0x2192) + "ignore"
NOT_A_LIST = chr(0x2192) + "not_a_list"
COLOURS = chr(0x2192) + "colours"
BADVALUE = chr(0x2192) + "badvalue"
UPPERCASE = chr(0x2192) + "uppercase"
LOWERCASE = chr(0x2192) + "lowercase"
UNKNOWN = chr(0x2192) + "UNKNOWN"
ON = chr(0x2192) + "on"
OFF = chr(0x2192) + "off"
ALERT = chr(0x2192) + "alert"
CHEER = chr(0x2192) + "cheer"

# Date re checks for date that might be in another string
_DATE_RE = r"(2[0-9][0-9][0-9])[/-]([01]?[0-9])[/-]([0123]?[0-9])"
# Match a date within another string
DATE_PART_RE = re.compile(r"(\b|[^a-zA-Z0-9])" + _DATE_RE + r"\b")
# Match a date as the whole string
DATE_FULL_RE = re.compile(r"^ *" + _DATE_RE + " *$")

# How long a single time block is (minutes) - for charts/stats etc
BLOCK_DURATION = 30



# Styles related to colour
STYLE = {}
PROMPT_STYLE = "prompt_style"
SUBPROMPT_STYLE = "subprompt_style"
ANSWER_STYLE = "answer_style"
TITLE_STYLE = "title_style"
SUBTITLE_STYLE = "subtitle_style"
NORMAL_STYLE = "normal_style"
RESET_STYLE = "reset_style"
HIGHLIGHT_STYLE = "highlight_style"
WARNING_STYLE = "warn_style"
ERROR_STYLE = "error_style"
ALERT_STYLE = "alert_style"
STRONG_ALERT_STYLE = "strong_alert_style"


def set_html_style():
    """Set STYLE values to work in an HTML doc."""
    global STYLE  # pylint:disable=global-statement
    STYLE = {
        PROMPT_STYLE: '<span style="color: green; background-color: black; font-weight: bold;">',
        SUBPROMPT_STYLE: '<span style="color: green; background-color: black; font-weight: bold;">',
        ANSWER_STYLE: '<span style="color: yellow; background-color: blue; font-weight: bold;">',
        TITLE_STYLE: '<span style="color: white; background-color: blue; font-weight: bold;">',
        SUBTITLE_STYLE: '<span style="color: cyan; background-color: black; font-weight: bold;">',
        RESET_STYLE: "</span>",  # Closes the style tag
        NORMAL_STYLE: '<span style="color:white;background-color:black;">',  # Nothing
        HIGHLIGHT_STYLE: '<span style="color: cyan; background-color: black; font-weight: bold;">',
        WARNING_STYLE: '<span style="color: red; background-color: black; font-weight: bold;">',
        ERROR_STYLE: '<span style="color: white; background-color: red; font-weight: bold;">',
        ALERT_STYLE: '<span style="color: white; background-color: blue; font-weight: bold;">',
        STRONG_ALERT_STYLE:
            '<span style="color: white; background-color: red; font-weight: bold;">',
    }


def set_terminal_style():
    """Set STYLE values to work on a terminal."""
    global STYLE  # pylint:disable=global-statement
    STYLE = {
        PROMPT_STYLE: f"{Style.BRIGHT}{Fore.GREEN}{Back.BLACK}",
        SUBPROMPT_STYLE: f"{Style.BRIGHT}{Fore.GREEN}{Back.BLACK}",
        ANSWER_STYLE: f"{Style.BRIGHT}{Fore.YELLOW}{Back.BLUE}",
        TITLE_STYLE: f"{Style.BRIGHT}{Fore.WHITE}{Back.BLUE}",
        SUBTITLE_STYLE: f"{Style.BRIGHT}{Fore.CYAN}{Back.BLACK}",
        RESET_STYLE: f"{Style.RESET_ALL}",
        NORMAL_STYLE: f"{Style.RESET_ALL}",
        HIGHLIGHT_STYLE: f"{Style.BRIGHT}{Fore.CYAN}{Back.BLACK}",
        WARNING_STYLE: f"{Style.BRIGHT}{Fore.RED}{Back.BLACK}",
        ERROR_STYLE: f"{Style.BRIGHT}{Fore.WHITE}{Back.RED}",
        ALERT_STYLE: f"{Style.BRIGHT}{Fore.WHITE}{Back.BLUE}",
        STRONG_ALERT_STYLE: f"{Style.BRIGHT}{Fore.WHITE}{Back.RED}",
    }


# Colour combinations.
set_terminal_style()


class TagTrackerError(Exception):
    """Generic TagTracker error."""
