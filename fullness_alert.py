#!/usr/bin/env python3
"""TagTracker utility to (maybe) send email.

Copyright (C) 2023 Julias Hocking

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


import argparse
import os
import sys
import tt_dbutil as db
import tt_util as ut


def parse_args() -> argparse.Namespace:
    """Collect command args into an argparse.Namespace."""
    parser = argparse.ArgumentParser(
        description="Prints a message if DATE's max bikes were over THRESHOLD",
        epilog="This is intended to pipe into a mailer as an alert on "
        "whether the valet was reaching critical capacity.  If bikes "
        "are below THRESHOLD then normally no message is printed; "
        "this is to fit into the 'discard empty messages' option "
        "of mailing programs (e.g. -E for s-nail).  To make always "
        "print a message, use the --force option.",
    )
    parser.add_argument(
        "database_file",
        metavar="DATABASE_FILE",
        help="TagTracker database file",
    )
    DEFAULT_DATE = "yesterday"
    parser.add_argument(
        "--date",
        default=DEFAULT_DATE,
        help=f"date to test for fullness (default='{DEFAULT_DATE}')",
    )
    DEFAULT_THRESHOLD = "135"
    parser.add_argument(
        "--threshold",
        default=DEFAULT_THRESHOLD,
        help="Print message if at least this many bikes "
        f"(default={DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Print a message even if max bikes is below threshold",
    )

    the_args = parser.parse_args()
    the_args.date = ut.date_str(the_args.date)
    if not the_args.date:
        print("Bad date", file=sys.stderr)
        sys.exit(1)
    # What threshold to alert on?
    if the_args.threshold and not the_args.threshold.isdigit():
        print("Threshold must be integer", file=sys.stderr)
        sys.exit(1)
    the_args.threshold = int(the_args.threshold)

    return the_args


# args needed: email address(es), option threshhold, database_file
args = parse_args()

# How many bikes are there on the given date?
if not os.path.exists(args.database_file):
    print(f"Database file {args.database_file} not found", file=sys.stderr)
    sys.exit(1)
database = db.db_connect(args.database_file, must_exist=True)
dbrows = db.db_fetch(
    database, f"select max_total from day where date = '{args.date}'"
)
if not dbrows:
    print(f"No data for {args.date}", file=sys.stderr)
    exit(1)
max_total = dbrows[0].max_total
if max_total >= args.threshold:
    print(
        f"Date {args.date} had {max_total} bikes; >= threshold of {args.threshold}"
    )
elif args.force:
    print(
        f"Date {args.date} had {max_total} bikes; less than threshold of {args.threshold}"
    )
