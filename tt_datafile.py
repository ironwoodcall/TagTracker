"""Functions to save and retrieve data (OldTrackerDay objects) in datafiles.

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

    Datafiles (datafiles) contain a full day's tracker data.
    It is made of both
        key:value lines (for valet date, opening and closing time)
        header/list sections (for tag lists and events):
        Anything following comments (#) is ignored, as are blank lines and
            lead/trailing whitespace

"""

# import os
import re

# import tempfile

import common.tt_constants as k
from common.tt_tag import TagID
from common.tt_time import VTime
import common.tt_util as ut
from common.tt_trackerday import OldTrackerDay
import client_base_config as cfg

# Header strings to use in datafile and tags- config file
# These are used when writing & also for string-matching when reading.
HEADER_BIKES_IN = "Bikes checked in / tags out:"
HEADER_BIKES_OUT = "Bikes checked out / tags in:"
HEADER_DATE = "Date:"
HEADER_OPENS = "Opens:"
HEADER_CLOSES = "Closes:"
HEADER_OLD_DATE = "Valet date:"  # For back-compatibility
HEADER_OLD_OPENS = "Valet opens:"  # For back-compatibility
HEADER_OLD_CLOSES = "Valet closes:"  # For back-compatibility
HEADER_OVERSIZE = "Oversize-bike tags:"
HEADER_REGULAR = "Regular-bike tags:"
HEADER_RETIRED = "Retired tags:"
HEADER_COLOURS = "Colour codes:"
HEADER_NOTES = "Notes:"
HEADER_REGISTRATIONS = "Registrations:"

def datafile_name(folder: str, whatdate: str = "today") -> str:
    """Return the name of the data file (datafile) to read/write."""
    # Use default filename
    date = ut.date_str(whatdate)
    if not date:
        return ""
    return f"{folder}/{cfg.DATA_BASENAME}{date}.json"




def _read_time_or_date(
    line: str,
    data: OldTrackerDay,
    err_count: int,
    err_msgs: list[str],
    filename: str,
    line_num: int,
    header: str,
    val: k.MaybeDate | k.MaybeTime,
) -> int:
    """
    Process a time or date section.

    Parameters:
        - line: The current line being processed.
        - data: The OldTrackerDay object to update with the processed data.
        - err_msgs: A list to which any error messages will be appended.
        - filename: The name of the file being processed.
        - line_num: The line number of the current line.
        - header: The header string for the section being processed.
        - val: The value that follows the header on that line

    Returns:
        The number of errors encountered during processing.
    """
    # Extract information from the line based on the header
    r = re.match(rf"{header} *(.+)", line)
    if not r:
        return _read_error_msg(
            f"Unable to interpret {header}",
            err_msgs,
            errs=err_count,
            fname=filename,
            fline=line_num,
        )

    # Process based on the header type
    if header in [HEADER_DATE, HEADER_OLD_DATE]:
        # Read the datafile's date and update data.date
        maybedate = ut.date_str(val)
        if not maybedate:
            return _read_error_msg(
                f"Unable to interpret '{val}' as a date",
                message_list=err_msgs,
                errs=err_count,
                fname=filename,
                fline=line_num,
            )
        data.date = maybedate
    elif header in [HEADER_OPENS, HEADER_CLOSES, HEADER_OLD_OPENS, HEADER_OLD_CLOSES]:
        # This is an open or a close time (probably)
        maybetime = VTime(val)
        if not maybetime:
            return _read_error_msg(
                f"Unable to interpret '{val}' as a time",
                message_list=err_msgs,
                errs=err_count,
                fname=filename,
                fline=line_num,
            )
        if header in [HEADER_OPENS, HEADER_OLD_OPENS]:
            data.time_open = maybetime
        else:
            data.time_closed = maybetime
    else:
        ut.squawk(f"Unexpected unrecognition of header {header} line {line_num}")
        return err_count + 1

    return err_count


def _read_error_msg(
    text: str,
    message_list: list[str],
    errs: int = 0,
    fname: str = "",
    fline: int = None,
) -> int:
    """Print a datafile read error, increments error counter.

    This returns the incremented error counter.  Ugh.
    Also, if this is the first error (errors_before is None or 0)
    then this makes an initial print() on the assumptino that the
    immediately preceding print() statement had end="".
    """
    text = f" {text}"
    if fline:
        text = f"{fline}:{text}"
    if fname:
        text = f"{fname}:{text}"
    message_list.append(text)
    return errs + 1


def read_datafile(
    filename: str, err_msgs: list[str], usable_tags: list[TagID] = None
) -> OldTrackerDay:
    """Fetch tag data from file into a OldTrackerDay object.

    Read data from a pre-existing data file, returns the info in a
    OldTrackerDay object.  If no file, OldTrackerDay will be mostly blank.

    err_msgs is the (presumably empty) list, to which any error messages
    will be appended.  If no messages are added, then it means this
    ran without error.

    usable_tags is a list of tags that can be used; if a tag is not in the
    list then it's an error.  If usable_tags is empty or None then no
    checking takes place.
    """

    data = OldTrackerDay()
    errors = 0  # How many errors found reading datafile?
    section = None
    with open(filename, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            # ignore blank or # comment lines
            line = re.sub(r"\s*#.*", "", line)
            line = line.strip()
            if not line:
                continue
            # Look for section headers to figure out what section we will process
            if re.match(rf"^ *{HEADER_BIKES_IN}", line):
                section = k.BIKE_IN
                continue
            elif re.match(rf"^ *{HEADER_BIKES_OUT}", line):
                section = k.BIKE_OUT
                continue
            # Look for headers for oversize & regular bikes, ignore them.
            elif re.match(rf"^ *{HEADER_REGULAR}", line):
                section = k.REGULAR
                continue
            elif re.match(rf"^ *{HEADER_OVERSIZE}", line):
                section = k.OVERSIZE
                continue
            elif re.match(rf"^ *{HEADER_RETIRED}", line):
                section = k.RETIRED
                continue
            elif re.match(rf"^ *{HEADER_COLOURS}", line):
                section = k.COLOURS
                continue
            elif re.match(rf"^ *{HEADER_NOTES}", line):
                section = k.NOTES
                continue
            elif re.match(rf"^ *{HEADER_REGISTRATIONS}", line):
                # Read the number of registrations
                section = k.NOT_A_LIST
                r = re.match(rf"{HEADER_REGISTRATIONS} *(.+)", line)
                try:
                    data.registrations = int(r.group(1))
                except ValueError:
                    errors = _read_error_msg(
                        "Unable to read registrations value",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                if data.registrations < 0:
                    errors = _read_error_msg(
                        "Registrations value < 0",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                continue

            elif r := re.match(
                rf"({HEADER_OPENS}|{HEADER_CLOSES}|{HEADER_DATE}"
                rf"|{HEADER_OLD_OPENS}|{HEADER_OLD_CLOSES}|{HEADER_OLD_DATE})"
                r"\s+(.+)",
                line,
            ):
                # This is a time or date (probably)
                section = k.NOT_A_LIST
                errors = _read_time_or_date(
                    line=line,
                    data=data,
                    err_msgs=err_msgs,
                    err_count=errors,
                    filename=filename,
                    line_num=line_num,
                    header=r.group(1),
                    val=r.group(2),
                )

            # Can do nothing unless we know what section we're in
            if section is None:
                errors = _read_error_msg(
                    f"Unexpected unintelligibility in line '{line}'",
                    err_msgs,
                    errs=errors,
                    fname=filename,
                    fline=line_num,
                )
                continue

            if section == k.NOT_A_LIST:
                # IUgnore anything htat is not a list section
                continue

            if section == k.NOTES:
                # Read operator notes
                data.notes.append(line)
                continue

            if section == k.COLOURS:
                # Ignore the colour dictionary
                continue

            if section in [k.REGULAR, k.OVERSIZE, k.RETIRED]:
                # Break each line into 0 or more tags
                bits = ut.splitline(line)
                taglist = [TagID(x) for x in bits]
                taglist = [x for x in taglist if x]  # remove blanks
                # Any errors?
                if len(taglist) != len(bits):
                    errors = _read_error_msg(
                        f"Bad tag(s) in '{line}",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                # Looks like we have some tags
                if section == k.REGULAR:
                    data.regular |= set(taglist)
                elif section == k.OVERSIZE:
                    data.oversize |= set(taglist)
                elif section == k.RETIRED:
                    data.retired |= set(taglist)
                else:
                    ut.squawk(f"Bad section value in read_datafile(), '{section}")
                    return
                continue

            if section not in [k.BIKE_IN, k.BIKE_OUT]:
                ut.squawk(f"Bad section value in read_datafile(), '{section}")
                return

            # This is a tags in or tags out section
            # Break into putative tag and text, looking for errors
            cells = line.split(",")
            if len(cells) != 2:
                errors = _read_error_msg(
                    "Bad line in file",
                    err_msgs,
                    errs=errors,
                    fname=filename,
                    fline=line_num,
                )
                continue
            this_tag = TagID(cells[0])
            if not this_tag:
                errors = _read_error_msg(
                    "String does not appear to be a tag",
                    err_msgs,
                    errs=errors,
                    fname=filename,
                    fline=line_num,
                )
                continue
            if usable_tags and this_tag not in usable_tags:
                errors = _read_error_msg(
                    f"Tag '{this_tag}' not in use",
                    err_msgs,
                    errs=errors,
                    fname=filename,
                    fline=line_num,
                )
                continue
            this_time = VTime(cells[1])
            if not this_time:
                errors = _read_error_msg(
                    "Poorly formed time value",
                    err_msgs,
                    errs=errors,
                    fname=filename,
                    fline=line_num,
                )
                continue
            # Maybe add to data.bikes_in or data.bikes_out structures.
            if section == k.BIKE_IN:
                # Maybe add to check_in structure
                if this_tag in data.bikes_in:
                    errors = _read_error_msg(
                        f"Duplicate {this_tag} check-in",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                if this_tag in data.bikes_out and data.bikes_out[this_tag] < this_time:
                    errors = _read_error_msg(
                        f"Tag {this_tag} check out before check-in",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                data.bikes_in[this_tag] = this_time
            elif section == k.BIKE_OUT:
                if this_tag in data.bikes_out:
                    errors = _read_error_msg(
                        f"Duplicate {this_tag} check-out",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                if this_tag not in data.bikes_in:
                    errors = _read_error_msg(
                        f"Tag {this_tag} checked out but not in",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                if this_tag in data.bikes_in and data.bikes_in[this_tag] > this_time:
                    errors = _read_error_msg(
                        f"Tag {this_tag} check out before check-in",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                data.bikes_out[this_tag] = this_time
            else:
                ut.squawk("PROGRAM ERROR: should not reach this code spot")
                errors += 1
                continue

    if errors:
        err_msgs.append(f"Found {errors} errors in datafile {filename}")

    # Return today's working data.
    return data


# def prep_datafile_info(data: OldTrackerDay) -> list[str]:
#     """Prepare a list of lines to write to the datafile."""
#     lines = []
#     lines.append(
#         "# TagTracker datafile (data file) created on "
#         f"{ut.date_str('today')} {VTime('now')}"
#     )
#     lines.append(f"# TagTracker version {ut.get_version()}")
#     # For convenience, show # of leftovers & latest event
#     if data.bikes_in:
#         latest_event = max(list(data.bikes_in.values()) + list(data.bikes_out.values()))
#         leftovers = len(data.bikes_in) - len(data.bikes_out)
#         lines.append(f"# {leftovers} bikes left as of {latest_event}")
#     else:
#         lines.append("# No bikes")
#     # Date, opening & closing hours
#     if data.date:
#         lines.append(f"{HEADER_DATE} {data.date}")
#     if data.time_open:
#         lines.append(f"{HEADER_OPENS} {data.time_open}")
#     if data.time_closed:
#         lines.append(f"{HEADER_CLOSES} {data.time_closed}")
#     if data.registrations:
#         lines.append(f"{HEADER_REGISTRATIONS} {data.registrations}")

#     lines.append(HEADER_BIKES_IN)
#     for tag, atime in data.bikes_in.items():  # for each bike checked in
#         lines.append(f"{tag.canon},{atime}")  # add a line "tag,time"
#     lines.append(HEADER_BIKES_OUT)
#     for tag, atime in data.bikes_out.items():  # for each  checked
#         lines.append(f"{tag.canon},{atime}")  # add a line "tag,time"
#     # Save any operator notes.
#     lines.append(HEADER_NOTES)
#     lines.extend(data.notes)
#     # Also write tag info of which bikes are oversize, which are regular.
#     # This to make complete bundles for historic information
#     lines.append("# Following sections are context for the check-ins/outs")
#     lines.append(HEADER_REGULAR)
#     for group in ut.taglists_by_prefix(data.regular):
#         lines.append(" ".join(group).lower())
#     lines.append(HEADER_OVERSIZE)
#     for group in ut.taglists_by_prefix(data.oversize):
#         lines.append(" ".join(group).lower())
#     lines.append(HEADER_RETIRED)
#     lines.append(" ".join(data.retired).lower())
#     lines.append("# Normal end of file")
#     return lines


# def write_datafile_old(filename: str, data: OldTrackerDay) -> bool:
#     """Write current data to today's data file.

#     Return True if succeeded, False if failed.
#     """
#     lines = prep_datafile_info(data)
#     # Write the data to the file.
#     try:
#         with open(filename, "w", encoding="utf-8") as f:  # write stored lines to file
#             for line in lines:
#                 f.write(line)
#                 f.write("\n")
#     except OSError:
#         ut.squawk(f"PROBLEM: Unable to create datafile '{filename}'")
#         return False
#     return True


# def write_datafile(datafile: str, content: list[str], make_bak: bool) -> bool:
#     """Write 'content' to datafile, possibly saving old as .bak.

#     On entry:
#         datafile is the filepath of the current datafile, which might exist
#         content is a list of strings that are the content to write
#         make_bak, if True, make the existing datafile '.bak'

#     To avoid a "Invalid cross-device link" error, make the tmp file
#     inthe same folder as the datafile will be.
#     """

#     # Write the content to a temporary file
#     temp_filename = f"{datafile}.tmp"
#     try:
#         with open(temp_filename, mode="w", encoding="utf-8") as temp_file:
#             for line in content:
#                 temp_file.write(line)
#                 temp_file.write("\n")
#     except OSError as e:
#         ut.squawk(
#             f"PROBLEM: Unable to create temporary datafile '{temp_filename}': {e}"
#         )
#         return False

#     # If datafile already exists and making .bak, change it to .bak
#     if make_bak and os.path.exists(datafile):
#         try:
#             os.replace(datafile, f"{datafile}.bak")
#         except OSError as e:
#             ut.squawk(f"PROBLEM: Unable to change '{datafile}' to .bak: {e}")
#             return False

#     # Rename the temp file to the datafile name
#     try:
#         os.replace(temp_filename, datafile)
#     except OSError as e:
#         ut.squawk(f"PROBLEM: Unable to change '{temp_filename}'to '{datafile}': {e}")
#         return False

#     # Success
#     return True
