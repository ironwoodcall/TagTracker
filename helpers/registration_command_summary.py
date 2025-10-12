#!/usr/bin/env python3
"""Summarize registration commands from TagTracker ECHO transcripts."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, NamedTuple

DATE_PATTERN = re.compile(r"\((\d{4}-\d{2}-\d{2})\)")
COMMAND_PATTERN = re.compile(
    r"^\s*(?P<time>\d{1,2}:\d{2}).*?>>\s*(?P<cmd>[A-Za-z]+)\s*(?P<op>[+\-=])\s*(?P<count>\d+)",
    re.IGNORECASE,
)
VALID_COMMANDS = {"R", "REG", "REGISTER", "REGISTRATION"}


class RegistrationEvent(NamedTuple):
    date: str
    weekday: str
    time: str
    operator: str
    count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print registration command summaries from one or more TagTracker "
            "ECHO transcript files."
        )
    )
    parser.add_argument(
        "echo_files",
        type=Path,
        nargs="+",
        help="Path(s) to TagTracker ECHO transcript file(s)",
    )
    return parser.parse_args()


def normalize_time(raw_time: str) -> str:
    hour_text, minute_text = raw_time.strip().split(":", 1)
    try:
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        raise ValueError(f"Unrecognizable time value: {raw_time!r}")
    return f"{hour:02d}:{minute:02d}"


def extract_date(lines: Iterable[str]) -> str | None:
    for line in lines:
        match = DATE_PATTERN.search(line)
        if match:
            return match.group(1)
    return None


def find_registrations(lines: Iterable[str]) -> list[tuple[str, str, int]]:
    matches: list[tuple[str, str, int]] = []
    for line in lines:
        match = COMMAND_PATTERN.search(line)
        if not match:
            continue
        command = match.group("cmd").upper()
        if command not in VALID_COMMANDS:
            continue
        count = int(match.group("count"))
        if count == 0:
            continue
        time_value = normalize_time(match.group("time"))
        matches.append((time_value, match.group("op"), count))
    return matches


def process_file(path: Path) -> list[RegistrationEvent]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error reading {path}: {exc}", file=sys.stderr)
        return []

    lines = content.splitlines()
    date_text = extract_date(lines)
    if date_text is None:
        print(f"Warning: Could not find date in {path}", file=sys.stderr)
        return []

    try:
        weekday = datetime.strptime(date_text, "%Y-%m-%d").strftime("%a")
    except ValueError:
        print(f"Warning: Invalid date format in {path}: {date_text}", file=sys.stderr)
        return []

    registrations = find_registrations(lines)
    return [
        RegistrationEvent(date_text, weekday, time, op, count)
        for time, op, count in registrations
    ]


def main() -> None:
    args = parse_args()
    events: list[RegistrationEvent] = []
    for echo_file in args.echo_files:
        if not echo_file.exists():
            print(f"File not found: {echo_file}", file=sys.stderr)
            continue
        events.extend(process_file(echo_file))

    for event in events:
        print(
            f"{event.date} {event.weekday} {event.time} {event.operator} {event.count}"
        )

    if not events:
        return

    print()
    print()

    per_day: dict[str, list[RegistrationEvent]] = {}
    order: list[str] = []
    for event in events:
        if event.date not in per_day:
            per_day[event.date] = []
            order.append(event.date)
        per_day[event.date].append(event)

    for date_key in order:
        day_events = per_day[date_key]
        weekday = day_events[0].weekday
        total = 0
        for event in day_events:
            if event.operator == "+":
                total += event.count
            elif event.operator == "-":
                total -= event.count
            else:
                total = event.count
        print(
            f"{date_key} {weekday} {total} reg; {len(day_events)} reg commands"
        )


if __name__ == "__main__":
    main()
