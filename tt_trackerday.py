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
        self.regular = []
        self.oversize = []
        self.retired = []
        self.colour_letters = {}
        self.is_uppercase = None  # Tags in uppercase or lowercase?

    def all_tags(self) -> list[Tag]:
        """Return list of all usable tags."""
        return list(set(self.regular + self.oversize))

    def make_lowercase(self) -> None:
        """Set TrackerDay object to all lowercase."""
        self.regular = [t.lower for t in self.regular]
        self.oversize = [t.lower for t in self.oversize]
        self.retired = [t.lower for t in self.retired]
        self.bikes_in = {k.lower(): v for k, v in self.bikes_in.items()}
        self.bikes_out = {k.lower(): v for k, v in self.bikes_out.items()}
        self.is_uppercase = False

    def make_uppercase(self) -> None:
        """Set TrackerDay object to all uppercase."""
        self.regular = [t.upper for t in self.regular]
        self.oversize = [t.upper for t in self.oversize]
        self.retired = [t.upper for t in self.retired]
        self.bikes_in = {k.upper(): v for k, v in self.bikes_in.items()}
        self.bikes_out = {k.upper(): v for k, v in self.bikes_out.items()}
        self.is_uppercase = True

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

        def bad_tags(taglist: list[Tag], listname: str) -> list[str]:
            """Get list of err msgs about poorly formed tags in taglist."""
            msgs = []
            for tag in taglist:
                if ut.fix_tag(tag, uppercase=self.is_uppercase) != tag:
                    msgs.append(f"Bad tag '{tag}' in {listname}")
            return msgs

        def bad_times(timesdict: dict[str, Time], listname: str) -> list[str]:
            """Get list of errors about mal-formed time values in timesdict."""
            msgs = []
            for key, atime in timesdict.items():
                if ut.time_str(atime) != atime:
                    msgs.append(
                        f"Bad time '{atime}' in " f"{listname} with key '{key}'"
                    )
            return msgs

        def dup_check(taglist: list[Tag], listname: str) -> list[str]:
            """Get list of err msgs about tag in taglist more than once."""
            msgs = []
            if len(taglist) != len(list(set(taglist))):
                msgs.append(f"Duplicate tags in {listname}")
            return msgs

        errors = []
        # Look for missing or bad times and dates
        if strict_datetimes:
            if not self.date or ut.date_str(self.date) != self.date:
                errors.append(f"Bad or missing valet date {self.date}")
            if (
                not self.opening_time
                or ut.time_str(self.opening_time) != self.opening_time
            ):
                errors.append(f"Bad or missing opening time {self.opening_time}")
            if (
                not self.closing_time
                or ut.time_str(self.closing_time) != self.closing_time
            ):
                errors.append(f"Bad or missing closing time {self.closing_time}")
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
        errors += dup_check(self.regular + self.oversize, "oversize + regular tags")
        # Look for bike checked out but not in, or check-in later than check-out
        for tag, atime in self.bikes_out.items():
            if tag not in self.bikes_in:
                errors.append(f"Bike {tag} checked in but not out")
            elif atime < self.bikes_in[tag]:
                errors.append(f"Bike {tag} check-out earlier than check-in")
        # Bikes that are not in the list of allowed bikes
        _allowed_tags = self.regular + self.oversize
        _used_tags = list(set(list(self.bikes_in.keys()) + list(self.bikes_out.keys())))
        for tag in _used_tags:
            if tag not in _allowed_tags:
                errors.append(f"Tag {tag} not in use (not regular nor oversized)")
            if tag in self.retired:
                errors.append(f"Tag {tag} is marked as retired")
        return errors

    def earliest_event(self) -> ut.Time:
        """Return the earliest event of the day as HH:MM (or "" if none)."""
        all_events = list(self.bikes_in.keys()) + list(self.bikes_out.keys())
        if not all_events:
            return ""
        return min(all_events)

    def latest_event(self, as_of_when: Union[ut.Time, int, None] = None) -> ut.Time:
        """Return the latest event of the day at or before as_of_when.

        If no events in the time period, return "".
        If as_of_when is blank or None, then this will use the whole day.
        FIXME: check that this is the right choice. Would it be better to
        go only up to the current moment?
        """
        if not as_of_when:
            as_of_when = "24:00"
        else:
            as_of_when = ut.time_str(as_of_when)
            if not (as_of_when):
                return ""
        events = [
            x
            for x in (list(self.bikes_in.values()) + list(self.bikes_out.values()))
            if x <= as_of_when
        ]
        # Anything?
        if not events:
            return ""
        # Find latest event of the day
        latest = max(events)
        return latest

    def num_later_events(self, after_when: Union[ut.Time, int, None] = None) -> int:
        """Get count of events that are later than after_when."""
        if not after_when:
            after_when = ut.get_time()
        else:
            after_when = ut.time_str(after_when)
            if not (after_when):
                return ""

        events = [
            x
            for x in (list(self.bikes_in.values()) + list(self.bikes_out.values()))
            if x > after_when
        ]
        return len(events)
