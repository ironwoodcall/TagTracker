#!/usr/bin/env python3
"""Update TagTracker DAY table with weather data from configured CSV feeds.

This module replaces the old dbupdate/update_from_remote.sh flow. It fetches
CSV payloads from the ordered list in database_base_config.WX_SITES, and for
each day older than WX_MIN_AGE_DAYS fills precipitation and max_temperature
values (or overwrites when --force). If a site leaves blanks, the next site in
the list is tried until all blanks are filled or sources are exhausted.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import io
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional

from database import database_base_config as cfg
import database.tt_dbutil as db


@dataclass
class WxRow:
    """Parsed weather values for a single date."""

    date: str
    max_temperature: Optional[float]
    precipitation: Optional[float]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Populate TagTracker DAY weather fields from configured CSV feeds.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Update even when database values are already present.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print progress while running.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=datetime.date.today().year,
        help="Year for CSV URLs that include {year}; defaults to current year.",
    )
    return parser.parse_args()


def _normalize_date(raw: str, fmt: Optional[str]) -> str:
    """Return YYYY-MM-DD or '' if parsing fails."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if fmt:
        try:
            return datetime.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            return ""
    # Try ISO-ish fallback
    try:
        return datetime.datetime.fromisoformat(raw).date().isoformat()
    except ValueError:
        return ""


def _safe_float(raw: str) -> Optional[float]:
    """Convert string to float if possible; otherwise None."""
    raw = (raw or "").strip()
    if raw in ["", "NA", "N/A", "nan", "null", "None"]:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def fetch_csv_text(url: str, verbose: bool, label: str = "") -> str:
    """Fetch CSV content from url."""
    if verbose:
        prefix = f"[{label}] " if label else ""
        print(f"{prefix}Fetching: {url}")
    try:
        with urllib.request.urlopen(url) as resp:  # nosec B310
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset)
    except (urllib.error.URLError, UnicodeDecodeError) as err:
        print(f"Unable to fetch {url}: {err}", file=sys.stderr)
        return ""


def parse_site_rows(site_cfg: dict, csv_text: str, verbose: bool) -> Dict[str, WxRow]:
    """Parse CSV rows for one site into a date -> WxRow map."""
    data: Dict[str, WxRow] = {}
    if not csv_text:
        return data

    required_keys = ["url", "date_col", "max_temp_col", "precip_col"]
    missing = [k for k in required_keys if k not in site_cfg]
    if missing:
        print(f"Site config missing keys {missing}; skipping.", file=sys.stderr)
        return data

    try:
        date_col = int(site_cfg.get("date_col")) - 1
        max_col = int(site_cfg.get("max_temp_col")) - 1
        precip_col = int(site_cfg.get("precip_col")) - 1
    except (TypeError, ValueError):
        print("Invalid column numbers in WX_SITES; must be integers.", file=sys.stderr)
        return data
    if min(date_col, max_col, precip_col) < 0:
        print("Column numbers in WX_SITES must be 1-based (>=1).", file=sys.stderr)
        return data
    date_format = site_cfg.get("date_format")
    has_header = bool(site_cfg.get("has_header"))

    reader = csv.reader(io.StringIO(csv_text))
    for idx, row in enumerate(reader):
        if idx == 0 and has_header:
            continue
        try:
            date_raw = row[date_col]
            max_raw = row[max_col]
            precip_raw = row[precip_col]
        except IndexError:
            if verbose:
                print(f"Row too short at line {idx+1}; skipping.")
            continue

        normalized_date = _normalize_date(date_raw, date_format)
        if not normalized_date:
            continue
        max_temp = _safe_float(max_raw)
        precip = _safe_float(precip_raw)
        data[normalized_date] = WxRow(
            date=normalized_date,
            max_temperature=max_temp,
            precipitation=precip,
        )
    return data


def load_existing_weather(ttdb, cutoff_date: str) -> Dict[str, dict]:
    """Fetch existing precipitation/max_temperature for dates up to cutoff_date."""
    rows = db.db_fetch(
        ttdb,
        (
            "select date, precipitation, max_temperature "
            f"from day where date < '{cutoff_date}' order by date;"
        ),
    )
    return {
        row.date: {
            "precipitation": row.precipitation,
            "max_temperature": row.max_temperature,
        }
        for row in rows
    }


def apply_site(
    ttdb,
    site_idx: int,
    site_cfg: dict,
    site_rows: Dict[str, WxRow],
    existing: Dict[str, dict],
    force: bool,
    cutoff_date: str,
    verbose: bool,
) -> tuple[int, int]:
    """Apply updates from a single site."""
    label = site_cfg.get("label", f"site {site_idx}")
    precip_updates = 0
    max_temp_updates = 0

    for date, newvals in site_rows.items():
        if date not in existing or date >= cutoff_date:
            continue
        current = existing[date]
        assignments = []

        if newvals.precipitation is not None and (force or current["precipitation"] is None):
            assignments.append(f"precipitation = {newvals.precipitation}")
            current["precipitation"] = newvals.precipitation
            precip_updates += 1

        if newvals.max_temperature is not None and (
            force or current["max_temperature"] is None
        ):
            assignments.append(f"max_temperature = {newvals.max_temperature}")
            current["max_temperature"] = newvals.max_temperature
            max_temp_updates += 1

        if not assignments:
            continue

        sql = f"update day set {', '.join(assignments)} where date = '{date}';"
        db.db_update(ttdb, sql, commit=False)
        if verbose:
            print(f"[{label}] {date}: {'; '.join(assignments)}")

    return precip_updates, max_temp_updates


def have_blanks(existing: Dict[str, dict]) -> bool:
    """Return True if any date still has missing precip or max temp."""
    return any(
        row.get("precipitation") is None or row.get("max_temperature") is None
        for row in existing.values()
    )


def main():
    args = parse_args()

    if not cfg.WX_SITES:
        print("No WX_SITES configured in database_base_config.", file=sys.stderr)
        sys.exit(1)

    cutoff_date = (
        datetime.date.today() - datetime.timedelta(days=getattr(cfg, "WX_MIN_AGE_DAYS", 2))
    ).isoformat()

    ttdb = db.db_connect(cfg.DB_FILENAME)
    if not ttdb:
        sys.exit(1)

    existing = load_existing_weather(ttdb, cutoff_date)
    if not existing:
        print("No DAY rows found before cutoff; nothing to update.")
        sys.exit(0)

    if not have_blanks(existing) and not args.force:
        print(f"No empty weather fields before cutoff {cutoff_date}; exiting.")
        sys.exit(0)

    total_precip = 0
    total_maxtemp = 0

    for idx, site in enumerate(cfg.WX_SITES, start=1):
        url_template = site.get("url", "")
        label = site.get("label", f"site {idx}")
        url = url_template.format(year=args.year) if "{year" in url_template else url_template
        csv_text = fetch_csv_text(url, args.verbose, label=label)
        site_rows = parse_site_rows(site, csv_text, args.verbose)

        p_updates, t_updates = apply_site(
            ttdb,
            idx,
            site,
            site_rows,
            existing,
            args.force,
            cutoff_date,
            args.verbose,
        )
        total_precip += p_updates
        total_maxtemp += t_updates

        if args.verbose:
            print(f"[{label}] applied {p_updates} precip and {t_updates} max temp updates.")

        if not have_blanks(existing):
            break

    db.db_commit(ttdb)

    print(
        f"Weather updates complete (cutoff {cutoff_date}): "
        f"{total_precip} precip, {total_maxtemp} max temp updates."
    )


if __name__ == "__main__":
    main()
