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


# Arbitrary string to describe this location
SITE_NAME = ""
TAGS_UPPERCASE = False

# data owner -- If set, the program will display this data owner notice on
# web pages and when tagtracker starts.
# This can be a string, or if a list of strings, displays as
# multiple lines.
DATA_OWNER = ""

# Database filename
DB_FILENAME = "../data/v2.db"  # Filepath to sqlite3 database

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
