"""TagTracker by Julias Hocking.

Block class to help with reporting in the TagTracker suite.

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
import tt_trackerday
import tt_event

class Block:
    """Class to help with reporting.

    Each instance is a timeblock of duration cfg.BLOCK_DURATION.
    """

    def __init__(self, start_time: Union[ut.Time, int]) -> None:
        """Initialize. Assumes that start_time is valid."""
        if isinstance(start_time, str):
            self.start = ut.time_str(start_time)
        else:
            self.start = ut.time_str(start_time)
        self.ins_list = []  # Tags of bikes that came in.
        self.num_ins = 0  # Number of bikes that came in.
        self.num_ins_regular = 0
        self.num_ins_oversize = 0
        self.outs_list = []  # Tags of bikes returned out.
        self.num_outs = 0  # Number of bikes that went out.
        self.num_outs_regular = 0
        self.num_outs_oversize = 0
        self.here_list = []  # Tags of bikes in valet at end of block.
        self.num_here = 0  # Number of bikes in valet at end of block.
        self.num_here_regular = 0
        self.num_here_oversize = 0
        self.max_here_list = [] # Tags at time max bikes here during the block
        self.max_here = 0 # Mxx number of bikes here any time in this block
        self.max_here_regular = 0
        self.max_here_oversize = 0

def block_start(
    atime: Union[int, ut.Time], as_number: bool = False
) -> Union[ut.Time, int]:
    """Return the start time of the block that contains time 'atime'.

    'atime' can be minutes since midnight or HHMM.
    Returns HHMM unless as_number is True, in which case returns int.
    """
    # Get time in minutes
    atime = ut.time_int(atime) if isinstance(atime, str) else atime
    # which block of time does it fall in?
    block_start_min = (atime // BLOCK_DURATION) * BLOCK_DURATION
    if as_number:
        return block_start_min
    return ut.time_str(block_start_min)


def block_end(
    atime: Union[int, ut.Time], as_number: bool = False
) -> Union[ut.Time, int]:
    """Return the last minute of the timeblock that contains time 'atime'.

    'atime' can be minutes since midnight or HHMM.
    Returns HHMM unless as_number is True, in which case returns int.
    """
    # Get block start
    start = block_start(atime, as_number=True)
    # Calculate block end
    end = start + BLOCK_DURATION - 1
    # Return as minutes or HHMM
    if as_number:
        return end
    return ut.time_str(end)


def get_timeblock_list(
    day: tt_trackerday.TrackerDay, as_of_when: ut.Time
) -> list[ut.Time]:
    """Build a list of timeblocks from beg of day until as_of_when.

    Latest block of the day will be the latest timeblock that
    had any transactions at or before as_of_when.
    """
    as_of_when = as_of_when if as_of_when else ut.get_time()
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
    min_block_min = block_start(min(transx), as_number=True)
    max_block_min = block_start(max(transx), as_number=True)
    # Create list of timeblocks for the the whole day.
    timeblocks = []
    for t in range(min_block_min, max_block_min + BLOCK_DURATION, BLOCK_DURATION):
        timeblocks.append(ut.time_str(t))
    return timeblocks


def calc_blocks(
    day: tt_trackerday.TrackerDay, as_of_when: ut.Time = None
) -> dict[ut.Time, object]:
    """Create a dictionary of Blocks {start:Block} for whole day."""
    if not as_of_when:
        as_of_when = day.latest_event("24:00")
        if as_of_when < day.closing_time:
            as_of_when = day.closing_time
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
    latest_time = block_end(max(timeblock_list), as_number=False)
    # Load check-ins & check-outs into the blocks to which they belong
    # This has to happen carefully, in the order in which they occurred,
    # thus processing as Events rather than reading check_ins & _outs
    events = tt_event.calc_events(day,as_of_when=as_of_when)
    for evtime in sorted(events.keys()):
        ev:tt_event.Event
        ev = events[evtime]
        bstart = block_start(ev.event_time)
        blk:Block
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

'''
    for tag, atime in day.bikes_in.items():
        if atime > latest_time:
            continue
        bstart = block_start(atime)
        blocks[bstart].ins_list += [tag]
    for tag, atime in day.bikes_out.items():
        if atime > latest_time:
            continue
        bstart = block_start(atime)
        blocks[bstart].outs_list += [tag]
    # For each block, see what bikes are present at some time in the block.
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


    return blocks
'''