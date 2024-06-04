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
import tt_reports as rep
# from tt_realtag import Stay
from tt_time import VTime
import tt_util as ut
from tt_trackerday import TrackerDay, TrackerDayError
import client_base_config as cfg
import tt_printer as pr
import tt_datafile as df
import tt_publish as pub

# import tt_notes as notes
from tt_process_command import process_command, lint_report

# from tt_cmdparse import CmdBits
from tt_commands import (
    CmdKeys,
    get_parsed_command,
    PARSED_OK,
    tags_arg
)
from tt_sounds import NoiseMaker
from tt_internet_monitor import InternetMonitorController
import tt_main_bits as bits

# The assignments below are unneccessary but stop pylint from whining.
publishment = None


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


def bikes_on_hand_reminder(day: TrackerDay) -> None:
    """Remind how many bikes should be present, if close to closing time."""
    if day.closing_time.num - VTime("now").num < 60:  # last hour
        num_bikes = len(day.tags_in_use("now"))
        pr.iprint(
            f"There should currently be {num_bikes} {ut.plural(num_bikes,'bike')}"
            " here.",
            style=k.HIGHLIGHT_STYLE,
        )


def main_loop(today: TrackerDay):
    """Run main program command loop."""

    done = False
    todays_date = ut.date_str("today")
    while not done:
        pr.iprint()
        # Nag about bikes expected to be present if close to closing time
        bikes_on_hand_reminder(day=today)
        # # Allow tag notes for this next command
        # rep.print_tag_notes(today,"", reset=True)

        # Get a command from the user.
        cmd_bits = get_parsed_command()
        # Exit if exit
        if cmd_bits.command == CmdKeys.CMD_EXIT:
            break
        # If midnight has passed then need to restart
        if midnight_passed(todays_date):
            midnight_message()
            break
        # If null input, just ignore
        if cmd_bits.status != PARSED_OK:
            continue  # No input, ignore

        # Process the command
        data_changed = False
        if cmd_bits.status == PARSED_OK:
            data_changed = process_command(
                cmd_bits=cmd_bits, today=today, publishment=publishment
            )
            # Print any notes particularly associated with tag(s) in this command.
            tag_arg = tags_arg(cmd_bits.command)
            if tag_arg is not None:
                for tag in cmd_bits.result_args[tag_arg]:
                    rep.print_tag_notes(today,tag)

        # If any time has becomne "24:00" change it to "23:59" (I forget why)
        if data_changed and today.fix_2400_events():
            pr.iprint(
                "(Changed any '24:00' check-in/out times to '23:59'.)",
                style=k.WARNING_STYLE,
            )

        # Save if any data has changed
        if data_changed:
            today.save_to_file()
            data_changed = False
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



def set_taglists_from_config(day:TrackerDay):
    """Assign oversize, regular, and retired tag IDs from config."""

    day.regular_tagids, errors = TagID.parse_tagids_str(
        cfg.REGULAR_TAGS, "REGULAR_TAGS configuration"
    )
    day.oversize_tagids, errs = TagID.parse_tagids_str(
        cfg.OVERSIZE_TAGS, "OVERSIZE_TAGS configuration"
    )
    errors += errs
    day.retired_tagids, errs = TagID.parse_tagids_str(
        cfg.RETIRED_TAGS, "RETIRED_TAGS configuration"
    )
    errors += errs
    if errors:
        raise TrackerDayError(*errors)

    overlap = day.regular_tagids.intersection(day.oversize_tagids)
    if overlap:
        raise TrackerDayError(
            f"These tags are configured as both regular and oversize:\n{overlap}"
        )

    if not day.regular_tagids and not day.oversize_tagids:
        raise TrackerDayError("Configuration file defines to tags.")

    day.determine_tagids_conformity()
    # FIXME: Is this the right place for this? I don't think so.
    if not day.biketags:
        day.initialize_biketags()



def error_exit() -> None:
    """If an error has occurred, give a message and shut down.

    Any specific info about the error should already have been printed.
    """
    pr.iprint()
    pr.iprint("Closing in 30 seconds", style=k.ERROR_STYLE)
    time.sleep(30)
    exit()


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
        try:
            day = TrackerDay.load_from_file(datafilepath)
        except TrackerDayError as e:
            for s in e.args:
                pr.iprint(s,style=k.ERROR_STYLE)
            error_exit()
    else:
        day = TrackerDay(
            datafilepath, site_handle=cfg.SITE_HANDLE, site_name=cfg.SITE_NAME
        )
    # Just in case there's no date, guess it from the filename
    if not day.date:
        day.date = deduce_parking_date(datafilepath)

    # Set some bits, if missing
    day.fill_default_bits(site_name = cfg.SITE_NAME,site_handle=cfg.SITE_HANDLE)

    # Find the tag reference lists (regular, oversize, etc).
    # If there's no tag reference lists, or it's today's date,
    # then fetch the tag reference lists from tags config
    if day.date == ut.date_str("today") or (
        not day.regular_tagids and not day.oversize_tagids
    ):
        ut.squawk("Setting taglists from config",cfg.DEBUG)
        try:
            set_taglists_from_config(day)
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
    if lint_report(today=day, strict_datetimes=True, chatty=False):
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
            echo_msg = (
                f"Echo folder '{cfg.ECHO_FOLDER}' "
                "missing or not writeable, setting echo off."
            )
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
