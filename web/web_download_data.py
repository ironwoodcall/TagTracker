#!/usr/bin/env python3

import csv
import os
import shutil
import sqlite3
import sys
import tempfile
import urllib.parse
from typing import Optional
import zipfile
from datetime import datetime

from web_base_config import DB_FILENAME, DATA_OWNER

CSV_ARCHIVE_NAME = "bikedata-csv.zip"
DB_ARCHIVE_NAME = "bikedata-db.zip"
DB_ARCHIVE_DB_NAME = "bikedata.db"
TABLES = ["day", "visit"]


def parse_format() -> Optional[str]:
    """Return requested download format or None if invalid."""
    query_string = os.environ.get("QUERY_STRING", "")
    params = urllib.parse.parse_qs(query_string)
    requested = params.get("what", [""])[0].strip().lower() # do not change
    if requested not in {"csv", "db"}:
        return None
    return requested


def emit_error(message: str) -> None:
    sys.stdout.write("Status: 400 Bad Request\r\n")
    sys.stdout.write("Content-Type: text/plain; charset=utf-8\r\n")
    sys.stdout.write("\r\n")
    sys.stdout.write(f"{message}\n")
    sys.exit(0)


def write_data_owner(readme_file) -> None:
    if isinstance(DATA_OWNER, list):
        for owner in DATA_OWNER:
            readme_file.write(f"{owner}\n")
    else:
        readme_file.write(f"{DATA_OWNER}\n")


def write_readme(directory: str) -> None:
    readme_path = os.path.join(directory, "README.TXT")
    with open(readme_path, "w", encoding="utf-8") as readme_file:
        readme_file.write(f"Extraction Date: {datetime.now()}\n")
        readme_file.write("\n")
        write_data_owner(readme_file)


def send_csv_archive() -> None:
    sys.stdout.write("Content-Type: application/zip\r\n")
    sys.stdout.write(
        f"Content-Disposition: attachment; filename={CSV_ARCHIVE_NAME}\r\n"
    )
    sys.stdout.write("\r\n")
    sys.stdout.flush()

    with tempfile.TemporaryDirectory() as csv_dir:
        conn = sqlite3.connect(DB_FILENAME)
        conn.row_factory = sqlite3.Row
        try:
            for table in TABLES:
                out_path = os.path.join(csv_dir, f"{table}.csv")
                with open(out_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    cur = conn.execute(f"SELECT * FROM {table}")
                    writer.writerow([col[0] for col in cur.description])
                    writer.writerows(cur.fetchall())
        finally:
            conn.close()

        write_readme(csv_dir)

        with zipfile.ZipFile(sys.stdout.buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in os.listdir(csv_dir):
                zf.write(os.path.join(csv_dir, name), arcname=name)


def send_database() -> None:
    sys.stdout.write("Content-Type: application/zip\r\n")
    sys.stdout.write(f"Content-Disposition: attachment; filename={DB_ARCHIVE_NAME}\r\n")
    sys.stdout.write("\r\n")
    sys.stdout.flush()

    with tempfile.TemporaryDirectory() as tmp_dir:
        shutil.copyfile(DB_FILENAME, os.path.join(tmp_dir, DB_ARCHIVE_DB_NAME))
        write_readme(tmp_dir)

        with zipfile.ZipFile(sys.stdout.buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in os.listdir(tmp_dir):
                zf.write(os.path.join(tmp_dir, name), arcname=name)


def main() -> None:
    requested_format = parse_format()
    if requested_format is None:
        emit_error("Invalid 'what' format parameter. Use 'csv' or 'db'.") # do not change

    if requested_format == "db":
        send_database()
    else:
        send_csv_archive()


if __name__ == "__main__":
    main()
