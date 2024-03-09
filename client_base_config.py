"""Config for TagTracker by Julias Hocking.

Configuration items for the data entry module.

This module sets configs then overrides with any same-named
values that are set in tt_local_config

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
from tt_colours import Style, Fore, Back


# Screen appearance
SCREEN_WIDTH = 80  # characters
USE_COLOUR = True
CURSOR = ">>> "
INCLUDE_TIME_IN_PROMPT = True
TAGS_UPPERCASE = False

# data owner -- If set, this notice will display when tagtraacker starts.
# This can be a string, or if a list of strings, displays as multiple lines.
DATA_OWNER = ""

# Things related to playing sounds (client only)
SOUND_PLAYER = "mpg321"   # If not full filepath then this needs to be on PATH
# Sound file locations are relative to the python files dir
SOUND_BIKE_IN = "sounds/bike-in.mp3"
SOUND_BIKE_OUT = "sounds/bike-out.mp3"
SOUND_ALERT = "sounds/alert.mp3"
SOUND_CHEER = "sounds/cheer"
# This flag can set the (initial) state of whether sounds are enabled
SOUND_ENABLED = True

# This tells TT how often to check for an active internet connection (minutes).
# If set to 0 (or anything else that evalues False), no monitoring is done.
INTERNET_MONITORING_FREQUENCY = 10

# This file defines what tags are available, for current-day sessions.
# FIXME: theis TAGS_CONFIG_FILE will go away
TAG_CONFIG_FILE = "tags.cfg"

# Files and folder locations
DATA_FOLDER = "../data"  # Folder to keep datafiles in
DATA_BASENAME = "cityhall_"  # Files will be {BASENAME}YY-MM-DD.dat
# Where and how often to publish reports
REPORTS_FOLDER = r"/mnt/chromeos/GoogleDrive/MyDrive/tracker_data/"
PUBLISH_FREQUENCY = 15  # minutes. "0" means do not publish

# Echo captures full transcripts of a day's TT session
ECHO_FOLDER = r"/mnt/chromeos/GoogleDrive/MyDrive/tracker_data/"
ECHO = False

# Base of URL to use for calls to estimator
# E.g. "http://example.com/cgi-bin/estimator"
# "" disables estimations
ESTIMATOR_URL_BASE = ""

# Maximum length for Notes
MAX_NOTE_LENGTH = 80

# Ask confirmatino for checkouts when visits less than this duration.
CHECK_OUT_CONFIRM_TIME = 10  # mins

# Stubs here; the default hours should be defined in the local config file.
REGULAR_TAGS = ""
OVERSIZE_TAGS = ""
RETIRED_TAGS = ""
TAG_COLOUR_NAMES = {}
SEASON_HOURS = {}
SPECIAL_HOURS = {}


# Import any local config to override this module's values.
try:
    from client_local_config import * # pylint:disable=wildcard-import,unused-wildcard-import
except ModuleNotFoundError:
    pass
except Exception as e: # pylint:disable=broad-exception-caught
    print()
    print("** Configuration error: **")
    print(f"   Error type: {type(e).__name__}")
    print(f"   Error message: {e}")
    print("Contact TagTracker admin.")
    print()
    import sys
    sys.exit(1)

######## BELOW HERE SHOULD MOVE TO tt_constants.py #################

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

# Colour combinations. Override these in local config as desired.
STYLE[PROMPT_STYLE] = f"{Style.BRIGHT}{Fore.GREEN}{Back.BLACK}"
STYLE[SUBPROMPT_STYLE] = f"{Style.BRIGHT}{Fore.GREEN}{Back.BLACK}"
STYLE[ANSWER_STYLE] = f"{Style.BRIGHT}{Fore.YELLOW}{Back.BLUE}"
STYLE[TITLE_STYLE] = f"{Style.BRIGHT}{Fore.WHITE}{Back.BLUE}"
STYLE[SUBTITLE_STYLE] = f"{Style.BRIGHT}{Fore.CYAN}{Back.BLACK}"
STYLE[RESET_STYLE] = f"{Style.RESET_ALL}"
STYLE[NORMAL_STYLE] = f"{Style.RESET_ALL}"
STYLE[HIGHLIGHT_STYLE] = f"{Style.BRIGHT}{Fore.CYAN}{Back.BLACK}"
STYLE[WARNING_STYLE] = f"{Style.BRIGHT}{Fore.RED}{Back.BLACK}"
STYLE[ERROR_STYLE] = f"{Style.BRIGHT}{Fore.WHITE}{Back.RED}"
STYLE[ALERT_STYLE] = f"{Style.BRIGHT}{Fore.WHITE}{Back.BLUE}"
STYLE[STRONG_ALERT_STYLE] = f"{Style.BRIGHT}{Fore.WHITE}{Back.RED}"

# These are the symbols & styles used in the tag inventory matrix.
# Each is a tuple of (symbol,style).
# Each symbol should be 2 characters wide.  Warning if using fancy unicode
# that those characters come in various widths, platform-dependent.
TAG_INV_UNKNOWN = ("  ", NORMAL_STYLE)
TAG_INV_AVAILABLE = (" -", NORMAL_STYLE)
TAG_INV_BIKE_IN = ("In", ANSWER_STYLE)
TAG_INV_BIKE_OUT = ("Ou", PROMPT_STYLE)
TAG_INV_RETIRED = ("Re", WARNING_STYLE)
TAG_INV_ERROR = ("!?", ERROR_STYLE)

# Command keys and aliases.
CMD_AUDIT = "audit"
CMD_DELETE = "delete"
CMD_EDIT = "edit"
CMD_EXIT = "exit"
CMD_BLOCK = "block"
CMD_HELP = "help"
CMD_LOOKBACK = "lookback"
CMD_QUERY = "query"
CMD_STATS = "stats"
CMD_BUSY = "busy"
CMD_VALET_HOURS = "operating_hours"
CMD_CSV = "csv"
CMD_UPPERCASE = "uppercase"
CMD_LOWERCASE = "lowercase"
CMD_LINT = "lint"
CMD_NOTES = "notes"
CMD_REGISTRATION = "registration"
CMD_DUMP = "dump"
CMD_BUSY_CHART = "busy_chart"
CMD_FULL_CHART = "full_chart"
CMD_CHART = "chart"
CMD_PUBLISH = "publish"
CMD_COLOURS = "colours"  # FIXME: remove in a while. Now "tags"
CMD_RETIRED = "retired"  # FIXME: remove in a while.  Now "tags"
CMD_TAGS = "tags"
CMD_ESTIMATE = "estimate"


COMMANDS = {}
COMMANDS[CMD_AUDIT] = ["audit", "a", "aud"]
COMMANDS[CMD_DELETE] = ["del", "delete", "d"]
COMMANDS[CMD_EDIT] = ["edit", "e", "ed"]
COMMANDS[CMD_EXIT] = ["quit", "exit", "stop", "x", "bye"]
COMMANDS[CMD_BLOCK] = ["log", "l", "form", "f"]
COMMANDS[CMD_HELP] = ["help", "h"]
COMMANDS[CMD_LOOKBACK] = ["recent", "rec"]
COMMANDS[CMD_QUERY] = ["query", "q", "?", "/"]
COMMANDS[CMD_STATS] = ["s", "stat", "stats", "statistics"]
COMMANDS[CMD_BUSY] = ["b", "busy", "busyness", "business"]
COMMANDS[CMD_VALET_HOURS] = ["hour", "hours", "v"]
COMMANDS[CMD_CSV] = ["csv"]
COMMANDS[CMD_UPPERCASE] = ["uc", "uppercase", "upper"]
COMMANDS[CMD_LOWERCASE] = ["lc", "lowercase", "lower"]
COMMANDS[CMD_RETIRED] = ["retired", "ret"]
COMMANDS[CMD_LINT] = ["consistency", "consistent", "cons", "con"]
COMMANDS[CMD_DUMP] = ["dump"]
COMMANDS[CMD_BUSY_CHART] = [
    "chart-busy",
    "graph-busy",
    "busy-chart",
    "busy-graph",
]
COMMANDS[CMD_FULL_CHART] = [
    "chart-full",
    "graph-full",
    "full-chart",
    "full-graph",
]
COMMANDS[CMD_CHART] = ["chart", "c"]
COMMANDS[CMD_PUBLISH] = ["pub", "publish"]
COMMANDS[CMD_COLOURS] = ["col", "color", "colors", "colour", "colours"]
COMMANDS[CMD_TAGS] = ["tag", "tags", "t"]
COMMANDS[CMD_NOTES] = ["note", "notes", "n"]
COMMANDS[CMD_REGISTRATION] = ["registrations","register","reg","r"]
COMMANDS[CMD_ESTIMATE] = ["est", "estimate", "guess"]
# These are for commands that are not recognized so *maybe* are a tag
CMD_UNKNOWN = "unknown" + chr(
    12345
)  # special value to mean unrecognized command
CMD_TAG_RETIRED = "tag_retired" + chr(
    12345
)  # For a tag that's retired (not a command)
CMD_TAG_UNUSABLE = "tag_unusable" + chr(12345)

