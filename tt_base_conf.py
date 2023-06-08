"""Config for TagTracker by Julias Hocking.

Configuration items for the data entry module.

This module sets configs then overrides with any same-named
values that are set in tt_local_config

Copyright (C) 2023 Julias Hocking

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
SCREEN_WIDTH = 80 # characters
USE_COLOUR = True
CURSOR = ">>> "
INCLUDE_TIME_IN_PROMPT = True
TAGS_UPPERCASE = False

# This file defines what tags are available, for current-day sessions.
TAG_CONFIG_FILE = "tags.cfg"
# Files and folder locations
DATA_FOLDER = "../data" # Folder to keep datafiles in
DATA_BASENAME = "cityhall_" # Files will be {BASENAME}YY-MM-DD.dat
# Persistent database is put in the REPORTS_FOLDER
DB_FILENAME = "cityhall_bikevalet.db" # Name of persistent database
# Where and how often to publish reports
REPORTS_FOLDER = r"/mnt/chromeos/GoogleDrive/MyDrive/tracker_data/"
PUBLISH_FREQUENCY = 15 # minutes. "0" means do not publish
# Echo captures full transcripts of a day's TT session
ECHO_FOLDER = r"/mnt/chromeos/GoogleDrive/MyDrive/tracker_data/"
ECHO = False

# Ask confirmatino for checkouts when visits less than this duration.
CHECK_OUT_CONFIRM_TIME = 30 # mins
# Duration (minutes) for roll-up blocks (e.g. for datasheet report)
BLOCK_DURATION = 30

# Help message.  Colour styles will be applied as:
#       First non-blank line will be in TITLE_STYLE, after which
#       lines that are flush left will be in SUBTITLE_STYLE; and
#       all other lines will be in NORMAL_STYLE
HELP_MESSAGE = """
TagTracker Commands

To enter and change valet data
  Check bike in or out         :   <tag name> (eg “wa3”)
  Edit check in/out times      :   edit / e
  Delete a check in/out        :   delete / del  / d
  Set valet open/close hours   :   valet / v

Information and reports
  Show info about one tag      :   query / q / ?
  Show recent activity         :   recent / r
  Show audit info              :   audit / a
  Show day-end stats report    :   stat  / s
  Show valet busy-ness report  :   busy / b
  Show data as on paper form   :   form / f
  Show tag configurations      :   tags / t
  Show chart of all activity   :   chart / c

Other
  Show this list of commands   :   help  /  h
  Set tag display to UPPERCASE :   uppercase / uc
  Set tag display to lowercase :   lowercase / lc
  Send reports to shared drive :   publish / pub
  Exit                         :   exit / x
"""

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



# Command keys and aliases.
CMD_AUDIT = "audit"
CMD_DELETE = "delete"
CMD_EDIT = "edit"
CMD_EXIT ="exit"
CMD_BLOCK = "block"
CMD_HELP ="help"
CMD_LOOKBACK = "lookback"
CMD_QUERY ="query"
CMD_STATS ="stats"
CMD_BUSY = "busy"
CMD_VALET_HOURS = "valet_hours"
CMD_CSV = "csv"
CMD_UPPERCASE = "uppercase"
CMD_LOWERCASE = "lowercase"
CMD_LINT = "lint"
CMD_DUMP = "dump"
CMD_BUSY_CHART = "busy_chart"
CMD_FULL_CHART = "full_chart"
CMD_CHART = "chart"
CMD_PUBLISH = "publish"
CMD_COLOURS = "colours" # FIXME: remove in a while. Now "tags"
CMD_RETIRED = "retired" # FIXME: remove in a while.  Now "tags"
CMD_TAGS = "tags"


COMMANDS = {}
COMMANDS[CMD_AUDIT] = ['audit','a','aud']
COMMANDS[CMD_DELETE] = ['del','delete','d']
COMMANDS[CMD_EDIT] = ['edit','e','ed']
COMMANDS[CMD_EXIT] = ['quit','exit','stop','x','bye']
COMMANDS[CMD_BLOCK] = ['log', 'l', 'form', 'f']
COMMANDS[CMD_HELP] = ['help','h']
COMMANDS[CMD_LOOKBACK] = ['recent', 'r']
COMMANDS[CMD_QUERY] = ['query','q','?','/']
COMMANDS[CMD_STATS] = ['s','stat','stats','statistics']
COMMANDS[CMD_BUSY] = ["b", "busy","busyness","business"]
COMMANDS[CMD_VALET_HOURS] = ["v","valet"]
COMMANDS[CMD_CSV] = ["csv"]
COMMANDS[CMD_UPPERCASE] = ["uc","uppercase", "upper"]
COMMANDS[CMD_LOWERCASE] = ["lc","lowercase", "lower"]
COMMANDS[CMD_RETIRED] = ["retired","ret"]
COMMANDS[CMD_LINT] = ["consistency","consistent","cons","con"]
COMMANDS[CMD_DUMP] = ["dump"]
COMMANDS[CMD_BUSY_CHART] = ["chart-busy","graph-busy","busy-chart","busy-graph"]
COMMANDS[CMD_FULL_CHART] = ["chart-full","graph-full","full-chart","full-graph"]
COMMANDS[CMD_CHART] = ["chart","c"]
COMMANDS[CMD_PUBLISH] = ["pub","publish"]
COMMANDS[CMD_COLOURS] = ["col","color","colors","colour","colours"]
COMMANDS[CMD_TAGS] = ["tag", "tags", "t"]
CMD_UNKNOWN = -1 # special value to mean unrecognized command



