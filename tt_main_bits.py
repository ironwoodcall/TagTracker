"""TagTracker by Julias Hocking.

Various helper bit for the main startup/loop in data entry client of tagtracker.

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
import tt_util as ut
import client_base_config as cfg
from tt_time import VTime
import tt_constants as k
import tt_default_hours

# Import pyfiglet if it's available.
try:
    import random
    import pyfiglet

    PYFIGLET = True
except ImportError:
    PYFIGLET = False


def splash():
    """Print a splash message including version & credits."""
    if not splash_top_pyfiglet():
        splash_top_default()
    pr.iprint()
    pr.iprint("TagTracker by Julias Hocking")
    pr.iprint(f"Version: {ut.get_version()}")
    pr.iprint("See github.com/ironwoodcall/tagtracker for version details.")


def splash_top_pyfiglet():
    """Print a randomly-selected pyfiglet message.

    If nothing fits then returns False. If worked ok then True.
    """

    def render(
        message, font, max_width: int = 80, hpadding: int = 0, vpadding: int = 0
    ) -> list[str]:
        """Render message in the font, return strings list or None.

        On return, all the strings will be of the same length.
        Empty strings will be removed from the top and bottom.
        Strings will be padded front and back with 'hpadding' spaces,
        and 'vpadding' blank lines above & below.
        """

        f = pyfiglet.Figlet(font=font)
        f.width = 2000
        lines = f.renderText(message).split("\n")
        lines = [s.rstrip() for s in lines]
        longest = max((len(s) for s in lines))
        if longest > max_width or longest == len(message):
            return None
        # Remove empty strings from the end..
        while lines and len(lines[-1]) == 0:
            lines.pop()
        # ..and the beginning of the list
        while lines and len(lines[0]) == 0:
            lines.pop(0)
        # Now add any vertical padding blank lines
        vpad = [""] * vpadding
        lines = vpad + lines + vpad
        # Pad them to the same length, including extra padding.
        lines = [" " * hpadding + s.ljust(longest + hpadding) for s in lines]
        # Add any vertical padding
        # Return the result
        return lines

    if not PYFIGLET:
        return False
    available_fonts = pyfiglet.FigletFont.getFonts()
    msg_lines = None
    while available_fonts and not msg_lines:
        font = random.choice(available_fonts)
        available_fonts.remove(font)
        msg_lines = render("TagTracker", font, hpadding=2, vpadding=1)

    if not msg_lines:
        return False

    # Print the message
    for line in msg_lines:
        pr.iprint(line, style=k.ANSWER_STYLE)
    return True


def splash_top_default():
    """Print the default intro splash message."""

    for line in [
        r"   _______       _______             _               ",
        r"  |__   __|     |__   __|           | |              ",
        r"     | | __ _  __ _| |_ __ __ _  ___| | _____ _ __   ",
        r"     | |/ _` |/ _` | | '__/ _` |/ __| |/ / _ \ '__|  ",
        r"     | | (_| | (_| | | | | (_| | (__|   <  __/ |     ",
        r"     |_|\__,_|\__, |_|_|  \__,_|\___|_|\_\___|_|     ",
        r"               __/ |                                 ",
        r"              |___/                                  ",
    ]:
        pr.iprint(
            line,
            style=k.ANSWER_STYLE,
        )


def show_help():
    """Show help_message with colour style highlighting.

    Prints first non-blank line as title;
    lines that are flush-left as subtitles;
    other lines in normal style.
    """
    title_done = False
    for line in k.HELP_MESSAGE.split("\n"):
        if not line:
            pr.iprint()
        elif not title_done:
            title_done = True
            pr.iprint(line, style=k.TITLE_STYLE)
        elif line[0] != " ":
            pr.iprint(line, style=k.SUBTITLE_STYLE)
        else:
            pr.iprint(line, style=k.NORMAL_STYLE)


def show_notes(notes_obj, header: bool = False, styled: bool = True) -> None:
    """Print notes."""
    notes_list = notes_obj.fetch()
    pr.iprint()

    if header:
        if notes_list:
            pr.iprint("Today's notes:", style=k.TITLE_STYLE)
        else:
            pr.iprint("There are no notes yet today.")
            pr.iprint("(To create a note, enter NOTE [note text])")
    for line in notes_list:
        if styled:
            pr.iprint(line, style=k.WARNING_STYLE)
        else:
            pr.iprint(line, style=k.NORMAL_STYLE)


def confirm_hours(
    date: k.MaybeDate, current_open: k.MaybeTime, current_close: k.MaybeTime
) -> tuple[bool, VTime, VTime]:
    """Get/set operating hours.

    Returns flag True if values have changed
    and new (or unchanged) open and close times as as tuple:
        changed:bool, open:VTime, closed:VTime

    Logic:
    - On entry, current_open/close are either times or ""
    - If "", sets from defaults
    - Prompts user for get/confirm
    - Returns result tuple

    """
    maybe_open, maybe_close = (current_open, current_close)
    if not maybe_open or not maybe_close:
        # Set any blank value from config'd defaults
        default_open, default_close = tt_default_hours.get_default_hours(date)
        maybe_open = maybe_open if maybe_open else default_open
        maybe_close = maybe_close if maybe_close else default_close

    # Prompt user to get/confirm times
    done = False
    new_open, new_close = VTime(maybe_open), VTime(maybe_close)
    while not done:
        new_open, new_close = get_operating_hours(new_open, new_close)
        if new_open >= new_close:
            pr.iprint(
                "Closing time must be later than opening time", style=k.ERROR_STYLE
            )
        else:
            done = True
    # Has anything changed?
    return (
        bool(new_open != current_open or new_close != current_close),
        new_open,
        new_close,
    )


def get_operating_hours(opening: str = "", closing: str = "") -> tuple[str, str]:
    """Get/confirm today's operating hours."""

    def get_one_time(current_time: str, prompt_bit: str) -> str:
        """Confirm/get an opening or closing time."""
        current_time = VTime(current_time)
        while True:
            if current_time:
                pr.iprint(
                    f"Enter new 24-hour HHMM {prompt_bit} time or press <Enter> to leave as {current_time.short}: ",
                    end="",
                    style=k.PROMPT_STYLE,
                )
            else:
                pr.iprint(f"Enter 24-hour HHMM {prompt_bit} time: ", end="")
            inp = pr.tt_inp().strip()
            if current_time and not inp:
                return current_time
            new_time = VTime(inp)
            if new_time:
                return new_time
            else:
                pr.iprint("Not a time. ", style=k.WARNING_STYLE)

    which = "confirm" if opening else "enter"
    pr.iprint()
    pr.iprint(
        f"Please {which} today's operating hours.", style=k.HIGHLIGHT_STYLE, end=""
    )
    if opening and closing:
        pr.iprint(
            f"  Currently set at {opening.short} - {closing.short}.",
            num_indents=0,
            style=k.HIGHLIGHT_STYLE,
            end="",
        )
    pr.iprint()  # linefeed for end of the above line
    opening = get_one_time(opening, "opening")
    closing = get_one_time(closing, "closing")
    return opening, closing


def data_owner_notice():
    """Print a data ownership notice."""
    if cfg.DATA_OWNER:
        pr.iprint()
        data_note = (
            cfg.DATA_OWNER if isinstance(cfg.DATA_OWNER, list) else [cfg.DATA_OWNER]
        )
        for line in data_note:
            pr.iprint(line, style=k.ANSWER_STYLE)
