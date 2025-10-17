"""Config for TagTracker by Julias Hocking.

Configuration items for the data entry module.

This module sets configs then overrides with any same-named
values that are set in tt_local_config

Copyright (C) 2023-2025 Julias Hocking & Todd Glover

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
import sys
import re

###########################################################
#            BEGINNING OF CONFIG SECTION                  #
# To make a new client_local_config.py configuration file,#
# copy from here down to "END OF CONFIG SECTION" and put  #
# it into a new file called "client_local_config.py"      #
# in the same directory as this file.                     #
###########################################################

# Screen appearance
SCREEN_WIDTH = 80  # characters
USE_COLOUR = True
CURSOR = ">>> "
INCLUDE_TIME_IN_PROMPT = True
TAGS_UPPERCASE = False

# data owner -- If set, this notice will display when tagtraacker starts.
# This can be a string, or if a list of strings, displays as multiple lines.
DATA_OWNER = ""

# Things related to playing sounds (client only)
SOUND_PLAYER = "mpg321"  # If not full filepath then this needs to be on PATH
# Sound file locations are relative to the python files dir
SOUND_BIKE_IN = "sounds/bike-in.mp3"
SOUND_BIKE_OUT = "sounds/bike-out.mp3"
SOUND_ALERT = "sounds/alert.mp3"
SOUND_CHEER = "sounds/cheer"
# This flag can set the (initial) state of whether sounds are enabled
SOUND_ENABLED = True

# This tells TT how often to check for an active internet connection (minutes).
# If set to 0 (or anything else that evalues False), no monitoring is done.
INTERNET_MONITORING_FREQUENCY = 10
INTERNET_LOG_FOLDER = ""    # Folder for log of internet checks

# Site name identifier goes into the datafile, used in aggregation
SITE_NAME = "Default Site"
SITE_HANDLE = "bikeparking"  # This is used in aggregation and filenames

# Files and folder locations
DATA_FOLDER = "../data"  # Folder to keep datafiles in
# (DATA_BASENAME is set following import of local config, below)

# Where and how often to publish reports
REPORTS_FOLDER = "../reports"
PUBLISH_FREQUENCY = 15  # minutes. "0" means do not publish

# Echo captures full transcripts of a day's TT session
ECHO_FOLDER = ""
ECHO = False

# Base of URL to use for calls to estimator
# E.g. "http://example.com/cgi-bin/estimator"
# "" disables estimations
ESTIMATOR_URL_BASE = ""

# Maximum length for Notes
MAX_NOTE_LENGTH = 80

# Ask confirmatino for checkouts when visits less than this duration.
CHECK_OUT_CONFIRM_TIME = 10  # mins

# This is for development debugging
DEBUG = False

# Stubs here; the default hours should be defined in the local config file.
# They would look something like this:
# REGULAR_TAGS = """
#   wa0 wa1 wa2 wa3 wa4 wa5 bf0 bf2 bf5
#   bf7 wc0 wc1 wc3
# """
# Where tags can be in any order, separated by spaces or commas,
# on multiple lines
REGULAR_TAGS = """

"""
OVERSIZE_TAGS = """

"""
RETIRED_TAGS = """

"""

TAG_COLOUR_NAMES = {}

SEASON_HOURS = {}
SPECIAL_HOURS = {}
# The format for SEASON_HOURS and SPECIAL_HOURS is like this:
# SEASON_HOURS = [
#     ["2024-05-01", "2024-09-30"],
#     {
#         1: ["1:00", "22:00"],  # Monday
#         2: ["2:00", "22:00"],  # Tuesday
#         3: ["3:00", "22:00"],  # Wednesday
#         4: ["4:00", "22:00"],  # Thursday
#         5: ["5:00", "22:00"],  # Friday
#         6: ["6:00", "22:00"],  # Saturday
#         7: ["7:00", "22:00"],  # Sunday
#     },
#     ["2024-01-01", "2024-04-30"],
#     {
#         1: ["1:00", "20:00"],  # Monday
#         2: ["2:00", "20:00"],  # Tuesday
#         3: ["3:00", "20:00"],  # Wednesday
#         4: ["4:00", "20:00"],  # Thursday
#         5: ["5:00", "20:00"],  # Friday
#         6: ["6:00", "20:00"],  # Saturday
#         7: ["7:00", "20:00"],  # Sunday
#     },
# ]
# SPECIAL_HOURS = {
#     "2024-05-03": ["14:00", "23:00"],
#     "2024-02-06": ["1:00", "23:00"],
# }

#######################################
#        END OF CONFIG SECTION        #
#                                     #
# Do not include any code below here  #
# in the client_local_config.py file. #
#######################################


# Import any local config to override this module's values.
try:
    from client_local_config import *  # pylint:disable=wildcard-import,unused-wildcard-import
except ModuleNotFoundError:
    pass
except Exception as e:  # pylint:disable=broad-exception-caught
    print()
    print("** Configuration error: **")
    print(f"   Error type: {type(e).__name__}")
    print(f"   Error message: {e}")
    print("Contact TagTracker admin.")
    print()
    sys.exit(1)

# Final checks of local config and adjustments based on it.

# SITE_HANDLE forms filename and database ID parts.
if not re.match(r'^[a-zA-Z0-9_\-.\~!]+$',SITE_HANDLE) or len(SITE_HANDLE) > 32:
    print()
    print("** Configuration error: **")
    print("   SITE_HANDLE has unsuitable characters or is too long (max len 32).")
    print("Contact TagTracker admin.")
    print()
    sys.exit(1)

# Filenames are based on SITE_HANDLE
DATA_BASENAME = f"{SITE_HANDLE}_"  # Files will be {BASENAME}YY-MM-DD.dat

