"""TagTracker by Julias Hocking.

Summary & associated classes for tagtracker.

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

from dataclasses import dataclass, field
from collections import defaultdict
from common.tt_trackerday import TrackerDay
from common.tt_time import VTime
import common.tt_constants as k
from common.tt_util import block_start
# from common.tt_biketag import BikeTag
# from common.tt_bikevisit import BikeVisit


@dataclass
class MomentDetail:
    """Class to summarize all bike activity & holdings at one moment in the day."""

    time: str = ""
    num_incoming: dict = field(
        default_factory=lambda: {k.REGULAR: 0, k.OVERSIZE: 0, k.COMBINED: 0}
    )
    num_outgoing: dict = field(
        default_factory=lambda: {k.REGULAR: 0, k.OVERSIZE: 0, k.COMBINED: 0}
    )
    num_on_hand: dict = field(
        default_factory=lambda: {k.REGULAR: 0, k.OVERSIZE: 0, k.COMBINED: 0}
    )
    tag_descriptions_incoming: dict = field(default_factory=lambda: [])
    tag_descriptions_outgoing: dict = field(default_factory=lambda: [])


@dataclass
class PeriodDetail:
    """Class to summarize what happened during one period (block) in the day."""

    time_start: str = ""
    num_incoming: dict = field(
        default_factory=lambda: {k.REGULAR: 0, k.OVERSIZE: 0, k.COMBINED: 0}
    )
    num_outgoing: dict = field(
        default_factory=lambda: {k.REGULAR: 0, k.OVERSIZE: 0, k.COMBINED: 0}
    )
    num_on_hand: dict = field(
        default_factory=lambda: {k.REGULAR: 0, k.OVERSIZE: 0, k.COMBINED: 0}
    )
    num_fullest: dict = field(
        default_factory=lambda: {k.REGULAR: 0, k.OVERSIZE: 0, k.COMBINED: 0}
    )
    time_fullest: dict = field(
        default_factory=lambda: {k.REGULAR: "", k.OVERSIZE: "", k.COMBINED: ""}
    )


@dataclass
class DayTotals:
    """Whole-day summary, to match the database DAY table.

    Some of these properties are only meaningful when this is assigned from
    the database. (E.g. weather data, which is added only in the database.)

    This is intended to have a close resemblance to a database DAY row, both
    in the names of items and their meaning.

    Some properties overlap with those in a TrackerDay but since this is
    effectively a reporting structure not an operational structure, that seems ok.
    """

    org:str = ""
    site_handle:str = ""
    site_name:str = ""

    date: str = ""

    time_open: VTime = VTime("")
    time_closed: VTime = VTime("")
    weekday: int = None

    num_parked_regular: int = 0
    num_parked_oversize: int = 0
    num_parked_combined: int = 0

    num_remaining_regular: int = 0
    num_remaining_oversize: int = 0
    num_remaining_combined: int = 0

    num_fullest_regular: int = 0
    num_fullest_oversize: int = 0
    num_fullest_combined: int = 0

    time_fullest_regular: VTime = VTime("")
    time_fullest_oversize: VTime = VTime("")
    time_fullest_combined: VTime = VTime("")

    bikes_registered: int = 0
    max_temperature: float = None
    precipitation: float = None


class DaySummary:
    """Complex class for whole-day summary of events and blocks (for reporting)."""

    def __init__(self, day: TrackerDay, as_of_when: str = ""):
        self.date = day.date

        # If no time given, set to latest event of the day
        if not as_of_when:
            as_of_when = day.latest_event("24:00")
        if not as_of_when:
            as_of_when = "now"
        self.as_of_when = VTime(as_of_when)

        self.moments = self._summarize_moments(day=day, as_of_when=self.as_of_when)
        self.blocks = self._summarize_blocks(moments=self.moments)
        self.whole_day = self._summarize_whole_day(day=day,blocks=self.blocks)

    def __repr__(self):
        s = f"DaySummary for {self.date}, as of {self.as_of_when}\n"

        s += "Whole day overview (tuples are Regular,Oversize,Combined):\n"
        whole: DayTotals = self.whole_day
        s += (
            f"   In {whole.num_parked_regular:2d}, {whole.num_parked_oversize:2d}, "
            f"{whole.num_parked_combined:2d};  "
        )
        s += (
            f"Here {whole.num_remaining_regular:3d}, {whole.num_remaining_oversize:3d}, "
            f"{whole.num_remaining_combined:3d};  "
        )
        s += (
            f"Fullest {whole.num_fullest_regular:3d} @{whole.time_fullest_regular:5s}, "
            f"{whole.num_fullest_oversize:3d} @{whole.time_fullest_oversize:5s}, "
            f"{whole.num_fullest_combined:3d} @{whole.time_fullest_combined:5s}\n"
        )

        s += "Moments  (tuples are Regular,Oversize,Combined):\n"
        for m in sorted(self.moments.keys()):
            moment: MomentDetail = self.moments[m]
            s += f"   {m}: "
            s += (
                f"In {moment.num_incoming[k.REGULAR]:2d}, {moment.num_incoming[k.OVERSIZE]:2d}, "
                f"{moment.num_incoming[k.COMBINED]:2d};  "
            )
            s += (
                f"Out {moment.num_outgoing[k.REGULAR]:2d}, {moment.num_outgoing[k.OVERSIZE]:2d}, "
                f"{moment.num_outgoing[k.COMBINED]:2d};  "
            )
            s += (
                f"Here {moment.num_on_hand[k.REGULAR]:3d}, {moment.num_on_hand[k.OVERSIZE]:3d}, "
                f"{moment.num_on_hand[k.COMBINED]:3d}\n"
            )

        s += "Blocks:\n"
        for b in sorted(self.blocks.keys()):
            block: PeriodDetail = self.blocks[b]
            s += f"   {b}: "
            s += (
                f"In {block.num_incoming[k.REGULAR]:2d}, {block.num_incoming[k.OVERSIZE]:2d}, "
                f"{block.num_incoming[k.COMBINED]:2d};  "
            )
            s += (
                f"Out {block.num_outgoing[k.REGULAR]:2d}, {block.num_outgoing[k.OVERSIZE]:2d}, "
                f"{block.num_outgoing[k.COMBINED]:2d};  "
            )
            s += (
                f"Here {block.num_on_hand[k.REGULAR]:3d}, {block.num_on_hand[k.OVERSIZE]:3d}, "
                f"{block.num_on_hand[k.COMBINED]:3d};  "
            )
            s += (
                f"Fullest {block.num_fullest[k.REGULAR]:3d} @{block.time_fullest[k.REGULAR]:5s}, "
                f"{block.num_fullest[k.OVERSIZE]:3d} @{block.time_fullest[k.OVERSIZE]:5s}, "
                f"{block.num_fullest[k.COMBINED]:3d} @{block.time_fullest[k.COMBINED]:5s}\n"
            )

        return s

    @staticmethod
    def _summarize_moments(
        day: TrackerDay, as_of_when: VTime
    ) -> dict[str, MomentDetail]:
        """Create a dict of moments keyed by HH:MM time."""
        moments = defaultdict(lambda: MomentDetail(time=None))

        for biketag in day.biketags.values():
            for visit_num, visit in enumerate(biketag.visits, start=1):
                if visit.time_in <= as_of_when:
                    bike_type = day.biketags[visit.tagid].bike_type
                    moments[visit.time_in].time = visit.time_in
                    moments[visit.time_in].num_incoming[bike_type] += 1
                    moments[visit.time_in].tag_descriptions_incoming.append(
                        f"{visit.tagid}:{visit_num}"
                    )
                if visit.time_out and visit.time_out <= as_of_when:
                    moments[visit.time_out].time = visit.time_out
                    moments[visit.time_out].num_outgoing[bike_type] += 1
                    moments[visit.time_out].tag_descriptions_outgoing.append(
                        f"{visit.tagid}:{visit_num}"
                    )

        here = {k.REGULAR: 0, k.OVERSIZE: 0, k.COMBINED: 0}
        for moment_time in sorted(moments):
            moment = moments[moment_time]
            moment.num_incoming[k.COMBINED] = (
                moment.num_incoming[k.REGULAR] + moment.num_incoming[k.OVERSIZE]
            )
            moment.num_outgoing[k.COMBINED] = (
                moment.num_outgoing[k.REGULAR] + moment.num_outgoing[k.OVERSIZE]
            )
            for bike_type in [k.REGULAR, k.OVERSIZE, k.COMBINED]:
                here[bike_type] += (
                    moment.num_incoming[bike_type] - moment.num_outgoing[bike_type]
                )
                moment.num_on_hand[bike_type] = here[bike_type]

        return moments

    @staticmethod
    def _summarize_blocks(
        moments: dict[VTime, MomentDetail]
    ) -> dict[VTime, PeriodDetail]:
        """Create a dictionary of PeriodDetail objects for this day."""
        blocks = defaultdict(lambda: PeriodDetail(time_start=None))

        if not moments:
            return blocks

        # Get sorted times from moments
        earliest_time = min(moments.keys())
        latest_time = max(moments.keys())

        # Calculate start time for blocks

        day_here = {
            k.REGULAR: 0,
            k.OVERSIZE: 0,
            k.COMBINED: 0,
        }  # running totals on hand
        block_start_time = block_start(earliest_time)
        while block_start_time.num <= latest_time.num:  # yes blocks need to be in order
            block_end_time = VTime(block_start_time.num + k.BLOCK_DURATION - 1)
            current_block = PeriodDetail(time_start=block_start_time)
            block_ins = {
                k.REGULAR: 0,
                k.OVERSIZE: 0,
                k.COMBINED: 0,
            }  # running totals on hand
            block_outs = {
                k.REGULAR: 0,
                k.OVERSIZE: 0,
                k.COMBINED: 0,
            }  # running totals on hand

            for moment_time in sorted(moments):  # yes moments need to be in order
                moment: MomentDetail = moments[moment_time]
                if block_start_time <= moment_time <= block_end_time:

                    for bike_type in [k.REGULAR, k.OVERSIZE, k.COMBINED]:
                        block_ins[bike_type] += moment.num_incoming[bike_type]
                        block_outs[bike_type] += moment.num_outgoing[bike_type]
                        day_here[bike_type] += (
                            moment.num_incoming[bike_type]
                            - moment.num_outgoing[bike_type]
                        )
                        if day_here[bike_type] > current_block.num_fullest[bike_type]:
                            current_block.num_fullest[bike_type] = day_here[bike_type]
                            current_block.time_fullest[bike_type] = moment_time

            # Have looked at all the moments, now finish off the block
            for bike_type in [k.REGULAR, k.OVERSIZE, k.COMBINED]:
                current_block.num_incoming[bike_type] = block_ins[bike_type]
                current_block.num_outgoing[bike_type] = block_outs[bike_type]
                current_block.num_on_hand[bike_type] = day_here[bike_type]
                # Check fullest in case there was no activity
                if not current_block.time_fullest[bike_type]:
                    current_block.num_fullest[bike_type] = current_block.num_on_hand[
                        bike_type
                    ]
                    current_block.time_fullest[bike_type] = block_start_time

            blocks[block_start_time] = current_block
            block_start_time = VTime(block_start_time.num + k.BLOCK_DURATION)

        return blocks

    @staticmethod
    def _summarize_whole_day(day:TrackerDay,blocks: dict[VTime, PeriodDetail]) -> DayTotals:
        """Summarize the whole day's blocks as one time period."""

        whole_day = DayTotals()
        whole_day.site_handle = day.site_handle
        whole_day.site_name = day.site_name
        whole_day.date = day.date
        whole_day.time_open = day.time_open
        whole_day.time_closed = day.time_closed


        num_parked = {k.REGULAR:0,k.OVERSIZE:0,k.COMBINED:0}
        num_returned = {k.REGULAR:0,k.OVERSIZE:0,k.COMBINED:0}
        num_remaining = {k.REGULAR:0,k.OVERSIZE:0,k.COMBINED:0}
        num_fullest = {k.REGULAR:0,k.OVERSIZE:0,k.COMBINED:0}
        time_fullest = {k.REGULAR:"",k.OVERSIZE:"",k.COMBINED:""}
        for block in blocks.values():
            block: PeriodDetail
            for bike_type in [k.REGULAR, k.OVERSIZE, k.COMBINED]:
                num_parked[bike_type] += block.num_incoming[bike_type]
                num_returned[bike_type] += block.num_outgoing[bike_type]
                num_remaining[bike_type] = (
                    num_parked[bike_type]
                    - num_returned[bike_type]
                )
                if block.num_fullest[bike_type] > num_fullest[bike_type]:
                    num_fullest[bike_type] = block.num_fullest[bike_type]
                    time_fullest[bike_type] = block.time_fullest[bike_type]

        whole_day.num_parked_regular = num_parked[k.REGULAR]
        whole_day.num_parked_oversize = num_parked[k.OVERSIZE]
        whole_day.num_parked_combined = num_parked[k.COMBINED]

        whole_day.num_remaining_regular = num_remaining[k.REGULAR]
        whole_day.num_remaining_oversize = num_remaining[k.OVERSIZE]
        whole_day.num_remaining_combined = num_remaining[k.COMBINED]

        whole_day.num_fullest_regular = num_fullest[k.REGULAR]
        whole_day.num_fullest_oversize = num_fullest[k.OVERSIZE]
        whole_day.num_fullest_combined = num_fullest[k.COMBINED]

        whole_day.time_fullest_regular = time_fullest[k.REGULAR]
        whole_day.time_fullest_oversize = time_fullest[k.OVERSIZE]
        whole_day.time_fullest_combined = time_fullest[k.COMBINED]

        return whole_day

        # num_incoming = {k.REGULAR:0,k.OVERSIZE:0,k.COMBINED:0}
        # for block in blocks.values():
        #     block: PeriodDetail
        #     for bike_type in [k.REGULAR, k.OVERSIZE, k.COMBINED]:
        #         whole_day.num_incoming[bike_type] += block.num_incoming[bike_type]
        #         whole_day.num_outgoing[bike_type] += block.num_outgoing[bike_type]
        #         whole_day.num_on_hand[bike_type] = (
        #             whole_day.num_incoming[bike_type]
        #             - whole_day.num_outgoing[bike_type]
        #         )
        #         if block.num_fullest[bike_type] > whole_day.num_fullest[bike_type]:
        #             whole_day.num_fullest[bike_type] = block.num_fullest[bike_type]
        #             whole_day.time_fullest[bike_type] = block.time_fullest[bike_type]
        # return whole_day
