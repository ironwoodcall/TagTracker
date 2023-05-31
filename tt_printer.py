"""TagTracker by Julias Hocking.

Styling and printing functions for  the TagTracker suite.

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

import os
import io

# The readline module magically solves arrow keys creating ANSI esc codes
# on the Chromebook.  But it isn't on all platforms.
try:
    import readline # pylint:disable=unused-import
except ImportError:
    pass

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
import tt_util as ut
import tt_config as cfg

# Use colour in the program?
USE_COLOUR = True
# If use colour, try to import colorama library
if USE_COLOUR:
    try:
        from colorama import Style,Fore,Back
    except ImportError:
        USE_COLOUR = False
        print("WARNING: No 'colorame' module, text will be in black & white.")

# Amount to indent normal output. iprint() indents in units of _INDENT
_INDENT = '  '

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


# echo will save all input & (screen) output to an echo logfile
# To start echoing, call set_echo(True)
# To stop it, call set_echo(False)

_echo_state = False
_echo_filename = os.path.join(cfg.PUBLISH_FOLDER,f"echo-{ut.get_date()}.txt")
_echo_file = None # This is the file object

def get_echo() -> bool:
    """Return current echo state ON or OFF."""
    return _echo_state

def set_echo(state:bool) -> None:
    """Sets the echo state to ON or OFF."""
    global _echo_state, _echo_file
    if state == _echo_state:
        return
    _echo_state = state
    # If turning echo off, close the file
    if not state and isinstance(_echo_file,io.TextIOWrapper):
        _echo_file.close()
    # If turning echo on, try to open the file
    if state:
        try:
            _echo_file = open(_echo_filename,"at",encoding="utf-8")
        except OSError:
            ut.squawk(f"OSError opening echo file '{_echo_filename}'")

def echo(text:str="") -> None:
    """Send text to the echo log."""
    if not _echo_state:
        return
    if not _echo_file:
        ut.squawk("call to echo when echo file not open")
        set_echo(False)
        return
    _echo_file.write(text,"\n")

def tt_inp(prompt:str="") -> str:
    """Get input, possibly echo to file."""
    inp = input(prompt)
    if _echo_state:
        echo(inp)
    return inp

# Output destination
_destination = ""   # blank == screen
_destination_file = None
_destination_filename = ""

def set_output(filename:str="") -> None:
    """Set print destination to filename or (default) screen.

    Only close the file if it has changed to a different filename
    (ie not just to screen)."""
    pass

def get_output() -> str:
    """Get the current output destination (filename), or "" if screen."""
    return _destination_filename


def text_style(text:str, style=None) -> str:
    """Return text with style 'style' applied."""
    if not USE_COLOUR:
        return text
    if not style:
        style = NORMAL_STYLE
    if style not in STYLE:
        ut.squawk(f"Call to text_style() with unknown style '{style}'")
        return "!!!???"
    return f"{STYLE[style]}{text}{STYLE[RESET_STYLE]}"

def iprint(text:str="", num_indents:int=1, style=None,end="\n") -> None:
    """Print the text, indented num_indents times.

    Recognizes the 'end=' keyword for the print() statement.
    """
    indented = f"{_INDENT * num_indents}{text}"
    if USE_COLOUR and style:
        styled = text_style(indented,style=style)
    else:
        style = indented
    # Output goes either to screen or to a file
    if _destination:
        _destination_file.write(indented,"\n")
    else:
        print(styled,end=end)

    if _echo_state:
        echo(indented)



