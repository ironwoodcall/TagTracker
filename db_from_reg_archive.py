#!/usr/bin/env python3
"""Update TagTraker database from archived registrations info.

Archived registration info is the remnant of the former day-end-form
CSV file.  It is made of three columns:
    DATE, REGISTRATIONS, REPORTED_LEFTOVERS
(This ignores REPORTED_LEFTOVERS. Also ignores 1st row, assumed
to be a header.)

It will update existing records in the DAY table of the database
such that registrations is set to the greater of any existing
registrations value or a corresponding REG_COUNT value from the
csv file.

This is a super simplistic script with minimal error checking
or reporting.

It is expected to be used only if needed to rebuild a database,
though it could be run harmlessly on a current database.  It should
be run *after* rows are created by loading from datafiles.


Copyright (C) 2023,2024 Julias Hocking. Written by tevpg.

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
import csv
import sqlite3

# Function to create or replace the day_end_form_archive table in the main database and load data from CSV into it
def load_csv_into_temp_table(archive_csv: str, tagtracker_db: str) -> None:
    connection = sqlite3.connect(tagtracker_db)
    cursor = connection.cursor()

    # Create or replace the day_end_form_archive table in the main database
    try:
        cursor.execute("DROP TABLE day_end_form_archive")
    except sqlite3.OperationalError:
        pass
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS day_end_form_archive (
                        date TEXT PRIMARY KEY,
                        csv_registrations INTEGER,
                        csv_leftovers INTEGER
                    )"""
    )
    # Make sure it's empty
    # cursor.execute("DELETE FROM day_end_form_archive")

    # Load data from CSV into day_end_form_archive and replace any NULL values with 0
    with open(archive_csv, "r") as file:
        reader = csv.reader(file)
        next(reader)  # Skip header
        for row in reader:
            csv_registrations = int(row[1]) if row[1] else 0
            csv_leftovers = int(row[2]) if row[2] else 0
            cursor.execute(
                "INSERT OR REPLACE INTO day_end_form_archive (DATE, csv_registrations,csv_leftovers) VALUES (?, ?, ?)",
                (row[0], csv_registrations, csv_leftovers),
            )

    # Set any NULL values in csv_registrations to 0
    cursor.execute(
        "UPDATE day_end_form_archive SET csv_registrations = 0 WHERE csv_registrations IS NULL"
    )
    connection.commit()
    connection.close()


# Function to update main table from the temporary table in the second database
def update_main_table_from_temp(tagtracker_db: str) -> None:
    connection = sqlite3.connect(tagtracker_db)
    cursor = connection.cursor()
    cursor.execute("UPDATE DAY SET REGISTRATIONS = 0 WHERE REGISTRATIONS IS NULL")
    cursor.execute(
        """UPDATE DAY
                      SET REGISTRATIONS = MAX(REGISTRATIONS, day_end_form_archive.csv_registrations)
                      FROM day_end_form_archive
                      WHERE DAY.DATE = day_end_form_archive.DATE"""
    )
    connection.commit()
    connection.close()


# Main function
def main(archive_csv: str, tagtracker_db: str) -> None:
    load_csv_into_temp_table(archive_csv, tagtracker_db)
    update_main_table_from_temp(tagtracker_db)
    print("Update completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process registrations from CSV file into database file.  "
        "CSV file is DATE, REGISTRATIONS, LEFTOVERS_REPORTED.  "
        "Registrations are set to the greater of existing value or CSV value."
    )
    parser.add_argument("archive_csv", type=str, help="CSV file path")
    parser.add_argument(
        "tagtracker_db", type=str, help="TagTracker database filepath"
    )

    args = parser.parse_args()

    main(args.archive_csv, args.tagtracker_db)
