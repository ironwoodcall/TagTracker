"""Config for TagTracker by Julias Hocking.

Configuration items for the data entry module.

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

# Use colours?
USE_COLOUR = True

# Datafiles/Logfiles
LOG_BASENAME = "cityhall_" # Files will be {BASENAME}YY-MM-DD.LOG.
LOG_FOLDER = "logs" # Folder to keep logfiles in
# System occasionally puts a copy of log in a publish folder
PUBLISH_FOLDER = r"/mnt/chromeos/GoogleDrive/MyDrive/tracker_logs/"
PUBLISH_FREQUENCY = 15 # minutes. "0" means do not publish

# Ask confirmatino for checkouts when visits less than this duration.
CHECK_OUT_CONFIRM_TIME = 30 # mins

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
  Show what tags are retired   :   retired / ret

Other
  Show this list of commands   :   help  /  h
  Set tag display to UPPERCASE :   uppercase / uc
  Set tag display to lowercase :   lowercase / lc
  Exit                         :   exit / x
"""

# Format preferences for prompting user.
CURSOR = ">>> "
INCLUDE_TIME_IN_PROMPT = True

# Tags display in uppercase or lowercase?
# (Note: in files always stored as lowercase)
# Discussion: tag case reflects whether the taglists and dictionaries
# are currently uppercase or lowercase.  It is part of the TrackerDay
# object but not stored in the data file, since (1) it's part of program
# state not data state (arguable), and more to the point (2), because
# datafile format is canonically all lowercase.
TAGS_UPPERCASE = False

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
CMD_RETIRED = "retired"
CMD_LINT = "lint"
CMD_DUMP = "dump"

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
CMD_UNKNOWN = -1 # special value to mean unrecognized command


