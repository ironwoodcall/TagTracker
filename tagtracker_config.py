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

# Use colour in the program?
USE_COLOUR = True
# If use colour, try to import colorama library
if USE_COLOUR:
    try:
        from colorama import Style,Fore,Back
    except ImportError:
        USE_COLOUR = False
        print("WARNING: No 'colorame' module, text will be in black & white.")

# Datafiles/Logfiles
LOG_BASENAME = "cityhall_" # Files will be {BASENAME}YY-MM-DD.LOG.
LOG_FOLDER = "logs" # Folder to keep logfiles in
# System occasionally puts a copy of log in a publish folder
PUBLISH_FOLDER = r"/mnt/chromeos/GoogleDrive/MyDrive/tracker_logs/"
PUBLISH_FREQUENCY = 15 # minutes. "0" means do not publish

# Duration (minutes) for roll-up blocks (e.g. for datasheet report)
BLOCK_DURATION=30

# Time ranges for categorizing stay-lengths, in hours.
# First category will always be 0 - [0], last will always be > [-1]
VISIT_CATEGORIES = [1.5,5]
VISIT_NOUN = "stay"    # Probably either "stay" or "visit"

# size of 'buckets' for calculating the mode stay time
MODE_ROUND_TO_NEAREST = 30 # mins

# List ow many ranked busiest times of day in report?
BUSIEST_RANKS = 4

# Ask confirmatino for checkouts when visits less than this duration.
CHECK_OUT_CONFIRM_TIME = 30 # mins

# Format preferences for prompting user.
INDENT = '  '
CURSOR = ">>> "
INCLUDE_TIME_IN_PROMPT = True

# Tags display in uppercase or lowercase?
# (Note: in files always stored as lowercase)
TAGS_UPPERCASE_DEFAULT=False

# Styles related to colour
STYLE={}
PROMPT_STYLE = "prompt_style"
SUBPROMPT_STYLE = "subprompt_style"
ANSWER_STYLE = "answer_style"
TITLE_STYLE = "title_style"
SUBTITLE_STYLE = "subtitle_style"
NORMAL_STYLE = "normal_style"
RESET_STYLE = "reset_style"
HIGHLIGHT_STYLE = "highlight_style"
QUIET_STYLE = "quiet_style"
WARNING_STYLE = "warn_style"
ERROR_STYLE = "error_style"
# These are assigned in 'if' in case could not import colorame.
if USE_COLOUR:
    STYLE[PROMPT_STYLE] = (
            f"{Style.BRIGHT}{Fore.GREEN}{Back.BLACK}")
    STYLE[SUBPROMPT_STYLE] = (
            f"{Style.BRIGHT}{Fore.GREEN}{Back.BLACK}")
    STYLE[ANSWER_STYLE] = (
            f"{Style.BRIGHT}{Fore.YELLOW}{Back.BLUE}")
    STYLE[TITLE_STYLE] = (
            f"{Style.BRIGHT}{Fore.WHITE}{Back.BLUE}")
    STYLE[SUBTITLE_STYLE] = (
            f"{Style.BRIGHT}{Fore.CYAN}{Back.BLACK}")
    STYLE[RESET_STYLE] = (
            f"{Style.RESET_ALL}")
    STYLE[NORMAL_STYLE] = (
            f"{Style.RESET_ALL}")
    STYLE[HIGHLIGHT_STYLE] = (
            f"{Style.BRIGHT}{Fore.CYAN}{Back.BLACK}")
    STYLE[QUIET_STYLE] = (
            f"{Style.RESET_ALL}{Fore.BLUE}")
    STYLE[WARNING_STYLE] = (
            f"{Style.BRIGHT}{Fore.RED}{Back.BLACK}")
    STYLE[ERROR_STYLE] = (
            f"{Style.BRIGHT}{Fore.WHITE}{Back.RED}")

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
CMD_UNKNOWN = -1 # special value to mean unrecognized command

help_message = f"""
{INDENT}This list of commands      :   help  /  h
{INDENT}Check bike in or out       :   <tag name> (eg “wa3”)
{INDENT}Edit a check in/out time   :   edit  / e
{INDENT}Delete a check in/out      :   delete / del  / d
{INDENT}Valet opening/closing hours:   valet / v
{INDENT}Show info about one tag    :   query / q / ?
{INDENT}Show summary statistics    :   stat  / s
{INDENT}Show how busy valet is     :   busy / b
{INDENT}Show accouting audit info  :   audit / a
{INDENT}Show recent logged events  :   recent / r
{INDENT}Show dataform log          :   form / f
{INDENT}Show what tags are retired :   retired / ret
{INDENT}Display tags in UPPER CASE :   uppercase / uc
{INDENT}Display tags in lower case :   lowercase / lc
{INDENT}Perform consistency check  :   consistency / con
{INDENT}Dump CSV records to file   :   csv
{INDENT}Exit                       :   x / stop / exit / quit / bye
"""

