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

from common.tt_tag import TagID
import tt_printer as pr
import common.tt_util as ut
import client_base_config as cfg
from common.tt_time import VTime
import common.tt_constants as k
import tt_default_hours
from common.tt_trackerday import TrackerDay
from common.get_version import get_version_info
from tt_sounds import NoiseMaker

# Import pyfiglet if it's available.
# (To create ascii art splash screen.)
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
    pr.iprint(f"TagTracker version: {get_version_info()}")
    pr.iprint("See github.com/ironwoodcall/tagtracker for version details.")
    pr.iprint()


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



def confirm_hours(today: TrackerDay) -> bool:
    #     date: k.MaybeDate, current_open: k.MaybeTime, current_close: k.MaybeTime
    # ) -> tuple[bool, VTime, VTime]:
    """Get/set operating hours.

    Returns flag True if values have changed

    Logic:
    - On entry, current_open/close are either times or ""
    - If "", sets from defaults
    - Prompts user for get/confirm
    - Changes values in TrackerDay

    """
    maybe_open = today.time_open
    maybe_close = today.time_closed
    if not maybe_open or not maybe_close:
        # Set any blank value from config'd defaults
        default_open, default_close = tt_default_hours.get_default_hours(today.date)
        maybe_open = maybe_open or default_open
        maybe_close = maybe_close or default_close

    # Prompt user to get/confirm times
    done = False
    new_open, new_close = VTime(maybe_open), VTime(maybe_close)
    while not done:
        new_open, new_close = get_operating_hours(new_open, new_close)
        if new_open >= new_close:
            pr.iprint(
                f"Closing time must be later than opening time {new_open}",
                style=k.ERROR_STYLE,
            )
        else:
            done = True
    # Has anything changed?
    data_changed = bool(
        new_open != today.time_open or new_close != today.time_closed
    )
    # Save the changed
    today.time_open = new_open
    today.time_closed = new_close
    # Done, return whether data has changed
    return data_changed


def get_operating_hours(opening: str = "", closing: str = "") -> tuple[str, str]:
    """Get/confirm today's operating hours."""

    def get_one_time(current_time: str, prompt_bit: str) -> str:
        """Confirm/get an opening or closing time."""
        current_time = VTime(current_time)
        while True:
            if current_time:
                pr.iprint(
                    f"Enter new 24-hour HHMM {prompt_bit} time or press <Enter> "
                    f"to leave as {current_time.short}: ",
                    end="",
                    style=k.SUBPROMPT_STYLE,
                )
            else:
                pr.iprint(
                    f"Enter 24-hour HHMM {prompt_bit} time: ",
                    end="",
                    style=k.SUBPROMPT_STYLE,
                )
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


def check_bike_time_reasonable(bike_time: VTime, day: TrackerDay) -> bool:
    """Check if 'bike_time' is reasonably close to operating hours.

    Will give an error message if not.

    Returns True if seems reasonable, False otherwise.
    If operating hours not set, returns True.
    """

    if day.bike_time_reasonable(bike_time):
        return True

    pr.iprint(
        f"Time ({bike_time.short}) is too far outside open hours "
        f"({day.time_open.short}-{day.time_closed.short}).",
        style=k.WARNING_STYLE,
    )
    NoiseMaker.play(k.ALERT)
    return False


def check_tagid_usable(tagid: TagID, today: TrackerDay) -> bool:
    """Checks if tagid is usable, error msg if not.

    In this context, usable means REGULAR or OVERSIZE and
    not RETIRED.

    Returns True if usable, False if not.
    """
    if tagid in today.all_usable_tags():
        return True

    if tagid in today.retired_tagids:
        msg = f"Tag {tagid} is retired."
    else:
        msg = f"No tag '{tagid.original}' available today."
    pr.iprint(msg, style=k.WARNING_STYLE)
    NoiseMaker.play(k.ALERT)
    return False


def data_owner_notice():
    """Print a data ownership notice."""
    if cfg.DATA_OWNER:
        pr.iprint()
        data_note = (
            cfg.DATA_OWNER if isinstance(cfg.DATA_OWNER, list) else [cfg.DATA_OWNER]
        )
        for line in data_note:
            pr.iprint(line, style=k.ANSWER_STYLE)
