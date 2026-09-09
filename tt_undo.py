"""Undo/redo support for tag-mutating commands.

See docs/undo_redo_spec.md for the design this implements.

Copyright (C) 2023-2025 Julias Hocking & Todd Glover

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

import copy
import time
from dataclasses import dataclass, field
from typing import Optional, Union

import client_base_config as cfg
from common.tt_tag import TagID
from common.tt_biketag import BikeTag
from common.tt_trackerday import TrackerDay
from tt_commands import CmdKeys, COMMANDS
from tt_notes import Note

# How long an undo (or a redo) stays available, in real elapsed seconds.
# Set via client_base_config.UNDO_WINDOW_SECONDS (overridable per-site like
# any other client config).
# NB: this is wall-clock time, not VTime -- VTime is the backdatable
# in-log event time and must never be used for this window.
WINDOW_SECONDS = cfg.UNDO_WINDOW_SECONDS

# The tag-mutating commands undo/redo knows how to handle generically. Each
# of these takes a tag list as args[0] and is fully described, for replay
# purposes, by (cmd_key, resolved_args), and its undo is a BikeTag snapshot
# restore. RETIRE/UNRETIRE are deliberately excluded -- they also rewrite
# client_local_config.py on disk, which this mechanism does not attempt to
# reverse.
#
# NOTE creation is *also* undoable, but doesn't fit this shape (its args
# aren't a tag list, and its state lives in today.notes, not today.biketags)
# -- it's handled separately, via UndoManager.record_note_created() and the
# NoteRecord type below, sharing the same single pending-undo/redo slot.
TAG_UNDOABLE_COMMANDS = {
    CmdKeys.CMD_BIKE_IN,
    CmdKeys.CMD_BIKE_OUT,
    CmdKeys.CMD_BIKE_INOUT,
    CmdKeys.CMD_EDIT,
    CmdKeys.CMD_DELETE,
    CmdKeys.CMD_FLIP,
}

_INOUT_WORD = {"i": "in", "o": "out"}


def _is_expired(created_at: float) -> bool:
    return (time.monotonic() - created_at) > WINDOW_SECONDS


def _clone_biketag(biketag: BikeTag) -> BikeTag:
    """Deep-copy a BikeTag's mutable state.

    Can't just copy.deepcopy(biketag): BikeTag overrides __new__() to
    require a tagid argument, which breaks deepcopy's default
    no-argument reconstruction path. Build the clone through the normal
    constructor instead, then copy over the mutable state by hand.
    """
    clone = BikeTag(biketag.tagid, biketag.bike_type)
    clone.status = biketag.status
    clone.visits = copy.deepcopy(biketag.visits)
    return clone


def _state_key(biketag: BikeTag) -> tuple:
    """A comparable snapshot of the parts of a BikeTag that undo cares about."""
    return (
        biketag.status,
        tuple((v.time_in, v.time_out) for v in biketag.visits),
    )


def build_label(cmd_key: str, args: list) -> str:
    """Build a short human-readable label for a resolved command, e.g. 'in bg3 pa10'."""
    canonical = COMMANDS[cmd_key].invoke[0]
    tags = args[0] if args else []
    parts = [canonical, " ".join(str(t) for t in tags)]

    if cmd_key in (
        CmdKeys.CMD_BIKE_IN,
        CmdKeys.CMD_BIKE_OUT,
        CmdKeys.CMD_BIKE_INOUT,
        CmdKeys.CMD_FLIP,
    ):
        if len(args) > 1 and args[1]:
            parts.append(str(args[1]))
    elif cmd_key == CmdKeys.CMD_EDIT:
        if len(args) > 1:
            parts.append(_INOUT_WORD.get(args[1], args[1]))
        if len(args) > 2:
            parts.append(str(args[2]))
    elif cmd_key == CmdKeys.CMD_DELETE:
        if len(args) > 1:
            parts.append(_INOUT_WORD.get(args[1], args[1]))

    return " ".join(p for p in parts if p)


def build_note_label(note: Note) -> str:
    """Build a label for a just-created note, e.g. 'note flat tire on bg3'."""
    canonical = COMMANDS[CmdKeys.CMD_NOTES].invoke[0]
    return f"{canonical} {note.text}"


@dataclass
class UndoRecord:
    """Everything needed to undo (restore) and later redo (replay) one tag command."""

    cmd_key: str
    resolved_args: list
    tags: list[TagID]
    snapshot_before: dict[TagID, BikeTag]
    label: str
    created_at: float = field(default_factory=time.monotonic)

    def expired(self) -> bool:
        return _is_expired(self.created_at)


@dataclass
class RedoRecord:
    """Everything needed to replay a just-undone tag command."""

    cmd_key: str
    resolved_args: list
    label: str
    created_at: float = field(default_factory=time.monotonic)

    def expired(self) -> bool:
        return _is_expired(self.created_at)


@dataclass
class NoteRecord:
    """Undo/redo record for a just-created note (the only in-scope NOTE action).

    Used for both the pending-undo slot (where undoing means removing this
    exact note) and the pending-redo slot (where redoing means putting the
    same note object back) -- which action to take is determined by which
    slot it's sitting in, not by this record's type. It carries the actual
    Note object (with its real, original created_at) rather than replaying
    the NOTE command, precisely so a redo doesn't re-stamp a fresh 'now'.
    """

    note: Note
    label: str
    created_at: float = field(default_factory=time.monotonic)

    def expired(self) -> bool:
        return _is_expired(self.created_at)


class UndoManager:
    """Holds the single pending undo slot and single pending redo slot.

    Stack depth is exactly one of each -- this is deliberate, not a
    simplification to fix later. See docs/undo_redo_spec.md.
    """

    _pending_undo: Optional[Union[UndoRecord, NoteRecord]] = None
    _pending_redo: Optional[Union[RedoRecord, NoteRecord]] = None

    @classmethod
    def snapshot(cls, today: TrackerDay, tagids: list) -> dict:
        """Deep-copy the BikeTag for each tagid that exists today, before a command runs."""
        return {
            tagid: _clone_biketag(today.biketags[tagid])
            for tagid in tagids
            if tagid in today.biketags
        }

    @classmethod
    def record(
        cls,
        cmd_key: str,
        resolved_args: list,
        today: TrackerDay,
        tagids_requested: list,
        snapshot_before: dict,
        label: str,
    ) -> None:
        """Record the just-executed command as the new undo point.

        Scopes the undo strictly to the tags that actually changed (a
        partial-success batch only undoes the tags that succeeded), but
        keeps the full original resolved_args for redo, so a redo replays
        the whole original command -- including any tag that errored the
        first time, which will error the same way again.
        """
        changed = {}
        for tagid in tagids_requested:
            before = snapshot_before.get(tagid)
            after = today.biketags.get(tagid)
            if before is None or after is None:
                continue
            if _state_key(before) != _state_key(after):
                changed[tagid] = before

        if not changed:
            # Nothing this undo mechanism can see actually changed for any
            # requested tag; leave any existing pending undo/redo alone.
            return

        cls._pending_undo = UndoRecord(
            cmd_key=cmd_key,
            resolved_args=resolved_args,
            tags=list(changed.keys()),
            snapshot_before=changed,
            label=label,
        )
        cls._pending_redo = None

    @classmethod
    def record_note_created(cls, note: Note, label: str) -> None:
        """Record a just-created note as the new undo point.

        Like record(), this occupies the single shared undo slot -- a note
        creation competes with, and can bump out, a pending tag-command
        undo (and vice versa). That's a deliberate consequence of keeping
        one slot rather than a separate one per kind. See
        docs/undo_redo_spec.md.
        """
        cls._pending_undo = NoteRecord(note=note, label=label)
        cls._pending_redo = None

    @classmethod
    def try_undo(cls, today: TrackerDay) -> tuple[bool, str]:
        """Attempt to undo the pending command. Returns (ok, message_or_label)."""
        record_ = cls._pending_undo
        if record_ is None:
            return False, "Nothing to undo."
        if record_.expired():
            cls._pending_undo = None
            return False, "Nothing to undo (the undo window has passed)."

        if isinstance(record_, NoteRecord):
            if record_.note in today.notes.notes:
                today.notes.notes.remove(record_.note)
            cls._pending_redo = NoteRecord(note=record_.note, label=record_.label)
            cls._pending_undo = None
            return True, record_.label

        for tagid, snap in record_.snapshot_before.items():
            today.biketags[tagid] = snap

        cls._pending_redo = RedoRecord(
            cmd_key=record_.cmd_key,
            resolved_args=record_.resolved_args,
            label=record_.label,
        )
        cls._pending_undo = None
        return True, record_.label

    @classmethod
    def try_redo(cls, today: TrackerDay) -> tuple[bool, str, Optional[str], Optional[list]]:
        """Attempt to redo the pending undo.

        Returns (ok, message_or_label, cmd_key, resolved_args). For a
        NoteRecord there is nothing further to dispatch -- the redo is
        already fully applied by the time this returns -- so cmd_key and
        resolved_args come back as None; the caller should treat that as
        'already handled', not 'nothing to redo' (ok is still True).
        """
        record_ = cls._pending_redo
        if record_ is None:
            return False, "Nothing to redo.", None, None
        if record_.expired():
            cls._pending_redo = None
            return False, "Nothing to redo (the redo window has passed).", None, None

        cls._pending_redo = None

        if isinstance(record_, NoteRecord):
            today.notes.notes.append(record_.note)
            # Re-arm undo for it directly (mirrors how a replayed tag
            # command re-arms undo by falling through the normal dispatch
            # into record()) -- so redo-then-undo works symmetrically here
            # too, without re-running the NOTE command and re-stamping 'now'.
            cls._pending_undo = NoteRecord(note=record_.note, label=record_.label)
            return True, record_.label, None, None

        return True, record_.label, record_.cmd_key, record_.resolved_args
