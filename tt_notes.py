"""Class to manage Notes capability for TagTracker.


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

import re
import common.tt_constants as k
import common.tt_util as ut
import common.tt_time as tt_time
import client_base_config as cfg
import tt_printer as pr

# from common.tt_trackerday import TrackerDay
from common.tt_tag import TagID

# from common.tt_biketag import BikeTag

# Note status codes (moved here from tt_constants to localize concerns)
NOTE_ACTIVE = "A"
NOTE_AUTO_DELETED = "-"
NOTE_AUTO_RECOVERED = "+"
NOTE_HAND_DELETED = "D"
NOTE_HAND_RECOVERED = "R"
# Groups of note status codes, for convenience
NOTE_GROUP_ACTIVE = {NOTE_ACTIVE, NOTE_AUTO_RECOVERED, NOTE_HAND_RECOVERED}
NOTE_GROUP_INACTIVE = {NOTE_AUTO_DELETED, NOTE_HAND_DELETED}
NOTE_GROUP_HAND = {NOTE_HAND_DELETED, NOTE_HAND_RECOVERED}
NOTE_GROUP_ALL = {
    NOTE_ACTIVE,
    NOTE_AUTO_DELETED,
    NOTE_AUTO_RECOVERED,
    NOTE_HAND_DELETED,
    NOTE_HAND_RECOVERED,
}


class Note:
    """One note."""

    # Compiled regular expressions to recognize notes from datafile
    # in current or legacy format, or a straightforward new note from user
    _STATUS_CHARS = "".join(re.escape(ch) for ch in NOTE_GROUP_ALL)
    _TIME_PATTERN = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]"
    _PACKED_RE = re.compile(
        rf"^(?P<status>[{_STATUS_CHARS}])?\|(?P<time>{_TIME_PATTERN})?\|(?P<text>.*)$"
    )
    # _PACKED_RE = re.compile(
    #     rf"^"
    #     rf"(?P<status>[{NOTE_GROUP_ALL}])?\|"
    #     rf"(?P<time>{_TIME_PATTERN})?\|"
    #     rf"(?P<text>.*)$"
    # )
    _LEGACY_RE = re.compile(rf"^(?P<time>{_TIME_PATTERN})\s+(?P<text>.*)$")

    def __init__(self, init_str: str, oktags: list[TagID] = None):
        """Initialize a Note.

        On entry init_str is either the text to make into the note,
        or is a packed version of the note structure, or is the legacy
        form of the note, which includes its timestamp only.

        init_str can be:
        - Packed: "{status}|{time}|{note text}"  (status - see above)
        - Legacy: "{time} {note text}"
        - Plain text: any other string

        oktags is an optional list of TagID objects that are usable today; if present
        it is used as a filter on potential TagIDs found in the note text
        """
        self.status: str = ""
        self.created_at: tt_time.VTime = ""
        self.text: str = ""
        self.tags: list[TagID] = []

        self.unpack(init_str)
        self.tags = scan_for_tags(text=self.text, oktags=oktags)
        ut.squawk(f"{','.join(self.tags)=}; '{self.status=}','{self.created_at}','{self.text}'",cfg.DEBUG)

    def unpack(self, packed: str) -> None:
        """Unpack a note string into object attributes."""

        # Packed format
        m = self._PACKED_RE.match(packed)
        if m:
            self.status = m.group("status") or NOTE_ACTIVE

            time_str = m.group("time")
            self.created_at = (
                tt_time.VTime(time_str) if time_str else tt_time.VTime("now")
            )

            self.text = m.group("text") or ""
            return

        # Legacy format
        m = self._LEGACY_RE.match(packed)
        if m:
            self.status = NOTE_ACTIVE
            self.created_at = tt_time.VTime(m.group("time"))
            self.text = m.group("text") or ""
            return

        # Plain text
        self.status = NOTE_ACTIVE
        self.created_at = tt_time.VTime("now")
        self.text = packed.strip()

    def pack(self) -> str:
        """Serialize the note back into packed format: {status}|{time}|{text}"""
        time_str = str(self.created_at)  # relies on VTime.__str__()
        return f"{self.status}|{time_str}|{self.text}"

    def delete(self, by_hand:bool) -> None:
        if by_hand:
            self.status = NOTE_HAND_DELETED
        else:
            self.status = NOTE_AUTO_DELETED

    def recover(self, by_hand:bool) -> None:
        if by_hand:
            self.status = NOTE_HAND_RECOVERED
        else:
            self.status = NOTE_AUTO_RECOVERED

    def pretty(self) -> str:
        pretty_text = f"{self.created_at} {self.text}"
        # for t in self.tags:
        #     pretty_text = f"{pretty_text}; {t.tagid} {t.status} {len(t.visits)} visits"
        return pretty_text

    # def can_auto_delete(self) -> bool:
    #     """Returns True if ok to auto-delete this note.
    #     Can delete if
    #         note has >= 1 tag reference
    #         each visit for that tag whose visit includes created_at is
    #                 finished at least ~10 minutes in the past
    #         note was not maunally undeleted
    #     """
    #     if self.status == NOTE_HAND_RECOVERED:
    #         return False
    #     if len(self.tags) < 1:
    #         return False
    #     now = tt_time.VTime("now").num
    #     for tag in self.tags:
    #         tag: BikeTag
    #         end: tt_time.VTime
    #         end = tag.visit_finished_at(self.created_at)
    #         if not end:  # Visit is ongoing
    #             return False
    #         # If created eactly at checkout time, it's probably
    #         # a note for a tag that was immediately reused.
    #         if end.num == self.created_at:
    #             return False
    #         if (now - end.num) < cfg.NOTE_AUTODELETE_DELAY:
    #             return False
    #     return True


def scan_for_tags(text: str, oktags: list[TagID] = None) -> list[TagID]:
    """Scan 'text' for valid tags and return a list of TagIDs found.

    If oktags is non-null, then only include tags that are in that list.
    """
    tags: list[TagID] = []
    for word in re.findall(r"\w+", text):
        tagid = TagID(word)
        if tagid and (oktags is None or tagid in oktags) and tagid not in tags:
            tags.append(tagid)
    return tags


class NotesManager:
    """Look after the notes that the attendant makes through the day."""

    def __init__(self) -> None:
        """The only thing we care about is the list of notes."""
        self.notes = []
        # self.biketags = biketags

    def add(self, note_text: str) -> None:
        """Add a new note to the collection."""
        note_text = note_text.strip()
        note_text = ut.untaint(note_text)
        # For no particular reason, limit notes length
        note_text = note_text[: cfg.MAX_NOTE_LENGTH]
        if not note_text:
            return
        note = Note(note_text)
        self.notes.append(note)

    def clear(self) -> None:
        """Clear all notes from the collection."""
        self.notes = []

    def load(self, notes_list: list[str]) -> None:
        """Set notes list to the passed-in list."""
        self.clear()
        for one_note in notes_list:
            self.add(one_note)

    # def autodelete(self, give_message: bool = True) -> int:
    #     """Tries to autodelete notes.

    #     Returns number of notes deleted.
    #     Optionally gives a message if any deleted.
    #     """
    #     deleted = 0
    #     # Consider only active/recovered notes for auto-delete checks
    #     for note in self.active_notes():
    #         if note.status == NOTE_ACTIVE and note.can_auto_delete():
    #             note.delete()
    #             deleted += 1
    #     if deleted and give_message:
    #         pr.iprint()
    #         pr.iprint(
    #             f"Deleted {deleted} expired {ut.plural(deleted,'note')}.",
    #             style=k.SUBTITLE_STYLE,
    #         )
    #     return deleted

    def dump(self):
        """Print out the notes."""
        for line in self.notes:
            print(line)

    def serialize(self) -> list[str]:
        """Return the notes objects in the form of a list of strings."""
        packed = [n.pack() for n in self.notes]
        return packed

    def active_notes(self) -> list:
        """Return sorted list of active/recovered notes."""
        sublist = [
            n for n in self.notes if n.status in NOTE_GROUP_ACTIVE
        ]
        sublist.sort(key=lambda n: n.created_at)
        return sublist

    def deleted_notes(self) -> list:
        """Return sorted list of deleted notes."""
        sublist = [n for n in self.notes if n.status in NOTE_GROUP_INACTIVE]
        sublist.sort(key=lambda n: n.created_at)
        return sublist


def show_notes_sublist(
    notes_list,
    header_text: str | None = None,
    show_styled: bool = True,
    num_indents: int = 1,
    show_enumerated: bool = False,
) -> None:
    """Show a filtered list of notes.

    Args:
        notes_list: list of Note objects
        header_text: optional header string (only shown if not None)
        show_styled: whether to use warning style
        num_indents: indentation level
        show_enumerated: whether to show enumeration
    """
    if header_text:
        pr.iprint(header_text, style=k.SUBTITLE_STYLE)

    style = k.WARNING_STYLE if show_styled else k.NORMAL_STYLE

    for i, note in enumerate(notes_list, start=1):

        note_text = note.pretty()
        if show_enumerated:
            note_text = f"{i}: {note_text}"

        pr.iprint(note_text, style=style, num_indents=num_indents)


def show_all_notes(
    notes_list: NotesManager,
    show_header: bool = True,
) -> None:
    """Print all the notes."""

    if show_header:
        if notes_list.notes:
            pr.iprint("Today's notes:", style=k.TITLE_STYLE)
        else:
            pr.iprint("There are no notes yet today.")
            pr.iprint("(To create a note, enter NOTE [note text])")

    filtered_notes = notes_list.active_notes()
    show_notes_sublist(
        filtered_notes, "Active notes:", num_indents=2, show_styled=False
    )
    if not filtered_notes:
        pr.iprint("No active notes", num_indents=2)
    filtered_notes = notes_list.deleted_notes()
    if filtered_notes:
        show_notes_sublist(
            filtered_notes, "Deleted notes:", num_indents=2, show_styled=False
        )


def notes_command(notes_list: NotesManager, args: list[str]) -> bool:
    """Handle 'notes' command. Returns True if data has changed.

    args[0], if present, is either a keyword 'DELETE, UNDELETE,etc' or new note text.
    """
    data_changed = False

    if not args:
        pr.iprint()

        show_all_notes(notes_list=notes_list, show_header=True)
        return data_changed

    text = args[0].strip()  # .lower()

    if text.lower() in {"delete", "del", "d"}:
        return handle_delete_undelete_command(notes_list=notes_list, deleting=True)

    if text.lower() in {"undelete", "undel", "u", "recover"}:
        return handle_delete_undelete_command(notes_list=notes_list, deleting=False)

    # if text.lower() in {"auto", "autodelete", "ad"}:
    #     changed = notes_list.autodelete()
    #     return changed > 0

    # notes_list.add(f"{NOTE_ACTIVE}|{tt_time.VTime('now')}|{args[0]}")
    notes_list.add(args[0])
    data_changed = True
    pr.iprint("Noted.", style=k.SUBTITLE_STYLE)
    return data_changed


def handle_delete_undelete_command(notes_list: NotesManager, deleting: bool) -> bool:
    """Handle the note delete/undelete command."""
    data_changed = False
    pr.iprint()

    if deleting:
        filtered_notes = notes_list.active_notes()
        verb = "Delete"
    else:  # recovering a deleted note
        filtered_notes = notes_list.deleted_notes()
        verb = "Recover"

    if not filtered_notes:
        pr.iprint(f"No notes to {verb}.", style=k.WARNING_STYLE)
        return data_changed

    pr.iprint(f"{verb} a note:", style=k.TITLE_STYLE)

    show_notes_sublist(
        filtered_notes, num_indents=2, show_enumerated=True, show_styled=False
    )

    total_notes = len(filtered_notes)
    pr.iprint(
        f"{verb} which note (1..{total_notes}): ", end="", style=k.SUBPROMPT_STYLE
    )
    user_input = pr.tt_inp().strip()

    if not user_input:
        pr.iprint("Cancelled", style=k.WARNING_STYLE)
        return data_changed

    if not user_input.isdigit():
        pr.iprint("Error: Input is not a number.", style=k.WARNING_STYLE)
        return data_changed

    note_index = int(user_input)
    if note_index < 1 or note_index > total_notes:
        pr.iprint("Error: Number out of range.", style=k.WARNING_STYLE)
        return data_changed

    this_note: Note = filtered_notes[note_index - 1]
    if deleting:
        this_note.delete(by_hand=True)
    else:
        this_note.recover(by_hand=True)
    data_changed = True
    pr.iprint(f"{verb} successful.", style=k.SUBTITLE_STYLE)
    return data_changed
