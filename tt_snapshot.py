"""TagTracker by Julias Hocking.

Snapshot class for tagtracker.

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

from tt_trackerday import TrackerDay
from tt_time import VTime
import tt_constants as k


class Snapshot:
    """A snapshot of the state of the site at a specific time of day."""

    def __init__(self, snapshot_time: VTime) -> None:
        """Create empty Snapshot, attributes initialized to type.

        bikes_arked and bikes_returned are lists of the tagids
        of bikes with check-in/out times at this moment.
        """

        self.snapshot_time = snapshot_time
        self.num_here_total = None  # will be int
        self.num_here_regular = None
        self.num_here_oversize = None
        self.bikes_parked = []  # TagIDs of bikes that get checked in at this moment
        self.bikes_returned = []  # TagIDs of bikes checked out during this moment
        self.bikes_here = []  # TagIDs of bikes here (each tagid unique)
        self.num_bikes_parked = 0  # This is just len(self.bikes_parked).
        self.num_bikes_returned = 0  # This is just len(self.bikes_returned).

    @staticmethod
    def calc_moments(
        day: TrackerDay, as_of_when: int | VTime = None
    ) -> dict[VTime, "Snapshot"]:
        """Create a dict of moments keyed by HH:MM time.

        If as_of_when is not given, then this will choose the latest
        event of the day as its time.
        """
        if as_of_when is None:
            # Set as_of_when to be the time of the latest checkout of the day.
            if day.bikes_in:
                as_of_when = day.latest_event("24:00")
            else:
                as_of_when = "now"
        as_of_when = VTime(as_of_when)
        # First pass, create all the Snapshots and list their tags in & out.
        moments = {}
        for visit in day.all_visits():
            # Record the changes that happened at this moment.
            if visit.time_in <= as_of_when:
                if visit.time_in not in moments:
                    moments[visit.time_in] = Snapshot(visit.time_in)
                moments[visit.time_in].bikes_parked.append(visit.tagid)
            if visit.time_out and visit.time_out <= as_of_when:
                if visit.time_out not in moments:
                    moments[visit.time_out] = Snapshot(visit.time_out)
                moments[visit.time_out].bikes_returned.append(visit.tagid)

        # Second pass, calculate the running totals.
        num_regular = 0  # Running balance of regular & oversize bikes.
        num_oversize = 0
        here_set = set()
        for atime in sorted(moments.keys()):
            snapshot = moments[atime]
            snapshot.num_bikes_parked = len(snapshot.bikes_parked)
            snapshot.num_bikes_returned = len(snapshot.bikes_returned)
            # How many regular & oversize bikes have we added or lost?
            delta_regular = len(
                [
                    x
                    for x in snapshot.bikes_parked
                    if day.biketags[x].bike_type == k.REGULAR
                ]
            ) - len(
                [
                    x
                    for x in snapshot.bikes_returned
                    if day.bikestags[x].bike_type == k.REGULAR
                ]
            )
            delta_oversize = len(
                [
                    x
                    for x in snapshot.bikes_parked
                    if day.biketags[x].bike_type == k.OVERSIZE
                ]
            ) - len(
                [
                    x
                    for x in snapshot.bikes_returned
                    if day.bikestags[x].bike_type == k.OVERSIZE
                ]
            )
            num_regular += delta_regular
            num_oversize += delta_oversize
            snapshot.num_here_regular = num_regular
            snapshot.num_here_oversize = num_oversize
            snapshot.num_here_total = num_regular + num_oversize
            snapshot.num_bikes_parked = len(snapshot.bikes_parked)
            snapshot.num_bikes_returned = len(snapshot.bikes_returned)
            # FIXME: The logic below is no longer correct
            here_set = (here_set | set(snapshot.bikes_parked)) - set(
                snapshot.bikes_returned
            )
            snapshot.bikes_here = list(here_set)
        return moments
