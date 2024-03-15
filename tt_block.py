"""TagTracker by Julias Hocking.

Block class to help with reporting in the TagTracker suite.

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

import tt_constants as k
from tt_trackerday import TrackerDay
from tt_time import VTime
from tt_event import Event


class Block:
    """Class to help with reporting.

    Each instance is a timeblock of duration k.BLOCK_DURATION.
    """

    def __init__(self, start_time: VTime|int) -> None:
        """Initialize. Assumes that start_time is valid."""
        self.start = VTime(start_time)  # in case it's a str not a VTime
        self.ins_list = []  # Tags of bikes that came in.
        self.num_ins = 0  # Number of bikes that came in.
        self.num_ins_regular = 0
        self.num_ins_oversize = 0
        self.outs_list = []  # Tags of bikes returned out.
        self.num_outs = 0  # Number of bikes that went out.
        self.num_outs_regular = 0
        self.num_outs_oversize = 0
        self.here_list = []  # Tags of bikes onsite at end of block.
        self.num_here = 0  # Number of bikes onsite at end of block.
        self.num_here_regular = 0
        self.num_here_oversize = 0
        self.max_here_list = []  # Tags at time max bikes here during the block
        self.max_here = 0  # Mxx number of bikes here any time in this block
        self.max_here_regular = 0
        self.max_here_oversize = 0


def block_start(atime: int|str) -> VTime:
    """Return the start time of the block that contains time 'atime'.

    'atime' can be minutes since midnight or HHMM.
    """
    # Get time in minutes
    atime = VTime(atime)
    if atime is None:
        return ""
    # which block of time does it fall in?
    block_start_min = (atime.num // k.BLOCK_DURATION) * k.BLOCK_DURATION
    return VTime(block_start_min)


def block_end(atime: int|str) -> VTime:
    """Return the last minute of the timeblock that contains time 'atime'.

    'atime' can be minutes since midnight or HHMM.
    """
    # Get block start
    start = block_start(atime)
    # Calculate block end
    end = start.num + k.BLOCK_DURATION - 1
    # Return as minutes or HHMM
    return VTime(end)


def get_timeblock_list(day: TrackerDay, as_of_when: str) -> list[VTime]:
    """Build a list of timeblocks from beg of day until as_of_when.

    Latest block of the day will be the latest timeblock that
    had any transactions at or before as_of_when.
    """

    as_of_when = as_of_when if as_of_when else "now"
    as_of_when = VTime(as_of_when)
    # Make list of transactions <= as_of_when
    transx = [
        x
        for x in (list(day.bikes_in.values()) + list(day.bikes_out.values()))
        if x <= as_of_when
    ]
    # Anything?
    if not transx:
        return []
    # Find earliest and latest block of the day
    min_block_min = block_start(min(transx)).num
    max_block_min = block_start(max(transx)).num
    # Create list of timeblocks for the the whole day.
    timeblocks = []
    for t in range(
        min_block_min, max_block_min + k.BLOCK_DURATION, k.BLOCK_DURATION
    ):
        timeblocks.append(VTime(t))
    return timeblocks


def calc_blocks(day: TrackerDay, as_of_when: str = None) -> dict[VTime, object]:
    """Create a dictionary of Blocks {start:Block} for whole day."""
    if not as_of_when:
        as_of_when = day.latest_event("24:00")
        if as_of_when < day.closing_time:
            as_of_when = day.closing_time
    as_of_when = VTime(as_of_when)
    ##as_of_when = as_of_when if as_of_when else "18:00"
    # Create dict with all the blocktimes as keys (None as values)
    blocktimes = get_timeblock_list(day, as_of_when=as_of_when)
    if not blocktimes:
        return {}
    blocks = {}
    timeblock_list = get_timeblock_list(day, as_of_when=as_of_when)
    for t in timeblock_list:
        blocks[t] = Block(t)
    # latest_time is the end of the latest block that interests us
    latest_time = block_end(max(timeblock_list))
    # Load check-ins & check-outs into the blocks to which they belong
    # This has to happen carefully, in the order in which they occurred,
    # thus processing as Events rather than reading check_ins & _outs
    events = Event.calc_events(day, as_of_when=as_of_when)
    for evtime in sorted(events.keys()):
        ev: Event
        ev = events[evtime]
        bstart = block_start(ev.event_time)
        blk: Block
        blk = blocks[bstart]
        if ev.event_time > latest_time:
            continue
        blk.ins_list += ev.bikes_in
        blk.outs_list += ev.bikes_out
        # Watch for highwater-mark *within* the block
        if ev.num_here_total > blk.max_here:
            blk.max_here = ev.num_here_total
            blk.max_here_list = ev.bikes_here
    # For each block, see what bikes are present at the end of the block
    # Use a set to be able to find the set difference (ie list that's here)
    here_set = set()
    for blk in blocks.values():
        blk.num_ins = len(blk.ins_list)
        blk.num_outs = len(blk.outs_list)
        here_set = (here_set | set(blk.ins_list)) - set(blk.outs_list)
        blk.here_list = here_set
        blk.num_here = len(here_set)
    # Calculate the ins/outs and bikes here categorized by regular/oversize.
    for blk in blocks.values():
        for tag in blk.ins_list:
            if tag in day.regular:
                blk.num_ins_regular += 1
            elif tag in day.oversize:
                blk.num_ins_oversize += 1
        for tag in blk.outs_list:
            if tag in day.regular:
                blk.num_outs_regular += 1
            elif tag in day.oversize:
                blk.num_outs_oversize += 1
        for tag in blk.here_list:
            if tag in day.regular:
                blk.num_here_regular += 1
            elif tag in day.oversize:
                blk.num_here_oversize += 1
        # Categorize the tag lists & counts at peak within the block
        for tag in blk.max_here_list:
            if tag in day.regular:
                blk.max_here_regular += 1
            elif tag in day.oversize:
                blk.max_here_oversize += 1

    return blocks
