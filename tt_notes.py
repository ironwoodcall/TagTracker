"""Class to manage Notes capability for TagTracker.


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

import re
import tt_constants as k
import tt_util as ut
import tt_time
import client_base_config as cfg
import tt_printer as pr

class Notes:
    """Keep tagtracker operator notes."""

    def __init__(self, list_of_notes: list = None) -> None:
        """The only thing we care about is the list of notes."""
        self.notes = list_of_notes or []

    def add(self, note: str, timestamp: bool = True) -> None:
        """Add a new note to the collection."""
        note = note.strip()
        note = ut.untaint(note)
        # For no particular reason, limit notes length
        note = note[:cfg.MAX_NOTE_LENGTH]
        if not note:
            return
        if timestamp:
            note = f"{tt_time.VTime('now')} {note}"
        self.notes.append(note)

    def clear(self) -> None:
        """Clear all notes from the collection."""
        self.notes = []

    def load(self, notes_list: list[str]) -> None:
        """Set notes list to the passed-in list."""
        self.notes = notes_list

    def find(self, pattern: str) -> list[str]:
        """Return list of notes that contain 'pattern' (not a regex)."""
        results = []
        re_pat = re.compile(r"\b" + pattern + r"\b", flags=re.IGNORECASE)
        results = [line for line in self.notes if re_pat.search(line)]
        return results

    def dump(self):
        """Print out the notes."""
        for line in self.notes:
            print(line)

    def delete(self,note_index) -> None:
        """Delete a note from the collection.  notes_index is 1-based."""
        if not self.notes:
            return

        if note_index < 1 or note_index > len(self.notes):
            ut.squawk(f"Unexpected value for {note_index=}, out of range.")
            return

        # Delete the corresponding note
        del self.notes[note_index - 1]


def show_notes(
    notes_obj,
    header: bool = False,
    styled: bool = True,
    num_indents: int = 1,
    enumerated: bool = False,
) -> None:
    """Print notes."""
    notes_list = notes_obj.notes

    if header:
        if notes_list:
            pr.iprint("Today's notes:", style=k.TITLE_STYLE)
        else:
            pr.iprint("There are no notes yet today.")
            pr.iprint("(To create a note, enter NOTE [note text])")
    for i, line in enumerate(notes_list, start=1):
        text = f"{i}: {line}" if enumerated else line
        if styled:
            pr.iprint(text, style=k.WARNING_STYLE, num_indents=num_indents)
        else:
            pr.iprint(text, style=k.NORMAL_STYLE, num_indents=num_indents)

def notes_command(notes_obj:Notes, args: list[str]) -> bool:
    """Handle 'notes' command. Returns True if data has changed.

    args[0], if present, is either the keyword 'DELETE' or new note text.
    """
    data_changed = False

    if not args:
        pr.iprint()
        show_notes(notes_obj=notes_obj, header=True, styled=False)
        return data_changed

    text = args[0].strip().lower()

    if text in {"delete", "del", "d"}:
        return handle_delete_command(notes_obj=notes_obj)

    notes_obj.add(args[0])
    data_changed = True
    pr.iprint("Noted.", style=k.SUBTITLE_STYLE)
    return data_changed

def handle_delete_command(notes_obj:Notes) -> bool:
    """Handle the delete note command."""
    data_changed = False
    pr.iprint()

    if not notes_obj.notes:
        pr.iprint("No notes to delete", style=k.WARNING_STYLE)
        return data_changed

    pr.iprint("Deleting a note:", style=k.TITLE_STYLE)
    show_notes(
        notes_obj, header=False, styled=False, num_indents=2, enumerated=True
    )

    total_notes = len(notes_obj.notes)
    pr.iprint(f"Delete which note (1..{total_notes}): ", end="", style=k.SUBPROMPT_STYLE)
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

    notes_obj.delete(note_index)
    data_changed = True
    pr.iprint("Note deleted.", style=k.SUBTITLE_STYLE)
    return data_changed

# def notes_command(today: TrackerDay, args: list) -> bool:
#     """Handle 'notes' command. Returns True if data has changed.

#     args[0], if present, is either the keyword 'DELETE' or new note text.
#     """

#     data_changed = False
#     if not args:
#         pr.iprint()
#         show_notes(notes_obj=today.notes, header=True, styled=False)
#         return data_changed

#     text = args[0]
#     if text.strip().lower() in {"delete", "del", "d"}:

#         pr.iprint()
#         if not today.notes.notes:
#             pr.iprint("No notes to delete",style=k.WARNING_STYLE)
#             return data_changed

#         pr.iprint("Deleting a note:", style=k.TITLE_STYLE)
#         show_notes(
#             today.notes, header=False, styled=False, num_indents=2, enumerated=True
#         )

#         # Prompt for input
#         total_notes = len(today.notes.notes)
#         pr.iprint(f"Delete which note (1..{total_notes}): ",end="",style=k.SUBPROMPT_STYLE)
#         user_input = pr.tt_inp()

#         # Handle the input
#         if user_input.strip() == "":
#             pr.iprint("Cancelled", style=k.WARNING_STYLE)
#             return data_changed

#         if not user_input.isdigit():
#             pr.iprint("Error: Input is not a number.", style=k.WARNING_STYLE)
#             return data_changed

#         note_index = int(user_input)
#         if note_index < 1 or note_index > total_notes:
#             pr.iprint("Error: Number out of range.", style=k.WARNING_STYLE)
#             return data_changed

#         data_changed = True
#         today.notes.delete(note_index)
#         pr.iprint("Note deleted.", style=k.SUBTITLE_STYLE)

#     else:
#         today.notes.add(text)
#         data_changed = True
#         pr.iprint("Noted.", style=k.SUBTITLE_STYLE)

#     return data_changed
