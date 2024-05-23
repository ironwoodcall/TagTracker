"""Command parser

Copyright (c) 2024 Todd Glover & Julias Hocking

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.


    THESE ARE ROUGH NOTES

"""
import re
from datetime import datetime

# Validation functions
def is_valid_tag(tagid):
    valid_tags = {"tag1", "tag2", "tag3"}  # Example set of valid tags
    return tagid in valid_tags

class Validation:
    def validate(self, value):
        raise NotImplementedError("Subclasses should implement this method")

class ChoiceValidation(Validation):
    def __init__(self, choices):
        self.choices = choices

    def validate(self, value):
        return value in self.choices

class TimeValidation(Validation):
    def validate(self, value):
        return value in ["morning", "afternoon", "evening"]

class DateValidation(Validation):
    def validate(self, value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False

# Command constants
CMD_ADD = "CMD_ADD"
CMD_REMOVE = "CMD_REMOVE"
CMD_UPDATE = "CMD_UPDATE"
CMD_NOTES = "CMD_NOTES"
CMD_REG = "CMD_REG"
CMD_HELP = "CMD_HELP"
CMD_INOUT = "CMD_INOUT"

CMD_NONE = "nothing"
CMD_AUDIT = "audit"
CMD_DELETE = "delete"
CMD_EDIT = "edit"
CMD_IN = "tag_in"
CMD_OUT = "tag_out"
CMD_INOUT = "tag_inout"
# These ones can take arguments
CMD_LOOKBACK = "lookback"
CMD_QUERY = "query"
CMD_STATS = "stats"
CMD_BUSY = "busy"
CMD_HOURS = "operating_hours"
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
CMD_TAGS = "tags"
CMD_ESTIMATE = "estimate"
CMD_EXIT = "exit"
CMD_HELP = "help"

# CommandConfig class
class CommandConfig:
    def __init__(self, command_constant, tokens, requires_tags=True, requires_args=False, validation=None, prompts=None):
        self.command_constant = command_constant
        self.tokens = tokens
        self.requires_tags = requires_tags
        self.requires_args = requires_args
        self.validation = validation or []
        self.prompts = prompts or []

    def matches(self, name):
        return name in self.tokens

# Commands dictionary
commands = [
    CommandConfig(command_constant=CMD_ADD, tokens=["add", "a"], requires_tags=True, requires_args=False),
    CommandConfig(command_constant=CMD_REMOVE, tokens=["remove", "rm"], requires_tags=True, requires_args=False),
    CommandConfig(
        command_constant=CMD_UPDATE,
        tokens=["update", "upd"],
        requires_tags=True,
        requires_args=True,
        validation=[
            ChoiceValidation(["in", "out"]),
            TimeValidation(),
            DateValidation()
        ],
        prompts=[
            "Enter 'in' or 'out': ",
            "Enter a valid time (e.g., 'morning', 'afternoon', 'evening'): ",
            "Enter a date (YYYY-MM-DD): "
        ]
    ),
    CommandConfig(command_constant=CMD_NOTES, tokens=["notes"], requires_tags=False, requires_args=False),
    CommandConfig(command_constant=CMD_REG, tokens=["reg"], requires_tags=False, requires_args=True),
    CommandConfig(command_constant=CMD_HELP, tokens=["help"], requires_tags=False, requires_args=False),
    # Add more commands as needed
]

def find_command(command_name):
    for command in commands:
        if command.matches(command_name):
            return command
    return None

# Input sanitization
def sanitize_input(user_input):
    return user_input.strip().lower()

class ParsedCommand:
    def __init__(self, command=None, tagids=None, args=None, status="OK", message=""):
        self.command = command
        self.tagids = tagids or []
        self.args = args or []
        self.status = status
        self.message = message

def parse_user_input(user_input):
    parts = sanitize_input(user_input).split()
    if not parts:
        return ParsedCommand(status="Error", message="No command provided.")

    command_name = parts[0]
    command_config = find_command(command_name)
    if command_config is None:
        return ParsedCommand(status="Error", message=f"Invalid command '{command_name}'.")

    tagids = []
    additional_args = []

    if command_config.requires_tags:
        for part in parts[1:]:
            if is_valid_tag(part):
                tagids.append(part)
            else:
                additional_args.append(part)

        if not tagids:
            return ParsedCommand(status="Error", message="No tags provided.")
    else:
        additional_args = parts[1:]

    if command_config.command_constant == CMD_NOTES:
        notes_text = ' '.join(additional_args)
        return ParsedCommand(command_config.command_constant, [], [notes_text])

    if command_config.command_constant == CMD_REG:
        if additional_args:
            reg_arg = additional_args[0]
            if re.match(r"^[+-=]\d+$", reg_arg):
                return ParsedCommand(command_config.command_constant, [], [reg_arg])
            else:
                return ParsedCommand(status="Error", message=f"Invalid argument for 'reg': {reg_arg}")
        else:
            return ParsedCommand(command_config.command_constant, [], [])

    if command_config.command_constant == CMD_HELP:
        if additional_args:
            return ParsedCommand(status="Error", message="'help' command does not take arguments.")
        return ParsedCommand(command_config.command_constant, [], [])

    if command_config.requires_args:
        if len(additional_args) < len(command_config.validation):
            additional_args = prompt_for_args(command_config, len(additional_args), additional_args)

        if additional_args is None:
            return ParsedCommand(status="Cancelled", message="Command cancelled.")

    return ParsedCommand(command_config.command_constant, tagids, additional_args)

def process_command(parsed_command):
    if parsed_command.status == "Error":
        print(parsed_command.message)
        return
    elif parsed_command.status == "Cancelled":
        print("Command cancelled.")
        return

    command_name = parsed_command.command
    tagids = parsed_command.tagids
    args = parsed_command.args

    if not args and find_command(command_name).requires_args:
        print("Command requires additional arguments.")
        return

    # Implement command-specific processing here
    if command_name == CMD_ADD:
        print(f"Adding tags: {tagids}")
    elif command_name == CMD_REMOVE:
        print(f"Removing tags: {tagids}")
    elif command_name == CMD_UPDATE:
        print(f"Updating tags: {tagids} with arguments: {args}")
    elif command_name == CMD_INOUT:
        print(f"Processing inout command with tags: {tagids}")
    elif command_name == CMD_NOTES:
        print(f"Notes: {' '.join(args)}")
    elif command_name == CMD_REG:
        print(f"Register command with argument: {args[0] if args else 'None'}")
    elif command_name == CMD_HELP:
        print("Help command invoked.")
    else:
        print(f"Unknown command '{command_name}'.")


def prompt_for_args(command_config, starting_index, existing_args):
    args = existing_args.copy()
    for i in range(starting_index, len(command_config.prompts)):
        while True:
            user_input = input(command_config.prompts[i]).strip()
            if not user_input:
                print("Command cancelled.")
                return None
            if command_config.validation[i].validate(user_input):
                args.append(user_input)
                break
            else:
                print("Invalid input. Please try again.")
    return args


# Main function
def main():
    while True:
        user_input = input("Enter your command: ")
        parsed_command = parse_user_input(user_input)
        process_command(parsed_command)

if __name__ == "__main__":
    main()


"""
#-----------------------------------------
import re
from datetime import datetime

# Validation functions
def is_a_tag(tagid):
    valid_tags = {"tag1", "tag2", "tag3"}  # Example set of valid tags
    return tagid in valid_tags

# Command constants
CMD_ADD = "CMD_ADD"
CMD_REMOVE = "CMD_REMOVE"
CMD_UPDATE = "CMD_UPDATE"
CMD_INOUT = "CMD_INOUT"
CMD_NOTES = "CMD_NOTES"
CMD_REG = "CMD_REG"
CMD_HELP = "CMD_HELP"

# Base Validation class and subclasses
class Validation:
    def validate(self, value):
        raise NotImplementedError("Subclasses should implement this method")

class ChoiceValidation(Validation):
    def __init__(self, choices):
        self.choices = choices

    def validate(self, value):
        return value in self.choices

class VTimeValidation(Validation):
    def validate(self, value):
        return value in ["morning", "afternoon", "evening"]

class DateValidation(Validation):
    def validate(self, value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False

# CommandConfig class
class CommandConfig:
    def __init__(self, command_constant, tokens, requires_tags=True, requires_args=False, validation=None, prompts=None):
        self.command_constant = command_constant
        self.tokens = tokens
        self.requires_tags = requires_tags
        self.requires_args = requires_args
        self.validation = validation or []
        self.prompts = prompts or []

    def matches(self, name):
        return name in self.tokens

# ParsedCommand class
class ParsedCommand:
    def __init__(self, command, tagids, args):
        self.command = command
        self.tagids = tagids
        self.args = args

# Commands dictionary
commands = [
    CommandConfig(command_constant=CMD_ADD, tokens=["add", "a"], requires_tags=True, requires_args=False),
    CommandConfig(command_constant=CMD_REMOVE, tokens=["remove", "rm"], requires_tags=True, requires_args=False),
    CommandConfig(
        command_constant=CMD_UPDATE,
        tokens=["update", "upd"],
        requires_tags=True,
        requires_args=True,
        validation=[
            ChoiceValidation(["in", "out"]),
            VTimeValidation(),
            DateValidation()
        ],
        prompts=[
            "Enter 'in' or 'out': ",
            "Enter a valid time (e.g., 'morning', 'afternoon', 'evening'): ",
            "Enter a date (YYYY-MM-DD): "
        ]
    ),
    CommandConfig(command_constant=CMD_NOTES, tokens=["notes"], requires_tags=False, requires_args=False),
    CommandConfig(command_constant=CMD_REG, tokens=["reg"], requires_tags=False, requires_args=False),
    CommandConfig(command_constant=CMD_HELP, tokens=["help"], requires_tags=False, requires_args=False),
    # Add more commands as needed
]

def find_command(command_name):
    for command in commands:
        if command.matches(command_name):
            return command
    return None

def parse_user_input(user_input):
    parts = user_input.split()
    if not parts:
        return "Error: No command provided."

    # Check if the first token is a tag, if so, prepend "inout"
    if is_a_tag(parts[0]):
        user_input = "inout " + user_input
        parts = user_input.split()

    command_name = parts[0]
    command_config = find_command(command_name)
    if command_config is None:
        return f"Error: Invalid command '{command_name}'."

    tagids = []
    additional_args = []

    if command_config.requires_tags:
        for part in parts[1:]:
            if is_a_tag(part):
                tagids.append(part)
            else:
                additional_args.append(part)

        if not tagids:
            return "Error: No tags provided."
    else:
        additional_args = parts[1:]

    if command_config.command_constant == CMD_NOTES:
        # Everything after 'notes' is the argument
        notes_text = ' '.join(additional_args)
        return ParsedCommand(command_config.command_constant, [], [notes_text])

    if command_config.command_constant == CMD_REG:
        # Check if argument is valid (+n, -n, =n)
        if additional_args:
            reg_arg = additional_args[0]
            if re.match(r"^[+-=]\d+$", reg_arg):
                return ParsedCommand(command_config.command_constant, [], [reg_arg])
            else:
                return f"Error: Invalid argument for 'reg': {reg_arg}"
        else:
            return ParsedCommand(command_config.command_constant, [], [])

    if command_config.command_constant == CMD_HELP:
        # Help command takes no arguments
        if additional_args:
            return "Error: 'help' command does not take arguments."
        return ParsedCommand(command_config.command_constant, [], [])

    if command_config.requires_args:
        if len(additional_args) < len(command_config.validation):
            additional_args = prompt_for_args(command_config, len(additional_args), additional_args)

    if additional_args is None:
        return "Command cancelled."

    return ParsedCommand(command_config.command_constant, tagids, additional_args)

def prompt_for_args(command_config, starting_index, existing_args):
    args = existing_args.copy()
    for i in range(starting_index, len(command_config.prompts)):
        while True:
            user_input = input(command_config.prompts[i]).strip()
            if not user_input:
                print("Command cancelled.")
                return None
            if command_config.validation[i].validate(user_input):
                args.append(user_input)
                break
            else:
                print("Invalid input. Please try again.")
    return args

def process_command(parsed_command):
    if isinstance(parsed_command, str):
        print(parsed_command)
        return

    command_name = parsed_command.command
    tagids = parsed_command.tagids
    args = parsed_command.args

    if not args and find_command(command_name).requires_args:
        print("Command cancelled.")
        return

    # Implement command-specific processing here
    if command_name == CMD_ADD:
        print(f"Adding tags: {tagids}")
    elif command_name == CMD_REMOVE:
        print(f"Removing tags: {tagids}")
    elif command_name == CMD_UPDATE:
        print(f"Updating tags: {tagids} with arguments: {args}")
    elif command_name == CMD_INOUT:
        print(f"Processing inout command with tags: {tagids}")
    elif command_name == CMD_NOTES:
        print(f"Notes: {' '.join(args)}")
    elif command_name == CMD_REG:
        print(f"Register command with argument: {args[0] if args else 'None'}")
    elif command_name == CMD_HELP:
        print("Help command invoked.")
    else:
        print(f"Unknown command '{command_name}'.")

# Example usage
user_input = "tag1 tag2"
parsed_command = parse_user_input(user_input)
process_command(parsed_command)

user_input = "notes This is a note"
parsed_command = parse_user_input(user_input)
process_command(parsed_command)

user_input = "reg +5"
parsed_command = parse_user_input(user_input)
process_command(parsed_command)

user_input = "help"
parsed_command = parse_user_input(user_input)
process_command(parsed_command)
"""