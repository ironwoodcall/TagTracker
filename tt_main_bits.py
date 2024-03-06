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
import tt_conf as cfg
from tt_time import VTime


def show_help():
    """Show help_message with colour style highlighting.

    Prints first non-blank line as title;
    lines that are flush-left as subtitles;
    other lines in normal style.
    """
    title_done = False
    for line in cfg.HELP_MESSAGE.split("\n"):
        if not line:
            pr.iprint()
        elif not title_done:
            title_done = True
            pr.iprint(line, style=cfg.TITLE_STYLE)
        elif line[0] != " ":
            pr.iprint(line, style=cfg.SUBTITLE_STYLE)
        else:
            pr.iprint(line, style=cfg.NORMAL_STYLE)


def show_notes(notes_obj, header: bool = False, styled: bool = True) -> None:
    """Print notes."""
    notes_list = notes_obj.fetch()
    pr.iprint()

    if header:
        if notes_list:
            pr.iprint("Today's notes:", style=cfg.TITLE_STYLE)
        else:
            pr.iprint("There are no notes yet today.")
            pr.iprint("(To create a note, enter NOTE [note text])")
    for line in notes_list:
        if styled:
            pr.iprint(line, style=cfg.WARNING_STYLE)
        else:
            pr.iprint(line, style=cfg.NORMAL_STYLE)


def splash():
    """Print the intro splash message."""

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
            style=cfg.ANSWER_STYLE,
        )

    # pr.iprint("#####################", style=cfg.ANSWER_STYLE)
    # pr.iprint("##                 ##", style=cfg.ANSWER_STYLE)
    # pr.iprint("##   TagTracker    ##", style=cfg.ANSWER_STYLE)
    # pr.iprint("##                 ##", style=cfg.ANSWER_STYLE)
    # pr.iprint("#####################", style=cfg.ANSWER_STYLE)
    pr.iprint()
    pr.iprint("TagTracker by Julias Hocking")
    pr.iprint(f"Version: {ut.get_version()}")
    pr.iprint("See github.com/ironwoodcall/tagtracker for version details.")


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
                    style=cfg.PROMPT_STYLE,
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
                pr.iprint("Not a time. ", style=cfg.WARNING_STYLE)

    which = "confirm" if opening else "enter"
    pr.iprint()
    pr.iprint(
        f"Please {which} today's operating hours.", style=cfg.HIGHLIGHT_STYLE, end=""
    )
    if opening and closing:
        pr.iprint(
            f"  Currently set at {opening.short} - {closing.short}.",
            num_indents=0,
            style=cfg.HIGHLIGHT_STYLE,
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
            pr.iprint(line, style=cfg.ANSWER_STYLE)
