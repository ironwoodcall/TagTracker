#!/usr/bin/env python3

import csv
import os
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime

# Import database path from your config
from web_base_config import DB_FILENAME, DATA_OWNER

# --- CGI headers ---
sys.stdout.write("Content-Type: application/zip\r\n")
sys.stdout.write("Content-Disposition: attachment; filename=bikedata-csv.zip\r\n")
sys.stdout.write("\r\n")
sys.stdout.flush()

# --- Setup ---
tables = ["day", "visit"]

with tempfile.TemporaryDirectory() as csv_dir:
    # --- Extract each table to CSV ---
    conn = sqlite3.connect(DB_FILENAME)
    conn.row_factory = sqlite3.Row
    try:
        for table in tables:
            out_path = os.path.join(csv_dir, f"{table}.csv")
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                cur = conn.execute(f"SELECT * FROM {table}")
                writer.writerow([col[0] for col in cur.description])  # headers
                writer.writerows(cur.fetchall())
    finally:
        conn.close()

    # --- Create README file ---
    readme_path = os.path.join(csv_dir, "README.TXT")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(f"Extraction Date: {datetime.now()}\n")
        f.write("\n")
        if isinstance(DATA_OWNER, list):
            for item in DATA_OWNER:
                f.write(f"{item}\n")
        else:
            f.write(f"{DATA_OWNER}\n")

    # --- Stream zip to stdout ---
    with zipfile.ZipFile(sys.stdout.buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in os.listdir(csv_dir):
            zf.write(os.path.join(csv_dir, name), arcname=name)
