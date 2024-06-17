"""TagTracker by Julias Hocking.

Calculate visits mode, mean, median.

Copyright (C) 2023-2024 Todd Glover & Julias Hocking

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

import collections
from statistics import median,mean
from common.tt_constants import BLOCK_DURATION
from common.tt_time import VTime


def _calculate_visit_frequencies(
    durations_list: list, category_width: int = 30
) -> collections.Counter:
    """Helper function for calculating modes."""
    durations = []
    for d in durations_list:
        if isinstance(d, int):
            durations.append(d)
        else:
            durations.append(VTime(d).num)
    durations = [d for d in durations if isinstance(d, int)]

    # Make a new list of the durations, categorized
    categorized = [(d // category_width) * category_width for d in durations]

    # Count how many are in each category
    return collections.Counter(categorized)


def calculate_visit_modes(
    durations_list: list, category_width: int = BLOCK_DURATION
) -> tuple[list[VTime], int]:
    """Calculate the mode(s) for the list of durations.

    The elements in durations can be VTime, str, or int,
    as long as they all evaluate to a VTime.

    For purposes of determining mode, times within one
    block of time of length category_width are
    considered identical.  Defaulit 30 (1/2 hour)

    Returns a list of sorted VTimes().tidy of all the centre times of
    the modes and the number of times it/they occurred.
    """
    freq_list = _calculate_visit_frequencies(durations_list, category_width)
    mosts = freq_list.most_common()
    occurences = mosts[0][1]
    modes_numeric = sorted([element for element, count in mosts if count == occurences])
    modes_list = [f"{VTime(x+category_width/2).tidy}" for x in modes_numeric]
    # modes_list = []
    # modes_list = [x.tidy for x in modes_list]

    return modes_list, occurences

class VisitStats:
    """The statistical measures for a set of visits mostly as VTime().tidy values."""
    def __init__(self,visit_durations:list):
        self.mean = None
        self.median = None
        self.modes = None
        self.mode_occurences = 0
        self.shortest = None
        self.longest = None
        if not visit_durations:
            return
        # If the durations are strings, make them int
        if isinstance(visit_durations[0],str):
            visit_durations = [VTime(v).num for v in visit_durations]
        #
        self.modes,self.mode_occurences = calculate_visit_modes(visit_durations)
        self.mean = VTime(mean(visit_durations)).tidy
        self.median = VTime(median(visit_durations)).tidy
        self.shortest = VTime(min(visit_durations)).tidy
        self.longest = VTime(max(visit_durations)).tidy
