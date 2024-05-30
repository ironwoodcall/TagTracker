#!/usr/bin/env python3

"""This is the data entry module for the TagTracker suite.

Its configuration file is tagtracker_config.py.

Copyright (C) 2023-2024 Todd Glover & Julias Hocking

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

# from tt_realtag import Stay
from tt_time import VTime
import tt_util as ut
import tt_trackerday as td
from tt_trackerday import TrackerDay, TrackerDayError
from tt_bikevisit import BikeVisit
from tt_biketag import BikeTag, BikeTagError
import client_base_config as cfg
import tt_printer as pr
import tt_datafile as df
import tt_publish as pub
import tt_help

import tt_audit_report as aud

import tt_reports as rep
import tt_tag_inv as inv
# import tt_notes as notes

# from tt_cmdparse import CmdBits
from tt_commands import (
    CmdKeys,
    ParsedCommand,
    get_parsed_command,
    PARSED_OK,
    PARSED_CANCELLED,
    PARSED_EMPTY,
    COMMANDS,
)
import tt_call_estimator
import tt_registrations as reg
from tt_sounds import NoiseMaker
from tt_internet_monitor import InternetMonitorController
import tt_main_bits as bits

# The assignments below are unneccessary but stop pylint from whining.
publishment = None


def print_tag_inout(tag: TagID, inout: str, when: VTime) -> None:
    """Pretty-print a check-in or check-out message.

    This makes a one-line message only about the most recent visit.
    """

    when_msg = f"at {when.short}"  ##if when == VTime('now') else ""
    if inout == k.BIKE_IN:
        basemsg = f"Bike {tag} checked in {when_msg}"
        finalmsg = f"{basemsg:40} <---in---  "
    elif inout == k.BIKE_OUT:
        basemsg = f"Bike {tag} checked out {when_msg}"
        finalmsg = f"{basemsg:55} ---out--->  "
    else:
        ut.squawk(f"bad call to called print_tag_inout({tag}, {inout})")
        return
    # Print
    pr.iprint(finalmsg, style=k.ANSWER_STYLE)
    NoiseMaker.play(inout)


def deduce_parking_date(filename: str) -> str:
    """Guess what date the current data is for based on the filename.

    Logic:
        If current_guess is set (presumably read from the contents
        of the datafile) then it is used.
        Else if there appears to be a date embedded in the name of
        the datafile, it is used.
        Else today's date is used.
    """

    r = k.DATE_PART_RE.search(filename)
    if r:
        return f"{int(r.group(2)):04d}-{int(r.group(3)):02d}-" f"{int(r.group(4)):02d}"
    return ut.date_str("today")


def pack_day_data() -> td.OldTrackerDay:
    # FIXME: remove
    return td.OldTrackerDay()


def unpack_day_data(_: td.OldTrackerDay):
    # FIXME: remove
    pass


def edit_event(args: list, today: TrackerDay) -> bool:
    """Possibly edit a check in or check-out for one or more tags' latest visit.

    Will only edit events from the most recent visit for the tag(s).

    This can not be used to create a new check-in or check-out event
    (unlike earlier version of TagTracker). Use 'IN' or 'OUT' command
    with [time] argument for that.

    Its actions are restricted to the check in/out for the most recent
    visit with any given tagid, otherwise the intentino of the command
    would be ambiguous.

    On entry:
        args is list:
            0: list of one or more syntactically correct tagids
            1: what event: "i" or "o"
            2: a new time for the event
        today: is the current day's data

    Error conditions
        unusable time
        tagid not of a usable tag
        request is to edit an "in" when biketag status != IN_USE or DONE
        request is to edit an "out" when status != DONE

    """
    which = args[1]  # "i" or "o"
    if which not in {"i", "o"}:
        ut.squawk(f"Unexpected in/out value '{which}'")
        return False
    bike_time = args[2]
    if not bits.check_bike_time_reasonable(bike_time=bike_time, day=today):
        return False

    data_changed = False
    for tagid in args[0]:
        tagid: TagID
        try:
            if not bits.check_tagid_usable(tagid, today):
                continue

            biketag = today.biketags[tagid]
            if which == "i":
                if biketag.status not in {biketag.IN_USE, biketag.DONE}:
                    pr.iprint(
                        f"Tag {tagid.original} has no check-in to edit.",
                        style=k.WARNING_STYLE,
                    )
                    NoiseMaker.play(k.ALERT)
                    continue
                biketag.edit_in(bike_time)
                data_changed = True
                print_tag_inout(tagid, k.BIKE_IN, bike_time)

            elif which == "o":
                if biketag.status != biketag.DONE:
                    pr.iprint(
                        f"Tag {tagid.original} has no check-out available to edit.",
                        style=k.WARNING_STYLE,
                    )
                    NoiseMaker.play(k.ALERT)
                    continue
                biketag.edit_out(bike_time)
                data_changed = True
                print_tag_inout(tagid, k.BIKE_OUT, bike_time)

        except (BikeTagError, TrackerDayError) as e:
            pr.iprint(e, style=k.WARNING_STYLE)
            NoiseMaker.play(k.ALERT)
    return data_changed


def delete_event(args: list, today: TrackerDay) -> bool:
    """Possibly delete an event in most recent visit. Return True if data has changed.

    Will only delete from the most recent visit for the tag(s)

    On entry:
        args is list:
            0: list of one or more syntactically correct tagids
            1: what event: "i" or "o" (or "both"/"b")
            2: a confirmation "y" or "n"
        today: is the current day's data

    Error/cancellation conditions, for each tag
        confirmation is not "yes" (affects all tags)
        tagid not of a usable tag
        no visits with that tagid
        request is for "in" when there is already an "out"
        request is for "out" when there is no "out"
        request is for "both" when there is only "in" (maybe do that anyway)

    """
    data_changed = False
    if args[2] != "y":
        pr.iprint("Delete cancelled.", style=k.HIGHLIGHT_STYLE)
        return data_changed
    for tagid in args[0]:
        if not bits.check_tagid_usable(tagid, today):
            continue
        try:
            biketag: BikeTag = today.biketags[tagid]
            if biketag.status == biketag.UNUSED:
                pr.iprint(f"Tag '{tagid}' not used yet today.", style=k.WARNING_STYLE)
                NoiseMaker.play(k.ALERT)
                continue
            visit: BikeVisit = biketag.latest_visit()
            if args[1] == "i":
                if visit.time_out:
                    pr.iprint(
                        f"Can't delete '{tagid}' checkin, latest visit has a checkout.",
                        style=k.WARNING_STYLE,
                    )
                    NoiseMaker.play(k.ALERT)
                else:
                    biketag.delete_in()
                    pr.iprint(
                        f"Deleted check-in for latest {tagid} visit.",
                        style=k.ANSWER_STYLE,
                    )
                    data_changed = True
            elif args[1] == "o":
                if not visit.time_out:
                    pr.iprint(
                        f"Can't delete '{tagid}' checkout, latest visit has no checkout.",
                        style=k.WARNING_STYLE,
                    )
                    NoiseMaker.play(k.ALERT)

                else:
                    biketag.delete_out()
                    pr.iprint(
                        f"Deleted check-out for latest {tagid} visit.",
                        style=k.ANSWER_STYLE,
                    )
                    data_changed = True
        except (BikeTagError, TrackerDayError) as e:
            pr.iprint(e, style=k.WARNING_STYLE)
            NoiseMaker.play(k.ALERT)

    return data_changed


def check_in(args: list, today: TrackerDay) -> bool:
    """Check bike(s) in.

    On entry:
        args[0] is a list of syntactically correct tag(s)
        args[1] if present is a time to assign to the check-in
        today is the data for today
    On exit:
        error messages will have een given
        bikes will have been (maybe) checked in
        return is True if the data has changed.

    Errors to check for:
        - not a usable tag
        - tag already checked in
        - time is earlier than previous visit's check-out
        - time is super-early or super-late (> 1.5 hours outside open/close)


    """

    bike_time = VTime(args[1]) if len(args) > 1 else VTime("now")
    if not bits.check_bike_time_reasonable(bike_time=bike_time, day=today):
        return False

    data_changed = False
    for tagid in args[0]:
        tagid: TagID
        try:
            if not bits.check_tagid_usable(tagid, today):
                continue
            biketag = today.biketags[tagid]
            if biketag.status == biketag.IN_USE:
                pr.iprint(
                    f"Tag {tagid.original} already checked in.", style=k.WARNING_STYLE
                )
                NoiseMaker.play(k.ALERT)
                continue
            # Check this bike out at this time
            biketag.check_in(bike_time)
            data_changed = True
            print_tag_inout(tagid, k.BIKE_IN, bike_time)
        except (BikeTagError, TrackerDayError) as e:
            pr.iprint(e, style=k.WARNING_STYLE)
            NoiseMaker.play(k.ALERT)
    return data_changed


def check_out(args: list, today: TrackerDay) -> bool:
    """Check bike(s) out.

    On entry:
        args[0] is a list of syntactically correct tag(s)
        args[1] if present is a time to assign to the check-out
        today is the data for today
    On exit:
        error messages will have een given
        bikes will have been (maybe) checked out
        return is True if the data has changed.

    Errors to check for:
        - not a usable tag
        - latest visit for this tag is not checked in
        - time is earlier than check-in
        - time is super-early or super-late (> 1.5 hours outside open/close)

    """

    bike_time = VTime(args[1]) if len(args) > 1 else VTime("now")
    if not bits.check_bike_time_reasonable(bike_time=bike_time, day=today):
        return False

    data_changed = False
    for tagid in args[0]:
        tagid: TagID
        try:
            if not bits.check_tagid_usable(tagid, today):
                continue
            biketag = today.biketags[tagid]
            if biketag.status != biketag.IN_USE:
                pr.iprint(
                    f"Tag {tagid.original} not checked in.", style=k.WARNING_STYLE
                )
                NoiseMaker.play(k.ALERT)
                continue
            # Check this bike in at this time
            biketag.edit_out(bike_time)
            data_changed = True
            print_tag_inout(tagid, k.BIKE_OUT, bike_time)
        except (BikeTagError, TrackerDayError) as e:
            pr.iprint(e, style=k.WARNING_STYLE)
            NoiseMaker.play(k.ALERT)

    return data_changed


def guess_check_inout(args: list, today: TrackerDay) -> bool:
    """Check bike(s) in or out, guessing which is appropriate.

    On entry:
        args[0] is a list of syntactically correct tag(s)
        today is the data for today
    On exit:
        error messages will have been given
        bikes will have been (maybe) checked in or out
        return is True if the data has changed.

    Overview:
        If a tag is IN_USE, will check it out.
        If a tag is UNUSED, will check it in.
        If a tag is DONE, will error w/message to use "IN" to reuse tag.

    Errors to check for:
        - not a usable tag
        - DONE
        - latest visit for this tag is not checked in
        - time is earlier than check-in
        - time is super-early or super-late (> 1.5 hours outside open/close)

    """

    bike_time = VTime("now")
    if not bits.check_bike_time_reasonable(bike_time=bike_time, day=today):
        # In addition to default error message, add something helpful
        pr.iprint(
            f"Use {COMMANDS[CmdKeys.CMD_BIKE_IN].invoke[0].upper()} [tag] [time] or "
            "{COMMANDS[CmdKeys.CMD_BIKE_OUT].invoke[0].upper()} [tag] [time].",
            style=k.WARNING_STYLE,
        )
        return False

    data_changed = False
    for tagid in args[0]:
        tagid: TagID
        try:
            if not bits.check_tagid_usable(tagid, today):
                continue
            biketag = today.biketags[tagid]
            if biketag.status == biketag.DONE:
                pr.iprint(
                    f"Tag {tagid.original} already checked in and out. "
                    "To reuse this tag, use the 'IN' command.",
                    style=k.WARNING_STYLE,
                )
                NoiseMaker.play(k.ALERT)
                continue
            if biketag.status == biketag.UNUSED:
                # Check in.
                data_changed = check_in([[tagid], bike_time], today=today)
            elif biketag.status == biketag.IN_USE:
                data_changed = check_out([[tagid], bike_time], today=today)
        except (BikeTagError, TrackerDayError) as e:
            pr.iprint(e, style=k.WARNING_STYLE)
            NoiseMaker.play(k.ALERT)

    return data_changed


def query_command(day: TrackerDay, targets: list[TagID]) -> None:
    """Query one or more tags."""
    pr.iprint()
    for tagid in targets:
        msgs = []
        biketag: BikeTag = day.biketags[tagid]
        if biketag.status == biketag.UNUSED:
            msgs = [f"Tag {tagid} not used yet today."]
        elif biketag.status == biketag.RETIRED:
            msgs = [f"Tag {tagid} is retired."]
        else:
            msgs = []
            for i, visit in enumerate(biketag.visits, start=0):
                visit: BikeVisit
                msg = f"Tag {tagid} visit {i}: bike in at {visit.time_in.short}; "
                if visit.time_out:
                    msg += f"out at {visit.time_out.short}"
                else:
                    msg += "still on-site."
                msgs.append(msg)

        for msg in msgs:
            pr.iprint(msg, style=k.ANSWER_STYLE)


def set_tag_case(want_uppercase: bool) -> None:
    """Set tags to be uppercase or lowercase depending on 'command'."""
    ##global UC_TAGS  # pylint: disable=global-statement
    case_str = "upper case" if want_uppercase else "lower case"
    if TagID.uc() == want_uppercase:
        pr.iprint(f"Tags already {case_str}.", style=k.WARNING_STYLE)
        return
    TagID.uc(want_uppercase)
    pr.iprint(f" Tags will now show in {case_str}. ", style=k.ANSWER_STYLE)


def dump_data_command(today: TrackerDay, args: list):
    """For debugging. Dump current contents of TrackerDay object.

    on entry:
        today is TrackerDay object of this day's data
        args[0] if present might be the string 'full'
    """

    if args and args[0] not in ["full", "f", "detailed", "detail"]:
        pr.iprint(f"Unknown parameter '{args[0]}'\nDUMP [full]")
        return
    detailed = bool(args)

    pr.iprint()
    pr.iprint("TrackerDay:", num_indents=0, style=k.ERROR_STYLE)
    info = today.dump(detailed=detailed)
    for l in info:
        pr.iprint(l)

    pr.iprint("Config:", num_indents=0, style=k.ERROR_STYLE)
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


def estimate(today:TrackerDay) -> None:
    """Estimate how many more bikes.
    # Args:
    #     bikes_so_far: default current bikes so far
    #     as_of_when: default right now
    #     dow: default today (else 1..7 or a date)
    #     closing_time: default - today's closing time
    """
    pr.iprint()
    pr.iprint("Estimating...")
    # time.sleep(1)
    message_lines = tt_call_estimator.get_estimate_via_url(today)
    if not message_lines:
        message_lines = ["Nothing returned, don't know why. Sorry."]
    pr.iprint()
    for i, line in enumerate(message_lines):
        if i == 0:
            pr.iprint(line, style=k.TITLE_STYLE)
        else:
            pr.iprint(line)
    pr.iprint()


def bikes_on_hand_reminder(day: TrackerDay) -> None:
    """Remind how many bikes should be present, if close to closing time."""
    if day.closing_time.num - VTime("now").num < 60:  # last hour
        num_bikes = len(day.tags_in_use("now"))
        pr.iprint(
            f"There should currently be {num_bikes} {ut.plural(num_bikes,'bike')}"
            " here.",
            style=k.HIGHLIGHT_STYLE,
        )


def process_command(cmd_bits: ParsedCommand, today: TrackerDay) -> bool:
    """Process the command.  Return True if data has (probably) changed."""

    if cmd_bits.status == PARSED_EMPTY:
        return False

    if cmd_bits.status != PARSED_OK:
        ut.squawk(
            f"Unexpected {cmd_bits.status=},{cmd_bits.command=},{cmd_bits.result_args=}"
        )
        return False

    # Even though 'OK', there might still be a message (e.g. warning of duplicate
    # tagids in list)
    if cmd_bits.message:
        pr.iprint(cmd_bits.message, style=k.WARNING_STYLE)

    # These are for convenience
    cmd = cmd_bits.command
    args = cmd_bits.result_args

    # Assume no change in data unless we find out otherwise.
    data_changed = False
    # Easy things
    if cmd == CmdKeys.CMD_EXIT:
        return
    elif cmd == CmdKeys.CMD_HELP:
        tt_help.help_command(args)

    # Things that can change data
    elif cmd == CmdKeys.CMD_DEBUG:
        cfg.DEBUG = args[0]
        pr.iprint(f"DEBUG is now {cfg.DEBUG}")
    elif cmd == CmdKeys.CMD_DELETE:
        # Delete a check-in or check-out
        data_changed = delete_event(args=args, today=today)
    elif cmd == CmdKeys.CMD_BIKE_IN:
        # Check a bike in, possibly reusing a tag.
        data_changed = check_in(args=args, today=today)
    elif cmd == CmdKeys.CMD_BIKE_OUT:
        # Check a bike out. Hard to imagine anyone even using this command.
        data_changed = check_out(args=args, today=today)
    elif cmd == CmdKeys.CMD_BIKE_INOUT:
        # Guess whether to check a bike in or out; will not reuse a tag.
        data_changed = guess_check_inout(args=args, today=today)
    elif cmd == CmdKeys.CMD_EDIT:
        data_changed = edit_event(args=args, today=today)

    elif cmd_bits.command == CmdKeys.CMD_REGISTRATIONS:
        # FIXME: should really adjust the count in trackerday
        # so that don't have to do side-effect changes to it
        # when change one day to another.
        if reg.Registrations.process_registration("".join(args)):
            today.registrations = reg.Registrations.num_registrations
            data_changed = True


    elif cmd_bits.command == CmdKeys.CMD_HOURS:
        # FIXME: this is done but needs testing
        data_changed = bits.confirm_hours(today=today)

    # Information and reports
    elif cmd_bits.command == CmdKeys.CMD_QUERY:
        # Done. FIXME
        query_command(day=today, targets=args[0])

    elif cmd_bits.command == CmdKeys.CMD_AUDIT:
        aud.audit_report(today, cmd_bits.result_args, include_returns=True)
        publishment.publish_audit(today, cmd_bits.result_args)
    elif cmd_bits.command == CmdKeys.CMD_RECENT:
        rep.recent(today, args)

    elif cmd_bits.command == CmdKeys.CMD_TAGS:
        inv.tags_config_report(today, args, False)


    # elif cmd_bits.command == CmdKeys.CMD_NOTES:
    #     if cmd_bits.result_args:
    #         # FIXME: Notes needs to be a list in TrackerDay
    #         # not a standalone thingy.
    #         notes.Notes.add(cmd_bits.tail)
    #         pr.iprint("Noted.")
    #     else:
    #         bits.show_notes(notes.Notes, header=True, styled=False)



    # # Things that operate on the larger environment
    # elif cmd_bits.command == CmdKeys.CMD_PUBLISH:
    #     # FIXME: this call is ok, still need to adjust publish_*
    #     publishment.publish_reports(day=today, args=args)



    elif cmd_bits.command == CmdKeys.CMD_STATS:
        rep.day_end_report(day=today, args=args)
        # Force publication when do day-end reports
        publishment.publish(pack_day_data())
        ##last_published = maybe_publish(last_published, force=True)


    # elif cmd_bits.command == CmdKeys.CMD_BUSY:
    #     rep.busyness_report(pack_day_data(), cmd_bits.result_args)
    # elif cmd_bits.command == CmdKeys.CMD_CHART:
    #     rep.full_chart(pack_day_data())
    # elif cmd_bits.command == CmdKeys.CMD_BUSY_CHART:
    #     rep.busy_graph(pack_day_data())
    # elif cmd_bits.command == CmdKeys.CMD_FULL_CHART:
    #     rep.fullness_graph(pack_day_data())
    elif cmd == CmdKeys.CMD_DUMP:
        # Done. Probably. FIXME
        dump_data_command(today=today, args=args)
    elif cmd_bits.command == CmdKeys.CMD_LINT:
        # FIXME: this is done
        lint_report(today=today, strict_datetimes=True, chatty=True)
    elif cmd_bits.command == CmdKeys.CMD_ESTIMATE:
         estimate(today=today)


    elif cmd in {CmdKeys.CMD_UPPERCASE, CmdKeys.CMD_LOWERCASE}:
        # Change to uc or lc tags
        set_tag_case(cmd == CmdKeys.CMD_UPPERCASE)

    else:
        # An unhandled command
        pr.iprint(f"Command {cmd.upper()} is not available.")

    return data_changed


def main_loop(today: TrackerDay):
    """Run main program command loop."""

    done = False
    todays_date = ut.date_str("today")
    while not done:
        pr.iprint()
        # Nag about bikes expected to be present if close to closing time
        bikes_on_hand_reminder(day=today)
        # Allow tag notes for this next command
        pr.print_tag_notes("", reset=True)
        # Break command into tokens, parse as command
        cmd_bits = get_parsed_command()
        # If midnight has passed then need to restart
        if midnight_passed(todays_date):
            if not cmd_bits.command or cmd_bits.command != CmdKeys.CMD_EXIT:
                midnight_message()
            done = True
            continue
        # If null input, just ignore
        if cmd_bits.status != PARSED_OK:
            continue  # No input, ignore

        # Dispatcher
        # Each command can take the ParsedCommand as its argument
        # Or, the dispatcher
        data_changed = False
        if cmd_bits.command == CmdKeys.CMD_EXIT:
            done = True
        elif cmd_bits.status == PARSED_OK:
            data_changed = process_command(cmd_bits=cmd_bits, today=today)

        # If any time has becomne "24:00" change it to "23:59" (I forget why)
        if data_changed and today.fix_2400_events():
            pr.iprint(
                "(Changed any '24:00' check-in/out times to '23:59'.)",
                style=k.WARNING_STYLE,
            )

        # Save if anything has changed
        if data_changed:
            data_changed = False
            today.save_to_file()
            publishment.maybe_publish(today)
            ##last_published = maybe_publish(last_published)
        # Flush any echo buffer
        pr.echo_flush()
    # Exiting; one last  publishing
    publishment.publish(today)


def custom_datafile() -> str:
    """Return filepath of  custom datafilename specified.

    Returns custom filepath if given, "" if not.
    File is checked to exist.
    """
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


def error_exit() -> None:
    """If an error has occurred, give a message and shut down.

    Any specific info about the error should already have been printed.
    """
    pr.iprint()
    pr.iprint("Closing in 30 seconds", style=k.ERROR_STYLE)
    time.sleep(30)
    exit()


def lint_report(
    today: TrackerDay, strict_datetimes: bool = True, chatty: bool = False
) -> bool:
    """Check tag lists and event lists for consistency.

    If chatty, does this as a report - otherwise as an eruption of errors.

    Returns True if errors were detected.
    """
    if chatty:
        style = k.NORMAL_STYLE
    else:
        style = k.WARNING_STYLE

    errs = today.lint_check(strict_datetimes)
    if errs:
        for msg in errs:
            pr.iprint(msg, style=style)
    elif chatty:
        pr.iprint("Lint check found no inconsistencies.", style=k.SUBTITLE_STYLE)

    return bool(errs)


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


# def get_taglists_from_old_config(old_config_file: str) -> td.OldTrackerDay:
#     """Read tag lists (oversize, etc) from tag config file."""
#     # Lists of normal, oversize, retired tags
#     # Return a OldTrackerDay object, though its bikes_in/out are meaningless.
#     errs = []
#     day = df.read_datafile(old_config_file, errs)
#     if errs:
#         print(f"Errors in file, {errs=}")
#         error_exit()
#     pr.iprint()
#     pr.iprint(
#         f"Using tag configurations from deprecated '{old_config_file}' configuration file.",
#         style=k.ERROR_STYLE,
#     )
#     pr.iprint(
#         "Define tag configurations in client_local_config.py.",
#         style=k.ERROR_STYLE,
#     )
#     return day


def set_up_today() -> TrackerDay:
    """Initialize today's tracking data."""

    datafilepath = custom_datafile()
    datafilepath = datafilepath or df.datafile_name(cfg.DATA_FOLDER)
    if os.path.exists(datafilepath):
        day = TrackerDay.load_from_file(datafilepath)
    else:
        day = TrackerDay(
            datafilepath, site_label=cfg.SITE_LABEL, site_name=cfg.SITE_NAME
        )
    # Just in case there's no date, guess it from the filename
    if not day.date:
        day.date = deduce_parking_date(datafilepath)

    # Set the site name
    day.site_name = day.site_name or cfg.SITE_NAME

    # Find the tag reference lists (regular, oversize, etc).
    # If there's no tag reference lists, or it's today's date,
    # then fetch the tag reference lists from tags config
    if day.date == ut.date_str("today") or (
        not day.regular_tagids and not day.oversize_tagids
    ):
        try:
            day.set_taglists_from_config()
        except TrackerDayError as e:
            pr.iprint()
            for text in e.args:
                pr.iprint(text, style=k.ERROR_STYLE)
            error_exit()

    pr.iprint(
        f"Editing {day.site_name} bike parking data for {ut.date_str(day.date,long_date=True)}.",
        style=k.HIGHLIGHT_STYLE,
    )
    # In case doing a date that's not today, warn
    if day.date != ut.date_str("today"):
        pr.iprint(f"Warning: Data is from {day.date}, not today", style=k.ERROR_STYLE)

    # Get/set operating hours
    bits.confirm_hours(day)

    # Look for inconsistencies
    if lint_report(today=day, strict_datetimes=True):
        error_exit()

    # Save
    day.save_to_file()

    return day


if __name__ == "__main__":

    # Set up TagTracker system

    # Set colour module's colour flag based on config
    pr.COLOUR_ACTIVE = cfg.USE_COLOUR

    # Possibly turn on echo. Print any error msgs later, though
    echo_msg = ""
    if cfg.ECHO:
        if not cfg.ECHO_FOLDER:
            echo_msg = "No echo folder configured, setting echo off."
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
    # Start internet monitoring (if enabled in config)
    InternetMonitorController.start_monitor()

    # Initialize today's tracking data
    today_data = set_up_today()

    # Display data owner notice
    bits.data_owner_notice()

    # Set UC if needed (NB: datafiles are always LC)
    TagID.uc(cfg.TAGS_UPPERCASE)

    # Start tracking tags
    main_loop(today_data)

    # Finished, turn off echo
    pr.set_echo(False)
# ==========================================
