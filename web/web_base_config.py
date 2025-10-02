"""Config for TagTracker by Julias Hocking.

Configuration items for the webserver module.

This module sets configs then overrides with any same-named
values that are set in the local config file.

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
###########################################################
#            BEGINNING OF CONFIG SECTION                  #
# To make a new web_local_config.py configuration file,   #
# copy from here down to "END OF CONFIG SECTION" and put  #
# it into a new file called "web_local_config.py" in the  #
# 'web' subdirectory (the same directory as this file.)   #
###########################################################


# Arbitrary string to describe this location
SITE_NAME = ""
TAGS_UPPERCASE = True

# data owner -- If set, the program will display this data owner notice on
# web pages and when tagtracker starts.
# This can be a string, or if a list of strings, displays as
# multiple lines.
DATA_OWNER = ""

# Database filename
DB_FILENAME = ""  # Filepath to sqlite3 database

# Estimator configuration (override in web_local_config.py if desired)
# Confidence level thresholds: minimum matched cohort size (min_n) and
# minimum fraction of day elapsed (min_frac) for Medium/High.
EST_CONF_THRESHOLDS = {
    "High": {"min_n": 12, "min_frac": 0.4},
    "Medium": {"min_n": 8, "min_frac": 0.2},
}

# The Day Detail page calls estimator (if it's 'today').
# Using a STANDARD estimation type for this can be slow. QUICK speeds it up
# by leaving out the random forest model
EST_TYPE_FOR_ONEDAY_SUMMARY = "STANDARD"   # QUICK or STANDARD

# Confidence bands (display ranges) per measure.
# Measures: remainder (further bikes), activity (next-hour ins+outs),
# peak (max bikes today), peaktime (time of max, minutes).
EST_BANDS = {
    "remainder": {"High": 10, "Medium": 18, "Low": 30},
    "activity": {"High": 8, "Medium": 12, "Low": 16},
    "peak": {"High": 10, "Medium": 15, "Low": 25},
    "peaktime": {"High": 20, "Medium": 30, "Low": 60},
}

# Similarity matching and trimming for the same-day estimator
EST_VARIANCE = 15
EST_Z_CUTOFF = 2.5

# Recent-window size for schedule-only model
EST_RECENT_DAYS = 30

# Optional path to calibration JSON (produced by helpers/estimator_calibrate_models.py --recommended)
# If set, estimator will use per-model, per-measure, per-time-bin residual bands and
# best-model guidance for mixed outputs.
EST_CALIBRATION_FILE = ""

# Selection strategy for 'best guess' rows in STANDARD output.
#   'accuracy_first' (default): calibration best_model -> narrowest range -> confidence
#   'range_first'            : narrowest range -> confidence (legacy behavior)
EST_SELECTION_MODE = "accuracy_first"

#######################################
#        END OF CONFIG SECTION        #
#                                     #
# Do not include any code below here  #
# in the web_local_config.py file.    #
#######################################

# Import any local web config to override this module's values.
try:
    from web_local_config import * # pylint:disable=wildcard-import
except ModuleNotFoundError:
    pass
except Exception as e: # pylint:disable=broad-exception-caught
    print()
    print("** Configuration error: **")
    print(f"   Error type: {type(e).__name__}")
    print(f"   Error message: {e}")
    print("Contact TagTracker admin.")
    print()
    import sys
    sys.exit(1)
