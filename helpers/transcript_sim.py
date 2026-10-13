"""Simulate a TagTracker session from an ECHO transcript.

See docs/recreate-datafile-from-transcript.md for the design this
implements. This module is the shared parsing/state core; it only builds
an in-memory picture of "what the day's data ended up being" -- it does
not know about datafiles or playback-command scripts. Those are thin
renderers (see helpers/transcript_to_datafile.py) built on top of the
`SimulatedDay` this produces.

Deliberately NOT a command-grammar parser: transcripts span versions of
TagTracker whose input wording and abbreviations drifted (e.g. "held"
became "suspended"), but the small set of *confirmation* strings ("Bike
TAG checked in at HH:MM", "Deleted check-in for latest TAG visit.", ...)
stayed stable throughout, so this scans for those instead of trying to
parse what the user typed.

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

import copy
import re
from dataclasses import dataclass, field


# --------------------------------------------------------------------------
# Line patterns. Kept narrow and anchored on the handful of confirmation
# strings that are stable across the whole transcript corpus -- see
# docs/recreate-datafile-from-transcript.md section 2.
# --------------------------------------------------------------------------

_PROMPT_RE = re.compile(r"^\s*\d{1,2}:\d{2}\s+Bike tag or command\s+>>>\s*(.*)$")
_CHECKED_RE = re.compile(r"^\s*Bike\s+(\S+)\s+checked (in|out) at\s+(\d{1,2}:\d{2})\b")
_DELETED_RE = re.compile(
    r"^\s*Deleted check-(in|out) for latest\s+(\S+)\s+visit\.", re.IGNORECASE
)
_UNDOING_RE = re.compile(r"^\s*Undoing:\s")
_REDOING_RE = re.compile(r"^\s*Redoing:\s")
_SUSPEND_RE = re.compile(
    r"^\s*(\S+)\s+is (?:now )?(?:held|suspended)"
    r"(?:\s*\(marked as unavailable until tomorrow\))?\s*$",
    re.IGNORECASE,
)
_UNSUSPEND_RE = re.compile(
    r"^\s*(\S+)\s+is no longer (?:held|suspended)\s*$", re.IGNORECASE
)
_NOTED_RE = re.compile(r"^\s*Noted\.")
_REG_RE = re.compile(
    r"^\s*There is a total of (\d+) bike registrations? today\.", re.IGNORECASE
)
_EDITING_DATE_RE = re.compile(r"Editing .*\((\d{4}-\d{2}-\d{2})\)\.")
_HOURS_CURRENT_RE = re.compile(
    r"Currently set at\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})"
)
_HOURS_PROMPT_RE = re.compile(
    r"Enter new 24-hour HHMM (opening|closing) time or press <Enter> to leave as"
    r"\s+(\d{1,2}:\d{2}):\s*(.*)$"
)

# Invocation words for the NOTE command (tt_commands.py CmdKeys.CMD_NOTES),
# used only to strip the command word off the prompt-line text so the rest
# can be recorded as the note's text.
_NOTE_INVOKE_WORDS = ("note", "notes", "n")


def _valid_time(text: str) -> str | None:
    """Return a normalized 'HH:MM' if text parses as one, else None.

    A tiny, dependency-free stand-in for VTime's parsing -- this module
    intentionally doesn't import common.tt_time/tt_tag so it has no
    TagTracker import-path dependency; callers that want canonical
    TagID/VTime semantics do that normalization themselves.
    """
    text = text.strip()
    m = re.match(r"^([0-2]?[0-9]):([0-5][0-9])$", text)
    if not m:
        m = re.match(r"^([0-9]{3,4})$", text)
        if not m:
            return None
        digits = m.group(1)
        hour, minute = int(digits[:-2]), int(digits[-2:])
    else:
        hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 24 or minute > 59 or (hour == 24 and minute != 0):
        return None
    return f"{hour:02d}:{minute:02d}"


# --------------------------------------------------------------------------
# Tag normalization, shared by both renderers (transcript_to_datafile.py,
# transcript_to_playback.py). Mirrors common.tt_tag.TagID's own parsing
# (colour+letter+digits, canonical form always lowercase), reimplemented
# here so this module has no TagTracker import dependency.
# --------------------------------------------------------------------------

_TAGID_RE = re.compile(r"^\s*([a-zA-Z])([a-zA-Z])0*([0-9]+)\s*$")


def canonical_tagid(raw: str) -> str | None:
    """Return the canonical lowercase form of a tagid, or None if invalid."""
    m = _TAGID_RE.match(raw)
    if not m:
        return None
    return f"{m.group(1)}{m.group(2)}{m.group(3)}".lower()


def parse_tagids_str(tags_str: str) -> set[str]:
    """Parse a REGULAR_TAGS/OVERSIZE_TAGS/RETIRED_TAGS-style blob into a set."""
    tags = set()
    for token in re.split(r"[\s,]+", tags_str):
        if not token:
            continue
        tagid = canonical_tagid(token)
        if tagid:
            tags.add(tagid)
    return tags


@dataclass
class Visit:
    """One tag visit as the simulator understands it: start, maybe an end."""

    time_in: str
    time_out: str | None = None


@dataclass
class SimulatedDay:
    """End state (and some diagnostics) reconstructed from a transcript."""

    date: str | None = None
    time_open: str | None = None
    time_closed: str | None = None
    registrations: int = 0
    # tag (whatever casing/spelling the transcript used) -> visits, in order
    visits: dict[str, list[Visit]] = field(default_factory=dict)
    # (time, text) in the order notes were created; time is the *prompt*
    # time of the NOTE command turn, since "Noted." carries no timestamp
    # of its own.
    notes: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# A pending undo/redo slot is (kind, payload):
#   "visits" -> payload: dict[tag, list[Visit]]  (the tags' state *before*
#               the command that's now the slot's subject)
#   "other"  -> payload: None                    (hold/unhold -- nothing
#               for us to snapshot, we just need to occupy the slot)
#   "note"   -> payload: (time, text)             (the exact note entry,
#               so an undo can remove that one and a redo can restore it)
_Slot = tuple


class TranscriptSimulator:
    """Replays one transcript's confirmation lines into a SimulatedDay.

    Mirrors the real UndoManager (tt_undo.py): a single pending-undo slot
    and a single pending-redo slot, generic across every tag-mutating
    command. See docs/recreate-datafile-from-transcript.md section 3 for
    why this needs no per-command-type logic.
    """

    def __init__(self) -> None:
        self.day = SimulatedDay()
        self._pending_undo: _Slot | None = None
        self._pending_redo: _Slot | None = None
        self._turn_effects: list[tuple[str, str | None, str | None]] = []
        self._turn_kind: str | None = None  # None | "undo" | "redo"
        self._current_prompt_time: str | None = None
        self._current_command_text: str = ""
        self._hours_current_seen = False

    # -- public API ---------------------------------------------------

    def feed(self, lines) -> SimulatedDay:
        """Process an iterable of transcript lines; return the end state."""
        for raw_line in lines:
            self._feed_line(raw_line.rstrip("\n"))
        self._flush_turn()
        return self.day

    # -- line dispatch -------------------------------------------------

    def _feed_line(self, line: str) -> None:
        m = _PROMPT_RE.match(line)
        if m:
            self._flush_turn()
            self._current_command_text = m.group(1).strip()
            prompt_time_m = re.match(r"^\s*(\d{1,2}:\d{2})", line)
            if prompt_time_m:
                self._current_prompt_time = _valid_time(prompt_time_m.group(1))
            return

        if _UNDOING_RE.match(line):
            self._turn_kind = "undo"
            return
        if _REDOING_RE.match(line):
            self._turn_kind = "redo"
            return

        m = _CHECKED_RE.match(line)
        if m:
            tag, direction, time_str = m.group(1), m.group(2), m.group(3)
            self._turn_effects.append((direction, tag, _valid_time(time_str) or time_str))
            return

        m = _DELETED_RE.match(line)
        if m:
            which, tag = m.group(1).lower(), m.group(2)
            self._turn_effects.append((f"del_{which}", tag, None))
            return

        if _NOTED_RE.match(line):
            text = self._current_command_text
            for word in _NOTE_INVOKE_WORDS:
                if text.lower().startswith(word + " ") or text.lower() == word:
                    text = text[len(word):].strip()
                    break
            self._turn_effects.append(("note", None, text))
            return

        if _SUSPEND_RE.match(line) or _UNSUSPEND_RE.match(line):
            self._turn_effects.append(("other", None, None))
            return

        m = _REG_RE.match(line)
        if m:
            # Registrations are never undoable (verified empirically against
            # the whole transcript corpus -- "Undoing:"/"Redoing:" never
            # names a reg/registrations command), so this is applied
            # immediately and independent of the undo/redo slot machinery.
            self.day.registrations = int(m.group(1))
            return

        m = _EDITING_DATE_RE.search(line)
        if m:
            if self.day.date is None:
                self.day.date = m.group(1)
            else:
                # Seeing this banner line again means the program exited
                # and was restarted mid-transcript (e.g. an explicit
                # "exit" then a fresh run). The pending undo/redo slots
                # are in-memory only -- they do not survive a restart --
                # so a stale one here would otherwise make a later
                # "Undoing:"/"Redoing:" restore the wrong thing.
                if self._pending_undo is not None or self._pending_redo is not None:
                    self.day.warnings.append(
                        "Program restart detected mid-transcript -- clearing "
                        "pending undo/redo (does not survive a restart)"
                    )
                self._pending_undo = None
                self._pending_redo = None
            return

        m = _HOURS_CURRENT_RE.search(line)
        if m:
            # Only seed from the *first* such line in the file -- hours may
            # be re-confirmed later in the session (e.g. via the HOURS
            # command), and at that point "currently set" reflects
            # whatever was already decided, not a fresh default.
            if not self._hours_current_seen:
                self.day.time_open = _valid_time(m.group(1))
                self.day.time_closed = _valid_time(m.group(2))
                self._hours_current_seen = True
            return

        m = _HOURS_PROMPT_RE.search(line)
        if m:
            which, _default, typed = m.group(1), m.group(2), m.group(3)
            new_val = _valid_time(typed)
            if new_val is not None:
                if which == "opening":
                    self.day.time_open = new_val
                else:
                    self.day.time_closed = new_val
            # A blank or unparsable answer ("Not a time.") means "no
            # change" -- nothing to do.
            return

    # -- turn handling ---------------------------------------------------

    def _flush_turn(self) -> None:
        effects, kind = self._turn_effects, self._turn_kind
        self._turn_effects, self._turn_kind = [], None
        if not effects and kind is None:
            return

        if kind == "undo":
            self._apply_slot(from_name="undo", to_name="redo")
            if effects:
                self.day.warnings.append(
                    f"Unexpected output alongside 'Undoing:' (ignored): {effects}"
                )
            return
        if kind == "redo":
            self._apply_slot(from_name="redo", to_name="undo")
            # Any effect lines after "Redoing:" (e.g. the restated
            # "Bike TAG checked in/out ..." line) are redundant restatements
            # of what the snapshot restore above already applied -- see
            # docs/recreate-datafile-from-transcript.md section 3.
            return

        self._apply_normal(effects)

    def _apply_normal(self, effects) -> None:
        tag_effects = [e for e in effects if e[0] in ("in", "out", "del_in", "del_out")]
        note_effects = [e for e in effects if e[0] == "note"]
        other = any(e[0] == "other" for e in effects)

        if tag_effects:
            tags = {tag for _, tag, _ in tag_effects}
            before = {t: copy.deepcopy(self.day.visits.get(t, [])) for t in tags}
            for kind_, tag, value in tag_effects:
                self._apply_tag_effect(kind_, tag, value)
            self._pending_undo = ("visits", before)
            self._pending_redo = None
        elif note_effects:
            # Exactly one NOTE command per turn in practice.
            _, _, text = note_effects[0]
            entry = (self._current_prompt_time or "", text)
            self.day.notes.append(entry)
            self._pending_undo = ("note", entry)
            self._pending_redo = None
        elif other:
            self._pending_undo = ("other", None)
            self._pending_redo = None
        # else: nothing recognized changed (error, query, retire, report,
        # ...) -- leave pending undo/redo exactly as they were, matching
        # the real UndoManager, which only arms/clears the slot for
        # commands that actually mutate a tag, hold state, or a note.

    def _apply_tag_effect(self, kind: str, tag: str, time_str: str | None) -> None:
        visits = self.day.visits.setdefault(tag, [])
        if kind == "in":
            if visits and visits[-1].time_out is None:
                # Tag already has an open visit: this "checked in" line can
                # only be edit_in() on that visit (a fresh check-in is
                # rejected by the real app whenever a visit is already
                # open) -- see common/tt_biketag.py _test_time_in().
                visits[-1].time_in = time_str
            else:
                visits.append(Visit(time_in=time_str, time_out=None))
        elif kind == "out":
            if visits and visits[-1].time_out is None:
                visits[-1].time_out = time_str
            elif visits:
                # Latest visit already closed: edit_out() on a DONE tag
                # just overwrites time_out -- see common/tt_biketag.py.
                visits[-1].time_out = time_str
            else:
                self.day.warnings.append(
                    f"'{tag}' checked out at {time_str} with no prior visit on record"
                )
        elif kind == "del_in":
            if visits and visits[-1].time_out is None:
                visits.pop()
            else:
                self.day.warnings.append(
                    f"Unexpected 'Deleted check-in' for '{tag}' (no open visit to drop)"
                )
        elif kind == "del_out":
            if visits and visits[-1].time_out is not None:
                visits[-1].time_out = None
            else:
                self.day.warnings.append(
                    f"Unexpected 'Deleted check-out' for '{tag}' (latest visit wasn't closed)"
                )

    def _apply_slot(self, from_name: str, to_name: str) -> None:
        slot = self._pending_undo if from_name == "undo" else self._pending_redo
        if slot is None:
            self.day.warnings.append(
                f"'{from_name.title()}ing:' seen with nothing pending -- ignored"
            )
            return
        kind, payload = slot
        if kind == "visits":
            tags = set(payload.keys())
            current = {t: copy.deepcopy(self.day.visits.get(t, [])) for t in tags}
            for t, v in payload.items():
                self.day.visits[t] = copy.deepcopy(v)
            new_slot: _Slot = ("visits", current)
        elif kind == "note":
            if from_name == "undo":
                self._remove_last_note(payload)
            else:
                self.day.notes.append(payload)
            new_slot = ("note", payload)
        else:  # "other"
            new_slot = ("other", None)

        if from_name == "undo":
            self._pending_undo, self._pending_redo = None, new_slot
        else:
            self._pending_redo, self._pending_undo = None, new_slot

    def _remove_last_note(self, entry: tuple[str, str]) -> None:
        for i in range(len(self.day.notes) - 1, -1, -1):
            if self.day.notes[i] == entry:
                del self.day.notes[i]
                return
        self.day.warnings.append(f"Could not find note {entry!r} to undo")


def simulate(text: str) -> SimulatedDay:
    """Convenience wrapper: simulate an entire transcript given as one string."""
    return TranscriptSimulator().feed(text.splitlines())
