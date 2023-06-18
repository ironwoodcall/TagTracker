"""TagTracker by Julias Hocking.

Visist (stay) class for tagtracker.

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
import tt_trackerday as td


class Visit:
    """Just a data structure to keep track of bike visits."""

    def __init__(self, tag: str) -> None:
        """Initialize blank."""
        self.tag = tag  # canonical
        self.time_in = ""  # HH:MM
        self.time_out = ""  # HH:MM
        self.duration = 0  # minutes
        self.type = None  # REGULAR, OVERSIZE
        self.still_here = None  # True or False

    def dump(self) -> None:
        """Get contents of the Visit."""
        return (
            f"{self.tag=},{self.time_in=},{self.time_out=},"
            f"{self.duration=},{self.type=},{self.still_here=}"
        )


def dump_visits(visits: dict[Visit]) -> None:
    """Dump whole visits dictionary."""
    print("\nvisits\n")
    for v in visits.values():
        print(v.dump())


def calc_visits(
    day: td.TrackerDay, as_of_when: Union[int, VTime]
) -> dict[TagID, Visit]:
    """Create a dict of visits keyed by tag as of as_of_when.

    If as_of_when is not given, then this will use the current time.

    If there are bikes that are not checked out, then this will
    consider their check-out time to be:
        earlier of:
            current time
            closing time if there is one, else time of latest event of the day.

    As a special case, this will also accept the word "now" to
    mean the current time.
    """
    as_of_when = "now" if not as_of_when else as_of_when
    as_of_when = VTime(as_of_when)

    # If a bike isn't checked out or its checkout is after the requested
    # time, then use what as its checkout time?
    latest_time = day.closing_time if day.closing_time else day.latest_event()
    missing_checkout_time = min([latest_time, as_of_when])

    visits = {}
    for tag, time_in in day.bikes_in.items():
        if time_in > as_of_when:
            continue
        this_visit = Visit(tag)
        this_visit.time_in = time_in
        if tag in day.bikes_out and day.bikes_out[tag] <= as_of_when:
            this_visit.time_out = day.bikes_out[tag]
            this_visit.still_here = False
        else:
            this_visit.time_out = missing_checkout_time
            this_visit.still_here = True
        this_visit.duration = max(
            1,
            (
                ut.time_int(this_visit.time_out)
                - ut.time_int(this_visit.time_in)
            ),
        )
        if tag in day.regular:
            this_visit.type = REGULAR
        else:
            this_visit.type = OVERSIZE
        visits[tag] = this_visit
    return visits
