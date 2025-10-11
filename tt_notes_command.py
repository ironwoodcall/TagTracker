"""Manage the notes command for TagTracker.

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



# import re
import common.tt_constants as k
# import common.tt_util as ut
# import common.tt_time as tt_time
# import client_base_config as cfg
import tt_printer as pr
from tt_notes import Note, NotesManager
# from common.tt_trackerday import TrackerDay
# from common.tt_tag import TagID



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
            filtered_notes, "Inactive notes:", num_indents=2, show_styled=False
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

    if text.lower() in {"deactiavte", "de", "delete", "del", "d"}:
        return handle_delete_undelete_command(notes_list=notes_list, deleting=True)

    if text.lower() in {"recover", "reactivate", "re", "undelete", "undel", "u", "r"}:
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
        verb = "Deactivate"
    else:  # recovering a deleted note
        filtered_notes = notes_list.deleted_notes()
        verb = "Reactivate"

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
