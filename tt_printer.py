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
##from tt_colours import *
from tt_colours import (HAVE_COLOURS, STYLE,
            PROMPT_STYLE, SUBPROMPT_STYLE, ANSWER_STYLE, TITLE_STYLE,
            SUBTITLE_STYLE, RESET_STYLE, NORMAL_STYLE, HIGHLIGHT_STYLE,
            WARNING_STYLE, ERROR_STYLE,Fore,Back,Style)


# Amount to indent normal output. iprint() indents in units of _INDENT
_INDENT = '  '

# If use colour, try to import colorama library
#USE_COLOUR = True
#if USE_COLOUR and not HAVE_COLOURS:
#    USE_COLOUR = False
#    print("WARNING: No colours available, text will be in black & white.")


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
    """Set the echo state to ON or OFF."""
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
    (ie not just to screen).
    """
    pass

def get_output() -> str:
    """Get the current output destination (filename), or "" if screen."""
    return _destination_filename


def text_style(text:str, style=None) -> str:
    """Return text with style 'style' applied."""
    if not cfg.USE_COLOUR:
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
    indent = _INDENT * num_indents
    if cfg.USE_COLOUR and style:
        styled = f"{indent}{text_style(text,style=style)}"
    else:
        styled = f"{indent}{text}"
    # Output goes either to screen or to a file
    #FIXME : this will send styled output to file and echo
    if _destination:
        _destination_file.write(styled,"\n")
    else:
        print(styled,end=end)

    if _echo_state:
        echo(styled)



