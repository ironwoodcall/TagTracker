"""Parse a Sling schedule export into a normalized shift CSV."""

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

TIME_RANGE_PATTERN = re.compile(
    r"(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)", re.IGNORECASE
)


@dataclass
class Shift:
    person: str
    date: str
    start_time: str
    end_time: str


def normalize_time(value: str) -> str:
    """Convert a 12-hour clock string into 24-hour HH:MM representation."""
    cleaned = value.strip().upper()
    dt = datetime.strptime(cleaned, "%I:%M %p")
    return dt.strftime("%H:%M")


def extract_shifts(cell_text: str) -> List[tuple[str, str]]:
    """
    Pull out every time range contained in the cell text.

    Shifts are encoded as lines such as "4:00 PM - 6:30 PM • 2h 30min".
    Comments or bullet separators are ignored.
    """
    if not cell_text:
        return []
    shifts: List[tuple[str, str]] = []
    lines = [line.strip() for line in cell_text.splitlines()]
    blocks: List[List[str]] = []
    current: List[str] = []

    for line in lines:
        if line == "":
            continue
        if TIME_RANGE_PATTERN.search(line):
            if current:
                blocks.append(current)
            current = [line]
        else:
            if not current:
                continue
            current.append(line)
    if current:
        blocks.append(current)

    for block in blocks:
        block_text = " ".join(block).lower()
        if "unavailable" in block_text or "sick callout" in block_text:
            continue
        if "cov bike valet attendant" not in block_text:
            continue
        matches = TIME_RANGE_PATTERN.findall(" ".join(block))
        shifts.extend(
            (normalize_time(start), normalize_time(end)) for start, end in matches
        )
    return shifts


def parse_schedule(path: Path) -> Iterable[Shift]:
    """
    Parse schedule CSV exported with one column per date and rows per person.
    """
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        rows = list(reader)

    if not rows:
        return []

    header = rows[0]
    # First column is blank; remaining columns are ISO8601 date strings.
    dates = header[1:]

    shifts: List[Shift] = []
    shift_counts_by_date = {date.strip(): 0 for date in dates if date.strip()}
    for row in rows[2:]:  # Skip header and "Scheduled shifts" row.
        if not row:
            continue
        person = row[0].strip()
        if not person:
            continue
        for date_str, cell in zip(dates, row[1:]):
            if not date_str or not cell.strip():
                continue
            for start_time, end_time in extract_shifts(cell):
                shifts.append(
                    Shift(
                        person=person,
                        date=date_str.strip(),
                        start_time=start_time,
                        end_time=end_time,
                    )
                )
                shift_counts_by_date[date_str.strip()] += 1
    for date_str, count in shift_counts_by_date.items():
        if count == 0:
            print(
                f"Warning: No matching shifts found for {date_str}",
                file=sys.stderr,
            )
    return shifts


def write_shifts(shifts: Iterable[Shift], destination: csv.writer) -> None:
    """Write shift rows to a CSV writer."""
    destination.writerow(["PERSON", "DATE", "START_TIME", "END_TIME"])
    for shift in shifts:
        destination.writerow(
            [shift.person, shift.date, shift.start_time, shift.end_time]
        )


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Convert one or more schedule CSV files (one date column per day, one row per person) "
            "into PERSON,DATE,START_TIME,END_TIME rows."
        )
    )
    parser.add_argument(
        "input_csvs",
        type=Path,
        nargs="+",
        help="Path(s) to exported schedule CSV file(s).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path for output CSV (defaults to stdout).",
    )
    return parser


def main(argv: List[str] | None = None) -> None:
    """CLI entry point."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    shifts: List[Shift] = []
    for input_csv in args.input_csvs:
        shifts.extend(parse_schedule(input_csv))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8") as outfile:
            writer = csv.writer(outfile)
            write_shifts(shifts, writer)
    else:
        writer = csv.writer(sys.stdout)
        write_shifts(shifts, writer)


if __name__ == "__main__":
    main()
