"""TagTracker by Julias Hocking.

Provides colorama-based colour codes for TagTracker program.  Exposes:
    Fore, Back, Style objects which either are loaded with colorama
        values or blanks (if colorama was not available).
    HAVE_COLOURS which is T/F if colorama colours were loaded.
    STYLE dictionary
    Style names (e.g. HIGHLIGHT_STYLE)

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


class _ForeClass:
    """An empty mockup of colorama's Fore class."""

    def __init__(self):
        """Set the colorama attributes."""
        self.BLACK = ""
        self.BLUE = ""
        self.CYAN = ""
        self.GREEN = ""
        self.LIGHTBLACK_EX = ""
        self.LIGHTBLUE_EX = ""
        self.LIGHTCYAN_EX = ""
        self.LIGHTGREEN_EX = ""
        self.LIGHTMAGENTA_EX = ""
        self.LIGHTRED_EX = ""
        self.LIGHTWHITE_EX = ""
        self.LIGHTYELLOW_EX = ""
        self.MAGENTA = ""
        self.RED = ""
        self.RESET = ""
        self.WHITE = ""
        self.YELLOW = ""


class _BackClass:
    """An empty mockup of colorama's Back class."""

    def __init__(self):
        """Set the colorama attributes."""
        self.BLACK = ""
        self.BLUE = ""
        self.CYAN = ""
        self.GREEN = ""
        self.LIGHTBLACK_EX = ""
        self.LIGHTBLUE_EX = ""
        self.LIGHTCYAN_EX = ""
        self.LIGHTGREEN_EX = ""
        self.LIGHTMAGENTA_EX = ""
        self.LIGHTRED_EX = ""
        self.LIGHTWHITE_EX = ""
        self.LIGHTYELLOW_EX = ""
        self.MAGENTA = ""
        self.RED = ""
        self.RESET = ""
        self.WHITE = ""
        self.YELLOW = ""


class _StyleClass:
    """An empty mockup of colorama's Style class."""

    def __init__(self):
        """Set the colorama attributes."""
        self.BRIGHT = ""
        self.DIM = ""
        self.NORMAL = ""
        self.RESET_ALL = ""


# If use colour, try to import colorama library
HAVE_COLOURS = True
try:
    import colorama

    # from colorama import Style,Fore,Back
except ImportError:
    print("No colouring available (colorama module not installed)")
    HAVE_COLOURS = False

# Set Fore, Back, Style objects - either from colorama or as blank
if HAVE_COLOURS:
    Fore = colorama.Fore
    Back = colorama.Back
    Style = colorama.Style
else:
    Fore = _ForeClass()
    Back = _BackClass()
    Style = _StyleClass()


# Styles related to colour
STYLE = {}
PROMPT_STYLE = "prompt_style"
SUBPROMPT_STYLE = "subprompt_style"
ANSWER_STYLE = "answer_style"
TITLE_STYLE = "title_style"
SUBTITLE_STYLE = "subtitle_style"
NORMAL_STYLE = "normal_style"
RESET_STYLE = "reset_style"
HIGHLIGHT_STYLE = "highlight_style"
WARNING_STYLE = "warn_style"
ERROR_STYLE = "error_style"

# Colour combinations. Override these in local config as desired.
STYLE[PROMPT_STYLE] = f"{Style.BRIGHT}{Fore.GREEN}{Back.BLACK}"
STYLE[SUBPROMPT_STYLE] = f"{Style.BRIGHT}{Fore.GREEN}{Back.BLACK}"
STYLE[ANSWER_STYLE] = f"{Style.BRIGHT}{Fore.YELLOW}{Back.BLUE}"
STYLE[TITLE_STYLE] = f"{Style.BRIGHT}{Fore.WHITE}{Back.BLUE}"
STYLE[SUBTITLE_STYLE] = f"{Style.BRIGHT}{Fore.CYAN}{Back.BLACK}"
STYLE[RESET_STYLE] = f"{Style.RESET_ALL}"
STYLE[NORMAL_STYLE] = f"{Style.RESET_ALL}"
STYLE[HIGHLIGHT_STYLE] = f"{Style.BRIGHT}{Fore.CYAN}{Back.BLACK}"
STYLE[WARNING_STYLE] = f"{Style.BRIGHT}{Fore.RED}{Back.BLACK}"
STYLE[ERROR_STYLE] = f"{Style.BRIGHT}{Fore.WHITE}{Back.RED}"
