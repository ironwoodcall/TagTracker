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
import tt_util as ut
import tt_time
import client_base_config as cfg

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



# class Notes:
#     """Keep tagtracker operator notes."""

#     def __init__(self,list_of_notes:list=None) -> None:
#         """The only thing we care about is the list of notes."""
#         self.notes = list_of_notes or []

#     @classmethod
#     def add(cls, note: str, timestamp: bool = True) -> None:
#         """Add a new note to the collection."""
#         note = note.strip()
#         note = ut.untaint(note)
#         # For no particular reason, limit notes length
#         note = note[: cfg.MAX_NOTE_LENGTH]
#         if not note:
#             return
#         if timestamp:
#             note = f"{tt_time.VTime('now')} {note}"
#         cls._notes.append(note)

#     @classmethod
#     def clear(cls) -> None:
#         """Clear all notes from the collection."""
#         cls._notes = []

#     @classmethod
#     def load(cls, notes_list: list[str]) -> None:
#         """Set notes list to the passed-in list."""
#         cls._notes = notes_list

#     @classmethod
#     def fetch(cls) -> list[str]:
#         """Fetch all the notes as a list of strings."""
#         return cls._notes

#     @classmethod
#     def find(cls, pattern: str) -> list[str]:
#         """Return list of notes that contain 'pattern' (not a regex)."""
#         results = []
#         re_pat = re.compile(r"\b" + pattern + r"\b", flags=re.IGNORECASE)
#         results = [line for line in cls._notes if re_pat.search(line)]
#         return results

#     @classmethod
#     def dump(cls):
#         """Print out the notes."""
#         for line in cls._notes:
#             print(line)
