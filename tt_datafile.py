"""TagTracker by Julias Hocking.

Functions to save and retrieve data (TrackerDay objects) in datafiles.

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

    Datafiles (logfiles) contain a full day's tracker data.
    It is made of both
        key:value lines (for valet date, opening and closing time)
        header/list sections (for tag lists and events):
        Anything following comments (#) is ignored, as are blank lines and
            lead/trailing whitespace

"""
import os

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
import tt_util as ut
import tt_trackerday

# Header strings to use in logfile and tags- config file
# These are used when writing & also for string-matching when reading.
HEADER_BIKES_IN = "Bikes checked in / tags out:"
HEADER_BIKES_OUT = "Bikes checked out / tags in:"
HEADER_VALET_DATE = "Valet date:"
HEADER_VALET_OPENS = "Valet opens:"
HEADER_VALET_CLOSES = "Valet closes:"
HEADER_OVERSIZE = "Oversize-bike tags:"
HEADER_REGULAR = "Regular-bike tags:"
HEADER_RETIRED = "Retired tags:"
HEADER_COLOURS = "Colour codes:"


def rotate_log(filename: str) -> None:
    """Rename the current logfile to <itself>.bak."""
    backuppath = f"{filename}.bak"
    if os.path.exists(backuppath):
        os.unlink(backuppath)
    if os.path.exists(filename):
        os.rename(filename, backuppath)
    return None


def read_logfile(
    filename: str, err_msgs: list[str], usable_tags: list[Tag] = None
) -> tt_trackerday.TrackerDay:
    """Fetch tag data from file into a TrackerDay object.

    Read data from a pre-existing data file, returns the info in a
    TrackerDay object.  If no file, TrackerDay will be mostly blank.

    err_msgs is the (presumably empty) list, to which any error messages
    will be appended.  If no messages are added, then it means this
    ran without error.

    usable_tags is a list of tags that can be used; if a tag is not in the
    list then it's an error.  If usable_tags is empty or None then no
    checking takes place.

    """

    def data_read_error(
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

    data = tt_trackerday.TrackerDay()
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
                section = BIKE_IN
                continue
            elif re.match(rf"^ *{HEADER_BIKES_OUT}", line):
                section = BIKE_OUT
                continue
            # Look for headers for oversize & regular bikes, ignore them.
            elif re.match(rf"^ *{HEADER_REGULAR}", line):
                section = REGULAR
                continue
            elif re.match(rf"^ *{HEADER_OVERSIZE}", line):
                section = OVERSIZE
                continue
            elif re.match(rf"^ *{HEADER_RETIRED}", line):
                section = RETIRED
                continue
            elif re.match(rf"^ *{HEADER_COLOURS}", line):
                section = COLOURS
                continue
            elif re.match(rf"^ *{HEADER_VALET_DATE}", line):
                # Read the logfile's date
                section = IGNORE
                r = re.match(rf"{HEADER_VALET_DATE} *(.+)", line)
                maybedate = ut.date_str(r.group(1))
                if not maybedate:
                    errors = data_read_error(
                        "Unable to read valet date",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                data.date = maybedate
                continue
            elif re.match(rf"({HEADER_VALET_OPENS}|{HEADER_VALET_CLOSES})", line):
                # This is an open or a close time (probably)
                section = IGNORE
                r = re.match(
                    rf"({HEADER_VALET_OPENS}|{HEADER_VALET_CLOSES}) *(.+)", line
                )
                maybetime = ut.time_str(r.group(2))
                if not maybetime:
                    errors = data_read_error(
                        "Unable to read valet open/close time",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                if r.group(1) == HEADER_VALET_OPENS:
                    data.opening_time = maybetime
                else:
                    data.closing_time = maybetime
                continue
            # Can do nothing unless we know what section we're in
            if section is None:
                errors = data_read_error(
                    "Unexpected unintelligibility in line",
                    err_msgs,
                    errs=errors,
                    fname=filename,
                    fline=line_num,
                )
                continue

            if section == IGNORE:
                # Things to ignore
                continue

            if section == COLOURS:
                # Read the colour dictionary
                bits = ut.splitline(line)
                if len(bits) < 2:
                    errors = data_read_error(
                        f"Bad colour code '{line}",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                if bits[0] in data.colour_letters:
                    errors = data_read_error(
                        f"Duplicate colour code '{bits[0]}",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                data.colour_letters[bits[0]] = " ".join(bits[1:])
                continue

            if section in [REGULAR, OVERSIZE, RETIRED]:
                # Break each line into 0 or more tags
                bits = ut.splitline(line)
                taglist = [ut.fix_tag(x,uppercase=False) for x in bits]
                taglist = [x for x in taglist if x]  # remove blanks
                # Any errors?
                if len(taglist) != len(bits):
                    errors = data_read_error(
                        f"Bad tag(s) in '{line}",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                # Looks like we have some tags
                if section == REGULAR:
                    data.regular += taglist
                elif section == OVERSIZE:
                    data.oversize += taglist
                elif section == RETIRED:
                    data.retired += taglist
                else:
                    ut.squawk(f"Bad section value in read_logfile(), '{section}")
                    return
                continue

            if section not in [BIKE_IN, BIKE_OUT]:
                ut.squawk(f"Bad section value in read_logfile(), '{section}")
                return

            # This is a tags in or tags out section
            # Break into putative tag and text, looking for errors
            cells = line.split(",")
            if len(cells) != 2:
                errors = data_read_error(
                    "Bad line in file",
                    err_msgs,
                    errs=errors,
                    fname=filename,
                    fline=line_num,
                )
                continue
            this_tag = ut.fix_tag(cells[0],uppercase=False)
            if not (this_tag):
                errors = data_read_error(
                    "String does not appear to be a tag",
                    err_msgs,
                    errs=errors,
                    fname=filename,
                    fline=line_num,
                )
                continue
            if usable_tags and this_tag not in usable_tags:
                errors = data_read_error(
                    f"Tag '{this_tag}' not in use",
                    err_msgs,
                    errs=errors,
                    fname=filename,
                    fline=line_num,
                )
                continue
            this_time = ut.time_str(cells[1])
            if not (this_time):
                errors = data_read_error(
                    "Poorly formed time value",
                    err_msgs,
                    errs=errors,
                    fname=filename,
                    fline=line_num,
                )
                continue
            # Maybe add to data.bikes_in or data.bikes_out structures.
            if section == BIKE_IN:
                # Maybe add to check_in structure
                if this_tag in data.bikes_in:
                    errors = data_read_error(
                        f"Duplicate {this_tag} check-in",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                if this_tag in data.bikes_out and data.bikes_out[this_tag] < this_time:
                    errors = data_read_error(
                        f"Tag {this_tag} check out before check-in",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                data.bikes_in[this_tag] = this_time
            elif section == BIKE_OUT:
                if this_tag in data.bikes_out:
                    errors = data_read_error(
                        f"Duplicate {this_tag} check-out",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                if this_tag not in data.bikes_in:
                    errors = data_read_error(
                        f"Tag {this_tag} checked out but not in",
                        err_msgs,
                        errs=errors,
                        fname=filename,
                        fline=line_num,
                    )
                    continue
                if this_tag in data.bikes_in and data.bikes_in[this_tag] > this_time:
                    errors = data_read_error(
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
    # remove duplicates from tag reference lists
    data.regular = sorted(list(set(data.regular)))
    data.oversize = sorted(list(set(data.oversize)))
    data.retired = sorted(list(set(data.retired)))
    # Return today's working data.
    return data


def write_logfile(
    filename: str, data: tt_trackerday.TrackerDay, header_lines: list = None
) -> None:
    """Write current data to today's data file."""
    lines = []
    if header_lines:
        lines = header_lines
    else:
        lines.append(
            "# TagTracker datafile (data file) created on "
            f"{ut.get_date()} {ut.get_time()}"
        )
        lines.append(f"# TagTracker version {ut.get_version()}")
    # Valet data, opening & closing hours
    if data.date:
        lines.append(f"{HEADER_VALET_DATE} {data.date}")
    if data.opening_time:
        lines.append(f"{HEADER_VALET_OPENS} {data.opening_time}")
    if data.closing_time:
        lines.append(f"{HEADER_VALET_CLOSES} {data.closing_time}")

    lines.append(HEADER_BIKES_IN)
    for tag, atime in data.bikes_in.items():  # for each bike checked in
        lines.append(f"{tag.lower()},{atime}")  # add a line "tag,time"
    lines.append(HEADER_BIKES_OUT)
    for tag, atime in data.bikes_out.items():  # for each  checked
        lines.append(f"{tag.lower()},{atime}")  # add a line "tag,time"
    # Also write tag info of which bikes are oversize, which are regular.
    # This to make complete bundles for historic information
    lines.append("# Following sections are context for the check-ins/outs")
    lines.append(HEADER_REGULAR)
    for tag in data.regular:
        lines.append(tag.lower())
    lines.append(HEADER_OVERSIZE)
    for tag in data.oversize:
        lines.append(tag.lower())
    lines.append(HEADER_RETIRED)
    for tag in data.retired:
        lines.append(tag.lower())
    lines.append(HEADER_COLOURS)
    for letter, name in data.colour_letters.items():
        lines.append(f"{letter},{name}")
    lines.append("# Normal end of file")
    # Write the data to the file.
    with open(filename, "w", encoding="utf-8") as f:  # write stored lines to file
        for line in lines:
            f.write(line)
            f.write("\n")


def new_tag_config_file(filename: str):
    """Create new, empty tags config file."""
    template = [
        "# Tags configuration file for TagTracker \n",
        "\n",
        "# Regular bike tags are tags that are used for bikes that are stored on racks.\n",
        "# List tags in any order, with one or more tags per line,\n",
        "# separated by spaces or commas.\n",
        "# E.g. bf1 bf2 bf3 bf4\n",
        "Regular-bike tags:\n\n",
        "# Oversize bike tags are tags that are used for oversize bikes.\n",
        "# List tags in any order, with one or more tags per line,\n",
        "# separated by spaces or commas.\n",
        "# E.g. bf1 bf2 bf3 bf4\n",
        "Oversize-bike tags:\n\n",
        "# Retired tags are tags that are no longer available for use.\n",
        "Retired tags:\n\n",
        "# Colour codes are used to format reports.\n",
        "# Each line is one- or two-letter colour code then the name of the colour\n",
        "# E.g. r red \n",
        "Colour codes:\n\n",
    ]
    if not os.path.exists(filename):  # make new tags config file only if needed
        with open(filename, "w", encoding="utf-8") as f:
            f.writelines(template)

