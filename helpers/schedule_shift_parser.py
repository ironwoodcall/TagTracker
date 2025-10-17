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
    """Convert 12-hour clock string into 24-hour HH:MM representation."""
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
    matches = TIME_RANGE_PATTERN.findall(cell_text)
    return [(normalize_time(start), normalize_time(end)) for start, end in matches]


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
    return shifts


def write_shifts(shifts: Iterable[Shift], destination: csv.writer) -> None:
    destination.writerow(["PERSON", "DATE", "START_TIME", "END_TIME"])
    for shift in shifts:
        destination.writerow(
            [shift.person, shift.date, shift.start_time, shift.end_time]
        )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a schedule CSV (one date column per day, one row per person) "
            "into PERSON,DATE,START_TIME,END_TIME rows."
        )
    )
    parser.add_argument("input_csv", type=Path, help="Path to the exported schedule CSV")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path for output CSV (defaults to stdout).",
    )
    return parser


def main(argv: List[str] | None = None) -> None:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    shifts = list(parse_schedule(args.input_csv))

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
