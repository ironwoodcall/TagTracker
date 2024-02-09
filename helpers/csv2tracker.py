"""Convert spreadsheet csv file to tagtracker format.

This is a standalone script to convert one csv file into one
tagracker *.dat file.

This rejects any check-ins without check-outs... which makes it weird if
converting a partial-day's data.  Need to think about that.

Copyright (C) 2023 Julias Hocking

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

import datetime
import sys
import os
import re
import random

##from typing import Union
from tt_globals import *
import tt_util as ut
from typing import Tuple
from tt_tag import TagID
from tt_time import VTime


HEADER_VALET_DATE = "Valet date:"
HEADER_VALET_OPENS = "Valet opens:"
HEADER_VALET_CLOSES = "Valet closes:"

# If set, RANDOMIZE_TIMES will randomize times within their block.
# To keep things crazy simple, this assumes blocks are 30 minutes.
# This will also then make a second pass and arbitrarily make any
# stays that are therefore 0-length or longer to a random length between
# 10 - 30 minutes.
RANDOMIZE_TIMES = False
if RANDOMIZE_TIMES:
    print("WARNING: this is bogifying times slightly for demo purposes")

WARNING_MSG = "Warning"
ERROR_MSG = "Error"
INFO_MSG = "Info"
# Record check ins/outs as this many minutes into the time block
BIKE_IN_OFFSET = 14
BIKE_OUT_OFFSET = 16
# Header lines to put in the datafile.
BIKE_IN_HEADER = "Bikes checked in / tags out:"
BIKE_OUT_HEADER = "Bikes checked out / tags in:"

messages = {}  # key=filename, value = list of messages


def message(filename: str, msg_text: str, severity: str = INFO_MSG) -> None:
    """Print (& save) warning for given filename."""
    if filename not in messages:
        messages[filename] = []
    full_msg = f"{severity}: {msg_text.strip()} in file '{filename}'"
    print(full_msg)
    if severity in [WARNING_MSG, ERROR_MSG]:
        messages[filename].append(full_msg)


def isadate(maybe: str) -> str:
    """Return maybe as a YYYY-MM-DD date string if it looks like a date."""
    if re.match(r"^ *[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9] *$", maybe):
        return maybe.strip()
    else:
        return ""


def readafile(file: str) -> Tuple[dict, dict]:
    """Read one file's tags, return as check_ins, check_outs list."""
    # Read one file.
    inout = ""
    check_ins = {}
    check_outs = {}
    lnum = 0
    # File there?
    if not os.path.exists(file):
        message(file, "not found", ERROR_MSG)
        return ["", dict(), dict()]
    # Open & read the file.
    with open(file, "r", encoding="utf-8") as f:
        for line in f:
            lnum += 1
            line = line.strip()
            chunks = line.split(",")
            # Weirdness.  If it's today's tracking sheet, it seems to
            # include an extra blank column at the start.  So....
            # ... throw away a blank first column
            if chunks and not chunks[0]:
                chunks = chunks[1:]
            if not chunks:
                continue
            # Is this a "check-in" or "check-out" header line?
            if re.match(r"^Tag given out", chunks[0]):
                inout = BIKE_IN
                continue
            elif re.match(r"^Tag returned", chunks[0]):
                inout = BIKE_OUT
                continue
            # Ignore non-date junk at top of the file
            if not inout:
                continue
            # This line is a line of tags in a block (presumably).
            # Timeblocks might start in col 1 or col 2. (!!!!!)
            if not chunks[0]:
                chunks = chunks[1:]
            if not chunks:
                continue
            if not (block_start := VTime(chunks[0])):
                message(file, f"ignoring line {lnum}: '{line}", WARNING_MSG)
                continue
            # Looks like a legit line. Read the tags.
            # (The two cells after start time are "-" and end time.  Ignore.)
            for cell in chunks[3:]:
                if not cell:
                    continue  # Ignore empty cells
                if not (tag := TagID(cell)):
                    # Warn about poorly formed maybe-tags
                    message(
                        file,
                        f"Unrecognized tag '{cell}' in line {lnum}",
                        WARNING_MSG,
                    )
                    continue
                # A legit tag at a legit time.
                if RANDOMIZE_TIMES:
                    block_begin = ut.time_int(block_start)
                    check_time = random.randint(block_begin, block_begin + 29)
                else:
                    offset = (
                        BIKE_IN_OFFSET if inout == BIKE_IN else BIKE_OUT_OFFSET
                    )
                    check_time = ut.time_int(block_start) + offset
                if inout == BIKE_IN:
                    check_ins[tag] = VTime(check_time)
                elif inout == BIKE_OUT:
                    check_outs[tag] = VTime(check_time)
    return (dict(check_ins), dict(check_outs))


def clean(file: str, check_ins: dict, check_outs: dict) -> None:
    """Remove bad tag records from the check_in/out dicts.

    Uses 'file' only as an arg to the messages function.
    """
    # Look for unmatched tags in check_ins
    ##bad_tags = []
    ##for tag in check_ins:
    ##    if tag not in check_outs:
    ##        message( file,f"Unmatched bike check-in {tag} (retained) ", WARNING_MSG)
    ##        #bad_tags.append(tag)
    ##for tag in bad_tags:
    ##    check_ins.pop(tag)
    # Look for checkouts without checkins
    bad_tags = []
    for tag in check_outs:
        if tag not in check_ins:
            message(
                file,
                f"Unmatched bike check-out {tag} (discarded) ",
                WARNING_MSG,
            )
            bad_tags.append(tag)
    for tag in bad_tags:
        check_outs.pop(tag)
    # Look for checkins later than checkouts
    bad_tags = []
    for tag in check_outs:
        if RANDOMIZE_TIMES:
            if check_outs[tag] <= check_ins[tag]:
                check_outs[tag] = ut.time_str(
                    ut.time_int(check_ins[tag]) + random.randint(10, 30)
                )
        elif check_outs[tag] < check_ins[tag]:
            message(
                file,
                f"Check out before check in for {tag} (discarded) ",
                WARNING_MSG,
            )
            bad_tags.append(tag)
    for tag in bad_tags:
        check_outs.pop(tag)
        check_ins.pop(tag)


def write_file(
    oldf: str,
    newf: str,
    filedate: str,
    the_hours: tuple,
    check_ins: dict,
    check_outs: dict,
) -> None:
    """Write the records to a tagtracker-complians file."""
    with open(newf, "w", encoding="utf-8") as f:  # write stored lines to file
        f.write(f"# {filedate}\n")
        timestamp = datetime.datetime.today().strftime("%Y-%m-%d %H:%M")
        f.write(f"# Converted from {oldf} on {timestamp}\n")
        if oldf in messages and len(messages[oldf]):
            f.write("# These issues detected during conversion:\n")
            for msg in messages[oldf]:
                f.write(f"# {msg}\n")
        f.write(f"{HEADER_VALET_DATE} {filedate}\n")
        f.write(f"{HEADER_VALET_OPENS} {the_hours[0]}\n")
        f.write(f"{HEADER_VALET_CLOSES} {the_hours[1]}\n")
        f.write(f"{BIKE_IN_HEADER}\n")
        for tag, time in check_ins.items():
            f.write(f"{tag},{time}\n")
        f.write(f"{BIKE_OUT_HEADER}\n")
        for tag, time in check_outs.items():
            f.write(f"{tag},{time}\n")


def filename_to_date(filename: str) -> str:
    """Convert filename to a string of the day *before* the filename."""
    # Assumes filenames are YYYY-MM-DD.csv

    bits = re.search(r"(2023-[0-9][0-9]-[0-9][0-9])", filename)
    if not bits:
        return ""
    date_string = bits.group(1)
    this_day = datetime.datetime.strptime(date_string, "%Y-%m-%d")
    prev_day = this_day - datetime.timedelta(1)
    return datetime.datetime.strftime(prev_day, "%Y-%m-%d")


def valet_hours(the_date: str) -> Tuple[VTime, VTime]:
    """Report what time the valet opened this the_date."""
    day = datetime.datetime.strptime(the_date, "%Y-%m-%d")
    day_of_week = datetime.datetime.weekday(day)  # 0..6
    spring = {
        0: ("10:00", "17:00"),  # sunday
        1: ("07:30", "18:00"),
        2: ("07:30", "18:00"),
        3: ("07:30", "18:00"),
        4: ("07:30", "18:00"),
        5: ("07:30", "20:00"),
        6: ("10:00", "18:00"),
    }
    summer = {  # summer hours start May 1
        0: ("10:00", "17:00"),  # sunday
        1: ("07:30", "18:00"),
        2: ("07:30", "18:00"),
        3: ("07:30", "20:00"),
        4: ("07:30", "20:00"),
        5: ("07:30", "22:00"),
        6: ("10:00", "12:00"),
    }
    if the_date == "2023-06-11":  # Unknown special day
        return ("10:00", "18:30")
    elif the_date == "2023-05-22":  # Victoria Day
        return ("09:00", "17:00")
    elif the_date >= "2023-05-01":
        return summer[day_of_week]
    elif the_date >= "2023-03-17":  # opening day
        return spring[day_of_week]
    else:
        return ("", "")


in_files = sys.argv[1:]
for oldfile in in_files:
    # Data's date is the day before the day represented by the filename
    # (I mean really.... !!!!????)
    date = filename_to_date(oldfile)
    if not date:
        print(f"Error: can not determine date from filename {oldfile}")
        continue
    hours = valet_hours(date)
    if not hours[0]:
        print(f"Error: have no hours known for {date}")
    print(f"\nReading file {oldfile}, data for {date}...")
    (bikes_in, bikes_out) = readafile(oldfile)
    # Check for errors
    print("   ...checking for errors...")
    clean(oldfile, bikes_in, bikes_out)
    # Write the file
    newfile = f"cityhall_{date}.dat"
    print(f"   ...writing tags to {newfile}")
    write_file(oldfile, newfile, date, hours, bikes_in, bikes_out)
    print("   ...done")
