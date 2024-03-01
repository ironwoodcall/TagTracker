"""TagTracker by Julias Hocking.

Styling and printing functions for  the TagTracker suite.

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

import os
import sys
import io

# The readline module magically solves arrow keys creating ANSI esc codes
# on the Chromebook.  But it isn't on all platforms.
try:
    import readline  # pylint:disable=unused-import
except ImportError:
    pass

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
import tt_util as ut
import tt_conf as cfg
import tt_notes as notes
from tt_time import VTime


# Amount to indent normal output. iprint() indents in units of _INDENT
_INDENT = "  "

# echo will save all input & (screen) output to an echo datafile
# To start echoing, call set_echo(True)
# To stop it, call set_echo(False)

_echo_state = False
_echo_filename = os.path.join(cfg.ECHO_FOLDER, f"echo-{ut.date_str('today')}.txt")
_echo_file = None  # This is the file object


def get_echo() -> bool:
    """Return current echo state ON or OFF."""
    return _echo_state


def set_echo(state: bool) -> None:
    """Set the echo state to ON or OFF."""
    global _echo_state, _echo_file
    if state == _echo_state:
        return
    _echo_state = state
    # If turning echo off, close the file
    if not state and isinstance(_echo_file, io.TextIOWrapper):
        _echo_file.close()
    # If turning echo on, try to open the file
    if state:
        try:
            _echo_file = open(_echo_filename, "at", encoding="utf-8")
        except OSError:
            ut.squawk(f"OSError opening echo file '{_echo_filename}'")
            ut.squawk("Setting echo off.")
            _echo_state = False


def echo(text: str = "") -> None:
    """Send text to the echo log."""
    if not _echo_state:
        return
    if not _echo_file:
        ut.squawk("call to echo when echo file not open")
        set_echo(False)
        return
    _echo_file.write(f"{text}")


def echo_flush() -> None:
    """If an echo file is active, flush buffer contents to it."""
    if _echo_state and _echo_file:
        # To make more robust, close & reopen echo file intead of flush
        set_echo(False)
        set_echo(True)
        ##_echo_file.flush()


def tt_inp(prompt: str = "", style: str = "") -> str:
    """Get input, possibly echo to file."""
    inp = input(text_style(prompt, style))
    if _echo_state:
        echo(f"{prompt}  {inp}\n")
    return inp


# Output destination
_destination: str = ""  # blank == screen
_destination_file = None


def set_output(filename: str = "") -> bool:
    """Set print destination to filename or (default) screen.

    Only close the file if it has changed to a different filename
    (ie not just to screen).

    Returns True/False if able to change to the new filename.
    (Always True if returning output to screen.)
    """
    global _destination, _destination_file
    if filename == _destination:
        return True
    if _destination:
        _destination_file.close()
    if filename:
        try:
            _destination_file = open(filename, mode="wt", encoding="utf-8")
        except OSError:
            iprint(
                f"OSError opening destination file '{filename}'",
                style=cfg.ERROR_STYLE,
            )
            iprint("Ignoring print redirect request.", style=cfg.ERROR_STYLE)
            _destination = ""
            return False
    _destination = filename
    return True


def get_output() -> str:
    """Get the current output destination (filename), or "" if screen."""
    return _destination


def text_style(text: str, style=None) -> str:
    """Return text with style 'style' applied."""
    # If redirecting to file, do not apply style
    if _destination:
        return text
    # If no colour avilable, do not apply style
    if not cfg.USE_COLOUR:
        return text
    if not style:
        style = cfg.NORMAL_STYLE
    if style not in cfg.STYLE:
        ut.squawk(f"Call to text_style() with unknown style '{style}'")
        return "!!!???"
    return f"{cfg.STYLE[style]}{text}{cfg.STYLE[cfg.RESET_STYLE]}"


def iprint(text: str = "", num_indents: int = None, style=None, end="\n") -> None:
    """Print the text, indented num_indents times.

    Recognizes the 'end=' keyword for the print() statement.

    Everything gets indented
    Only screen output gets styled; indents do *not* get styled to screen
    """
    num_indents = 1 if num_indents is None else num_indents
    indent = _INDENT * num_indents

    # Going to screen?
    if _destination:
        # Going to file - print with indents but no styling
        _destination_file.write(f"{indent}{text}{end}")
    else:
        # Going to screen.  Style and indent.
        if cfg.USE_COLOUR and style:
            styled_text = text_style(text, style=style)
            print(f"{indent}{styled_text}", end=end)
        else:
            print(f"{indent}{text}", end=end)

    # Also echo?
    if _echo_state and not _destination:
        echo(f"{indent}{text}{end}")


def text_alert(message: str = "", style=None) -> None:
    """Print an alert message at the top of the screen.

    The message will overwrite the entire top line of the screen
    in the given style, with some *'s or something around it.

    Will only print if destination is screen (not file).
    """

    # ANSI escape code constants for formatting
    SAVE_CURSOR = "\033[s"
    RESTORE_CURSOR = "\033[u"
    MOVE_CURSOR = "\033[{};{}H"
    MESSAGE_BRACKETING = "***"

    def _save_cursor_position():
        sys.stdout.write(SAVE_CURSOR)
        sys.stdout.flush()

    def _restore_cursor_position():
        sys.stdout.write(RESTORE_CURSOR)
        sys.stdout.flush()

    def _print_message_at_location(row, col, message):
        move_cursor_code = MOVE_CURSOR.format(row, col)
        sys.stdout.write(f"{move_cursor_code}{message}")
        sys.stdout.flush()

    def _get_terminal_size():
        rows, columns = os.popen("stty size", "r").read().split()
        return int(rows), int(columns)

    def _centred_string(text, str_len) -> str:
        """Return a str of len str_len with 'text' in its middle."""
        padding = " " * ((str_len - len(text)) // 2)
        centred_string = padding + text + padding + " "  # NB: extra space
        return centred_string[:str_len]  # Make sure is correct length

    # I suspect this is unneccessary, but benign.
    if _destination:
        return

    # Build the message centred with bracket decorations & color.
    _, screen_width = _get_terminal_size()
    padded_message = _centred_string(
        f"{MESSAGE_BRACKETING} {VTime('now').short} {message} {MESSAGE_BRACKETING}",
        screen_width,
    )
    if style:
        padded_message = text_style(padded_message, style=style)

    # Print the padded message centered on the screen
    _save_cursor_position()
    _print_message_at_location(1, 1, padded_message)
    _restore_cursor_position()


# This dict holds static control data for the print_tag_notes function.
_print_tag_notes_key_prev = "prev_tag"
_print_tag_notes_key_printed = "printed"
_print_tag_notes_control = {
    _print_tag_notes_key_prev: "",
    _print_tag_notes_key_printed: False,
}


def print_tag_notes(tag: str, reset: bool = False):
    """Print notes for a given tag.

    Only prints if not *already* printed .. what a kludge...
    and can be called with 'reset' flag to allow printing again.
    Will also reset if the tag is not the same as the previously-used tag.
    """
    if reset or tag != _print_tag_notes_control[_print_tag_notes_key_prev]:
        _print_tag_notes_control[_print_tag_notes_key_printed] = False

    if tag and not _print_tag_notes_control[_print_tag_notes_key_printed]:
        for line in notes.Notes.find(tag):
            iprint(line, style=cfg.WARNING_STYLE)
        _print_tag_notes_control[_print_tag_notes_key_printed] = True

    _print_tag_notes_control[_print_tag_notes_key_prev] = tag
