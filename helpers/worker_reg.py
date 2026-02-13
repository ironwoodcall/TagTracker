#!/usr/bin/env python3
"""Orchestrate worker registration summary generation from raw inputs."""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from pathlib import Path
from typing import List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from helpers import worker_reg_make_summary as make_summary
from helpers.worker_reg_process_echo_files import RegistrationEvent, process_file
from helpers.worker_reg_process_shift_export import parse_schedule, write_shifts


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the orchestration flow."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the full worker registration pipeline: parse ECHO transcripts, "
            "normalize shift exports, then generate summary tables."
        )
    )
    parser.add_argument(
        "--echo",
        type=Path,
        nargs="+",
        required=True,
        help="One or more TagTracker ECHO transcript files.",
    )
    parser.add_argument(
        "--shifts",
        type=Path,
        nargs="+",
        required=True,
        help="One or more Sling shift export CSV files.",
    )
    parser.add_argument(
        "--echo-debug",
        action="store_true",
        help="Enable debug output while parsing ECHO files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional destination CSV for summary output.",
    )
    parser.add_argument(
        "--by-month",
        action="store_true",
        help="Emit separate summary tables for each month in the schedule.",
    )
    parser.add_argument(
        "--report-unassigned",
        action="store_true",
        help="Print registration lines with no matching shift to stderr.",
    )
    return parser


def write_echo_activity(
    echo_paths: List[Path], destination: Path, debug: bool = False
) -> int:
    """Extract registration events from ECHO files and write DATE/TIME/REGISTRATIONS CSV."""
    events: List[RegistrationEvent] = []
    for echo_path in echo_paths:
        if not echo_path.exists():
            print(f"File not found: {echo_path}", file=sys.stderr)
            continue
        events.extend(process_file(echo_path, debug=debug))

    events.sort(key=lambda evt: (evt.date, evt.time))

    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["DATE", "TIME", "REGISTRATIONS"])
        for event in events:
            writer.writerow([event.date, event.time, event.registrations])

    return len(events)


def write_shift_rows(shift_exports: List[Path], destination: Path) -> int:
    """Normalize one or more Sling exports into PERSON/DATE/START_TIME/END_TIME rows."""
    shifts = []
    for shift_export in shift_exports:
        shifts.extend(parse_schedule(shift_export))
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        write_shifts(shifts, writer)
    return len(shifts)


def main(argv: List[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    for shift_export in args.shifts:
        if not shift_export.exists():
            print(f"Shift export not found: {shift_export}", file=sys.stderr)
            return 1

    with tempfile.TemporaryDirectory(prefix="worker_reg_") as temp_dir:
        temp_path = Path(temp_dir)
        activity_csv = temp_path / "registrations.csv"
        shifts_csv = temp_path / "shifts.csv"

        write_echo_activity(args.echo, activity_csv, debug=args.echo_debug)
        write_shift_rows(args.shifts, shifts_csv)

        summary_args: List[str] = [str(shifts_csv), str(activity_csv)]
        if args.output is not None:
            summary_args.extend(["--output", str(args.output)])
        if args.by_month:
            summary_args.append("--by-month")
        if args.report_unassigned:
            summary_args.append("--report-unassigned")

        make_summary.main(summary_args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
