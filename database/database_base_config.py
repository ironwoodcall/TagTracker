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
# To make a new database_local_config.py config file,     #
# copy from here down to "END OF CONFIG SECTION" and put  #
# it into a new file called "database_local_config.py" in #
# the 'database' subdirectory (same dir as this file.)    #
###########################################################

# Database filename
DB_FILENAME = ""  # Filepath to sqlite3 database

# Weather update configuration
# WX_SITES is an ordered list of mappings with keys:
#   url: CSV endpoint (may include {year} placeholder)
#   date_col: 1-based column number for the date
#   max_temp_col / precip_col: 1-based column numbers for max temp and precip
#   date_format: optional strptime format if not YYYY-MM-DD
#   has_header: optional bool to skip the first row
WX_SITES = []
WX_MIN_AGE_DAYS = 2

# Optional path to calibration JSON
# (produced by helpers/estimator_calibrate_models.py --recommended)
# If set, estimator will use per-model, per-measure, per-time-bin residual bands and
# best-model guidance for mixed outputs.
EST_CALIBRATION_FILE = ""

# Location for future prediction trained model data
TRAINED_MODEL_FOLDER = ""


#######################################
#        END OF CONFIG SECTION        #
#                                     #
# Do not include any code below here  #
# in database_local_config.py.        #
#######################################



# Import any local web config to override this module's values.
try:
    from database.database_local_config import * # pylint:disable=wildcard-import
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
