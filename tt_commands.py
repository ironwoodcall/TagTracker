"""Command parser

Copyright (c) 2024 Todd Glover & Julias Hocking

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.


"""

from tt_time import VTime
from tt_tag import TagID


# Types of argument validations (arg_type)
ARG_TAGS = "ARG_TAGS"
ARG_TIME = "ARG_TIME"
ARG_TOKEN = "ARG_TOKEN"
ARG_TEXT = "ARG_TEXT"
ARG_YESNO = "ARG_YESNO"
ARG_INOUT = "ARG_INOUT"

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

    def set_error(self, msg: str = "Parsing error."):
        """Sets to error snextate with this message."""
        self.status = PARSED_ERROR
        self.message = msg

    def dump(self):
        """Print the contents of the object (for debugging basically)."""
        print(f"  ParsedCommand.command      = '{self.command}'")
        print(f"                .status      = '{self.status}'")
        print(f"                .message     = '{self.message}'")
        print(f"                .result_args = '{self.result_args}'")

# List of commands.  These are keys to COMMANDS dictionary
CMD_EDIT = "EDIT"
CMD_DELETE = "DELETE"
CMD_BIKE_IN = "BIKE_IN"     # Explicit
CMD_BIKE_OUT = "BIKE_OUT"   # Explicit
CMD_BIKE_INOUT = "(GUESS_IN_OR_OUT)"    # Guess, but won't re-use a tag.
CMD_NOTES = "CMD_NOTES"
CMD_REGISTRATIONS = "CMD_REGISTRATIONS"
CMD_HELP = "CMD_HELP"
CMD_RECENT = "RECENT"
CMD_QUERY = "QUERY"
CMD_STATS = "STATS"
CMD_BUSY = "BUSY"
CMD_HOURS = "HOURS"
CMD_UPPERCASE = "UPPERCASE"
CMD_LOWERCASE = "LOWERCASE"
CMD_LINT = "LINT"
CMD_NOTES = "NOTES"
CMD_REGISTRATION = "REGISTRATION"
CMD_DUMP = "DUMP"
CMD_BUSY_CHART = "BUSY_CHART"
CMD_FULL_CHART = "FULLNESS_CHART"
CMD_CHART = "CHART"
CMD_PUBLISH = "PUBLISH"
CMD_TAGS = "TAGS"
CMD_ESTIMATE = "ESTIMATE"
CMD_EXIT = "EXIT"
CMD_HELP = "HELP"

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
COMMANDS = {
    CMD_QUERY: CmdConfig(
        invoke=["/", "?", "q", "query"],
        arg_configs=[ArgConfig(ARG_TAGS, optional=False, prompt="Query what tag(s)? ")],
    ),
    CMD_DELETE: CmdConfig(
        invoke=["d", "del", "delete"],
        arg_configs=[
            ArgConfig(
                ARG_TAGS, optional=False, prompt="Delete check in/out for what tag(s)? "
            ),
            ArgConfig(ARG_INOUT, optional=False, prompt="Enter 'in' or 'out': "),
            ArgConfig(ARG_YESNO, optional=False, prompt="Enter 'y' to confirm: "),
        ],
    ),
    CMD_EDIT: CmdConfig(
        invoke=["edit", "ed", "e"],
        arg_configs=[
            ArgConfig(ARG_TAGS, optional=False, prompt="Edit what tag(s)? "),
            ArgConfig(ARG_INOUT, optional=False, prompt="Edit visit 'in' or 'out': "),
            ArgConfig(
                ARG_TIME, optional=False, prompt="New time (HHMM or 'now'): "
            ),
        ],
    ),
    # InOut means guess whether to do BIKE_IN or BIKE_OUT.
    # It is invoked by typing one or more tags without a keyword.
    CMD_BIKE_INOUT: CmdConfig(
        invoke=["inout" ],
        arg_configs=[
            # ArgConfig(ARG_TAGS, optional=False, prompt="Edit what tag(s)? "),
            ArgConfig(ARG_TAGS, optional=False),
        ],
    ),
    CMD_RECENT: CmdConfig(
        invoke=["recent", "rec"],
        arg_configs=[
            ArgConfig(ARG_TIME, optional=True),
            ArgConfig(ARG_TIME, optional=True),
        ],
    ),
    CMD_NOTES: CmdConfig(
        invoke=["notes","note","n"],
        arg_configs=[ArgConfig(ARG_TEXT, optional=True, prompt="")],
    ),
    # Registrations:  e.g. r or r + 1 or r +1... so 2 args
    CMD_REGISTRATIONS: CmdConfig(
        invoke=["reg","registrations","registration","r"],
        arg_configs=[
            ArgConfig(ARG_TOKEN, optional=True),
            ArgConfig(ARG_TOKEN, optional=True),
        ],
    ),
    CMD_HELP: CmdConfig(invoke=["h", "help"]),
    CMD_EXIT: CmdConfig(invoke=["x", "ex", "exit"]),
    # Add more COMMANDS as needed
}


def find_command(command_invocation):
    """Find the command constant (e.g. CMD_EDIT) from a user input."""
    for command, conf in COMMANDS.items():
        if conf.matches(command_invocation):
            return command
    return None


def get_input(prompt: str = None) -> str:
    """Prompt the user for input."""
    prompt = prompt or "Enter a command: "
    return input(prompt).strip()


def subprompt(prompt: str) -> str:
    """Prompt user for information to complete an incomplete command."""
    return input(prompt).strip()


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

    # Out of input to process?
    if not arg_parts:
        parsed.status = PARSED_OK if arg_conf.optional else PARSED_INCOMPLETE
        return True

    if arg_conf.arg_type == ARG_INOUT:
        if arg_parts[0].lower() in {"in", "out", "i", "o"}:
            parsed.result_args.append(arg_parts[0])
            if arg_parts:
                del arg_parts[0]
        else:
            parsed.status = PARSED_ERROR
            parsed.message = (
                f"Unrecognized parameter '{arg_parts[0]}' (must be 'in' or 'out')."
            )
    elif arg_conf.arg_type == ARG_YESNO:
        if arg_parts[0].lower() in {"yes", "no", "y", "n"}:
            parsed.result_args.append(arg_parts[0])
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

    # print(f"  _parse_user_command has {user_str=}")
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
        parts.insert(0,COMMANDS[CMD_BIKE_INOUT].invoke[0])

    # What command is this?
    what_command = find_command(parts[0])
    if not what_command:
        return ParsedCommand(status=PARSED_ERROR, message="Unrecognized command.")
    cmd_config = COMMANDS[what_command]

    arg_parts = parts[1:]  # These are the potential arguments

    # This command takes some arguments
    parsed = ParsedCommand(command=what_command)
    parsed.status = PARSED_OK  # FIXME: Ugh? But works?
    for this_arg_config in cmd_config.arg_configs:
        if not _chunkize_for_one_arg(arg_parts, this_arg_config, parsed):
            break

    # There should now be no arg_parts left
    if parsed.status == PARSED_OK and arg_parts:
        parsed.status = PARSED_ERROR
        parsed.message = f"Extra text at end of command: '{' '.join(arg_parts)}'."

    return parsed


def fetch_user_command() -> ParsedCommand:
    """Get a completed command (or nothing) from user."""
    user_input = get_input()
    result = _parse_user_command(user_input)
    while result.status == PARSED_INCOMPLETE:
        # Need more args. Get the subprompt for the next arg
        subprompt_text = _subprompt_text(result)
        # Repeat the parsing using what had before + new input
        subprompt_input = subprompt(subprompt_text)
        if subprompt_input:
            user_input = user_input + " " + subprompt_input
            result = _parse_user_command(user_input)
        else:
            # Cancelled (no input)
            result.status = PARSED_CANCELLED
    return result

if __name__ == "__main__":
    while True:
        # user_input = input("Enter your command: ")
        print()
        parsed_command = fetch_user_command()
        parsed_command.dump()
        if parsed_command.command == CMD_EXIT and parsed_command.status == PARSED_OK:
            print("exiting")
            break
