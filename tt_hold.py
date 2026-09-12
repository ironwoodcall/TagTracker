"""TagTracker by Julias Hocking.

HOLD/UNHOLD helpers.

See docs/hold_tag_spec.md for the design this implements.

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

import json
import os
from dataclasses import dataclass
from typing import Sequence

import common.tt_constants as k
import common.tt_util as ut
from common.tt_biketag import BikeTag
from common.tt_tag import TagID
from common.tt_trackerday import TrackerDay, TOKEN_HELD_TAGIDS
import tt_datafile as df
import tt_printer as pr
from tt_sounds import NoiseMaker
from tt_tag_outcomes import TagOutcome, print_outcomes


@dataclass
class _TagOutcome(TagOutcome):
    changed: bool = False


class _Operation:
    HOLD = "hold"
    UNHOLD = "unhold"


def hold(today: TrackerDay, tags: Sequence[TagID]) -> bool:
    """Handle HOLD command; returns True if TrackerDay changed."""
    return _process(today=today, tags=tags, mode=_Operation.HOLD)


def unhold(today: TrackerDay, tags: Sequence[TagID]) -> bool:
    """Handle UNHOLD command; returns True if TrackerDay changed."""
    return _process(today=today, tags=tags, mode=_Operation.UNHOLD)


def _process(today: TrackerDay, tags: Sequence[TagID], mode: str) -> bool:
    """Process the hold or unhold command.

    On entry: tags is a list of syntactically valid tagids to process.
    Each tag's outcome is independent -- one tag being ineligible doesn't
    stop the others in the same command from being processed. Unlike
    RETIRE/UNRETIRE, there's no confirmation prompt and no config file to
    rewrite, so this is deliberately lighter-weight.
    """
    if not tags:
        pr.iprint("No tags supplied.", style=k.WARNING_STYLE)
        return False

    outcomes = [_evaluate_tag(TagID(tag), today, mode) for tag in tags]
    print_outcomes(outcomes)

    any_changed = any(outcome.changed for outcome in outcomes)
    if any_changed:
        NoiseMaker.play(k.OK_DONE)
    return any_changed


def _evaluate_tag(tag: TagID, today: TrackerDay, mode: str) -> _TagOutcome:
    biketag = today.biketags.get(tag)
    if not biketag:
        return _TagOutcome(
            tag, "is not available for use (ignoring)", k.WARNING_STYLE
        )

    if mode == _Operation.HOLD:
        return _evaluate_hold(tag, biketag, today)
    return _evaluate_unhold(tag, biketag, today)


def _evaluate_hold(tag: TagID, biketag: BikeTag, today: TrackerDay) -> _TagOutcome:
    if biketag.held:
        return _TagOutcome(tag, "is already suspended", k.ANSWER_STYLE)
    if biketag.status == BikeTag.RETIRED:
        return _TagOutcome(tag, "is retired; cannot be suspended", k.WARNING_STYLE)
    if biketag.status == BikeTag.IN_USE:
        return _TagOutcome(
            tag, "is checked in; check it out before suspending", k.WARNING_STYLE
        )
    if biketag.status not in {BikeTag.UNUSED, BikeTag.DONE}:
        return _TagOutcome(
            tag, f"cannot be suspended (status {biketag.status})", k.WARNING_STYLE
        )
    if today.hold_tag(tag):
        return _TagOutcome(
            tag,
            "is suspended (marked as unavailable until tomorrow)",
            k.ANSWER_STYLE,
            changed=True,
        )
    return _TagOutcome(tag, "could not be suspended", k.WARNING_STYLE)


def _evaluate_unhold(tag: TagID, biketag: BikeTag, today: TrackerDay) -> _TagOutcome:
    if not biketag.held:
        return _TagOutcome(tag, "is not suspended", k.ANSWER_STYLE)
    if today.unhold_tag(tag):
        return _TagOutcome(tag, "is no longer suspended", k.ANSWER_STYLE, changed=True)
    return _TagOutcome(tag, "could not be unsuspended", k.WARNING_STYLE)


def previous_day_held_tags(folder: str, whatdate: str = "yesterday") -> list[TagID] | None:
    """Return tags left suspended as of the end of whatdate, or None.

    This is a kludge: rather than tracking held-over-midnight state as its
    own thing, it just reaches into whatdate's own datafile (if there is
    one) and reads back the held-tags list it saved. Returns None if
    there's no datafile for that date (nothing to report); returns []
    (falsy) if there is a datafile but it has no held tags.

    Reads the file directly instead of doing a full TrackerDay.load_from_file()
    -- this is a peek at another day's leftover state, not an edit of it,
    and a full load could fail for reasons (schema drift, config mismatch)
    that have nothing to do with the one field being asked about here.
    """
    filepath = df.datafile_name(folder, whatdate)
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    tags = [TagID(t) for t in data.get(TOKEN_HELD_TAGIDS, [])]
    return sorted(t for t in tags if t)


def _report_tag_list(header: str, tags: Sequence[TagID]) -> None:
    """Print a header line followed by a space-separated, wrapped tag list."""
    pr.iprint()
    pr.iprint(header, style=k.SUBTITLE_STYLE)
    ut.line_wrapper(
        " ".join(tag.cased for tag in tags),
        print_handler=pr.iprint,
        print_handler_args={"num_indents": 2},
    )


def report_previous_day_held_tags(folder: str, whatdate: str = "yesterday") -> None:
    """Print a note of tags left suspended as of the end of whatdate, if any.

    Silent if there's no datafile for whatdate, or if it had no held tags
    -- this is an FYI, not a warning, so it says nothing unless there's
    something worth mentioning.
    """
    tags = previous_day_held_tags(folder, whatdate)
    if not tags:
        return
    resolved_date = ut.date_str(whatdate)
    date_label = (
        "yesterday"
        if resolved_date == ut.date_str("yesterday")
        else ut.date_str(resolved_date, long_date=True)
    )
    _report_tag_list(
        f"{len(tags)} {ut.plural(len(tags),'tag')} left suspended {date_label}:",
        tags,
    )


def report_current_held_tags(today: TrackerDay) -> None:
    """Print a note of tags currently suspended today, if any.

    Silent if nothing is currently held -- an FYI, not a warning.
    """
    tags = sorted(today.tags_held())
    if not tags:
        return
    _report_tag_list(
        f"{len(tags)} {ut.plural(len(tags),'tag')} currently suspended:", tags
    )
