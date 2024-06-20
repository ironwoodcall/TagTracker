"""Command parser

Copyright (c) 2024 Todd Glover & Julias Hocking

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.


"""

from common.tt_time import VTime
from common.tt_tag import TagID
import tt_printer as pr
import client_base_config as cfg
import common.tt_constants as k
import tt_sounds
from common.tt_util import squawk

# Types of argument validations (arg_type)
ARG_TAGS = "ARG_TAGS"  # Returns list of 1+ TagID()
ARG_TIME = "ARG_TIME"  # Returns valid VTime()
ARG_TOKEN = "ARG_TOKEN"  # Returns any whitespace-delimited token
ARG_TEXT = "ARG_TEXT"  # Returns all remaining tokens, space separated
ARG_YESNO = "ARG_YESNO"  # Returns "y" or "n"
ARG_INOUT = "ARG_INOUT"  # Returns "i" or "o"
ARG_ONOFF = "ARG_ONOFF"  # Returns True or False


class ArgConfig:
    """Configuration for one argument for one command."""

    def __init__(self, arg_type, optional=False, prompt=""):
        self.arg_type = arg_type
        self.optional = optional
        self.prompt = prompt


# Status types for ParsedCommand
PARSED_UNINITIALIZED = "PARSED_UNINITIALIZED"
PARSED_EMPTY = "PARSED_EMPTY"
PARSED_INCOMPLETE = "PARSED_INCOMPLETE"
PARSED_OK = "PARSED_OK"
PARSED_ERROR = "PARSED_ERROR"
PARSED_CANCELLED = "PARSED_CANCELLED"


class ParsedCommand:
    """The result of an attempt to parse an input string."""

    def __init__(self, command=None, status=PARSED_UNINITIALIZED, message=""):
        self.command = command
        self.result_args = []
        self.status = status
        self.message = message
        if self.status not in {
            PARSED_UNINITIALIZED,
            PARSED_EMPTY,
            PARSED_INCOMPLETE,
            PARSED_OK,
            PARSED_ERROR,
        }:
            raise ValueError(f"unknown status for ParsedCommand: '{self.status}")

    # def set_error(self, msg: str = "Parsing error."):
    #     """Sets to error state with this message."""
    #     self.status = PARSED_ERROR
    #     self.message = msg

    def dump(self):
        """Print the contents of the object (for debugging basically)."""
        print(f"  ParsedCommand.command      = '{self.command}'")
        print(f"                .status      = '{self.status}'")
        print(f"                .message     = '{self.message}'")
        print(f"                .result_args = '{self.result_args}'")


class CmdKeys:
    """Keys to the COMMANDS dictionary."""
    CMD_AUDIT = "AUDIT"
    CMD_BIKE_IN = "BIKE_IN"  # Explicit
    CMD_BIKE_INOUT = "BIKE_INOUT"  # Guess, but won't re-use a tag.
    CMD_BIKE_OUT = "BIKE_OUT"  # Explicit
    CMD_BUSY = "BUSY"
    CMD_BUSY_CHART = "BUSY_CHART"
    CMD_CHART = "CHART"
    CMD_DEBUG = "DEBUG"
    CMD_DELETE = "DELETE"
    CMD_DUMP = "DUMP"
    CMD_EDIT = "EDIT"
    CMD_ESTIMATE = "ESTIMATE"
    CMD_EXIT = "EXIT"
    CMD_DATAFORM = "DATAFORM"
    CMD_FULL_CHART = "FULLNESS_CHART"
    CMD_HELP = "HELP"
    CMD_HOURS = "HOURS"
    CMD_LINT = "LINT"
    CMD_LOWERCASE = "LOWERCASE"
    CMD_NOTES = "NOTES"
    CMD_PUBLISH = "PUBLISH"
    CMD_QUERY = "QUERY"
    CMD_RECENT = "RECENT"
    CMD_REGISTRATIONS = "REGISTRATIONS"
    CMD_STATS = "STATS"
    CMD_TAGS = "TAGS"
    CMD_UPPERCASE = "UPPERCASE"


# CmdConfig class
class CmdConfig:
    """This is the parsing configuration for one command."""

    def __init__(self, invoke, arg_configs=None):
        self.invoke = invoke
        self.arg_configs = arg_configs or []

    def matches(self, invocation):
        """Return whether the 'invocation' is an invocation word for the command."""
        return invocation in self.invoke


# Command configurations dictionary
# Optional args may not precede mandatory args.
# NB: Always have the canonical invocation as the first member of the 'invoke' list.
COMMANDS = {
    CmdKeys.CMD_AUDIT: CmdConfig(
        invoke=["audit", "a", "aud"],
        arg_configs=[
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    # This is the command to check a bike in, possibly reusing a tag.
    CmdKeys.CMD_BIKE_IN: CmdConfig(
        invoke=["in", "i", "check-in", "checkin"],
        arg_configs=[
            ArgConfig(
                ARG_TAGS, optional=False, prompt="Check in bike(s) using what tag(s)? "
            ),
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    # InOut means guess whether to do BIKE_IN or BIKE_OUT.
    # It is invoked by typing one or more tags without a keyword.
    CmdKeys.CMD_BIKE_INOUT: CmdConfig(
        invoke=["inout"],
        arg_configs=[
            ArgConfig(
                ARG_TAGS,
                optional=False,
                prompt="Check in or out bikes with what tag(s)? ",
            ),
        ],
    ),
    # This is the command to check a bike (only) out.
    CmdKeys.CMD_BIKE_OUT: CmdConfig(
        invoke=["out", "o", "check-out", "checkout"],
        arg_configs=[
            ArgConfig(
                ARG_TAGS,
                optional=False,
                prompt="Check out bike(s) having what tag(s)? ",
            ),
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    CmdKeys.CMD_BUSY: CmdConfig(
        invoke=["busy", "b"],
        arg_configs=[
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    CmdKeys.CMD_BUSY_CHART: CmdConfig(
        invoke=["busy-chart", "busy_chart"],
        arg_configs=[
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    CmdKeys.CMD_CHART: CmdConfig(
        invoke=["chart", "c", "ch"],
        arg_configs=[
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    CmdKeys.CMD_DATAFORM: CmdConfig(
        invoke=["dataform", "form"],
        arg_configs=[
            ArgConfig(ARG_TIME, optional=True),
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    CmdKeys.CMD_DEBUG: CmdConfig(
        invoke=["debug", "deb"],
        arg_configs=[
            ArgConfig(ARG_ONOFF, optional=False, prompt="on or off? "),
        ],
    ),
    CmdKeys.CMD_DELETE: CmdConfig(
        invoke=["delete", "del", "d"],
        arg_configs=[
            ArgConfig(
                ARG_TAGS, optional=False, prompt="Delete check in/out for what tag(s)? "
            ),
            ArgConfig(ARG_INOUT, optional=False, prompt="Enter 'in' or 'out': "),
            ArgConfig(ARG_YESNO, optional=False, prompt="Enter 'y' to confirm: "),
        ],
    ),
    CmdKeys.CMD_DUMP: CmdConfig(
        invoke=["dump"], arg_configs=[ArgConfig(ARG_TOKEN, optional=True)]
    ),
    CmdKeys.CMD_EDIT: CmdConfig(
        invoke=["edit", "ed", "e"],
        arg_configs=[
            ArgConfig(ARG_TAGS, optional=False, prompt="Edit what tag(s)? "),
            ArgConfig(ARG_INOUT, optional=False, prompt="Edit visit 'in' or 'out': "),
            ArgConfig(ARG_TIME, optional=False, prompt="New time (HHMM or 'now'): "),
        ],
    ),
    CmdKeys.CMD_ESTIMATE: CmdConfig(invoke=["estimate", "est"]),
    CmdKeys.CMD_EXIT: CmdConfig(invoke=["exit", "ex", "x"]),
    CmdKeys.CMD_FULL_CHART: CmdConfig(
        invoke=["fullness-chart", "full-chart", "fullness_chart", "full_chart"],
        arg_configs=[
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    CmdKeys.CMD_HELP: CmdConfig(
        invoke=["help", "h"],
        arg_configs=[
            ArgConfig(ARG_TOKEN, optional=True),
        ],
    ),
    CmdKeys.CMD_HOURS: CmdConfig(invoke=["hours", "hour", "open"]),
    CmdKeys.CMD_LINT: CmdConfig(invoke=["lint"]),
    CmdKeys.CMD_LOWERCASE: CmdConfig(invoke=["lc", "lowercase"]),
    CmdKeys.CMD_NOTES: CmdConfig(
        invoke=["note", "notes", "n"],
        arg_configs=[ArgConfig(ARG_TEXT, optional=True, prompt="")],
    ),
    CmdKeys.CMD_PUBLISH: CmdConfig(invoke=["publish", "pub"]),
    CmdKeys.CMD_QUERY: CmdConfig(
        invoke=["query", "q", "?", "/"],
        arg_configs=[
            ArgConfig(ARG_TAGS, optional=False, prompt="Query what tag(s)? "),
        ],
    ),
    CmdKeys.CMD_RECENT: CmdConfig(
        invoke=["recent", "rec"],
        arg_configs=[
            ArgConfig(ARG_TIME, optional=True),
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    # Registrations:  e.g. r or r + 1 or r +1... so 2 args total.
    CmdKeys.CMD_REGISTRATIONS: CmdConfig(
        invoke=["registrations", "registration", "register", "reg", "r"],
        arg_configs=[
            ArgConfig(ARG_TOKEN, optional=True),
            ArgConfig(ARG_TOKEN, optional=True),
        ],
    ),
    CmdKeys.CMD_STATS: CmdConfig(
        invoke=["statistics", "stats", "s"],
        arg_configs=[
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    CmdKeys.CMD_TAGS: CmdConfig(
        invoke=["tags", "tag", "t"],
        arg_configs=[
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    CmdKeys.CMD_UPPERCASE: CmdConfig(invoke=["uc", "uppercase"]),
}


def find_command(command_invocation):
    """Find the command constant (e.g. CmdKeys.CMD_EDIT) from a user input."""
    for command, conf in COMMANDS.items():
        if conf.matches(command_invocation):
            return command
    return ""

def tags_arg(cmd_keyword) -> int:
    """Returns which arg for cmd_keyword is an ARG_TAGS, or None."""
    cmd_conf:CmdConfig = COMMANDS[cmd_keyword]
    for i,arg_conf in enumerate(cmd_conf.arg_configs):
        arg_conf:ArgConfig
        if arg_conf.arg_type == ARG_TAGS:
            return i
    return None

def prompt_user() -> str:
    """Prompt the user for input."""
    # Prompt
    # pr.iprint()  # blank line above the prompt
    if cfg.INCLUDE_TIME_IN_PROMPT:
        pr.iprint(f"{VTime('now').short}", end="")
    pr.iprint(f"Bike tag or command {cfg.CURSOR}", style=k.PROMPT_STYLE, end="")
    user_str = pr.tt_inp().lower().strip("\\][ \t")
    return user_str


def subprompt_user(prompt: str) -> str:
    """Prompt user for information to complete an incomplete command."""
    pr.iprint(
        f"   {prompt} ",
        style=k.SUBPROMPT_STYLE,
        end="",
    )
    return pr.tt_inp().strip()


def _tokenize(user_str: str) -> list[str]:
    """Break user_str into whitespace-separated tokens."""
    return user_str.strip().lower().split()


def _subprompt_text(current: ParsedCommand) -> str:
    """Return the prompt string for the next argument needed."""
    cmd_conf = COMMANDS[current.command]
    s = cmd_conf.arg_configs[len(current.result_args)].prompt
    return s


def _chunkize_for_one_arg(
    arg_parts: list[str],
    arg_conf: ArgConfig,
    parsed: ParsedCommand,
):
    """Removes member(s) of arg_parts according to arg_conf into parsed.

    If fails mandatory validation, status & message in parsed is updated.

    If runs out of input args then status is PARSED_INCOMPLETE if the arg is
    mandatory (so can prompt for more input) or PARSED_OK if optional.

    Returns False if ParsedCommand has gone to error state, else True.
    """

    squawk(f"{arg_parts=}", cfg.DEBUG)

    # Out of input to process?
    if not arg_parts:
        parsed.status = PARSED_OK if arg_conf.optional else PARSED_INCOMPLETE
        return True

    if arg_conf.arg_type == ARG_INOUT:
        if arg_parts[0].lower() in {"in", "out", "i", "o"}:
            parsed.result_args.append(arg_parts[0][0])
            if arg_parts:
                del arg_parts[0]
        else:
            parsed.status = PARSED_ERROR
            parsed.message = (
                f"Unrecognized parameter '{arg_parts[0]}' (must be 'in' or 'out')."
            )
    elif arg_conf.arg_type == ARG_YESNO:
        if arg_parts[0].lower() in {"yes", "no", "y", "n"}:
            parsed.result_args.append(arg_parts[0][0])
            if arg_parts:
                del arg_parts[0]
        else:
            parsed.status = PARSED_ERROR
            parsed.message = (
                f"Unrecognized parameter '{arg_parts[0]}' (must be 'yes' or 'no')."
            )
    elif arg_conf.arg_type == ARG_ONOFF:
        test = arg_parts[0].lower()
        if test in {"on", "off", "true", "false", "yes", "no", "y", "n","+","-"}:
            parsed.result_args.append(test in {"on", "true", "yes","y","t","+"})
            if arg_parts:
                del arg_parts[0]
        else:
            parsed.status = PARSED_ERROR
            parsed.message = (
                f"Unrecognized parameter '{arg_parts[0]}' (must be 'yes' or 'no')."
            )
    elif arg_conf.arg_type == ARG_TIME:
        t = VTime(arg_parts[0])
        if t:
            parsed.result_args.append(t)
            if arg_parts:
                del arg_parts[0]
        else:
            parsed.status = PARSED_ERROR
            parsed.message = f"Unrecognized time parameter '{arg_parts[0]}'."
    elif arg_conf.arg_type == ARG_TOKEN:
        parsed.result_args.append(arg_parts[0])
        if arg_parts:
            del arg_parts[0]
    elif arg_conf.arg_type == ARG_TEXT:
        # All the remaining tokens
        parsed.result_args.append(" ".join(arg_parts))
        arg_parts.clear()

    elif arg_conf.arg_type == ARG_TAGS:
        tagslist = []
        while arg_parts:
            tag = TagID(arg_parts[0])
            if tag:
                # Check for and remove duplicate
                if tag in tagslist:
                    parsed.message = f"Ignoring duplicate of tagid '{tag.original}'."
                else:
                    tagslist.append(tag)
                del arg_parts[0]
            else:
                break
        if tagslist:

            parsed.result_args.append(tagslist)
        else:
            parsed.status = PARSED_ERROR
            parsed.message = f"Unrecognized tag parameter '{arg_parts[0]}'"

    else:
        raise ValueError(f"Unrecognized arg_type '{arg_conf.arg_type}'")

    return parsed.status != PARSED_ERROR


def _parse_user_command(user_str: str) -> ParsedCommand:
    """Parses user_str as a full command line."""

    squawk(f"  _parse_user_command has {user_str=}", cfg.DEBUG)
    if not user_str:
        return ParsedCommand(status=PARSED_EMPTY)

    # Special case: If first chr is '/' make it a 'query' command
    if user_str[0] == "/":
        user_str = "query " + user_str[1:]

    # Break into parts
    parts = _tokenize(user_str)
    if not parts:
        return ParsedCommand(status=PARSED_EMPTY)

    # Special case: if first token is a tag, prepend 'inout' command.
    if TagID(parts[0]):
        parts.insert(0, COMMANDS[CmdKeys.CMD_BIKE_INOUT].invoke[0])

    # What command is this?
    what_command = find_command(parts[0])
    if not what_command:
        return ParsedCommand(
            status=PARSED_ERROR, message="Unrecognized command. Enter 'help' for help."
        )
    cmd_config = COMMANDS[what_command]
    arg_parts = parts[1:]  # These are the potential arguments
    parsed = ParsedCommand(command=what_command)

    # Parse arguments to this command.
    # Want to go through the arg configs until we know
    # we are in error, are out out args
    parsed.status = PARSED_OK  # Assume ok
    for this_arg_config in cmd_config.arg_configs:
        this_arg_config: ArgConfig
        # if not this_arg_config.optional:
        # parsed.status = PARSED_INCOMPLETE   # FIXME: needed?
        # _chunkize returns with status set
        # if not _chunkize_for_one_arg(arg_parts, this_arg_config, parsed):
        _chunkize_for_one_arg(arg_parts, this_arg_config, parsed)
        squawk(f"returns from _chunkuze with {parsed.status=}", cfg.DEBUG)
        if parsed.status in (PARSED_ERROR, PARSED_INCOMPLETE):
            break

    # There should now be no arg_parts left
    if parsed.status == PARSED_OK and arg_parts:
        parsed.status = PARSED_ERROR
        parsed.message = f"Extra text at end of command: '{' '.join(arg_parts)}'."

    return parsed


def get_parsed_command() -> ParsedCommand:
    """Get a completed command (or nothing) from user."""
    user_input = prompt_user()
    result = _parse_user_command(user_input)
    while result.status == PARSED_INCOMPLETE:
        # Need more args. Get the subprompt for the next arg
        subprompt_text = _subprompt_text(result)
        # Repeat the parsing using what had before + new input
        subprompt_input = subprompt_user(subprompt_text)
        if subprompt_input:
            user_input = user_input + " " + subprompt_input
            result = _parse_user_command(user_input)
        else:
            # Cancelled (no input)
            result.status = PARSED_CANCELLED
    if result.status == PARSED_CANCELLED:
        pr.iprint("Cancelled", style=k.WARNING_STYLE)
    elif result.status == PARSED_ERROR:
        pr.iprint(result.message, style=k.WARNING_STYLE)
        tt_sounds.NoiseMaker.play(k.ALERT)

    return result


if __name__ == "__main__":
    while True:
        # user_input = input("Enter your command: ")
        print()
        parsed_command = get_parsed_command()
        parsed_command.dump()
        if (
            parsed_command.command == CmdKeys.CMD_EXIT
            and parsed_command.status == PARSED_OK
        ):
            print("exiting")
            break
