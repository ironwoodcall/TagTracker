#!/usr/bin/env python3

"""Process one user command.

Its configuration file is tagtracker_config.py.

Copyright (C) 2023-2025 Todd Glover & Julias Hocking

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


# pylint: disable=wrong-import-position
import common.tt_constants as k
from typing import Optional, List
from common.tt_tag import TagID

# from tt_realtag import Stay
from common.tt_time import VTime
import common.tt_util as ut
from common.tt_trackerday import TrackerDay, TrackerDayError
from common.tt_bikevisit import BikeVisit
from common.tt_biketag import BikeTag, BikeTagError
from common.tt_daysummary import DaySummary
import client_base_config as cfg
import tt_notes_command
import tt_printer as pr
import tt_publish as pub
import tt_help
import tt_audit_report as aud
import tt_reports as rep
import tt_tag_inv as inv
import tt_retire

# from tt_cmdparse import CmdBits
from tt_commands import (
    CmdKeys,
    ParsedCommand,
    PARSED_OK,
    PARSED_EMPTY,
    COMMANDS,
)
import tt_call_estimator
from tt_sounds import NoiseMaker
import tt_main_bits as bits
from tt_internet_monitor import InternetMonitorController


def print_tag_inout(biketag: BikeTag, inout: str, when: VTime) -> None:
    """Pretty-print a check-in or check-out message.

    This makes a one-line message only about the most recent visit.
    """
    tag = biketag.tagid
    visit = biketag.latest_visit()

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
    # Print any note(s)
    # visit = biketag.find_visit(when)
    ut.squawk(f"{visit.tagid=},{visit.attached_notes=}",cfg.DEBUG)
    for note_str in visit.active_note_strings():
        pr.iprint(f"    {note_str}", style=k.WARNING_STYLE)
    NoiseMaker.queue_add(inout)


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
                NoiseMaker.queue_add(k.ALERT)
                continue

            biketag = today.biketags[tagid]
            if which == "i":
                if biketag.status not in {biketag.IN_USE, biketag.DONE}:
                    pr.iprint(
                        f"Tag {tagid.original} has no check-in to edit.",
                        style=k.WARNING_STYLE,
                    )
                    NoiseMaker.queue_add(k.ALERT)
                    continue
                biketag.edit_in(bike_time)
                data_changed = True
                print_tag_inout(biketag, k.BIKE_IN, bike_time)

            elif which == "o":
                if biketag.status != biketag.DONE:
                    pr.iprint(
                        f"Tag {tagid.original} has no check-out available to edit.",
                        style=k.WARNING_STYLE,
                    )
                    NoiseMaker.queue_add(k.ALERT)
                    continue
                biketag.edit_out(bike_time)
                data_changed = True
                print_tag_inout(biketag, k.BIKE_OUT, bike_time)

        except (BikeTagError, TrackerDayError) as e:
            pr.iprint(e, style=k.WARNING_STYLE)
            NoiseMaker.queue_add(k.ALERT)

    # NoiseMaker.queue_play()

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
            NoiseMaker.queue_add(k.ALERT)
            continue
        try:
            biketag: BikeTag = today.biketags[tagid]
            if biketag.status == biketag.UNUSED:
                pr.iprint(f"Tag '{tagid}' not used yet today.", style=k.WARNING_STYLE)
                NoiseMaker.queue_add(k.ALERT)
                continue
            visit: BikeVisit = biketag.latest_visit()
            if args[1] == "i":
                if visit.time_out:
                    pr.iprint(
                        f"Can't delete '{tagid}' checkin, latest visit has a checkout.",
                        style=k.WARNING_STYLE,
                    )
                    NoiseMaker.queue_add(k.ALERT)
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
                    NoiseMaker.queue_add(k.ALERT)

                else:
                    biketag.delete_out()
                    pr.iprint(
                        f"Deleted check-out for latest {tagid} visit.",
                        style=k.ANSWER_STYLE,
                    )
                    data_changed = True
            # Add any applicable note(s)
            if data_changed:
                for note_str in visit.active_note_strings():
                    pr.iprint(f"    {note_str}", style=k.WARNING_STYLE)
        except (BikeTagError, TrackerDayError) as e:
            pr.iprint(e, style=k.WARNING_STYLE)
            NoiseMaker.queue_add(k.ALERT)

    # NoiseMaker.queue_play()
    return data_changed


def check_in(args: list, today: TrackerDay) -> bool:
    """Check bike(s) in.

    On entry:
        args[0] is a list of syntactically correct tag(s)
        args[1] if present is a time to assign to the check-in
        today is the data for today
    On exit:
        error messages will have been given
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
                NoiseMaker.queue_add(k.ALERT)
                continue
            biketag = today.biketags[tagid]
            if biketag.status == biketag.IN_USE:
                pr.iprint(f"Tag {tagid} already checked in.", style=k.WARNING_STYLE)
                NoiseMaker.queue_add(k.ALERT)
                continue
            # Check this bike out at this time
            biketag.check_in(bike_time)
            data_changed = True
            print_tag_inout(biketag, k.BIKE_IN, bike_time)
        except (BikeTagError, TrackerDayError) as e:
            pr.iprint(e, style=k.WARNING_STYLE)
            NoiseMaker.queue_add(k.ALERT)

    # NoiseMaker.queue_play()
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
                NoiseMaker.queue_add(k.ALERT)
                continue
            biketag = today.biketags[tagid]
            if biketag.status != biketag.IN_USE:
                pr.iprint(
                    f"Tag {tagid.original} not checked in.", style=k.WARNING_STYLE
                )
                NoiseMaker.queue_add(k.ALERT)
                continue
            # Check this bike in at this time
            biketag.edit_out(bike_time)
            data_changed = True
            print_tag_inout(biketag, k.BIKE_OUT, bike_time)
        except (BikeTagError, TrackerDayError) as e:
            pr.iprint(e, style=k.WARNING_STYLE)
            NoiseMaker.queue_add(k.ALERT)

    # NoiseMaker.queue_play()
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
                NoiseMaker.queue_add(k.ALERT)
                continue
            biketag = today.biketags[tagid]
            if biketag.status == biketag.DONE:
                pr.iprint(
                    f"Tag {tagid} already checked in and out. "
                    "To reuse this tag, use the 'IN' command.",
                    style=k.WARNING_STYLE,
                )
                NoiseMaker.queue_add(k.ALERT)
                continue
            if biketag.status == biketag.UNUSED:
                # Check in.
                data_changed = check_in([[tagid], bike_time], today=today)
            elif biketag.status == biketag.IN_USE:
                data_changed = check_out([[tagid], bike_time], today=today)
        except (BikeTagError, TrackerDayError) as e:
            pr.iprint(e, style=k.WARNING_STYLE)
            NoiseMaker.queue_add(k.ALERT)

    # NoiseMaker.queue_play()
    return data_changed


def query_command(day: TrackerDay, targets: list[TagID]) -> None:
    """Query one or more tags."""
    pr.iprint()
    for tagid in targets:
        msgs = []
        if tagid not in day.biketags:
            msgs = [f"Tag {tagid} unknown."]
        else:
            biketag: BikeTag = day.biketags[tagid]
            if biketag.status == biketag.UNUSED:
                msgs = [f"Tag {tagid} not used yet today."]
            elif biketag.status == biketag.RETIRED:
                msgs = [f"Tag {tagid} is retired."]
            else:
                msgs = []
                for i, visit in enumerate(biketag.visits, start=1):
                    visit: BikeVisit
                    msg = f"Tag {tagid} visit {i}: bike in at {visit.time_in.tidy}; "
                    if visit.time_out:
                        msg += f"out at {visit.time_out.tidy}"
                    else:
                        msg += "still on-site."
                    msgs.append(msg)
                    for note_str in visit.active_note_strings():
                        msgs.append(f"    {note_str}")

        for msg in msgs:
            pr.iprint(msg, style=k.ANSWER_STYLE)


def leftovers_query(today: TrackerDay):
    """List last check-in times for any bikes on-site."""

    msgs = {}
    # leftover_checkin has tuples of (tagid,check-in time), for sorting.
    leftover_checkin = []

    for tagid in today.tags_in_use(as_of_when="now"):
        bike = today.biketags[tagid]
        msgs[tagid] = ""
        if not bike.visits:
            msgs[tagid] += " logic error"
            continue
        last_visit: BikeVisit = bike.visits[-1]
        msgs[tagid] += f"  Visit: {len(bike.visits)}  In: {last_visit.time_in}"
        if last_visit.time_out:
            msgs[tagid] += f"  Out: {last_visit.time_out}"

        leftover_checkin.append((tagid, last_visit.time_in))

    # Sort by check-in times
    leftover_checkin.sort(key=lambda x: x[1])

    pr.iprint()
    pr.iprint("Most recent check-in times for bikes left on-site", style=k.ANSWER_STYLE)
    if not msgs:
        pr.iprint("No bikes on-site")
        return

    max_tagid_len = max([len(tagid) for tagid in msgs])
    for tagid, _ in leftover_checkin:
        msgs[tagid] = (
            f"{tagid.upper()}" + " " * (max_tagid_len - len(tagid)) + msgs[tagid]
        )
        pr.iprint(msgs[tagid], style=k.NORMAL_STYLE)
        bike = today.biketags[tagid]
        last_visit: BikeVisit = bike.visits[-1]
        if not last_visit.time_out:
            for note_str in last_visit.active_note_strings():
                pr.iprint(note_str, num_indents=3, style=k.NORMAL_STYLE)


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
        args[0] if present might be the string 'verbose'
    """

    verbose = False

    if args:
        choice = str(args[0]).strip().lower()
        if choice not in {"verbose", "v"}:
            pr.iprint(f"Unknown parameter '{args[0]}'\nDUMP [verbose]")
            return
        verbose = True

    pr.iprint()
    summary_lines = today.dump(detailed=verbose)
    for idx, line in enumerate(summary_lines):
        style = k.ERROR_STYLE if idx == 0 else k.NORMAL_STYLE
        pr.iprint(line, style=style)

    if verbose:
        pr.iprint()
        pr.iprint("DaySummary (verbose):", num_indents=0, style=k.ERROR_STYLE)
        for line in str(DaySummary(today)).splitlines():
            pr.iprint(line)


def estimate(today: TrackerDay, args: Optional[List[str]] = None) -> None:
    """Estimate how many more bikes.
    # Args:
    #     bikes_so_far: default current bikes so far
    #     as_of_when: default right now
    #     dow: default today (else 1..7 or a date)
    #     time_closed: default - today's closing time
    """
    pr.iprint()
    pr.iprint("Estimating...")
    # Always call the estimator via URL (DB lives on server)
    # Optional args:
    #   STANDARD -> same as default (current)
    #   LEGACY|OLD -> legacy estimator
    #   FULL|VERBOSE -> verbose output
    choice = (args[0].strip().upper() if args else "") if args else ""
    allowed = {"", "STANDARD", "FULL", "F", "VERBOSE", "V", "VER", "SCHEDULE", "QUICK"}
    if args and choice not in allowed:
        pr.iprint(f"Unrecognized ESTIMATE parameter '{args[0]}'", style=k.WARNING_STYLE)
        return
    estimation_type = "standard"
    if choice in {"FULL", "VERBOSE", "F", "VER", "V"}:
        estimation_type = "verbose"
    elif choice in {"SCHEDULE", "QUICK"}:
        estimation_type = choice.lower()

    # STANDARD or empty uses default 'current'
    message_lines: List[str] = tt_call_estimator.get_estimate_via_url(
        today, estimation_type=estimation_type
    )
    if not message_lines:
        message_lines = ["Nothing returned, don't know why. Sorry."]
    pr.iprint()
    for i, line in enumerate(message_lines):
        if i == 0:
            pr.iprint(line, style=k.TITLE_STYLE)
        else:
            pr.iprint(line)
    pr.iprint()


def process_command(
    cmd_bits: ParsedCommand, today: TrackerDay, publishment: pub.Publisher
) -> bool:
    """Process the command.  Return True if data has (probably) changed."""

    NoiseMaker.queue_reset()

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

    # This huge ladder of commands is in aphabetical order
    # in order to make it easy to confirm against the list of
    # command configurations.
    if cmd == CmdKeys.CMD_AUDIT:
        aud.audit_report(today, cmd_bits.result_args, include_returns=True)
        publishment.publish_audit(today, cmd_bits.result_args)
    elif cmd == CmdKeys.CMD_BIKE_IN:
        # Check a bike in, possibly reusing a tag.
        data_changed = check_in(args=args, today=today)
    elif cmd == CmdKeys.CMD_BIKE_INOUT:
        # Guess whether to check a bike in or out; will not reuse a tag.
        data_changed = guess_check_inout(args=args, today=today)
    elif cmd == CmdKeys.CMD_BIKE_OUT:
        # Check a bike out. Hard to imagine anyone even using this command.
        data_changed = check_out(args=args, today=today)
    # elif cmd == CmdKeys.CMD_BUSY:
    #     pr.iprint(
    #         "'BUSY' command is now part of 'STATS' command.", style=k.WARNING_STYLE
    #     )
    elif cmd == CmdKeys.CMD_CHART:
        rep.full_chart(day=today)
    elif cmd == CmdKeys.CMD_DEBUG:
        cfg.DEBUG = args[0]
        InternetMonitorController.set_debug(args[0])
        pr.iprint(f"DEBUG is now {cfg.DEBUG}")
    elif cmd == CmdKeys.CMD_DELETE:
        # Delete a check-in or check-out
        data_changed = delete_event(args=args, today=today)
    elif cmd == CmdKeys.CMD_DUMP:
        dump_data_command(today=today, args=args)
    elif cmd == CmdKeys.CMD_EDIT:
        data_changed = edit_event(args=args, today=today)
    elif cmd == CmdKeys.CMD_ESTIMATE:
        estimate(today=today, args=args)
    elif cmd == CmdKeys.CMD_EXIT:
        return False
    # elif cmd == CmdKeys.CMD_FULL_CHART:
    #     rep.fullness_graph(pack_day_data())
    elif cmd == CmdKeys.CMD_GRAPHS:
        when = args[0] if args else ""
        rep.busy_graph(day=today, as_of_when=when)
        rep.fullness_graph(day=today, as_of_when=when)
    elif cmd == CmdKeys.CMD_HELP:
        tt_help.help_command(args)
    elif cmd == CmdKeys.CMD_HOURS:
        data_changed = bits.confirm_hours(today=today)
    elif cmd == CmdKeys.CMD_LEFTOVERS:
        leftovers_query(today=today)
    elif cmd == CmdKeys.CMD_LINT:
        lint_report(today=today, strict_datetimes=True, chatty=True)
    elif cmd == CmdKeys.CMD_MONITOR:
        if args[0]:  # True
            InternetMonitorController.monitor_on()
            pr.iprint("(Re)activating internet monitoring.")
        else:
            monitor_delay = 120
            InternetMonitorController.monitor_off(monitor_delay)
            pr.iprint(f"Suppressing internet monitoring for {monitor_delay} minutes.")
    elif cmd == CmdKeys.CMD_NOTES:
        data_changed = tt_notes_command.notes_command(notes_list=today.notes, args=args)
    elif cmd == CmdKeys.CMD_PUBLISH:
        publishment.publish_reports(day=today, args=args, mention=True)
    elif cmd == CmdKeys.CMD_QUERY:
        query_command(day=today, targets=args[0])
    elif cmd == CmdKeys.CMD_RECENT:
        rep.recent(today, args)
    elif cmd == CmdKeys.CMD_REGISTRATIONS:
        if today.registrations.process_registration("".join(args)):
            data_changed = True
    elif cmd == CmdKeys.CMD_RETIRE:
        data_changed = tt_retire.retire(today=today, tags=args[0])
    elif cmd == CmdKeys.CMD_STATS:
        rep.summary_report(day=today, args=args)
        # Force publication when do day-end reports
        publishment.publish(day=today)
        ##last_published = maybe_publish(last_published, force=True)
    elif cmd == CmdKeys.CMD_TAGS:
        inv.tags_config_report(today, args, False)
    elif cmd == CmdKeys.CMD_UNRETIRE:
        data_changed = tt_retire.unretire(today=today, tags=args[0])
    elif cmd in {CmdKeys.CMD_UPPERCASE, CmdKeys.CMD_LOWERCASE}:
        # Change to uc or lc tags
        set_tag_case(cmd == CmdKeys.CMD_UPPERCASE)
    else:
        # An unhandled command
        canonical_invocation = COMMANDS[cmd].invoke[0].upper()
        pr.iprint(f"Command {canonical_invocation} is not available.")
        NoiseMaker.queue_add(k.ALERT)

    # Note autodelete is handled in main loop after tag-note printing

    NoiseMaker.queue_play()
    return data_changed


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
