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

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import

# Use colour in the program?
USE_COLOUR = True
# If use colour, try to import colorama library
if USE_COLOUR:
    try:
        from colorama import Style,Fore,Back
    except ImportError:
        USE_COLOUR = False
        print("WARNING: No 'colorame' module, text will be in black & white.")

# Amount to indent normal output. iprint() indents in units of INDENT
INDENT = '  '

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

def text_style(text:str, style=None) -> str:
    """Return text with style 'style' applied."""
    if not USE_COLOUR:
        return text
    if not style:
        style = NORMAL_STYLE
    if style not in STYLE:
        iprint(f"*** PROGRAM ERROR: Unknown style '{style}' ***",
               style=ERROR_STYLE)
        return "!!!???"
    return f"{STYLE[style]}{text}{STYLE[RESET_STYLE]}"

def iprint(text:str="", num_indents:int=1, style=None,end="\n") -> None:
    """Print the text, indented num_indents times.

    Recognizes the 'end=' keyword for the print() statement.
    """
    if style:
        text = text_style(text,style=style)
    print(f"{INDENT * num_indents}{text}",end=end)

