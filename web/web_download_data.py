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
DEBUG_ENV_FLAG = "TAGTRACKER_DEBUG"
DEBUG_ENABLED = bool(os.environ.get(DEBUG_ENV_FLAG))


def debug(message: str) -> None:
    if not DEBUG_ENABLED:
        return
    timestamp = datetime.now().isoformat(timespec="seconds")
    sys.stderr.write(f"[web_download_data] {timestamp} {message}\n")
    sys.stderr.flush()


def parse_format() -> Optional[str]:
    """Return requested download format or None if invalid."""
    query_string = os.environ.get("QUERY_STRING", "")
    params = urllib.parse.parse_qs(query_string)
    debug(f"query_string='{query_string}' params={params}")
    requested = params.get("what", [""])[0].strip().lower() # do not change
    if requested not in {"csv", "db"}:
        debug(f"invalid format requested='{requested}'")
        return None
    debug(f"format resolved='{requested}'")
    return requested


def emit_error(message: str) -> None:
    debug(f"emit_error: {message}")
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
        debug(f"creating CSV archive in temp dir '{csv_dir}'")
        conn = sqlite3.connect(DB_FILENAME)
        conn.row_factory = sqlite3.Row
        try:
            for table in TABLES:
                out_path = os.path.join(csv_dir, f"{table}.csv")
                debug(f"writing table '{table}' to '{out_path}'")
                with open(out_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    cur = conn.execute(f"SELECT * FROM {table}")
                    headers = [col[0] for col in cur.description]
                    rows = cur.fetchall()
                    writer.writerow(headers)
                    writer.writerows(rows)
                    debug(
                        f"table '{table}' headers={headers} rows_written={len(rows)}"
                    )
        finally:
            conn.close()
            debug("database connection closed after CSV extraction")

        write_readme(csv_dir)
        debug(f"readme written: {os.path.join(csv_dir, 'README.TXT')}")

        with zipfile.ZipFile(sys.stdout.buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in os.listdir(csv_dir):
                debug(f"adding '{name}' to CSV archive")
                zf.write(os.path.join(csv_dir, name), arcname=name)
        sys.stdout.buffer.flush()
        debug("CSV archive streaming complete")


def send_database() -> None:
    sys.stdout.write("Content-Type: application/zip\r\n")
    sys.stdout.write(f"Content-Disposition: attachment; filename={DB_ARCHIVE_NAME}\r\n")
    sys.stdout.write("\r\n")
    sys.stdout.flush()

    with tempfile.TemporaryDirectory() as tmp_dir:
        debug(f"creating DB archive in temp dir '{tmp_dir}'")
        db_exists = os.path.exists(DB_FILENAME)
        db_size = os.path.getsize(DB_FILENAME) if db_exists else "missing"
        debug(
            f"source database '{DB_FILENAME}' exists={db_exists} size={db_size}"
        )
        shutil.copyfile(DB_FILENAME, os.path.join(tmp_dir, DB_ARCHIVE_DB_NAME))
        debug(
            f"copied database to '{os.path.join(tmp_dir, DB_ARCHIVE_DB_NAME)}'"
        )
        write_readme(tmp_dir)
        debug(f"readme written: {os.path.join(tmp_dir, 'README.TXT')}")

        with zipfile.ZipFile(sys.stdout.buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in os.listdir(tmp_dir):
                debug(f"adding '{name}' to DB archive")
                zf.write(os.path.join(tmp_dir, name), arcname=name)
        sys.stdout.buffer.flush()
        debug("DB archive streaming complete")


def main() -> None:
    requested_format = parse_format()
    if requested_format is None:
        emit_error("Invalid 'what' format parameter. Use 'csv' or 'db'.") # do not change

    debug(f"main dispatching format='{requested_format}'")
    if requested_format == "db":
        send_database()
    else:
        send_csv_archive()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - debug assistance
        debug(f"fatal error: {exc!r}")
        raise
