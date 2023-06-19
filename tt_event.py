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
from tt_trackerday import TrackerDay
from tt_time import VTime


class Event:
    """What happened at each discrete atime of day (that something happened)."""

    def __init__(self, event_time: VTime) -> None:
        """Create empty Event, attributes initialized to type."""
        self.event_time = event_time
        self.num_here_total = None  # will be int
        self.num_here_regular = None
        self.num_here_oversize = None
        self.bikes_in = []  # List of canonical tag ids.
        self.bikes_out = []
        self.num_ins = 0  # This is just len(self.bikes_in).
        self.num_outs = 0  # This is just len(self.bikes_out).
        self.bikes_here = []  # List of all bikes here

    @staticmethod
    def calc_events(
        day: TrackerDay, as_of_when: (int or VTime) = None
    ) -> dict[VTime, 'Event']:
        """Create a dict of events keyed by HH:MM time.

        If as_of_when is not given, then this will choose the latest
        check-out time of the day as its time.

        As a special case, this will also accept the word "now" to
        mean the current time.
        """
        if as_of_when is None:
            # Set as_of_when to be the time of the latest checkout of the day.
            if day.bikes_in:
                as_of_when = day.latest_event()
            else:
                as_of_when = "now"
        as_of_when = VTime(as_of_when)
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
        here_set = set()
        for atime in sorted(events.keys()):
            ev = events[atime]
            ev.num_ins = len(ev.bikes_in)
            ev.num_outs = len(ev.bikes_out)
            # How many regular & oversize bikes have we added or lost?
            delta_regular = len([x for x in ev.bikes_in if x in day.regular]) - len(
                [x for x in ev.bikes_out if x in day.regular]
            )
            delta_oversize = len([x for x in ev.bikes_in if x in day.oversize]) - len(
                [x for x in ev.bikes_out if x in day.oversize]
            )
            num_regular += delta_regular
            num_oversize += delta_oversize
            ev.num_here_regular = num_regular
            ev.num_here_oversize = num_oversize
            ev.num_here_total = num_regular + num_oversize
            ev.num_ins = len(ev.bikes_in)
            ev.num_outs = len(ev.bikes_out)
            here_set = (here_set | set(ev.bikes_in)) - set(ev.bikes_out)
            ev.bikes_here = list(here_set)
        return events
