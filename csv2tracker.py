"""Convert spreadsheet csv file to tagtracker format.

This is a standalone script to convert one csv file into one
tagracker *.dat file.

This rejects any check-ins without check-outs... which makes it weird if
converting a partial-day's data.  Need to think about that.
"""

import datetime
import sys
import os
import re
import random
##from typing import Union
from tt_globals import *
import tt_util as ut


# If set, RANDOMIZE_TIMES will randomize times within their block.
# To keep things crazy simple, this assumes blocks are 30 minutes.
# This will also then make a second pass and arbitrarily make any
# stays that are therefore 0-length or longer to a random length between
# 10 - 30 minutes.
RANDOMIZE_TIMES = False
if RANDOMIZE_TIMES:
    print( "WARNING: this is bogifying times slightly for demo purposes")

WARNING_MSG = "Warning"
ERROR_MSG = "Error"
INFO_MSG = "Info"
# Record check ins/outs as this many minutes into the time block
BIKE_IN_OFFSET = 14
BIKE_OUT_OFFSET = 16
# Header lines to put in the datafile.
BIKE_IN_HEADER = 'Bikes checked in / tags out:'
BIKE_OUT_HEADER = 'Bikes checked out / tags in:'

messages = {}   # key=filename, value = list of messages

def message( filename:str, msg_text:str, severity:str=INFO_MSG ) -> None:
    """Print (& save) warning for given filename."""
    if filename not in messages:
        messages[filename] = []
    full_msg = f"{severity}: {msg_text.strip()} in file '{filename}'"
    print(full_msg)
    if severity in [WARNING_MSG,ERROR_MSG]:
        messages[filename].append(full_msg)

def isadate(maybe:str ) -> str:
    """Return maybe as a YYYY-MM-DD date string if it looks like a date."""
    if re.match(r"^ *[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9] *$", maybe):
        return maybe.strip()
    else:
        return ""

def isatime(maybe:str) ->str:
    """Return maybe as a canonical HH:MM time (or "")."""
    if not (re.match(r"^ *([0-2]?[0-9]):([0-5][0-9])", maybe)):
        return ""
    bits = maybe.strip().split(":")
    if len(bits) < 2:
        return ""
    h=int(bits[0])
    m=int(bits[1])
    return f"{h:02d}:{m:02d}"

def isatag(maybe:str) -> str:
    """Test maybe as a tag, return it as canonical str (or "").

    Canonical tag id is a concatenation of
        tag_colour: 1+ lc letters representing the tag's colour,
                as defined in cfg.colour_letters
        tag_letter: 1 lc letter, the first character on the tag
        tag_number: a sequence number, without lead zeroes.
    """
    maybe = maybe.lower()
    if not bool(r := PARSE_TAG_RE.match(maybe)):
        return []

    tag_colour = r.group(1)
    tag_letter = r.group(2)
    tag_number = r.group(3)
    tag_id = f"{tag_colour}{tag_letter}{tag_number}"

    return tag_id

def readafile( file:str ) -> list[str, dict,dict]:
    """Read one file's tags, return as date, check_ins, check_outs list."""
    # Read one file.
    inout = ""
    this_date = ""
    check_ins = {}
    check_outs = {}
    lnum = 0
    # File there?
    if not os.path.exists(file):
        message(file, "not found", ERROR_MSG)
        return ["",dict(), dict()]
    # Open & read the file.
    with open(file,"r",encoding='utf-8') as f:
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
            # Find the date -- must be above "check-in" and "check-out" lines.
            if not inout and isadate(chunks[0]):
                this_date = chunks[0]
            # Is this a "check-in" or "check-out" header line?
            if re.match(r"^Tag given out",chunks[0]):
                inout = BIKE_IN
                continue
            elif re.match(r"^Tag returned",chunks[0]):
                inout = BIKE_OUT
                continue
            # Ignore non-date junk at top of the file
            if not inout:
                continue
            # We should have a date by now.
            if not this_date:
                message(file,"Found no date",ERROR_MSG)
                return ["",dict(),dict()]
            # This line is a line of tags in a block (presumably).
            # Timeblocks might start in col 1 or col 2. (!!!!!)
            if not chunks[0]:
                chunks = chunks[1:]
            if not chunks:
                continue
            if not (block_start := isatime(chunks[0])):
                message( file, f"ignoring line {lnum}: '{line}", WARNING_MSG)
                continue
            # Looks like a legit line. Read the tags.
            # (The two cells after start time are "-" and end time.  Ignore.)
            for cell in chunks[3:]:
                if not cell:
                    continue    # Ignore empty cells
                if not (tag := isatag(cell)):
                    # Warn about poorly formed maybe-tags
                    message(file,f"Unrecognized tag '{cell}' in line {lnum}",
                            WARNING_MSG)
                    continue
                # A legit tag at a legit time.
                if RANDOMIZE_TIMES:
                    block_begin = ut.time_int(block_start)
                    check_time = random.randint(block_begin,block_begin+29)
                else:
                    offset = BIKE_IN_OFFSET if inout == BIKE_IN else BIKE_OUT_OFFSET
                    check_time = (ut.time_int(block_start)
                            + offset)
                if inout == BIKE_IN:
                    check_ins[tag] = ut.time_str(check_time)
                elif inout == BIKE_OUT:
                    check_outs[tag] = ut.time_str(check_time)
    return [this_date, dict(check_ins), dict(check_outs)]

def clean(file:str, check_ins:dict, check_outs:dict) -> None:
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
            message( file,f"Unmatched bike check-out {tag} (discarded) ",
                    WARNING_MSG)
            bad_tags.append(tag)
    for tag in bad_tags:
        check_outs.pop(tag)
    # Look for checkins later than checkouts
    bad_tags = []
    for tag in check_outs:
        if RANDOMIZE_TIMES:
            if check_outs[tag] <= check_ins[tag]:
                check_outs[tag] = ut.time_str(
                    ut.time_int(check_ins[tag])
                    + random.randint(10,30))
        elif check_outs[tag] < check_ins[tag]:
            message( file,f"Check out before check in for {tag} (discarded) ",
                    WARNING_MSG)
            bad_tags.append(tag)
    for tag in bad_tags:
        check_outs.pop(tag)
        check_ins.pop(tag)

def write_file(oldf:str, newf:str, filedate:str,
        check_ins:dict, check_outs:dict ) ->None:
    """Write the records to a tagtracker-complians file."""
    with open(newf , 'w',encoding='utf-8') as f: # write stored lines to file
        f.write(f"# {filedate}\n")
        timestamp = datetime.datetime.today().strftime("%Y-%m-%d %H:%M")
        f.write(f"# Converted from {oldf} on {timestamp}\n")
        if  oldf  in messages and len(messages[oldf]):
            f.write("# These issues detected during conversion:\n")
            for msg in messages[ oldf ]:
                f.write(f"# {msg}\n")
        f.write(f"{BIKE_IN_HEADER}\n")
        for tag,time in check_ins.items():
            f.write(f"{tag},{time}\n")
        f.write(f"{BIKE_OUT_HEADER}\n")
        for tag,time in check_outs.items():
            f.write(f"{tag},{time}\n")

def filename_to_date(filename:str) -> str:
    """Convert filename to a string of the day *before* the filename."""
    # Assumes filenames are YYYY-MM-DD.csv

    bits = re.search(r"2023-([0-9][0-9])-([0-9][0-9])",filename)
    if not bits:
        return ""
    year = "2023"
    month = bits.group(1)
    day = bits.group(2)


in_files = sys.argv[1:]
for oldfile in in_files:
    print( f"\nReading file {oldfile}...")
    # Data's date is the day before the day represented by the filename
    # (I mean really.... !!!!????)

    (date, bikes_in, bikes_out) = readafile(oldfile)
    if not date:
        continue
    # Check for errors
    print("   ...checking for errors...")
    clean(oldfile, bikes_in, bikes_out)
    # Write the file
    newfile = f"cityhall_{date}.dat"
    print(f"   ...writing tags to {newfile}")
    write_file(oldfile, newfile, date, bikes_in, bikes_out)
    print("   ...done")
