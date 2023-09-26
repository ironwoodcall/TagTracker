"""Class to manage Notes capability for TagTracker."""

import re
import tt_util as ut
import tt_time
import tt_conf as cfg

# _notes is the master list of all notes.
# Initialize it only if it does not yet exist.
try:
    # pylint: disable-next=used-before-assignment
    _notes
except NameError:
    _notes = []


class Notes:
    """Keep tagtracker operator notes."""

    def __init__(self) -> None:
        """Do nothing; class initialization is done through import."""

    @classmethod
    def add(cls, note: str, timestamp:bool=True) -> None:
        """Add a new note to the collection."""
        note = note.strip()
        note = ut.untaint(note)
        # For no particular reason, limit notes length
        note = note[: cfg.MAX_NOTE_LENGTH]
        if not note:
            return
        if timestamp:
            note = f"{tt_time.VTime('now')} {note}"
        _notes.append(note)

    @classmethod
    def clear(cls) -> None:
        """Clear all notes from the collection."""
        cls._notes = []

    @classmethod
    def load(cls, notes_list:list[str]) -> None:
        """Set notes list to the passed-in list."""
        cls._notes = notes_list

    @classmethod
    def fetch(cls) -> list[str]:
        """Fetch all the notes as a list of strings."""
        return _notes

    @classmethod
    def find(cls, pattern: str) -> list[str]:
        """Return list of notes that match 'pattern' (not a regex)."""
        results = []
        re_pat = re.compile(r"\b" + pattern + r"\b", flags=re.IGNORECASE)
        results = [line for line in _notes if re_pat.search(line)]
        return results

    @classmethod
    def dump(cls):
        """Print out the notes."""
        for line in _notes:
            print(line)
