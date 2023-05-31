"""TagTracker by Julias Hocking.

Event class for tagtracker.

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
from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
import tt_util as ut
import tt_trackerday


class Event:
    """What happened at each discrete atime of day (that something happened)."""

    def __init__(self, event_time: ut.Time) -> None:
        """Create empty Event, attributes initialized to type."""
        self.event_time = event_time
        self.num_here_total = None  # will be int
        self.num_here_regular = None
        self.num_here_oversize = None
        self.bikes_in = []  # List of canonical tag ids.
        self.bikes_out = []
        self.num_ins = 0  # This is just len(self.bikes_in).
        self.num_outs = 0  # This is just len(self.bikes_out).


def calc_events(
    day: tt_trackerday.TrackerDay, as_of_when: (int or ut.Time) = None
) -> dict[ut.Time, Event]:
    """Create a dict of events keyed by HH:MM time.

    If as_of_when is not given, then this will choose the latest
    check-out time of the day as its time.

    As a special case, this will also accept the word "now" to
    mean the current time.
    """
    if as_of_when is None:
        # Set as_of_when to be the time of the latest checkout of the day.
        if day.bikes_in:
            as_of_when = min(list(day.bikes_in.values()))
        else:
            as_of_when = "now"
    as_of_when = ut.time_str(as_of_when, allow_now=True)
    # First pass, create all the Events and list their tags in & out.
    events = {}
    for tag, atime in day.bikes_in.items():
        if atime > as_of_when:
            continue
        if atime not in events:
            events[atime] = Event(atime)
        events[atime].bikes_in.append(tag)
    for tag, atime in day.bikes_out.items():
        if atime > as_of_when:
            continue
        if atime not in events:
            events[atime] = Event(atime)
        events[atime].bikes_out.append(tag)
    # Second pass, calculate other attributes of Events.
    num_regular = 0  # Running balance of regular & oversize bikes.
    num_oversize = 0
    for atime in sorted(events.keys()):
        vx = events[atime]
        vx.num_ins = len(vx.bikes_in)
        vx.num_outs = len(vx.bikes_out)
        # How many regular & oversize bikes have we added or lost?
        diff_normal = len([x for x in vx.bikes_in if x in day.regular]) - len(
            [x for x in vx.bikes_out if x in day.regular]
        )
        diff_oversize = len([x for x in vx.bikes_in if x in day.oversize]) - len(
            [x for x in vx.bikes_out if x in day.oversize]
        )
        num_regular += diff_normal
        num_oversize += diff_oversize
        vx.num_here_regular = num_regular
        vx.num_here_oversize = num_oversize
        vx.num_here_total = num_regular + num_oversize
        vx.num_ins = len(vx.bikes_in)
        vx.num_outs = len(vx.bikes_out)
    return events
