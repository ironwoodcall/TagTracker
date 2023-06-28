"""TagTracker by Julias Hocking.

TrackerDay class for tagtracker.
TrackerDay holds all the state information about a single day at the bike valet.

Copyright (C) 2023 Julias Hocking

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

from typing import Union
from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
from tt_tag import TagID
from tt_time import VTime
import tt_util as ut


class TrackerDay:
    """One day's worth of tracker info and its context."""

    def __init__(self) -> None:
        """Initialize blank."""
        self.date = ""
        self.opening_time = ""
        self.closing_time = ""
        self.bikes_in = {}
        self.bikes_out = {}
        self.regular = frozenset()
        self.oversize = frozenset()
        self.retired = frozenset()
        self.colour_letters = {}

    def all_tags(self) -> frozenset[TagID]:
        """Return list of all usable tags."""
        return frozenset((self.regular | self.oversize) - self.retired)

    def DISABLED__make_lowercase(self) -> None:
        """Set TrackerDay object to all lowercase."""
        self.regular = frozenset([t.lower() for t in self.regular])
        self.oversize = frozenset([t.lower() for t in self.oversize])
        self.retired = frozenset([t.lower() for t in self.retired])
        self.bikes_in = {k.lower(): v for k, v in self.bikes_in.items()}
        self.bikes_out = {k.lower(): v for k, v in self.bikes_out.items()}

    def DISABLED__make_uppercase(self) -> None:
        """Set TrackerDay object to all uppercase."""
        self.regular = frozenset([t.upper() for t in self.regular])
        self.oversize = frozenset([t.upper() for t in self.oversize])
        self.retired = frozenset([t.upper() for t in self.retired])
        self.bikes_in = {k.upper(): v for k, v in self.bikes_in.items()}
        self.bikes_out = {k.upper(): v for k, v in self.bikes_out.items()}

    def DISABLED__fold_case(self, uppercase: bool) -> None:
        """Folds to either uppercase or lowercase."""
        if uppercase:
            self.DISABLED__make_uppercase()
        else:
            self.DISABLED__make_lowercase()

    def make_fake_tag_lists(self) -> None:
        """Fake up regular/oversized tag ists based on City Hall use in 2023."""
        regulars = set()
        oversizes = set()
        for tag in set(self.bikes_in.keys()) | set(self.bikes_out.keys()):
            tag: TagID
            if tag.colour in ["o", "p", "w"]:
                regulars.add(tag)
            elif tag.colour == "b":
                oversizes.add(tag)
        self.regular = frozenset(regulars)
        self.oversize = frozenset(oversizes)

    def make_fake_colour_dict(self) -> None:
        """Fake up a colour dictionary in day from existing tags."""
        letters = set()
        for tag in self.bikes_in:
            letters.add(tag.colour)
        colour_dict = {}
        for c in letters:
            colour_dict[c] = f"colour {c}"
        self.colour_letters = colour_dict

    def lint_check(self, strict_datetimes: bool = False) -> list[str]:
        """Generate a list of logic error messages for TrackerDay object.

        If no errors found returns []
        If errors, returns list of error message strings.

        Check for:
        - bikes checked out but not in
        - checked out before in
        - multiple check-ins, multiple check-outs
        - unrecognized tag in check-ins & check-outs
        - poorly formed Tag
        - poorly formed Time
        - use of a tag that is retired (to do later)
        If strict_datetimes then checks:
        - valet date, opening and closing are well-formed
        - valet opening time < closing time
        """

        def bad_tags(taglist: list[TagID], listname: str) -> list[str]:
            """Get list of err msgs about poorly formed tags in taglist."""
            msgs = []
            for tag in taglist:
                tag: TagID
                if not isinstance(tag, TagID) or not tag.valid:
                    msgs.append(f"Bad tag '{tag}' in {listname}")
            return msgs

        def bad_times(timesdict: dict[str, VTime], listname: str) -> list[str]:
            """Get list of errors about mal-formed time values in timesdict."""
            msgs = []
            for key, atime in timesdict.items():
                if not isinstance(atime, VTime) or not atime:
                    msgs.append(
                        f"Bad time '{atime}' in "
                        f"{listname} with key '{key}'"
                    )
            return msgs

        errors = []
        # Look for missing or bad times and dates
        if strict_datetimes:
            if not self.date or ut.date_str(self.date) != self.date:
                errors.append(f"Bad or missing valet date {self.date}")
            if not self.opening_time or not isinstance(
                self.opening_time, VTime
            ):
                errors.append(
                    f"Bad or missing opening time {self.opening_time}"
                )
            if not self.closing_time or not isinstance(
                self.closing_time, VTime
            ):
                errors.append(
                    f"Bad or missing closing time {self.closing_time}"
                )
            if (
                self.opening_time
                and self.closing_time
                and self.opening_time >= self.closing_time
            ):
                errors.append(
                    f"Opening time '{self.opening_time}' is not "
                    f"earlier then closing time '{self.closing_time}'"
                )
        # Look for poorly formed times and tags
        errors += bad_tags(self.regular, "regular-tags")
        errors += bad_tags(self.oversize, "oversize-tags")
        errors += bad_tags(self.bikes_in.keys(), "bikes-checked-in")
        errors += bad_tags(self.bikes_out.keys(), "bikes-checked-out")
        errors += bad_times(self.bikes_in, "bikes-checked-in")
        errors += bad_times(self.bikes_out, "bikes-checked-out")
        # Look for duplicates in regular and oversize tags lists
        if len(self.regular | self.oversize) != len(self.regular) + len(
            self.oversize
        ):
            errors.append(
                "Size mismatch between regular+oversize tags and their union"
            )
        # Look for bike checked out but not in, or check-in later than check-out
        for tag, atime in self.bikes_out.items():
            if tag not in self.bikes_in:
                errors.append(f"Bike {tag} checked in but not out")
            elif atime < self.bikes_in[tag]:
                errors.append(f"Bike {tag} check-out earlier than check-in")
        # Bikes that are not in the list of allowed bikes
        _allowed_tags = self.regular | self.oversize
        _used_tags = self.bikes_in.keys() | self.bikes_out.keys()
        for tag in _used_tags:
            if tag not in _allowed_tags:
                errors.append(
                    f"Tag {tag} not in use (not regular nor oversized)"
                )
            if tag in self.retired:
                errors.append(f"Tag {tag} is marked as retired")
        return errors

    def earliest_event(self) -> VTime:
        """Return the earliest event of the day as HH:MM (or "" if none)."""
        all_events = self.bikes_in.keys() | self.bikes_out.keys()
        if not all_events:
            return ""
        return min(all_events)

    def latest_event(
        self, as_of_when: Union[VTime, int, None] = None
    ) -> VTime:
        """Return the latest event of the day at or before as_of_when.

        If no events in the time period, return "".
        If as_of_when is blank or None, then this will use the whole day.
        """
        if not as_of_when:
            as_of_when = VTime("24:00")
        else:
            as_of_when = VTime(as_of_when)
            if not (as_of_when):
                return ""
        events = [
            x
            for x in (
                set(self.bikes_in.values()) | set(self.bikes_out.values())
            )
            if x <= as_of_when
        ]
        # Anything?
        if not events:
            return ""
        # Find latest event of the day
        latest = max(events)
        return latest

    def num_later_events(
        self, after_when: Union[VTime, int, None] = None
    ) -> int:
        """Get count of events that are later than after_when."""
        if not after_when:
            after_when = VTime("now")
        else:
            after_when = VTime(after_when)
            if not (after_when):
                return ""

        events = [
            x
            for x in (
                set(self.bikes_in.values()) | set(self.bikes_out.values())
            )
            if x > after_when
        ]
        return len(events)
