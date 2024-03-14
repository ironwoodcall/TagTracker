"""This is the TagID class.

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



    A TagID is the name of a tag; it might be a correct tag name or not.
    It is a type of string, and its representation is canonical
    tag representation (e.g. "wa1").  TagIDs with identical representation
    are considered equal, even though the 'original' attribute
    might not be the same.
"""

import re


class TagID(str):
    """The label for a tag.

    Attributes & methods:
        original:   The string that was passed in to maybe be a TagID
        valid:      bool: is this a valid TagID?
        full:       The full version of the tagid E.g. for wa1, is wa001
        prefix:     The tag prefix. E.g. for wa1, is "wa"
        colour:     The tag colour. E.g. for wa1, is "w"
        letter:     The tag letter. E.g. for wa1, is "a"
        number:     The tag number (as int). E.g. for wa1, is 1
        cased:      The tag as a string, uc or lc depending on uc() state
        canon:      Canonical tagid (always lowercase)
        uc():       Sets uppercase representation on or off.
                    Returns current state. Can be called empty

        If the string passed in does not form a valid tag, all the str
        attributes will be "", the number attribute will be None, and
        valid will be False.

        Comparisons are made as if comparing full versions of the
        calculated TagID with case folded the same way, so:
            >>> TagID("wa1") == "   wA01"
            True
            >>> TagID("wa10") > TagID("wa3")
            True
        and even:
            >>> TagID("wa10") > "wa3"
            True
            >>> "wa3" < TagID("wa10")
            True

        uc() sets whether to represent the tag in uppercase.  String
        representations will always respect the uc() state, but there
        are some oddball cases.
        E.g.:
            >>> a.uc(True)
            True
            >>> a
            'WA1'
            >>> print(a)
            WA1
            >>> ' ' + a
            ' wa1'
            >>> type(' ' + a)
            <class 'str'>
            >>> str(' ' + a)
            ' wa1'
            >>> ' ' + str(a)
            ' WA1'
            >>> print(' ' + a)
            wa1
            >>> print(' ', a)
            WA1
        The moral seems to be: if in doubt, use str() or f-strings:
            >>> x = [TagID(s) for s in ["wa1","bf3","ob12"]]
            >>> x
            ['WA1', 'BF3', 'OB12']
            >>> " ".join(x)
            'wa1 bf3 ob12'
            >>> " ".join([str(tag) for tag in x])
            'WA1 BF3 OB12'
            >>>
    """

    # This ugly dodge is to deal with the linter
    _always_False = False

    # _uc indicates whether to print in uppercase (otherwise lc).
    # Canonical representation is *always* lowercase.
    _uc = False

    @classmethod
    def uc(cls, new_state: bool = None) -> bool:
        """Set uppercase state if given; return current state."""
        if new_state is not None:
            cls._uc = bool(new_state)
        return cls._uc

    def __new__(cls, string: str = ""):
        """Create a TagID string with its 'self' as canonical tag id."""
        if not isinstance(string, str):
            selfstring = ""
        else:
            r = re.match(r"^ *([a-z])([a-z])0*([0-9]+) *$", string.lower())
            if r:
                selfstring = f"{r.group(1)}{r.group(2)}{r.group(3)}".lower()
            else:
                selfstring = ""
        instance = super().__new__(cls, selfstring)
        instance.canon = selfstring
        instance.original = str(string)
        if bool(selfstring):
            instance.valid = True
            instance._colour = r.group(1)
            instance._letter = r.group(2)
            instance.number = int(r.group(3))
            instance._prefix = f"{r.group(1)}{r.group(2)}"
        else:
            instance.valid = False
            instance._colour = ""
            instance._letter = ""
            instance.number = None
            instance._prefix = ""
        return instance

    def __init__(self, string: str = ""):  # pylint:disable=unused-argument
        """Initialize attributes not done in __new__()."""
        # str.__init__("")
        # The following idiocy is to keep pylint happy
        if self._always_False:  # pylint:disable=using-constant-test
            self.original = ""
            self.canon = ""
            self.valid = False
            self._colour = ""
            self._letter = ""
            self.number = 0
            self._prefix = ""
        self.uppercase = self.upper()
        if self:
            self._full = f"{self._prefix}{self.number:03d}"
        else:
            self._full = ""

    def __eq__(self, otherstring: str) -> bool:
        """Define equality to mean represent same tag name."""
        return bool(str(self) == str(TagID(otherstring)))

    def __le__(self, otherstring: str) -> bool:
        return bool(self._full <= (TagID(otherstring)._full))

    def __lt__(self, otherstring: str) -> bool:
        return bool(self._full < TagID(otherstring)._full)

    def __ge__(self, otherstring: str) -> bool:
        return bool(self._full >= (TagID(otherstring)._full))

    def __gt__(self, otherstring: str) -> bool:
        return bool(self._full > (TagID(otherstring)._full))

    def __ne__(self, otherstring: str) -> bool:
        return bool(str(self) != str(TagID(otherstring)))

    def __bool__(self):
        """Define True/False as whether 'valid' flag is set."""
        return self.valid

    @property
    def prefix(self) -> str:
        """Return the tag's prefix. E.g. in WA01, the prefix is "WA"."""
        if TagID._uc:
            return self._prefix.upper()
        return self._prefix

    @property
    def letter(self) -> str:
        """Return the tag's letter. E.g. in WA01, the letter is "A"."""
        if TagID._uc:
            return self._letter.upper()
        return self._letter

    @property
    def colour(self) -> str:
        """Return the tag's colour. E.g. in WA01, the colour is "W"."""
        if TagID._uc:
            return self._colour.upper()
        return self._colour

    @property
    def full(self) -> str:
        """Return the full tag id - e.g. "WA001"."""
        if TagID._uc:
            return self._full.upper()
        return self._full

    @property
    def cased(self) -> str:
        """Return TagID as uppercase/lowercase depending on flag."""
        if TagID._uc:
            return self.upper()
        return self.lower()

    def __hash__(self):
        """Make hash int for the object.

        Not a simple object so not hashable (ie not usable as a dict key)
        so must provide own hash method that can be used as a dict key.
        For these, just hash the tag's string value (always lowercase!!!)
        """
        return hash(self.lower())

    def __str__(self) -> str:
        """Show as a string, respecting uppercase flag."""
        if self._uc:
            return self.upper()
        else:
            return self.lower()

    def __repr__(self) -> str:
        return f"'{self.__str__()}'"
