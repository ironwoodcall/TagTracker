"""Convert spreadsheet csv file to tagtracker format.

This is a standalone script to convert one csv file into one
tagracker *.log file.
"""

import datetime
import sys
import os
import re
from typing import Union

BIKE_IN = "bike_in"
BIKE_OUT = "bike_out"
PARSE_TAG_RE = re.compile(r"^ *([a-z]+)([a-z])0*([0-9]+) *$")
WARNING_MSG = "Warning"
ERROR_MSG = "Error"
INFO_MSG = "Info"
# Record check ins/outs as this many minutes into the time block
BIKE_IN_OFFSET = 14
BIKE_OUT_OFFSET = 16
# Header lines to put in the logfile.
BIKE_IN_HEADER = 'Bikes checked in / tags out:'
BIKE_OUT_HEADER = 'Bikes checked out / tags in:'

messages = {}   # key=filename, value = list of messages

def convert_time(time_in:Union[str,int],
            as_number:bool=False) -> Union[str,int]:
    """Convert time (as str or int) to time (as str or int).

    If int time, it is minutes since midnight.
    Assumes that time values are legit (this will not check).
    """
    if isinstance(time_in,str) and not as_number:
        #print("converting from str to str")
        return isatime(time_in)
    if isinstance(time_in,int) and as_number:
        #print("converting from int to int")
        return time_in
    # We now know we are changing types.
    if as_number:
        # Convert str to int
        #print("converting from str to int")
        bits = time_in.split(':')
        #print(f"{bits=},{bits[0]=},{bits[1]=},{(bits[0]*60+bits[1])=}")
        return int(bits[0]) * 60 + int(bits[1])
    else:
        # Convert int to str
        #print("converting from int to str")
        h = time_in // 60
        m = time_in % 60
        return f"{h:02d}:{m:02d}"

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
    with open(file,"r") as f:
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
                if inout == BIKE_IN:
                    check_time = (convert_time(block_start,as_number=True)
                            + BIKE_IN_OFFSET)
                    #print(f"{block_start=},{convert_time(block_start,as_number=True)}")
                    #print(f"Check-in time for tag {tag} is {check_time}")
                    check_ins[tag] = convert_time(check_time,
                            as_number=False)
                elif inout == BIKE_OUT:
                    check_time = (convert_time(block_start,as_number=True)
                            + BIKE_OUT_OFFSET)
                    check_outs[tag] = convert_time(check_time,
                            as_number=False)
    return [this_date, dict(check_ins), dict(check_outs)]

def clean(file:str, check_ins:dict, check_outs:dict) -> None:
    """Remove bad tag records from the check_in/out dicts.

    Uses 'file' only as an arg to the messages function.
    """
    # Look for unmatched tags in check_ins
    bad_tags = []
    for tag in check_ins:
        if tag not in check_outs:
            message( file,f"Unmatched bike check-in {tag} (discarded) ", WARNING_MSG)
            bad_tags.append(tag)
    for tag in bad_tags:
        check_ins.pop(tag)
    # Same again for check_outs
    bad_tags = []
    for tag in check_outs:
        if tag not in check_ins:
            message( file,f"Unmatched bike check-out {tag} (discarded) ",
                    WARNING_MSG)
            bad_tags.append(tag)
    for tag in bad_tags:
        check_outs.pop(tag)

def write_file( oldfile:str, newfile:str, date:str,
        check_ins:dict, check_outs:dict ) ->None:
    """Write the records to a tagtracker-complians file."""
    with open(newfile, 'w') as f: # write stored lines to file
        f.write(f"# {date}\n")
        timestamp = datetime.datetime.today().strftime("%Y-%m-%d %H:%M")
        f.write(f"# Converted from {oldfile} on {timestamp}\n")
        if len(messages[oldfile]):
            f.write("# These issues detected during conversion:\n")
            for msg in messages[oldfile]:
                f.write(f"# {msg}\n")
        f.write(f"{BIKE_IN_HEADER}\n")
        for tag,time in check_ins.items():
            f.write(f"{tag},{time}\n")
        f.write(f"{BIKE_OUT_HEADER}\n")
        for tag,time in check_outs.items():
            f.write(f"{tag},{time}\n")

in_files = sys.argv[1:]
for oldfile in in_files:
    print( f"\nReading file {oldfile}...")
    (date, bikes_in, bikes_out) = readafile(oldfile)
    if not date:
        continue
    # Check for errors
    print("   ...checking for errors...")
    clean(oldfile, bikes_in, bikes_out)
    # Write the file
    newfile = f"cityhall_{date}.log"
    print(f"   ...writing tags to {newfile}")
    write_file(oldfile, newfile, date, bikes_in, bikes_out)
    print("   ...done")
