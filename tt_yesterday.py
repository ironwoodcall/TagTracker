"""TagTracker by Julias Hocking.

YESTERDAY command: a quick look back at the most recent day before today.

Copyright (C) 2023-2026 Julias Hocking & Todd Glover

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

from __future__ import annotations

from common.tt_tag import TagID
from common.tt_time import VTime
from common.tt_trackerday import TrackerDay, TrackerDayError
import common.tt_constants as k
import common.tt_util as ut
import tt_audit_report as aud
import tt_datafile as df
import tt_hold
import tt_notes_command as notes_cmd
import tt_printer as pr


def _latest_event(day: TrackerDay) -> tuple[VTime, TagID, bool] | None:
    """Return (time, tag, is_check_in) for the day's single latest event.

    Considers both check-ins and check-outs across every tag; returns
    None if the day has no visits at all.
    """
    latest = None
    for visit in day.all_visits():
        for when, is_check_in in ((visit.time_in, True), (visit.time_out, False)):
            if when and (latest is None or when > latest[0]):
                latest = (when, visit.tagid, is_check_in)
    return latest


def report(folder: str) -> None:
    """Print a look-back at the most recent datafile dated before today.

    Loads that day's own saved state as-is (not reconciled against
    today's config -- see tt_hold.previous_day_held_tags()'s docstring
    for why that distinction matters here too) and reports its notes,
    what tags were left suspended at close of business, and the same
    in/out/on-site summary table AUDIT shows.

    Unlike the startup FYI report, this is a command the user asked for,
    so it always answers -- including when there's nothing to report for
    a given section.
    """
    filepath = df.most_recent_datafile_before(folder, "today")
    if not filepath:
        pr.iprint("No earlier data found.", style=k.WARNING_STYLE)
        return

    try:
        day = TrackerDay.load_from_file(filepath)
    except TrackerDayError as e:
        pr.iprint(f"Could not read {filepath}:", style=k.ERROR_STYLE)
        for s in e.args:
            pr.iprint(s, style=k.ERROR_STYLE, num_indents=2)
        return

    if day.date == ut.date_str("yesterday"):
        date_label = "yesterday"
    else:
        date_label = ut.date_str(day.date, long_date=True) if day.date else filepath
    pr.iprint()
    pr.iprint(f"Overview of {date_label}, as at end of day", style=k.TITLE_STYLE)

    active_notes = day.notes.active_notes()
    if active_notes:
        notes_cmd.show_notes_sublist(
            active_notes, "Notes:", num_indents=2, show_styled=False
        )
    else:
        pr.iprint()
        pr.iprint("No notes.", style=k.SUBTITLE_STYLE)

    held = sorted(day.tags_held())
    if held:
        tt_hold.print_tag_list(
            f"{len(held)} {ut.plural(len(held),'tag')} suspended at close "
            "of business:",
            held,
        )
    else:
        pr.iprint()
        pr.iprint("No tags were suspended at close of business.", style=k.SUBTITLE_STYLE)

    closing = day.time_closed or VTime("23:59")
    aud.inout_summary(day, as_of_when=closing, live=False)

    pr.iprint()
    latest = _latest_event(day)
    if latest:
        when, tag, is_check_in = latest
        action = "in" if is_check_in else "out"
        pr.iprint(f"Last tag activity: {tag} checked {action} at {when.short}.")
    else:
        pr.iprint("No tag activity recorded.")
