"""TagTracker by Julias Hocking.

This is the data entry module for the TagTracker suite.
Its configuration file is tagtracker_config.py.

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

import os
import sys
import time
import pathlib

# The readline module magically solves arrow keys creating ANSI esc codes
# on the Chromebook.  But it isn't on all platforms.
try:
    import readline  # pylint:disable=unused-import
except ImportError:
    pass

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
from tt_tag import TagID
from tt_realtag import Stay
from tt_time import VTime
import tt_util as ut
import tt_trackerday as td
import tt_conf as cfg
import tt_printer as pr
import tt_datafile as df
import tt_reports as rep
import tt_publish as pub
import tt_tag_inv as inv

# Local connfiguration
# try:
#    import tt_local_config  # pylint:disable=unused-import
# except ImportError:
#    pass

# Initialize valet open/close globals
# (These are all represented in TrackerDay attributes or methods)
VALET_OPENS = ""
VALET_CLOSES = ""
VALET_DATE = ""
NORMAL_TAGS = []
OVERSIZE_TAGS = []
RETIRED_TAGS = []
ALL_TAGS = []
COLOUR_LETTERS = {}
check_ins = {}
check_outs = {}


def valet_logo():
    """Print a cute bike valet logo using unicode."""
    UL = chr(0x256D)
    VR = chr(0x2502)
    HR = chr(0x2500)
    UR = chr(0x256E)
    LL = chr(0x2570)
    LR = chr(0x256F)
    BL = " "
    LOCK00 = chr(0x1F512)
    BIKE00 = chr(0x1F6B2)
    SCOOTR = chr(0x1F6F4)

    ln1 = f"{BL}{UL}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{UR}"
    ln2 = f"{BL}{VR}{BL}{BIKE00}{BIKE00}{SCOOTR}{BIKE00}{BL}{VR}"
    ln3 = f"{LOCK00}{BL}{BIKE00}{BIKE00}{BIKE00}{SCOOTR}{BL}{VR}"
    ln4 = f"{BL}{LL}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{HR}{LR}"

    WHATSTYLE = cfg.ANSWER_STYLE

    pr.iprint()
    pr.iprint(f"            {ln1}             ", style=WHATSTYLE)
    pr.iprint(f"   FREE     {ln2}     BIKE    ", style=WHATSTYLE)
    pr.iprint(f"   SAFE     {ln3}     VALET   ", style=WHATSTYLE)
    pr.iprint(f"            {ln4}             ", style=WHATSTYLE)
    pr.iprint()


def fix_2400_events() -> list[TagID]:
    """Change any 24:00 events to 23:59, warn, return Tags changed."""
    changed = []
    for tag, atime in check_ins.items():
        if atime == "24:00":
            check_ins[tag] = VTime("23:59")
            changed.append(tag)
    for tag, atime in check_outs.items():
        if atime == "24:00":
            check_outs[tag] = VTime("23:59")
            changed.append(tag)
    changed = list(set(changed))  # Remove duplicates.
    if changed:
        pr.iprint(
            f"(Time for {rep.simplified_taglist(changed)} adjusted to 23:59)",
            style=cfg.WARNING_STYLE,
        )
    return changed


def deduce_valet_date(current_guess: str, filename: str) -> str:
    """Guess what date the current data is for.

    Logic:
        If current_guess is set (presumably read from the contents
        of the datafile) then it is used.
        Else if there appears to be a date embedded in the name of
        the datafile, it is used.
        Else today's date is used.
    """
    if current_guess:
        return current_guess
    r = DATE_PART_RE.search(filename)
    if r:
        return (
            f"{int(r.group(2)):04d}-{int(r.group(3)):02d}-"
            f"{int(r.group(4)):02d}"
        )
    return ut.get_date()


def pack_day_data() -> td.TrackerDay:
    """Create a TrackerDay object loaded with today's data."""
    # Pack info into TrackerDay object
    day = td.TrackerDay()
    day.date = VALET_DATE
    day.opening_time = VALET_OPENS
    day.closing_time = VALET_CLOSES
    day.bikes_in = check_ins
    day.bikes_out = check_outs
    day.regular = NORMAL_TAGS
    day.oversize = OVERSIZE_TAGS
    day.retired = RETIRED_TAGS
    day.colour_letters = COLOUR_LETTERS
    return day


def unpack_day_data(today_data: td.TrackerDay) -> None:
    """Set globals from a TrackerDay data object."""
    # pylint: disable=global-statement
    global VALET_DATE, VALET_OPENS, VALET_CLOSES
    global check_ins, check_outs
    global NORMAL_TAGS, OVERSIZE_TAGS, RETIRED_TAGS
    global ALL_TAGS
    global COLOUR_LETTERS
    # pylint: enable=global-statement
    VALET_DATE = today_data.date
    VALET_OPENS = today_data.opening_time
    VALET_CLOSES = today_data.closing_time
    check_ins = today_data.bikes_in
    check_outs = today_data.bikes_out
    NORMAL_TAGS = today_data.regular
    OVERSIZE_TAGS = today_data.oversize
    RETIRED_TAGS = today_data.retired
    ALL_TAGS = (NORMAL_TAGS | OVERSIZE_TAGS) - RETIRED_TAGS
    COLOUR_LETTERS = today_data.colour_letters


def initialize_today() -> bool:
    """Read today's info from datafile & maybe tags-config file."""
    # Does the file even exist? (If not we will just create it later)
    new_datafile = False
    pathlib.Path(cfg.DATA_FOLDER).mkdir(
        exist_ok=True
    )  # make data folder if missing
    if not os.path.exists(DATA_FILEPATH):
        new_datafile = True
        pr.iprint(
            "Creating new datafile" f" {DATA_FILEPATH}.",
            style=cfg.SUBTITLE_STYLE,
        )
        today = td.TrackerDay()
    else:
        # Fetch data from file; errors go into error_msgs
        pr.iprint(
            f"Reading data from {DATA_FILEPATH}...",
            end="",
            style=cfg.SUBTITLE_STYLE,
        )
        error_msgs = []
        today = df.read_datafile(DATA_FILEPATH, error_msgs)
        if error_msgs:
            pr.iprint()
            for text in error_msgs:
                pr.iprint(text, style=cfg.ERROR_STYLE)
            return False
    # Figure out the date for this bunch of data
    if not today.date:
        today.date = deduce_valet_date(today.date, DATA_FILEPATH)
    # Find the tag reference lists (regular, oversize, etc).
    # If there's no tag reference lists, or it's today's date,
    # then fetch the tag reference lists from tags config
    if not (today.regular or today.oversize) or today.date == ut.get_date():
        tagconfig = get_taglists_from_config()
        today.regular = tagconfig.regular
        today.oversize = tagconfig.oversize
        today.retired = tagconfig.retired
        today.colour_letters = tagconfig.colour_letters
    # Set UC if needed (NB: datafiles are always LC)
    TagID.uc(cfg.TAGS_UPPERCASE)
    # On success, set today's working data
    unpack_day_data(today)
    # Now do a consistency check.
    errs = pack_day_data().lint_check(strict_datetimes=False)
    if errs:
        pr.iprint()
        for msg in errs:
            pr.iprint(msg, style=cfg.ERROR_STYLE)
        error_exit()
    # Done
    if not new_datafile:
        pr.iprint("done.", num_indents=0, style=cfg.SUBTITLE_STYLE)
    if VALET_DATE != ut.get_date():
        pr.iprint(
            f"Warning: Valet information is from {ut.long_date(VALET_DATE)}",
            style=cfg.WARNING_STYLE,
        )
    return True


def delete_entry(
    maybe_target: str = "",
    maybe_what: str = "",
    maybe_confirm: str = "",
    *extra,
) -> None:
    """Perform tag entry deletion dialogue.

    Delete syntax is:
        delete <tag> <in|out|both> <confirm>
    """

    def arg_prompt(maybe: str, prompt: str, optional: bool = False) -> str:
        """Prompt for one command argument (token)."""
        if optional or maybe:
            maybe = "" if maybe is None else f"{maybe}".strip().lower()
            return maybe
        pr.iprint(
            f"{prompt} {cfg.CURSOR}",
            style=cfg.SUBPROMPT_STYLE,
            end="",
        )
        return pr.tt_inp().strip().lower()

    def nogood(
        msg: str = "", syntax: bool = True, severe: bool = True
    ) -> None:
        """Print the nogood msg + syntax msg."""
        style = cfg.WARNING_STYLE if severe else cfg.HIGHLIGHT_STYLE
        if msg:
            pr.iprint(msg, style=style)
        if syntax:
            pr.iprint(
                "Syntax: delete <tag> <in|out|both> <y|n|!>",
                style=style,
            )

    def cancel():
        """Give a 'delete cancelled' message."""
        nogood("Delete cancelled", syntax=False, severe=False)

    if extra:
        nogood("", syntax=True, severe=True)
        return

    ##(maybe_target, maybe_what, maybe_confirm) = (args + ["", "", ""])[:3]
    # What tag are we to delete parts of?
    maybe_target = arg_prompt(maybe_target, "Delete entries for what tag?")
    if not maybe_target:
        cancel()
        return
    target = TagID(maybe_target)
    if not target:
        nogood(f"'{maybe_target}' is not a tag", syntax=False)
        return
    if target not in ALL_TAGS:
        nogood(f"'{maybe_target}' is not a tag in use", syntax=False)
        return
    if target not in check_ins:
        nogood(
            f"Tag {target} not checked in or out, nothing to do.", syntax=False
        )
        return
    # Special case: "!" after what without a space
    if maybe_what and maybe_what[-1] == "!" and not maybe_confirm:
        maybe_what = maybe_what[:-1]
        maybe_confirm = "!"
    # Find out what kind of checkin/out we are to delete
    what = arg_prompt(
        maybe_what, "Delete check-IN, check-OUT or BOTH (i/o/b)?"
    )
    if not what:
        cancel()
        return
    if what not in ["i", "in", "o", "out", "b", "both"]:
        nogood("Must indicate in, out or both")
        return
    if what in ["i", "in"] and target in check_outs:
        nogood(
            f"Bike {target} checked out.  Can't delete check-in "
            "for a returned bike without check-out too",
            syntax=False,
        )
        return
    # Get a confirmation
    confirm = arg_prompt(maybe_confirm, "Are you sure (y/N)?")
    if confirm not in ["n", "no", "!", "y", "yes"]:
        nogood(
            f"Confirmation must be 'y' or 'n', not '{confirm}'",
            severe=True,
            syntax=True,
        )
        return
    if confirm not in ["y", "yes", "!"]:
        cancel()
        return
    # Perform the delete
    if what in ["b", "both", "o", "out"] and target in check_outs:
        check_outs.pop(target)
    if what in ["b", "both", "i", "in"] and target in check_ins:
        check_ins.pop(target)
    pr.iprint("Deleted.", style=cfg.ANSWER_STYLE)


def query_one_tag(
    maybe_tag: str, day: td.TrackerDay, multi_line: bool = False
) -> None:
    """Print a summary of one tag's status.

    If multi_line is true, then this *may* print the status on multiple lines;
    otherwise will always put it on a single line.
    """
    tagid = TagID(maybe_tag)
    if not tagid:
        pr.iprint(
            f"Input '{tagid.original}' is not a tag name",
            style=cfg.WARNING_STYLE,
        )
        return
    tag = Stay(tagid, day, as_of_when="24:00")
    if not tag.state:
        pr.iprint(
            f"Tag {tag.tag} is not available",
            style=cfg.WARNING_STYLE,
        )
        return
    if tag.state == RETIRED:
        pr.iprint(f"Tag {tag.tag} is retired", style=cfg.WARNING_STYLE)
        return
    if tag.state == BIKE_OUT:
        if multi_line:
            pr.iprint(
                f"{tag.time_in.tidy}  " f"{tag.tag} checked in",
                style=cfg.ANSWER_STYLE,
            )
            pr.iprint(
                f"{tag.time_out.tidy}  " f"{tag.tag} checked out",
                style=cfg.ANSWER_STYLE,
            )
        else:
            pr.iprint(
                f"Tag {tag.tag} bike in at {tag.time_in.short}; "
                f"out at {tag.time_out.short}",
                style=cfg.ANSWER_STYLE,
            )
        return
    if tag.state == BIKE_IN:
        # Bike has come in sometime today but gone out
        dur = VTime("now").num - tag.time_in.num
        if multi_line:
            pr.iprint(
                f"{tag.time_in.tidy}  " f"{tag.tag} checked in",
                style=cfg.ANSWER_STYLE,
            )
            pr.iprint(
                f"       {tag.tag} not checked out", style=cfg.ANSWER_STYLE
            )
        else:
            if dur >= 60:
                dur_str = f"(in valet for {VTime(dur).short})"
            elif dur >= 0:
                dur_str = f"(in valet for {dur} minutes)"
            else:
                # a future time
                dur_str = f"({VTime(abs(dur)).short} in the future)"

            pr.iprint(
                f"Tag {tag.tag} bike in at {tag.time_in.short} {dur_str}",
                style=cfg.ANSWER_STYLE,
            )

        return
    if tag.state == USABLE:
        pr.iprint(
            f"Tag {tag.tag} not used yet today",
            style=cfg.ANSWER_STYLE,
        )
        return
    pr.iprint(f"Tag {tag.tag} has unknown state", style=cfg.ERROR_STYLE)


def query_tag(targets: list[str], multi_line: bool = None) -> None:
    """Query one or more tags"""
    if len(targets) == 0:
        # Have to prompt
        pr.iprint(
            f"Query which tags? (tag name) {cfg.CURSOR}",
            style=cfg.SUBPROMPT_STYLE,
            end="",
        )
        targets = ut.splitline(pr.tt_inp())
        if not targets:
            pr.iprint("Query cancelled", style=cfg.HIGHLIGHT_STYLE)
            return
    day = pack_day_data()
    pr.iprint()
    if multi_line is None:
        multi_line = len(targets) == 1

    for maybe_tag in targets:
        query_one_tag(maybe_tag, day, multi_line=multi_line)


def prompt_for_time(inp=False, prompt: str = None) -> VTime:
    """Prompt for a time input if needed.

    Helper for edit_entry() & others; if no time passed in, get a valid
    24h time input from the user and return an HH:MM string.
    """
    if not inp:
        if not prompt:
            prompt = "Correct time for this event? (HHMM or 'now')"
        pr.iprint(f"{prompt} {cfg.CURSOR}", style=cfg.SUBPROMPT_STYLE, end="")
        inp = pr.tt_inp()
    return VTime(inp)


def set_valet_hours(args: list[str]) -> None:
    """Set the valet opening & closing hours."""
    global VALET_OPENS, VALET_CLOSES  # pylint: disable=global-statement
    (open_arg, close_arg) = (args + ["", ""])[:2]
    pr.iprint()
    if VALET_DATE:
        pr.iprint(
            f"Bike Valet information for {ut.long_date(VALET_DATE)}",
            style=cfg.HIGHLIGHT_STYLE,
        )
    # Valet opening time
    if VALET_OPENS:
        pr.iprint(f"Opening time is: {VALET_OPENS}", style=cfg.HIGHLIGHT_STYLE)
    if VALET_CLOSES:
        pr.iprint(
            f"Closing time is: {VALET_CLOSES}", style=cfg.HIGHLIGHT_STYLE
        )

    maybe_open = prompt_for_time(
        open_arg,
        prompt="New valet opening time (24 hour clock HHMM or <Enter> to cancel)",
    )
    if not maybe_open:
        pr.iprint(
            "Input is not a time.  Opening time unchanged.",
            style=cfg.WARNING_STYLE,
        )
        return
    VALET_OPENS = maybe_open
    pr.iprint(f"Opening time now set to {VALET_OPENS}", style=cfg.ANSWER_STYLE)
    # Valet closing time
    maybe_close = prompt_for_time(
        close_arg,
        prompt="New valet closing time (24 hour clock HHMM or <Enter> to cancel)",
    )
    if not maybe_close:
        pr.iprint(
            "Input is not a time.  Closing time unchanged.",
            style=cfg.WARNING_STYLE,
        )
        return
    if maybe_close <= VALET_OPENS:
        pr.iprint(
            "Closing time must be later than opening time. Time unchanged.",
            style=cfg.ERROR_STYLE,
        )
        return
    VALET_CLOSES = maybe_close
    pr.iprint(
        f"Closing time now set to {VALET_CLOSES}", style=cfg.ANSWER_STYLE
    )


def multi_edit(args: list[str]):
    """Perform Dialog to correct a tag's check in/out time.

    Command syntax: edit [tag-list] [in|out] [time]
    Where:
        tag-list is a comma or whitespace-separated list of tags
        inout is 'in', 'i', 'out', 'o'
        time is a valid time (including 'now')
    """

    def prompt_for_stuff(prompt: str):
        pr.iprint(f"{prompt} {cfg.CURSOR}", style=cfg.SUBPROMPT_STYLE, end="")
        return pr.tt_inp().lower()

    def error(msg: str, severe: bool = True) -> None:
        if severe:
            pr.iprint(msg, style=cfg.WARNING_STYLE)
        else:
            pr.iprint(msg, style=cfg.HIGHLIGHT_STYLE)

    def cancel():
        error("Edit cancelled", severe=False)

    class TokenSet:
        """Local class to hold parsed portions of command."""

        def __init__(self, token_str: str) -> None:
            """Break token_str into token portions."""
            # In future this might do hyphenated tag lists
            #       - num_tokens is total of tokens in that list
            #       - add elements to taglist as long as look like tags
            #       - next element if present is INOUT
            #       - next element if present is TIME
            #       - remaining elements are REMAINDER
            parts = ut.splitline(token_str)
            self.num_tokens = len(parts)
            self.tags = []  # valid Tags (though possibly not available)
            self.inout_str = ""  # what the user said
            self.inout_value = BADVALUE  # or BIKE_IN, BIKE_OUT
            self.atime_str = ""  # What the user said
            self.atime_value = BADVALUE  # A valid time, or BADVALUE
            self.remainder = []  # whatever is left (hopefully nothing)
            if self.num_tokens == 0:
                return
            # Break into tags list and other list
            done_tags = False
            for part in parts:
                tag = TagID(part)
                if done_tags or not tag:
                    self.remainder.append(part)
                else:
                    self.tags.append(tag)
            # Anything left over?
            if not self.remainder:
                return
            # Is next part IN/OUT?
            self.inout_str = self.remainder[0]
            self.remainder = self.remainder[1:]
            if self.inout_str.lower() in ["i", "in"]:
                self.inout_value = BIKE_IN
            elif self.inout_str.lower() in ["o", "out"]:
                self.inout_value = BIKE_OUT
            else:
                return
            # Anything left over?
            if not self.remainder:
                return
            # Next part a time value?
            self.atime_str = self.remainder[0]
            self.remainder = self.remainder[1:]
            atime = VTime(self.atime_str)
            if not atime:
                return
            self.atime_value = atime
            # All done here
            return

    def edit_processor(
        maybe_tag: TagID, inout: str, target_time: VTime
    ) -> bool:
        """Execute one edit command with all its args known.

        On entry:
            tag: is a valid tag id (though possibly not usable)
            inout: is BIKE_IN or BIKE_OUT
            target_time: is a valid Time
        On exit, either:
            tag has been changed, msg delivered, returns True; or
            no change, error msg delivered, returns False
        """

        def success(tag: TagID, inout_str: str, newtime: VTime) -> None:
            """Print change message. inout_str is 'in' or 'out."""
            inoutflag = BIKE_IN if inout_str == "in" else BIKE_OUT
            print_tag_inout(tag, inoutflag, newtime)

        # Error conditions to test for
        # Unusable tag (not known, retired)
        # For checking in:
        #   Existing Out is earler than target time
        # For checking out:
        #   Not yet checked in
        #   Existing In later than target_time

        tag = TagID(maybe_tag)
        if not tag.valid:
            error(f"String '{tag.original}' is not a valid tag ID")
            return False
        if tag in RETIRED_TAGS:
            error(f"Tag '{tag}' is marked as retired")
            return False
        if tag not in ALL_TAGS:
            error(f"Tag '{tag}' not available for use")
            return False
        if (
            inout == BIKE_IN
            and tag in check_outs
            and check_outs[tag] < target_time
        ):
            error(f"Tag '{tag}' has check-out time earlier than {target_time}")
            return False
        if inout == BIKE_OUT:
            if tag not in check_ins:
                error(f"Tag '{tag}' not checked in")
                return False
            if check_ins[tag] > target_time:
                error(
                    f"Tag '{tag}' has checked in later than {target_time.short}"
                )
                return False
        # Have checked for errors, can now commit the change
        if inout == BIKE_IN:
            check_ins[tag] = target_time
            success(tag, "in", target_time)
        elif inout == BIKE_OUT:
            check_outs[tag] = target_time
            success(tag, "out", target_time)
        else:
            ut.squawk(f"Bad inout in call to edit_processor: '{inout}'")
            return False
        return True

    syntax = "Syntax: edit [tag(s)] [in|out] [time|'now']"
    # Turn all the args into a string, discarding the 'edit' at the front

    argstring = " ".join(args)
    cmd = TokenSet(argstring)
    if cmd.num_tokens > 0 and not cmd.tags:
        error(f"Bad input. {syntax}")
        return
    if not cmd.tags:
        response = prompt_for_stuff("Set time for which bike tag(s)?")
        if not response:
            cancel()
            return
        argstring += " " + response
        cmd = TokenSet(argstring)
        if not cmd.tags:
            error("Bad tag values", severe=True)
            return
    # At this point we know we have tags
    while not cmd.inout_str:
        response = prompt_for_stuff("Set bike check-IN or OUT (i/o)?")
        if not response:
            cancel()
            return
        argstring += " " + response
        cmd = TokenSet(argstring)
    if cmd.inout_value not in [BIKE_IN, BIKE_OUT]:
        error(f"Must specify IN or OUT, not '{cmd.inout_str}'. " f"{syntax}")
        return
    # Now we know we have tags and an INOUT
    while not cmd.atime_str:
        response = prompt_for_stuff("Set to what time?")
        if not response:
            cancel()
            return
        argstring += " " + response
        cmd = TokenSet(argstring)
    if cmd.atime_value == BADVALUE:
        error(
            f"Bad time '{cmd.atime_str}', " f"must be HHMM or 'now'. {syntax}"
        )
        return
    # That should be the whole command, with nothing left over.
    if cmd.remainder:
        error("Bad input at end " f"'{' '.join(cmd.remainder)}'. {syntax}")
        return
    # Now we have a list of maybe-ish Tags, a usable INOUT and a usable Time
    for tag in cmd.tags:
        edit_processor(tag, cmd.inout_value, cmd.atime_value)


def print_tag_inout(tag: TagID, inout: str, when: VTime = VTime("")) -> None:
    """Pretty-print a tag-in or tag-out message."""
    if inout == BIKE_IN:
        basemsg = f"Bike {tag} checked in"
        basemsg = f"{basemsg} at {when.short}" if when else basemsg
        finalmsg = f"{basemsg:40} <---in---  "
    elif inout == BIKE_OUT:
        basemsg = f"Bike {tag} checked out"
        basemsg = f"{basemsg} at {when.short}" if when else basemsg
        finalmsg = f"{basemsg:55} ---out--->  "
    else:
        ut.squawk(f"bad call to called print_tag_inout({tag}, {inout})")
        return
    # Print
    pr.iprint(finalmsg, style=cfg.ANSWER_STYLE)


def tag_check(tag: TagID) -> None:
    """Check a tag in or out.

    This processes a prompt that's just a tag ID.
    """
    if tag in RETIRED_TAGS:  # if retired print specific retirement message
        pr.iprint(f"{tag} is retired", style=cfg.WARNING_STYLE)
    else:  # must not be retired so handle as normal
        if tag in check_ins:
            if tag in check_outs:  # if tag has checked in & out
                query_tag([tag], multi_line=False)
                pr.iprint(
                    f"Overwrite {check_outs[tag]} check-out with "
                    f"current time ({VTime('now').short})? "
                    f"(y/N) {cfg.CURSOR}",
                    style=cfg.SUBPROMPT_STYLE,
                    end="",
                )
                sure = pr.tt_inp().lower() in ["y", "yes"]
                if sure:
                    multi_edit([tag, "o", VTime("now")])
                else:
                    pr.iprint("Cancelled", style=cfg.WARNING_STYLE)
            else:  # checked in only
                # How long ago checked in? Maybe ask operator to confirm.
                rightnow = VTime("now")
                time_diff_mins = rightnow.num - VTime(check_ins[tag]).num
                if time_diff_mins < 0:
                    query_tag([tag], multi_line=False)
                    pr.iprint(
                        "Check-in is in the future; check out cancelled",
                        style=cfg.WARNING_STYLE,
                    )
                    return
                if time_diff_mins < cfg.CHECK_OUT_CONFIRM_TIME:
                    query_tag([tag], multi_line=False)
                    pr.iprint(
                        "Do you want to check it out? " f"(y/N) {cfg.CURSOR}",
                        style=cfg.SUBPROMPT_STYLE,
                        end="",
                    )
                    sure = pr.tt_inp().lower() in ["yes", "y"]
                else:  # don't check for long stays
                    sure = True
                if sure:
                    multi_edit([tag, "o", rightnow])
                else:
                    pr.iprint(
                        "Cancelled bike check out", style=cfg.WARNING_STYLE
                    )
        else:  # if string is in neither dict
            check_ins[tag] = VTime("now")
            print_tag_inout(tag, BIKE_IN)


def parse_command(user_input: str) -> list[str]:
    """Parse user's input into list of [tag] or [command, command args].

    Return:
        [cfg.CMD_TAG_RETIRED,args] if a tag but is retired
        [cfg.CMD_TAG_UNUSABLE,args] if a tag but otherwise not usable
        [cfg.CMD_UNKNOWN,args] if not a tag & not a command
    """
    user_input = user_input.lower().strip()
    if not (user_input):
        return []
    # Special case - if user input starts with '/' or '?' add a space.
    if user_input[0] in ["/", "?"]:
        user_input = user_input[0] + " " + user_input[1:]
    # Split to list, test to see if tag.
    input_tokens = user_input.split()
    # See if it matches tag syntax
    maybetag = TagID(input_tokens[0])
    if maybetag:
        # This appears to be a tag
        if maybetag in RETIRED_TAGS:
            return [cfg.CMD_TAG_RETIRED] + input_tokens[1:]
        # Is this tag usable?
        if maybetag not in ALL_TAGS:
            return [cfg.CMD_TAG_UNUSABLE] + input_tokens[1:]
        # This appears to be a usable tag.
        return [maybetag]

    # See if it is a recognized command.
    # cfg.command_aliases is dict of lists of aliases keyed by
    # canonical command name (e.g. {"edit":["ed","e","edi"], etc})
    command = None
    for c, aliases in cfg.COMMANDS.items():
        if input_tokens[0] in aliases:
            command = c
            break
    # Is this an unrecognized command?
    if not command:
        return [cfg.CMD_UNKNOWN] + input_tokens[1:]
    # We have a recognized command, return it with its args.
    return [command] + input_tokens[1:]


def show_help():
    """Show help_message with colour style highlighting.

    Prints first non-blank line as title;
    lines that are flush-left as subtitles;
    other lines in normal style.
    """
    title_done = False
    for line in cfg.HELP_MESSAGE.split("\n"):
        if not line:
            pr.iprint()
        elif not title_done:
            title_done = True
            pr.iprint(line, style=cfg.TITLE_STYLE)
        elif line[0] != " ":
            pr.iprint(line, style=cfg.SUBTITLE_STYLE)
        else:
            pr.iprint(line, style=cfg.NORMAL_STYLE)


def dump_data():
    """For debugging. Dump current contents of core data structures."""
    pr.iprint()
    pr.iprint("    cfg   ", num_indents=0, style=cfg.ERROR_STYLE)
    for var in vars(cfg):
        if var[0] == "_":
            continue
        value = vars(cfg)[var]
        if isinstance(value, (str, dict, list, set, float, int)):
            pr.iprint(
                f"{var} {type(value)}:  ", style=cfg.ANSWER_STYLE, end=""
            )
            pr.iprint(value)
    pr.iprint()
    pr.iprint("    main module   ", num_indents=0, style=cfg.ERROR_STYLE)
    for var in globals():
        if var[0] == "_":
            continue
        value = globals()[var]
        if isinstance(value, (str, dict, list, frozenset, set, float, int)):
            pr.iprint(
                f"{var} {type(value)}:  ", style=cfg.ANSWER_STYLE, end=""
            )
            pr.iprint(value)
    if check_ins:
        pr.iprint()
        pr.iprint(f"{type(list(check_ins.keys())[0])=}")
        pr.iprint(f"{type(list(check_outs.keys())[0])=}")
        pr.iprint(f"{type(list(NORMAL_TAGS)[0])=}")


def main():
    """Run main program loop and dispatcher."""
    done = False
    todays_date = ut.get_date()
    publishment = pub.Publisher(cfg.REPORTS_FOLDER, cfg.PUBLISH_FREQUENCY)
    while not done:
        pr.iprint()
        if cfg.INCLUDE_TIME_IN_PROMPT:
            pr.iprint(f"{VTime('now').short}", end="")
        pr.iprint(
            f"Bike tag or command {cfg.CURSOR}", style=cfg.PROMPT_STYLE, end=""
        )
        user_str = pr.tt_inp()
        # Break command into tokens, parse as command
        tokens = parse_command(user_str)
        if not tokens:
            continue  # No input, ignore
        (cmd, *args) = tokens
        # Dispatcher
        # If midnight has passed then need to restart
        if midnight_passed(todays_date) and cmd != cfg.CMD_EXIT:
            done = True
            continue
        data_dirty = False
        if cmd == cfg.CMD_EDIT:
            multi_edit(args)
            data_dirty = True
        elif cmd == cfg.CMD_AUDIT:
            rep.audit_report(pack_day_data(), args)
            publishment.publish_audit(pack_day_data(), args)
        elif cmd == cfg.CMD_DELETE:
            delete_entry(*args)
            data_dirty = True
        elif cmd == cfg.CMD_EXIT:
            done = True
        elif cmd == cfg.CMD_BLOCK:
            rep.dataform_report(pack_day_data(), args)
        elif cmd == cfg.CMD_HELP:
            show_help()
        elif cmd == cfg.CMD_LOOKBACK:
            rep.recent(pack_day_data(), args)
        elif cmd == cfg.CMD_RETIRED or cmd == cfg.CMD_COLOURS:
            pr.iprint(
                "This command has been replaced by the 'tags' command.",
                style=cfg.WARNING_STYLE,
            )
        elif cmd == cfg.CMD_TAGS:
            inv.tags_config_report(pack_day_data(), args)
        elif cmd == cfg.CMD_QUERY:
            query_tag(args)
        elif cmd == cfg.CMD_STATS:
            rep.day_end_report(pack_day_data(), args)
            # Force publication when do day-end reports
            publishment.publish(pack_day_data())
            ##last_published = maybe_publish(last_published, force=True)
        elif cmd == cfg.CMD_BUSY:
            rep.busyness_report(pack_day_data(), args)
        elif cmd == cfg.CMD_CHART:
            rep.full_chart(pack_day_data())
        elif cmd == cfg.CMD_BUSY_CHART:
            rep.busy_graph(pack_day_data())
        elif cmd == cfg.CMD_FULL_CHART:
            rep.fullness_graph(pack_day_data())
        elif cmd == cfg.CMD_CSV:
            rep.csv_dump(pack_day_data(), args)
        elif cmd == cfg.CMD_DUMP:
            dump_data()
        elif cmd == cfg.CMD_LINT:
            lint_report(strict_datetimes=True)
        elif cmd == cfg.CMD_PUBLISH:
            publishment.publish_reports(pack_day_data(), args)
        elif cmd == cfg.CMD_VALET_HOURS:
            set_valet_hours(args)
            data_dirty = True
        elif cmd == cfg.CMD_UPPERCASE or cmd == cfg.CMD_LOWERCASE:
            set_tag_case(cmd == cfg.CMD_UPPERCASE)
        # Check for bad input
        elif not TagID(cmd):
            # This is not a tag
            if cmd == cfg.CMD_UNKNOWN or len(args) > 0:
                msg = "Unrecognized command, enter 'h' for help"
            elif cmd == cfg.CMD_TAG_RETIRED:
                msg = f"Tag '{TagID(user_str)}' is retired"
            elif cmd == cfg.CMD_TAG_UNUSABLE:
                msg = f"Valet not configured to use tag '{TagID(user_str)}'"
            else:
                # Should never get to this point
                msg = "Surprised by unrecognized command"
            pr.iprint()
            pr.iprint(msg, style=cfg.WARNING_STYLE)

        else:
            # This is a tag
            tag_check(cmd)
            data_dirty = True
        # If anything has becomne "24:00" change it to "23:59"
        if data_dirty:
            fix_2400_events()
        # Save if anything has changed
        if data_dirty:
            data_dirty = False
            save()
            publishment.maybe_publish(pack_day_data())
            ##last_published = maybe_publish(last_published)
        # Flush any echo buffer
        pr.echo_flush()
    # Exiting; one last save and publishing
    save()
    publishment.publish(pack_day_data())


def custom_datafile() -> str:
    """Return custom datafilename from command line arg or ""."""
    if len(sys.argv) <= 1:
        return ""
    # Custom datafile name or location
    file = sys.argv[1]
    # File there?
    if not os.path.exists(file):
        pr.iprint(f"Error: File {file} not found", style=cfg.ERROR_STYLE)
        error_exit()
    # This is the custom datafile & it exists
    return file


def save():
    """Save today's data in the datafile."""
    # Save .bak
    df.rotate_datafile(DATA_FILEPATH)
    # Pack data into a TrackerDay object to store
    day = pack_day_data()
    # Store the data
    if not df.write_datafile(DATA_FILEPATH, day):
        ut.squawk("CRITICAL ERROR. Can not continue")
        error_exit()


def error_exit() -> None:
    """If an error has occurred, give a message and shut down.

    Any specific info about the error should already have been printed.
    """
    pr.iprint()
    pr.iprint("Closing in 30 seconds", style=cfg.ERROR_STYLE)
    time.sleep(30)
    exit()


def set_tag_case(want_uppercase: bool) -> None:
    """Set tags to be uppercase or lowercase depending on 'command'."""
    ##global UC_TAGS  # pylint: disable=global-statement
    case_str = "upper case" if want_uppercase else "lower case"
    if TagID.uc() == want_uppercase:
        pr.iprint(f"Tags already {case_str}.", style=cfg.WARNING_STYLE)
        return
    TagID.uc(want_uppercase)
    pr.iprint(f" Tags will now show in {case_str}. ", style=cfg.ANSWER_STYLE)


def lint_report(strict_datetimes: bool = True) -> None:
    """Check tag lists and event lists for consistency."""
    errs = pack_day_data().lint_check(strict_datetimes)
    if errs:
        for msg in errs:
            pr.iprint(msg, style=cfg.WARNING_STYLE)
    else:
        pr.iprint("No inconsistencies found", style=cfg.HIGHLIGHT_STYLE)
    # And while we're at it, fix up any times that are set to "24:00"
    fix_2400_events()


def midnight_passed(today_is: str) -> bool:
    """Check if it's still the same day."""
    if today_is == ut.get_date():
        return False
    # Time has rolled over past midnight so need a new datafile.
    print("\n\n\n")
    pr.iprint(
        "Program has been running since yesterday.", style=cfg.WARNING_STYLE
    )
    pr.iprint(
        "Please restart program to reset for today's data.",
        style=cfg.WARNING_STYLE,
    )
    pr.iprint()
    print("\n\n\n")
    print("Automatically exiting in 15 seconds")
    time.sleep(15)
    return True


def get_taglists_from_config() -> td.TrackerDay:
    """Read tag lists (oversize, etc) from tag config file."""
    # Lists of normal, oversize, retired tags
    # Return a TrackerDay object, though its bikes_in/out are meaningless.
    errs = []
    day = df.read_datafile(cfg.TAG_CONFIG_FILE, errs)
    if errs:
        print(f"Errors in file, {errs=}")
        error_exit()
    return day


# ---------------------------------------------
# STARTUP

# Tags uppercase or lowercase?
# Data file
DATA_FILEPATH = custom_datafile()
CUSTOM_DAT = bool(DATA_FILEPATH)
if not CUSTOM_DAT:
    DATA_FILEPATH = df.datafile_name(cfg.DATA_FOLDER)


if __name__ == "__main__":
    # Possibly turn on echo
    if cfg.ECHO:
        pr.set_echo(True)

    pr.iprint()
    pr.iprint(
        "TagTracker by Julias Hocking",
        num_indents=0,
        style=cfg.ANSWER_STYLE,
    )
    pr.iprint(f"Version {ut.get_version()}")
    pr.iprint()
    # If no tags file, create one and tell them to edit it.
    if not os.path.exists(cfg.TAG_CONFIG_FILE):
        df.new_tag_config_file(cfg.TAG_CONFIG_FILE)
        pr.iprint("No tags configuration file found.", style=cfg.WARNING_STYLE)
        pr.iprint(
            f"Creating new configuration file {cfg.TAG_CONFIG_FILE}",
            style=cfg.WARNING_STYLE,
        )
        pr.iprint(
            "Edit this file then re-rerun TagTracker.", style=cfg.WARNING_STYLE
        )
        print("\n" * 3, "Exiting automatically in 15 seconds.")
        time.sleep(15)
        exit()

    # Configure check in- and out-lists and operating hours from file
    if not initialize_today():  # only run main() if tags read successfully
        error_exit()

    lint_report(strict_datetimes=False)

    # Get/set valet date & time
    if not VALET_OPENS or not VALET_CLOSES:
        pr.iprint()
        pr.iprint(
            "Please enter today's opening/closing times.",
            style=cfg.ERROR_STYLE,
        )
        set_valet_hours([VALET_OPENS, VALET_CLOSES])
        if VALET_OPENS or VALET_CLOSES:
            save()

    valet_logo()
    main()

    pr.set_echo(False)
# ==========================================
