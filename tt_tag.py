"""This is a semi-experimental TagID class


    A TagID is the name of a tag; it might be a correct tag name or not.
    It is a type of string, and its representation is canonical
    tag representation (e.g. "wa1").  TagIDs with identical representation
    are considered equal, even though the 'original' attribute
    might not be the same.


"""

import re

class TagID(str):
    # _uc indicates whether to print in uppercase (otherwise lc).
    # Canonical representation is *always*
    _uc = False

    @classmethod
    def uc(cls,new_state:bool=None) -> bool:
        """Set uppercase state if given; return current state."""
        if new_state is not None:
            cls._uc = bool(new_state)
        return cls._uc

    def __new__(cls, string:str=""):
        """Create a TagID string with its 'self' as canonical tag id."""
        if not isinstance(string, str):
            selfstring = ""
        else:
            r = re.match(r"^ *([a-z])([a-z]+)0*([0-9]+) *$", string.lower())
            if r:
                selfstring = f"{r.group(1)}{r.group(2)}{r.group(3)}".lower()
            else:
                selfstring = ""
        instance = super().__new__(cls, selfstring)
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

    def __init__(self, string:str=""): #pylint:disable=unused-argument
        """Initialize attributes not done in __new__()."""
        # str.__init__("")
        # The following idiocy is to keep pylint happy
        if False:  # pylint:disable=using-constant-test
            self.original = ""
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

    def __eq__(self, otherstring:str) -> bool:
        """Define equality to mean represent same tag name."""
        return bool(str(self) == str(TagID(otherstring)))

    def __le__(self,otherstring:str) -> bool:
        return bool(self._full <= (TagID(otherstring)._full))
    def __lt__(self,otherstring:str) -> bool:
        return bool(self._full < TagID(otherstring)._full)
    def __ge__(self, otherstring: str) -> bool:
        return bool(self._full >= (TagID(otherstring)._full))
    def __gt__(self,otherstring:str) -> bool:
        return bool(self._full > (TagID(otherstring)._full))
    def __ne__(self,otherstring:str) -> bool:
        return bool(str(self) != str(TagID(otherstring)))

    def __bool__(self):
        """Define True/False as whether 'valid' flag is set."""
        return self.valid

    @property
    def prefix(self) -> str:
        if TagID._uc:
            return self._prefix.upper()
        return self._prefix
    @property
    def letter(self) -> str:
        if TagID._uc:
            return self._letter.upper()
        return self._letter
    @property
    def colour(self) -> str:
        if TagID._uc:
            return self._colour.upper()
        return self._colour
    @property
    def full(self) -> str:
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
        if self._uc:
            return self.upper()
        else:
            return self.lower()

    __repr__ = __str__