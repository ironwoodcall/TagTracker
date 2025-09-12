"""TagTracker by Julias Hocking.

Print help message(s)

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

import tt_printer as pr
import common.tt_constants as k
from tt_commands import CmdKeys, find_command,COMMANDS

# Help messages.  Colour styles will be applied as:
#       First non-blank line will be in TITLE_STYLE, after which
#       lines that are flush left will be in SUBTITLE_STYLE; and
#       all other lines will be in NORMAL_STYLE

HELP_MESSAGES = {
    # Dictionary key "" is for general help (no 'command' arg given)
    "": """
TagTracker Commands

To enter and change tracking data
  Check bike in (can reuse tag):  IN <tag(s)> [time]
  Check bike out               :  OUT <tag(s)> [time]
  Guess about check in or out  :  INOUT <tag(s)> - or just <tag(s)>
  Edit check in/out times      :  EDIT <tag(s)> <in|out> <time>
  Delete a check in/out        :  DELETE <tag(s)> <in|out> <yes>
  Change operating hours       :  HOURS
  View/manage attendant notes  :  NOTE [DELETE|UNDELETE|note text]
  View/set bike registrations  :  REGISTER [+n|-n|=n]

Information and reports
  Show info about one tag      :  QUERY <tag(s)>
  Show recent activity         :  RECENT [time] [time]
  Show audit info              :  AUDIT [time]
  Show times for leftovers     :  LEFT
  Show day-end stats report    :  STATS [time]
  Graph of busy- and fullness  :  GRAPH
  Show tag configurations      :  TAGS
  Show chart of all activity   :  CHART
  Estimate further bikes today :  ESTIMATE
  Detailed dump of today data  :  DUMP ['full']

Other
  Help with commands           :  HELP [command]
  Set tag display to UPPERCASE :  UC | UPPERCASE
  Set tag display to lowercase :  LC | LOWECASE
  Send reports to shared drive :  PUBLISH
  Exit                         :  EXIT | x

Most commands have short forms.  Eg "i" for IN, "rec" for RECENT.
Parameters in angle brackets are mandatory, square brackets optional.
Any <tag> parameter can be a single tag, or a list of tags.
Time is in 24 hour time (eg '14:00' or '1400') or the word "now".

For help about a specific command, try 'help <command>' e.g. 'help edit'.
""",

    CmdKeys.CMD_BIKE_IN: """
Command: IN <tag(s)> [time]

Can be invoked as
  {}

Arguments:
    <tag(s)>: one or more tags to go onto bikes being checked in
    [time]: optional time to assign to the check-in(s). Default is 'now'

Description
  Check a bike in.  If 'time' is given, checks it in for that time.

  If the tag has been used previously, this will re-use the tag for
  this new visit.
""",

    CmdKeys.CMD_LEFTOVERS: """
Command: LEFT <tag(s)> [time]

Can be invoked as
  {}

Description
  Lists the most recent check-in times for any bikes currently on-site.

  This is to make it easier to find phone numbers for any bikes that
  are left on-site as the end of day approaches.

""",

    CmdKeys.CMD_NOTES: """
Command: NOTE [note message|DELETE|UNDELETE]

Can be invoked as
  {}

Description:
    Create or delete a note.  Notes are minor information items for
    the convenience of the bike attendants.

    E.g. "NOTE Bike GA4 has a flat tire."
         "N bike bh3 is leaning against west fence at end of F row"

    Call without arguments to list current notes.

    The system will automatically delete notes that seem no longer relevent.
    (E.g. in the examples above, after those those bikes are checked back out, then
    after a 15 minute delay, their corresponding notes will be automatically deleted.)
    If a note was wrongly deleted, use the 'UNDELETE' command (below), and the
    system will not auto-delete that note again.

    Call with argument 'DELETE" (or 'DEL' or 'D'), to manually delete notes.
    Call with argument 'UNDELETE' (or 'UNDEL' or 'U') to recover deleted notes.

""",

    CmdKeys.CMD_BIKE_OUT: """
Command: IN <tag(s)> [time]

Can be invoked as
  {}

Arguments:
    <tag(s)>: one or more tags of bikes being checked out
    [time]: optional time to assign to the check-out(s). Default is 'now'

Description
  Check a bike out.  This makes the tag available for re-use.


""",

    CmdKeys.CMD_BIKE_INOUT: """
Command: <tag(s)>

Can be invoked as
  {}

Arguments:
    <tag(s)>: one or more tags to check in or out

Description
  Check a bike in or out, depending on whether it it is currently on-site:
  - if the bike is on-site, this will check the bike out (same as OUT <tag>).
  - if the bike is coming in, this will check the bike in unless the tag is being re-used.

  If a tag has been previously checked in the out, this will not know whether
  this command is a duplicated check-out, or intended as a new check-in.

  To re-use a tag for a new check-in, use the 'IN' command.

  For convenience, this command can be invoked using only <tag(s)>.
  E.g.:
    >>> wa3 bf6 bf7
  Is identical to:
    >>> INOUT wa3 bf6 bf7
""",

    CmdKeys.CMD_GRAPHS: """
Command: GRAPH [end_time]

Can be invoked as
  {}

Arguments:
    [end_time] : optional ending time for graphs (default: end of day)

Description
    Shows histograms representing how busy (bikes in + out) and how
    full the site is through the day.  If optional [end_time] is supplied
    then only data up to that time is incorporated in the graphs.

""",
}


def help_command(maybe_command_list):
    """Print the requested help message.

    Arg maybe_command might be a command invocation keyword.

    If no maybe_command, gives general help.
    """
    if not maybe_command_list:
        _show_one_help()
    else:
        command = find_command(maybe_command_list[0])
        if command:
            if command in HELP_MESSAGES:
                _show_one_help(command)
            else:
                pr.iprint(
                    f"No help available for '{maybe_command_list[0].upper()}'.",
                    style=k.ANSWER_STYLE,
                )
        else:
            pr.iprint(
                f"No help for unrecognized command '{maybe_command_list[0].upper()}'. "
                "Enter 'help' for general help.",
                style=k.WARNING_STYLE,
            )
            pr.iprint("Enter 'help' for general help.", style=k.ANSWER_STYLE)


def _show_one_help(what_command: str=""):
    """Show help_message with colour style highlighting.

    Prints first non-blank line as title;
    lines that are flush-left as subtitles;
    other lines in normal style.
    """

    if not what_command:
        # general help
        _print_help(msg=HELP_MESSAGES[what_command])
        return

    # This is sub-help.
    ##canonical_invocation = COMMANDS[what_command].invoke[0].upper()
    aliases = ", ".join([s.upper() for s in COMMANDS[what_command].invoke])
    msg = HELP_MESSAGES[what_command].format(aliases)
    _print_help(msg=msg)

def _print_help(msg):

    title_done = False
    for line in msg.split("\n"):
        if not line:
            pr.iprint()
        elif not title_done:
            title_done = True
            pr.iprint(line, style=k.TITLE_STYLE)
        elif line[0] != " ":
            pr.iprint(line, style=k.SUBTITLE_STYLE)
        else:
            pr.iprint(line, style=k.NORMAL_STYLE)
