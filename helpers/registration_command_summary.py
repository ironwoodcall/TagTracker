#!/usr/bin/env python3
"""Summarize registration commands from TagTracker ECHO transcripts."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Iterable, NamedTuple

DATE_PATTERN = re.compile(r"\((\d{4}-\d{2}-\d{2})\)")
COMMAND_PATTERN = re.compile(
    r"^\s*(?P<time>\d{1,2}:\d{2}).*?>>\s*(?P<cmd>r|reg|register)\s*(?P<op>[+\-=])\s*(?P<count>[1-9]\d*)",
    re.IGNORECASE,
)
FOLLOWING_TIMESTAMP_PATTERN = re.compile(
    r"^\s*(?P<time>\d{1,2}:\d{2}) .*>>>", re.IGNORECASE
)
SUCCESS_PREFIX = "There is a total of "


class RegistrationEvent(NamedTuple):
    date: str
    time: str
    registrations: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Emit registration commands from TagTracker ECHO transcript files as CSV."
        )
    )
    parser.add_argument(
        "echo_files",
        type=Path,
        nargs="+",
        help="Path(s) to TagTracker ECHO transcript file(s)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug details about parsed commands to stderr.",
    )
    return parser.parse_args()


def normalize_time(raw_time: str) -> str:
    hour_text, minute_text = raw_time.strip().split(":", 1)
    try:
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise ValueError(f"Unrecognizable time value: {raw_time!r}") from exc
    return f"{hour:02d}:{minute:02d}"


def extract_date(lines: Iterable[str]) -> str | None:
    for line in lines:
        match = DATE_PATTERN.search(line)
        if match:
            return match.group(1)
    return None


def debug_print(enabled: bool, message: str) -> None:
    if enabled:
        print(message, file=sys.stderr)


def find_registrations(
    lines: list[str], debug: bool = False
) -> list[dict[str, str | int]]:
    matches: list[dict[str, str | int]] = []
    total_lines = len(lines)
    for index, line in enumerate(lines):
        match = COMMAND_PATTERN.search(line)
        if not match:
            continue
        count = int(match.group("count"))
        operator = match.group("op")
        # Locate success response.
        response_index = index + 1
        response_line: str | None = None
        while response_index < total_lines:
            candidate = lines[response_index].strip()
            if candidate == "":
                response_index += 1
                continue
            response_line = candidate
            break
        if response_line is None:
            debug_print(
                debug,
                f"Skipping command at line {index+1}: no response line found.",
            )
            continue
        if not response_line.startswith(SUCCESS_PREFIX):
            debug_print(
                debug,
                f"Skipping command at line {index+1}: response '{response_line}' is not a success message.",
            )
            continue

        # Determine timestamp using the first non-blank line after the response
        # that looks like a command prompt; fall back to the original command time.
        timestamp_value: str | None = None
        seek_index = response_index + 1
        while seek_index < total_lines:
            candidate_line = lines[seek_index]
            if candidate_line.strip() == "":
                seek_index += 1
                continue
            follow_match = FOLLOWING_TIMESTAMP_PATTERN.match(candidate_line)
            if follow_match:
                timestamp_value = normalize_time(follow_match.group("time"))
                debug_print(
                    debug,
                    f"Command at line {index+1}: using follow-up timestamp {timestamp_value}.",
                )
            break
        if timestamp_value is None:
            timestamp_value = normalize_time(match.group("time"))
            debug_print(
                debug,
                f"Command at line {index+1}: falling back to command timestamp {timestamp_value}.",
            )

        debug_print(
            debug,
            f"Accepted command at line {index+1}: operator='{operator}', count={count}, timestamp={timestamp_value}.",
        )
        matches.append(
            {
                "timestamp": timestamp_value,
                "operator": operator,
                "count": count,
                "line": index + 1,
            }
        )
    return matches


def process_file(path: Path, debug: bool = False) -> list[RegistrationEvent]:
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

    raw_commands = find_registrations(lines, debug=debug)
    running_total = 0
    events: list[RegistrationEvent] = []
    for command in raw_commands:
        timestamp = command["timestamp"]
        operator = command["operator"]
        count = command["count"]
        line_no = command["line"]

        if operator == "+":
            delta = count
            running_total += delta
        elif operator == "-":
            delta = -count
            running_total += delta
        else:  # "="
            new_total = count
            delta = new_total - running_total
            running_total = new_total

        if delta == 0:
            debug_print(
                debug,
                f"Ignoring zero delta at line {line_no}: running total unchanged.",
            )
            continue

        events.append(RegistrationEvent(date_text, timestamp, delta))
    return events


def main() -> None:
    args = parse_args()
    events: list[RegistrationEvent] = []
    for echo_file in args.echo_files:
        if not echo_file.exists():
            print(f"File not found: {echo_file}", file=sys.stderr)
            continue
        events.extend(process_file(echo_file, debug=args.debug))

    if not events:
        return

    events.sort(key=lambda evt: (evt.date, evt.time))

    writer = csv.writer(sys.stdout)
    writer.writerow(["DATE", "TIME", "REGISTRATIONS"])
    for event in events:
        writer.writerow([event.date, event.time, event.registrations])


if __name__ == "__main__":
    main()
