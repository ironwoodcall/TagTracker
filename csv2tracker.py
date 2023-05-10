"""Convert spreadsheet csv file to tagtracker format.

This is a standalone script to convert one csv file into one
tagracker *.log file.
"""

import os
import sys
import pathlib
import re

BIKE_IN = "bike_in"
BIKE_OUT = "bike_out"
PARSE_TAG_RE = re.compile(r"^ *([a-z]+)([a-z])0*([0-9]+) *$")
WARNING_MSG = "Warning"
ERROR_MSG = "Error"
INFO_MSG = "Info"

messages = {}   # key=filename, value = list of messages

def message( filename:str, msg_text:str, severity:str=INFO_MSG ) -> None:
    """Print (& save) warning for given filename."""
    global messages
    if filename not in messages:
        messages[filename] = []
    full_msg = f"# {severity}: {msg_text} in file {filename}"
    print(full_msg)
    if severity in [WARNING_MSG,ERROR_MSG]:
        messages[filename].append(full_msg)

def isadate( maybe:str ) -> str:
    """Return maybe as a YYYY-MM-DD date string if it looks like a date."""
    if re.match(r"^ *[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9] *$", maybe):
        return maybe.strip()
    else:
        return ""

def isatime( maybe:str) ->str:
    """Return maybe as a canonical HH:MM time (or "")."""
    if not (r := re.match(r"^ *([ 0-2][0-9]):([0-5][0-9])"),maybe):
        return ""
    bits = maybe.strip().split(":")
    if len(bits) < 2:
        return ""
    h=int(bits[0])
    m=int(bits[1])
    return f"{h:02d}:{m:02d}"

def isatag(maybe_tag:str) -> str:
    """Test maybe_tag as a tag, return it as canonical str (or "").

    Canonical tag id is a concatenation of
        tag_colour: 1+ lc letters representing the tag's colour,
                as defined in cfg.colour_letters
        tag_letter: 1 lc letter, the first character on the tag
        tag_number: a sequence number, without lead zeroes.
    """
    maybe_tag = maybe_tag.lower()
    if not bool(r := PARSE_TAG_RE.match(maybe_tag)):
        return []

    tag_colour = r.group(1)
    tag_letter = r.group(2)
    tag_number = r.group(3)
    tag_id = f"{tag_colour}{tag_letter}{tag_number}"

    return tag_id

in_files = sys.argv[1:]
for file in in_files:
    # File there?
    if not pathlib.Path.exists(file):
        message(file, "not found", ERROR_MSG)
        continue
    # Read one file.
    inout = ""
    this_date = ""
    check_ins = []
    check_outs = []
    lnum = 0
    with open(file,"r") as f:
        for line in f:
            lnum += 1
            chunks = line.strip().split(",")
            if not chunks:
                continue
            # Find the date -- must be above "check-in" and "check-out" lines.
            if not inout and isadate(chunks[0]):
                this_date = chunks[0]
            # Is this a "check-in" or "check-out" header line?
            if re.match(r"^Tag given out",chunks[0]):
                inout = BIKE_IN
            elif re.match(r"^Tag returned",chunks[0]):
                inout = BIKE_OUT
            # Ignore non-date junk at top of the file
            if not inout:
                continue
            # This line is a line of tags in a block (presumably).
            # Timeblocks might start in col 1 or col 2. (!!!!!)
            if not chunks[0]:
                chunks = chunks[1:]
            if not chunks:
                continue
            if not isatime(chunks[0]):
                message( file, f"ignoring line {lnum}: '{line}", WARNING_MSG)
                continue
            # Looks like a legit line.