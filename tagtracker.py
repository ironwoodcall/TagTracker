#!/usr/bin/env python3

"""TagTracker by Julias Hocking.

This is the data entry module for the TagTracker suite.
Its configuration file is tagtracker_config.py.

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

import os
import sys
import time

# The readline module magically solves arrow keys creating ANSI esc codes
# on the Chromebook.  But it isn't on all platforms.
try:
    import readline  # pylint:disable=unused-import
except ImportError:
    pass

# Make sure running usable version of python.
# Yes, this is before the imports.
if sys.version_info < (3, 10):
    print("TagTracker requires Python 3.10 or later.")
    sys.exit(1)

# pylint: disable=wrong-import-position
import tt_constants as k
from tt_tag import TagID
from tt_realtag import Stay
from tt_time import VTime
import tt_util as ut
import tt_trackerday as td
import client_base_config as cfg
import tt_printer as pr
import tt_datafile as df
import tt_reports as rep
import tt_publish as pub
import tt_tag_inv as inv
import tt_notes as notes
from tt_cmdparse import CmdBits
import tt_call_estimator
import tt_registrations as reg
from tt_sounds import NoiseMaker
import tt_audit_report as aud
from tt_internet_monitor import InternetMonitorController
import tt_main_bits as bits
import tt_default_hours

# pylint: enable=wrong-import-position


# Local connfiguration
# try:
#    import tt_local_config  # pylint:disable=unused-import
# except ImportError:
#    pass

# Initialize open/close globals
# (These are all represented in TrackerDay attributes or methods)
OPENING_TIME = ""
CLOSING_TIME = ""
PARKING_DATE = ""
NORMAL_TAGS = []
OVERSIZE_TAGS = []
RETIRED_TAGS = []
ALL_TAGS = []
TAG_COLOUR_NAMES = {}
check_ins = {}
check_outs = {}


# The assignments below are unneccessary but stop pylint from whining.
publishment = None
DATA_FILEPATH = ""


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
            style=k.WARNING_STYLE,
        )
    return changed


def deduce_parking_date(current_guess: str, filename: str) -> str:
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
    r = k.DATE_PART_RE.search(filename)
    if r:
        return f"{int(r.group(2)):04d}-{int(r.group(3)):02d}-" f"{int(r.group(4)):02d}"
    return ut.date_str("today")


def pack_day_data() -> td.TrackerDay:
    """Create a TrackerDay object loaded with today's data."""
    # Pack info into TrackerDay object
    day = td.TrackerDay()
    day.date = PARKING_DATE
    day.opening_time = OPENING_TIME
    day.closing_time = CLOSING_TIME
    day.registrations = reg.Registrations.num_registrations
    day.bikes_in = check_ins
    day.bikes_out = check_outs
    day.regular = NORMAL_TAGS
    day.oversize = OVERSIZE_TAGS
    day.retired = RETIRED_TAGS
    day.colour_letters = TAG_COLOUR_NAMES
    day.notes = notes.Notes.fetch()
    return day


def unpack_day_data(today_data: td.TrackerDay) -> None:
    """Set globals from a TrackerDay data object."""
    # pylint: disable=global-statement
    global PARKING_DATE, OPENING_TIME, CLOSING_TIME
    global check_ins, check_outs
    global NORMAL_TAGS, OVERSIZE_TAGS, RETIRED_TAGS
    global ALL_TAGS
    global TAG_COLOUR_NAMES
    # pylint: enable=global-statement
    PARKING_DATE = today_data.date
    OPENING_TIME = VTime(today_data.opening_time)
    CLOSING_TIME = VTime(today_data.closing_time)
    reg.Registrations.set_num_registrations(today_data.registrations)
    check_ins = today_data.bikes_in
    check_outs = today_data.bikes_out
    NORMAL_TAGS = today_data.regular
    OVERSIZE_TAGS = today_data.oversize
    RETIRED_TAGS = today_data.retired
    ALL_TAGS = (NORMAL_TAGS | OVERSIZE_TAGS) - RETIRED_TAGS
    TAG_COLOUR_NAMES = today_data.colour_letters
    notes.Notes.load(today_data.notes)


def initialize_today() -> bool:
    """Set up today's info from existing datafile or from configs.

    This does *not* /create/ the new datafile, just the data that
    will go into it.
    """

    def handle_msgs(msgs: list[str]):
        """Print a list of warning/error messages."""
        pr.iprint()
        for text in msgs:
            pr.iprint(text, style=k.ERROR_STYLE)

    if os.path.exists(DATA_FILEPATH):
        # Read from existing datafile
        error_msgs = []
        today = df.read_datafile(DATA_FILEPATH, error_msgs)
        if error_msgs:
            handle_msgs(error_msgs)
            return False
    else:
        # Set up for a new day
        today = td.TrackerDay()
    # Add/check parts of the 'roday' object
    if not today.date:
        today.date = deduce_parking_date(today.date, DATA_FILEPATH)
    # Find the tag reference lists (regular, oversize, etc).
    # If there's no tag reference lists, or it's today's date,
    # then fetch the tag reference lists from tags config
    if not (today.regular or today.oversize) or today.date == ut.date_str("today"):
        tagconfig = get_taglists_from_config()
        today.regular = tagconfig.regular
        today.oversize = tagconfig.oversize
        today.retired = tagconfig.retired
        today.colour_letters = tagconfig.colour_letters
    # Back-compatibility edge case read from old tags.cfg FIXME: remove after cutover
    old_config = "tags.cfg"
    if not today.regular and not today.oversize and os.path.exists(old_config):
        oldtagconfig = get_taglists_from_old_config(old_config)
        today.regular = oldtagconfig.regular
        today.oversize = oldtagconfig.oversize
        today.retired = oldtagconfig.retired
        today.fill_colour_dict_gaps()
    # Set UC if needed (NB: datafiles are always LC)
    TagID.uc(cfg.TAGS_UPPERCASE)
    # On success, set today's working data
    unpack_day_data(today)
    # Now do a consistency check.
    errs = pack_day_data().lint_check(strict_datetimes=False)
    if errs:
        pr.iprint()
        for msg in errs:
            pr.iprint(msg, style=k.ERROR_STYLE)
        error_exit()
    # In case doing a date that's not today, warn
    if PARKING_DATE != ut.date_str("today"):
        handle_msgs(
            [
                f"Warning: Data is from {ut.date_str(PARKING_DATE,long_date=True)}, not today"
            ]
        )
    # Done
    return True


# def initialize_today_old() -> bool:
#     """Read today's info from datafile & maybe tags-config file."""
#     # Does the file even exist? (If not we will just create it later)
#     pathlib.Path(cfg.DATA_FOLDER).mkdir(exist_ok=True)  # make data folder if missing
#     if not os.path.exists(DATA_FILEPATH):
#         # pr.iprint(
#         #     f"Creating datafile '{DATA_FILEPATH}'.",
#         #     style=k.SUBTITLE_STYLE,
#         # )
#         today = td.TrackerDay()
#     else:
#         # Fetch data from file; errors go into error_msgs
#         # pr.iprint(
#         #     f"Using datafile '{DATA_FILEPATH}'.",
#         #     style=k.SUBTITLE_STYLE,
#         # )
#         error_msgs = []
#         today = df.read_datafile(DATA_FILEPATH, error_msgs)
#         if error_msgs:
#             pr.iprint()
#             for text in error_msgs:
#                 pr.iprint(text, style=k.ERROR_STYLE)
#             return False
#     # Figure out the date for this bunch of data
#     if not today.date:
#         today.date = deduce_parking_date(today.date, DATA_FILEPATH)
#     # Find the tag reference lists (regular, oversize, etc).
#     # If there's no tag reference lists, or it's today's date,
#     # then fetch the tag reference lists from tags config
#     if not (today.regular or today.oversize) or today.date == ut.date_str("today"):
#         tagconfig = get_taglists_from_config()
#         today.regular = tagconfig.regular
#         today.oversize = tagconfig.oversize
#         today.retired = tagconfig.retired
#         today.colour_letters = tagconfig.colour_letters
#     # Set UC if needed (NB: datafiles are always LC)
#     TagID.uc(cfg.TAGS_UPPERCASE)
#     # On success, set today's working data
#     unpack_day_data(today)
#     # Now do a consistency check.
#     errs = pack_day_data().lint_check(strict_datetimes=False)
#     if errs:
#         pr.iprint()
#         for msg in errs:
#             pr.iprint(msg, style=k.ERROR_STYLE)
#         error_exit()
#     # Done
#     if PARKING_DATE != ut.date_str("today"):
#         pr.iprint(
#             f"Warning: Data is from {ut.date_str(PARKING_DATE,long_date=True)}, not today",
#             style=k.WARNING_STYLE,
#         )
#     return True


def delete_entry(  # pylint:disable=keyword-arg-before-vararg
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
            style=k.SUBPROMPT_STYLE,
            end="",
        )
        return pr.tt_inp().strip().lower()

    def nogood(msg: str = "", syntax: bool = True, severe: bool = True) -> None:
        """Print the nogood msg + syntax msg."""
        style = k.WARNING_STYLE if severe else k.HIGHLIGHT_STYLE
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
        nogood(f"Tag {target} not checked in or out, nothing to do.", syntax=False)
        return
    # Special case: "!" after what without a space
    if maybe_what and maybe_what[-1] == "!" and not maybe_confirm:
        maybe_what = maybe_what[:-1]
        maybe_confirm = "!"
    # Find out what kind of checkin/out we are to delete
    what = arg_prompt(maybe_what, "Delete check-IN, check-OUT or BOTH (i/o/b)?")
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
    pr.iprint("Deleted.", style=k.ANSWER_STYLE)


def query_one_tag(maybe_tag: str, day: td.TrackerDay, multi_line: bool = False) -> None:
    """Print a summary of one tag's status.

    If multi_line is true, then this *may* print the status on multiple lines;
    otherwise will always put it on a single line.

    If there are notes for the tag, that will always be on a new line.
    """
    tagid = TagID(maybe_tag)
    if not tagid:
        pr.iprint(
            f"Input '{tagid.original}' is not a tag name",
            style=k.WARNING_STYLE,
        )
        return

    # Any notes on the tag:
    pr.print_tag_notes(tagid)

    tag = Stay(tagid, day, as_of_when="24:00")
    if not tag.state:
        pr.iprint(
            f"Tag {tag.tag} is not available",
            style=k.WARNING_STYLE,
        )
        return
    if tag.state == k.RETIRED:
        pr.iprint(f"Tag {tag.tag} is retired", style=k.WARNING_STYLE)
        return
    if tag.state == k.BIKE_OUT:
        if multi_line:
            pr.iprint(
                f"{tag.time_in.tidy}  " f"{tag.tag} checked in",
                style=k.ANSWER_STYLE,
            )
            pr.iprint(
                f"{tag.time_out.tidy}  " f"{tag.tag} checked out",
                style=k.ANSWER_STYLE,
            )
        else:
            pr.iprint(
                f"Tag {tag.tag} bike in at {tag.time_in.short}; "
                f"out at {tag.time_out.short}",
                style=k.ANSWER_STYLE,
            )
        return
    if tag.state == k.BIKE_IN:
        # Bike has come in sometime today but gone out
        dur = VTime("now").num - tag.time_in.num
        if multi_line:
            pr.iprint(
                f"{tag.time_in.tidy}  " f"{tag.tag} checked in",
                style=k.ANSWER_STYLE,
            )
            pr.iprint(f"       {tag.tag} not checked out", style=k.ANSWER_STYLE)
        else:
            if dur >= 60:
                dur_str = f"(onsite for {VTime(dur).short})"
            elif dur >= 0:
                dur_str = f"(onsite for {dur} minutes)"
            else:
                # a future time
                dur_str = f"({VTime(abs(dur)).short} in the future)"

            pr.iprint(
                f"Tag {tag.tag} bike in at {tag.time_in.short} {dur_str}",
                style=k.ANSWER_STYLE,
            )

        return
    if tag.state == k.USABLE:
        pr.iprint(
            f"Tag {tag.tag} not used yet today",
            style=k.ANSWER_STYLE,
        )
        return
    pr.iprint(f"Tag {tag.tag} has unknown state", style=k.ERROR_STYLE)


def query_tag(targets: list[str], multi_line: bool = None) -> None:
    """Query one or more tags"""
    if len(targets) == 0:
        # Have to prompt
        pr.iprint(
            f"Query which tags? (tag name) {cfg.CURSOR}",
            style=k.SUBPROMPT_STYLE,
            end="",
        )
        targets = ut.splitline(pr.tt_inp())
        if not targets:
            pr.iprint("Query cancelled", style=k.HIGHLIGHT_STYLE)
            return
    day = pack_day_data()
    pr.iprint()
    if multi_line is None:
        multi_line = len(targets) == 1

    for maybe_tag in targets:
        query_one_tag(maybe_tag, day, multi_line=multi_line)


def operating_hours_command() -> None:
    """Respond to the 'hours' command."""
    global OPENING_TIME, CLOSING_TIME  # pylint: disable=global-statement
    OPENING_TIME, CLOSING_TIME = bits.get_operating_hours(OPENING_TIME, CLOSING_TIME)


def multi_edit(args: list[str]):
    """Perform Dialog to correct a tag's check in/out time.

    Command syntax: edit [tag-list] [in|out] [time]
    Where:
        tag-list is a comma or whitespace-separated list of tags
        inout is 'in', 'i', 'out', 'o'
        time is a valid time (including 'now')
    """

    def prompt_for_stuff(prompt: str):
        pr.iprint(f"{prompt} {cfg.CURSOR}", style=k.SUBPROMPT_STYLE, end="")
        return pr.tt_inp().lower()

    def error(msg: str, severe: bool = True) -> None:
        if severe:
            pr.iprint(msg, style=k.WARNING_STYLE)
        else:
            pr.iprint(msg, style=k.HIGHLIGHT_STYLE)

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
            self.inout_value = k.BADVALUE  # ork.BIKE_IN,k.BIKE_OUT
            self.atime_str = ""  # What the user said
            self.atime_value = k.BADVALUE  # A valid time, ork.BADVALUE
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
                self.inout_value = k.BIKE_IN
            elif self.inout_str.lower() in ["o", "out"]:
                self.inout_value = k.BIKE_OUT
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

    def edit_processor(maybe_tag: TagID, inout: str, target_time: VTime) -> str:
        """Execute one edit command with all its args known.

        On entry:
            tag: is a valid tag id (though possibly not usable)
            inout: isk.BIKE_IN ork.BIKE_OUT
            target_time: is a valid Time
        On exit, either:
            tag has been changed, msg delivered; returnsk.BIKE_IN ork.BIKE_OUT; or
            no change, error msg delivered, returns ""
        """

        def success(tag: TagID, inout_str: str, newtime: VTime) -> None:
            """Print change message. inout_str is 'in' or 'out."""
            inoutflag = k.BIKE_IN if inout_str == "in" else k.BIKE_OUT
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
            return ""
        if tag in RETIRED_TAGS:
            error(f"Tag '{tag}' is marked as retired")
            return ""
        if tag not in ALL_TAGS:
            error(f"Tag '{tag}' not available for use")
            return ""
        if inout == k.BIKE_IN and tag in check_outs and check_outs[tag] < target_time:
            error(f"Tag '{tag}' has check-out time earlier than {target_time}")
            return ""
        if inout == k.BIKE_OUT:
            if tag not in check_ins:
                error(f"Tag '{tag}' not checked in")
                return ""
            if check_ins[tag] > target_time:
                error(f"Tag '{tag}' has checked in later than {target_time.short}")
                return ""
        # Have checked for errors, can now commit the change
        if inout == k.BIKE_IN:
            check_ins[tag] = target_time
            success(tag, "in", target_time)
        elif inout == k.BIKE_OUT:
            check_outs[tag] = target_time
            success(tag, "out", target_time)
        else:
            ut.squawk(f"Bad inout in call to edit_processor: '{inout}'")
            return ""
        return inout

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
    if cmd.inout_value not in [k.BIKE_IN, k.BIKE_OUT]:
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
    if cmd.atime_value == k.BADVALUE:
        error(f"Bad time '{cmd.atime_str}', " f"must be HHMM or 'now'. {syntax}")
        return
    # That should be the whole command, with nothing left over.
    if cmd.remainder:
        error("Bad input at end " f"'{' '.join(cmd.remainder)}'. {syntax}")
        return
    # Now we have a list of maybe-ish Tags, a usable INOUT and a usable Time
    inouts = []
    for tag in cmd.tags:
        inouts.append(edit_processor(tag, cmd.inout_value, cmd.atime_value))
    # Play the sounds for this
    NoiseMaker.play(*inouts)


def print_tag_inout(tag: TagID, inout: str, when: VTime = VTime("")) -> None:
    """Pretty-print a tag-in or tag-out message."""
    if inout == k.BIKE_IN:
        basemsg = f"Bike {tag} checked in"
        basemsg = f"{basemsg} at {when.short}" if when else basemsg
        finalmsg = f"{basemsg:40} <---in---  "
    elif inout == k.BIKE_OUT:
        basemsg = f"Bike {tag} checked out"
        basemsg = f"{basemsg} at {when.short}" if when else basemsg
        finalmsg = f"{basemsg:55} ---out--->  "
    else:
        ut.squawk(f"bad call to called print_tag_inout({tag}, {inout})")
        return
    # Print
    pr.iprint(finalmsg, style=k.ANSWER_STYLE)


def tag_check(tag: TagID, cmd_tail: str) -> None:
    """Check a tag in or out.

    This processes a prompt that's just a tag ID.
    """

    # Has to be only the tag, no extra text
    if cmd_tail:
        pr.iprint("Error: Extra text following tag name", style=k.WARNING_STYLE)
        return

    pr.print_tag_notes(tag)

    if tag in RETIRED_TAGS:  # if retired print specific retirement message
        pr.iprint(f"{tag} is retired", style=k.WARNING_STYLE)
    else:  # must not be retired so handle as normal
        if tag in check_ins:
            if tag in check_outs:  # if tag has checked in & out
                query_tag([tag], multi_line=False)
                NoiseMaker.play(k.ALERT)
                pr.iprint(
                    f"Overwrite {check_outs[tag]} check-out with "
                    f"current time ({VTime('now').short})? "
                    f"(y/N) {cfg.CURSOR}",
                    style=k.SUBPROMPT_STYLE,
                    end="",
                )
                sure = pr.tt_inp().lower() in ["y", "yes"]
                if sure:
                    multi_edit([tag, "o", VTime("now")])
                else:
                    pr.iprint("Cancelled", style=k.WARNING_STYLE)
            else:  # checked in only
                # How long ago checked in? Maybe ask operator to confirm.
                rightnow = VTime("now")
                time_diff_mins = rightnow.num - VTime(check_ins[tag]).num
                if time_diff_mins < 0:
                    query_tag([tag], multi_line=False)
                    pr.iprint(
                        "Check-in is in the future; check out cancelled",
                        style=k.WARNING_STYLE,
                    )
                    return
                if time_diff_mins < cfg.CHECK_OUT_CONFIRM_TIME:
                    NoiseMaker.play(k.ALERT)
                    query_tag([tag], multi_line=False)
                    pr.iprint(
                        "Do you want to check it out? " f"(y/N) {cfg.CURSOR}",
                        style=k.SUBPROMPT_STYLE,
                        end="",
                    )
                    sure = pr.tt_inp().lower() in ["yes", "y"]
                else:  # don't check for long stays
                    sure = True
                if sure:
                    multi_edit([tag, "o", rightnow])
                else:
                    pr.iprint("Cancelled bike check out", style=k.WARNING_STYLE)
        else:  # if string is in neither dict
            check_ins[tag] = VTime("now")
            print_tag_inout(tag, k.BIKE_IN)
            NoiseMaker.play(k.BIKE_IN)


def parse_command(user_input: str) -> list[str]:
    """Parse user's input into list of [tag] or [command, command args].

    Return:
        [k.CMD_TAG_RETIRED,args] if a tag but is retired
        [k.CMD_TAG_UNUSABLE,args] if a tag but otherwise not usable
        [k.CMD_UNKNOWN,args] if not a tag & not a command
    """
    user_input = user_input.lower().strip("\\][ \t")
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
            return [k.CMD_TAG_RETIRED] + input_tokens[1:]
        # Is this tag usable?
        if maybetag not in ALL_TAGS:
            return [k.CMD_TAG_UNUSABLE] + input_tokens[1:]
        # This appears to be a usable tag.
        return [maybetag]

    # See if it is a recognized command.
    # cfg.command_aliases is dict of lists of aliases keyed by
    # canonical command name (e.g. {"edit":["ed","e","edi"], etc})
    command = None
    for c, aliases in k.COMMANDS.items():
        if input_tokens[0] in aliases:
            command = c
            break
    # Is this an unrecognized command?
    if not command:
        return [k.CMD_UNKNOWN] + input_tokens[1:]
    # We have a recognized command, return it with its args.
    return [command] + input_tokens[1:]


def dump_data():
    """For debugging. Dump current contents of core data structures."""
    pr.iprint()
    pr.iprint("    cfg   ", num_indents=0, style=k.ERROR_STYLE)
    for var in vars(cfg):
        if var[0] == "_":
            continue
        value = vars(cfg)[var]
        if isinstance(value, (str, dict, list, set, float, int)):
            pr.iprint(f"{var} {type(value)}:  ", style=k.ANSWER_STYLE, end="")
            pr.iprint(value)
    pr.iprint()
    pr.iprint("    main module   ", num_indents=0, style=k.ERROR_STYLE)
    for var in globals():
        if var[0] == "_":
            continue
        value = globals()[var]
        if isinstance(value, (str, dict, list, frozenset, set, float, int)):
            pr.iprint(f"{var} {type(value)}:  ", style=k.ANSWER_STYLE, end="")
            pr.iprint(value)
    if check_ins:
        pr.iprint()
        pr.iprint(f"{type(list(check_ins.keys())[0])=}")
        pr.iprint(f"{type(list(check_outs.keys())[0])=}")
        pr.iprint(f"{type(list(NORMAL_TAGS)[0])=}")
    pr.iprint()
    pr.iprint("  notes")
    for x in notes.Notes.fetch():
        pr.iprint(f"     {x}")


def estimate(args: list[str]) -> None:
    """Estimate how many more bikes.
    Args:
        bikes_so_far: default current bikes so far
        as_of_when: default right now
        dow: default today (else 1..7 or a date)
        closing_time: default - today's closing time
    """
    args += [""] * 4

    pr.iprint()
    pr.iprint("Estimating...")
    time.sleep(1)
    message_lines = tt_call_estimator.get_estimate_via_url(pack_day_data(), *args[:4])
    if not message_lines:
        message_lines = ["Nothing returned, don't know why. Sorry."]
    pr.iprint()
    for i, line in enumerate(message_lines):
        if i == 0:
            pr.iprint(line, style=k.TITLE_STYLE)
        else:
            pr.iprint(line)
    pr.iprint()


def bikes_on_hand_reminder() -> None:
    """Remind how many bikes should be present, if close to closing time."""
    if VTime(CLOSING_TIME).num - VTime("now").num < 60:  # last hour
        bikes_on_hand = len(check_ins) - len(check_outs)
        pr.iprint(
            f"There should currently be {bikes_on_hand} {ut.plural(bikes_on_hand,'bike')}"
            " here.",
            style=k.HIGHLIGHT_STYLE,
        )


def main():
    """Run main program loop and dispatcher."""
    done = False
    todays_date = ut.date_str("today")
    while not done:
        pr.iprint()
        # Nag about bikes expected to be present if close to closing time
        bikes_on_hand_reminder()
        # Allow tag notes for this next command
        pr.print_tag_notes("", reset=True)
        # Prompt
        if cfg.INCLUDE_TIME_IN_PROMPT:
            pr.iprint(f"{VTime('now').short}", end="")
        pr.iprint(f"Bike tag or command {cfg.CURSOR}", style=k.PROMPT_STYLE, end="")
        user_str = pr.tt_inp()
        # Break command into tokens, parse as command
        cmd_bits = CmdBits(user_str, RETIRED_TAGS, ALL_TAGS)
        ##FIXME tokens = parse_command(user_str)
        # If midnight has passed then need to restart
        if midnight_passed(todays_date):
            if not cmd_bits.command or cmd_bits.command != k.CMD_EXIT:
                midnight_message()
            done = True
            continue
        # If null input, just ignore
        if not cmd_bits.command:
            continue  # No input, ignore
        ##FIXME (cmd, *args) = tokens
        # Dispatcher
        data_dirty = False
        if cmd_bits.command == k.CMD_EDIT:
            multi_edit(cmd_bits.args)
            data_dirty = True
        elif cmd_bits.command == k.CMD_AUDIT:
            aud.audit_report(pack_day_data(), cmd_bits.args, include_returns=False)
            publishment.publish_audit(pack_day_data(), cmd_bits.args)
        elif cmd_bits.command == k.CMD_DELETE:
            delete_entry(*cmd_bits.args)
            data_dirty = True
        elif cmd_bits.command == k.CMD_EXIT:
            done = True
        elif cmd_bits.command == k.CMD_BLOCK:
            rep.dataform_report(pack_day_data(), cmd_bits.args)
        elif cmd_bits.command == k.CMD_HELP:
            bits.show_help()
        elif cmd_bits.command == k.CMD_LOOKBACK:
            rep.recent(pack_day_data(), cmd_bits.args)
        elif cmd_bits.command == k.CMD_RETIRED or cmd_bits.command == k.CMD_COLOURS:
            pr.iprint(
                "This command has been replaced by the 'tags' command.",
                style=k.WARNING_STYLE,
            )
        elif cmd_bits.command == k.CMD_TAGS:
            inv.tags_config_report(pack_day_data(), cmd_bits.args, False)
        elif cmd_bits.command == k.CMD_QUERY:
            query_tag(cmd_bits.args)
        elif cmd_bits.command == k.CMD_STATS:
            rep.day_end_report(pack_day_data(), cmd_bits.args)
            # Force publication when do day-end reports
            publishment.publish(pack_day_data())
            ##last_published = maybe_publish(last_published, force=True)
        elif cmd_bits.command == k.CMD_BUSY:
            rep.busyness_report(pack_day_data(), cmd_bits.args)
        elif cmd_bits.command == k.CMD_CHART:
            rep.full_chart(pack_day_data())
        elif cmd_bits.command == k.CMD_BUSY_CHART:
            rep.busy_graph(pack_day_data())
        elif cmd_bits.command == k.CMD_FULL_CHART:
            rep.fullness_graph(pack_day_data())
        elif cmd_bits.command == k.CMD_CSV:
            rep.csv_dump(pack_day_data(), cmd_bits.args)
        elif cmd_bits.command == k.CMD_DUMP:
            dump_data()
        elif cmd_bits.command == k.CMD_LINT:
            lint_report(strict_datetimes=True)
        elif cmd_bits.command == k.CMD_REGISTRATION:
            if reg.Registrations.process_registration(cmd_bits.tail):
                data_dirty = True
        elif cmd_bits.command == k.CMD_NOTES:
            if cmd_bits.args:
                notes.Notes.add(cmd_bits.tail)
                pr.iprint("Noted.")
            else:
                bits.show_notes(notes.Notes, header=True, styled=False)
        elif cmd_bits.command == k.CMD_ESTIMATE:
            estimate(cmd_bits.args)
        elif cmd_bits.command == k.CMD_PUBLISH:
            publishment.publish_reports(pack_day_data(), cmd_bits.args)
        elif cmd_bits.command == k.CMD_VALET_HOURS:
            operating_hours_command()
            data_dirty = True
        elif cmd_bits.command == k.CMD_UPPERCASE or cmd_bits.command == k.CMD_LOWERCASE:
            set_tag_case(cmd_bits.command == k.CMD_UPPERCASE)
        # Check for bad input
        elif not TagID(cmd_bits.command):
            # This is not a tag
            if cmd_bits.command == k.CMD_UNKNOWN or len(cmd_bits.args) > 0:
                NoiseMaker.play(k.ALERT)
                msg = "Unrecognized command, enter 'h' for help"
            elif cmd_bits.command == k.CMD_TAG_RETIRED:
                msg = f"Tag '{TagID(user_str)}' is retired"
            elif cmd_bits.command == k.CMD_TAG_UNUSABLE:
                msg = f"System not configured to use tag '{TagID(user_str)}'"
            else:
                # Should never get to this point
                msg = "Surprised by unrecognized command"
            pr.iprint()
            pr.iprint(msg, style=k.WARNING_STYLE)

        else:
            # This is a tag
            tag_check(cmd_bits.command, cmd_bits.tail)
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
        pr.iprint(f"Error: File {file} not found", style=k.ERROR_STYLE)
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
    pr.iprint("Closing in 30 seconds", style=k.ERROR_STYLE)
    time.sleep(30)
    exit()


def set_tag_case(want_uppercase: bool) -> None:
    """Set tags to be uppercase or lowercase depending on 'command'."""
    ##global UC_TAGS  # pylint: disable=global-statement
    case_str = "upper case" if want_uppercase else "lower case"
    if TagID.uc() == want_uppercase:
        pr.iprint(f"Tags already {case_str}.", style=k.WARNING_STYLE)
        return
    TagID.uc(want_uppercase)
    pr.iprint(f" Tags will now show in {case_str}. ", style=k.ANSWER_STYLE)


def lint_report(strict_datetimes: bool = True) -> None:
    """Check tag lists and event lists for consistency."""
    errs = pack_day_data().lint_check(strict_datetimes)
    if errs:
        for msg in errs:
            pr.iprint(msg, style=k.WARNING_STYLE)
    # else:
    #     pr.iprint("No inconsistencies found", style=k.HIGHLIGHT_STYLE)
    # And while we're at it, fix up any times that are set to "24:00"
    fix_2400_events()


def midnight_message():
    """Print a "you have to restart" message."""
    # Time has rolled over past midnight so need a new datafile.
    print("\n\n\n")
    pr.iprint("Program has been running since yesterday.", style=k.WARNING_STYLE)
    pr.iprint(
        "Please restart program to reset for today's data.",
        style=k.WARNING_STYLE,
    )
    pr.iprint()
    print("\n\n\n")
    print("Automatically exiting in 15 seconds")
    time.sleep(15)


def midnight_passed(today_is: str) -> bool:
    """Check if it's still the same day."""
    if today_is == ut.date_str("today"):
        return False
    return True


def get_taglists_from_old_config(old_config_file: str) -> td.TrackerDay:
    """Read tag lists (oversize, etc) from tag config file."""
    # Lists of normal, oversize, retired tags
    # Return a TrackerDay object, though its bikes_in/out are meaningless.
    errs = []
    day = df.read_datafile(old_config_file, errs)
    if errs:
        print(f"Errors in file, {errs=}")
        error_exit()
    pr.iprint()
    pr.iprint(
        f"Using tag configurations from deprecated '{old_config_file}' configuration file.",
        style=k.ERROR_STYLE,
    )
    pr.iprint(
        "Please define tag configurations in client_local_config.py.",
        style=k.ERROR_STYLE,
    )
    return day


def get_taglists_from_config() -> td.TrackerDay:
    """Read taglists from config module into tag lists part of a trackerday.

    In the trackerday object, only these will have meaning:
    - .colour_letters
    - .regular
    - .oversize
    - .retired

    'colour_letters' will be read from config but extended to include any
    tag colours that are not listed in the regular/oversize/retired lists.

    """

    def tokenize(s: str) -> list:
        """Break a string into a list of tokens."""
        lst = [x.split(",") for x in s.split()]  # split on whitespace & commas
        lst = [item for sublist in lst for item in sublist]  # flatten
        lst = [item for item in lst if item]  # discard empty members
        lst = list(set(lst))  # remove duplicates
        return lst

    def tagize(
        lst: list[k.MaybeTag], what_am_i: str, exclude: list[TagID] = None
    ) -> bool | list[TagID]:
        """Make a list of tags based on the tokens.

        Returns a list of tags and an error flag showing if there were errors.
        Prints error messages for any bad tags or tags in the 'exclude' list.
        'what_am_i' is used in error messages to describe what 'lst' is.

        """
        new_list = []
        exclude = exclude if exclude else []
        errors = False
        for maybe in lst:
            t = TagID(maybe)
            if not t or t in exclude:
                if not errors:
                    print(f"Error(s) in {what_am_i} list:")
                errors = True
                print(
                    f"  {maybe} {'already differently defined' if t else 'not a tag'}"
                )
                continue
            new_list.append(t)
        return new_list, errors

    reglr, reg_errors = tagize(tokenize(cfg.REGULAR_TAGS), "Regular Tags")
    over, over_errors = tagize(tokenize(cfg.OVERSIZE_TAGS), "Oversize Tags", reglr)
    ret, ret_errors = tagize(tokenize(cfg.RETIRED_TAGS), "Retired Tags")
    if reg_errors or over_errors or ret_errors:
        error_exit()
    day = td.TrackerDay()
    day.regular = frozenset(reglr)
    day.oversize = frozenset(over)
    day.retired = frozenset(ret)

    # Colour letters
    day.colour_letters = cfg.TAG_COLOUR_NAMES
    day.fill_colour_dict_gaps()
    # # Extend for any missing colours
    # tag_colours = set([x.colour for x in reg + over + ret])
    # for colour in tag_colours:
    #     if colour not in day.colour_letters:
    #         day.colour_letters[colour] = f"Colour {colour.upper()}"

    return day

def confirm_hours(
    date: k.MaybeDate, current_open: k.MaybeTime, current_close: k.MaybeTime
) -> tuple[bool, int, int]:
    """Get/set operating hours.

    Returns flag True if values have changed
    and new (or unchanged) open and close times.
    """
    # If no times yet set, fetch defaults
    new_open = ""
    new_close = ""
    if not current_open or not current_close:
        default_open, default_close = tt_default_hours.get_default_hours(date)
        (new_open, new_close) = tt_default_hours.get_default_hours(date)
        new_open = current_open if current_open else new_open
        new_close = current_close if current_close else new_close
    # Ask operator to enter or confirm
    new_open, new_close = bits.get_operating_hours(
        VTime(new_open), VTime(new_close)
    )
    # Has anything changed?
    return (
        bool(new_open != current_open or new_close != current_close),
        new_open,
        new_close,
    )


# ---------------------------------------------
# STARTUP


if __name__ == "__main__":

    # Data file
    DATA_FILEPATH = custom_datafile()
    CUSTOM_DAT = bool(DATA_FILEPATH)
    if not CUSTOM_DAT:
        DATA_FILEPATH = df.datafile_name(cfg.DATA_FOLDER)

    # Set colour module's colour flag based on config
    pr.COLOUR_ACTIVE = cfg.USE_COLOUR

    # Possibly turn on echo. Print any error msgs later, though
    echo_msg = ""
    if cfg.ECHO:
        if not cfg.ECHO_FOLDER:
            echo_msg = "No echo folder set, settig echo off."
            pr.set_echo(False)
        elif not ut.writable_dir(cfg.ECHO_FOLDER):
            echo_msg = f"Echo folder '{cfg.ECHO_FOLDER}' missing or not writeable, setting echo off."
            pr.set_echo(False)
        else:
            pr.set_echo(True)

    pr.clear_screen()
    bits.splash()

    # echo error messages now
    if echo_msg:
        pr.iprint()
        pr.iprint(echo_msg, style=k.WARNING_STYLE)

    # Check that data directory is writable
    if not ut.writable_dir(cfg.DATA_FOLDER):
        pr.iprint()
        pr.iprint(
            f"Data folder '{cfg.DATA_FOLDER}' missing or not writeable.",
            style=k.ERROR_STYLE,
        )
        sys.exit(1)

    # Set up publishing
    publishment = pub.Publisher(cfg.REPORTS_FOLDER, cfg.PUBLISH_FREQUENCY)
    # Check that sounds can work (if enabled).
    NoiseMaker.init_check()

    # # Check for tags config file
    # if not os.path.exists(cfg.TAG_CONFIG_FILE):
    #     df.new_tag_config_file(cfg.TAG_CONFIG_FILE)
    #     pr.iprint("No tags configuration file found.", style=k.WARNING_STYLE)
    #     pr.iprint(
    #         f"Creating new configuration file {cfg.TAG_CONFIG_FILE}",
    #         style=k.WARNING_STYLE,
    #     )
    #     pr.iprint("Edit this file then re-rerun TagTracker.", style=k.WARNING_STYLE)
    #     print("\n" * 3, "Exiting automatically in 15 seconds.")
    #     time.sleep(15)
    #     sys.exit()

    # Configure check in- and out-lists and operating hours from file
    pr.iprint()
    if not initialize_today():  # only run main() if tags read successfully
        error_exit()
    lint_report(strict_datetimes=False)
    pr.iprint(
        f"Editing information for {ut.date_str(PARKING_DATE,long_date=True)}.",
        style=k.HIGHLIGHT_STYLE,
    )
    # Start internet monitoring (if enabled in config)
    InternetMonitorController.start_monitor()

    # Display data owner notice
    bits.data_owner_notice()


    # Get/set operating hours
    hours_changed, OPENING_TIME, CLOSING_TIME = confirm_hours(
        PARKING_DATE, OPENING_TIME, CLOSING_TIME
    )
    if hours_changed:
        save()

    # Start tracking tags
    main()

    pr.set_echo(False)
# ==========================================
