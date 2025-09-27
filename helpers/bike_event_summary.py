#!/usr/bin/env python3
"""Summarize bike visit events from a TagTracker JSON datafile.

For analysing and debugging.

Reads the JSON datafile, aggregates arrivals and departures at each
event time, and prints the running total of bikes on site.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print arrival/departure counts and running totals for a TagTracker "
            "JSON datafile."
        )
    )
    parser.add_argument(
        "datafile",
        type=Path,
        help="Path to the TagTracker JSON datafile",
    )
    return parser.parse_args()


def clean_time(value) -> str:
    """Return a normalized time string or an empty string if not usable."""
    if value is None:
        return ""
    text = str(value).strip()
    return text


def load_events(datafile: Path) -> Dict[str, Dict[str, int]]:
    """Collect arrival and departure counts keyed by event time."""
    with datafile.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    visits = data.get("bike_visits", [])
    events: Dict[str, Dict[str, int]] = defaultdict(lambda: {"in": 0, "out": 0})

    for visit in visits:
        time_in = clean_time(visit.get("time_in"))
        if time_in:
            events[time_in]["in"] += 1

        time_out = clean_time(visit.get("time_out"))
        if time_out:
            events[time_out]["out"] += 1

    return events


def print_summary(events: Dict[str, Dict[str, int]]) -> None:
    """Print the event-by-event summary with running totals and peak info."""
    running_total = 0
    max_total: int | None = None
    max_time = ""
    for event_time in sorted(events.keys()):
        incoming = events[event_time]["in"]
        outgoing = events[event_time]["out"]
        running_total += incoming - outgoing
        print(f"{event_time} +{incoming} -{outgoing} = {running_total}")

        if max_total is None or running_total > max_total:
            max_total = running_total
            max_time = event_time

    if max_total is not None:
        print()
        print(f"Max onsite: {max_total} at {max_time}")


def main() -> None:
    args = parse_args()
    if not args.datafile.exists():
        raise SystemExit(f"Datafile not found: {args.datafile}")

    events = load_events(args.datafile)
    if not events:
        print("No bike visits found.")
        return

    print_summary(events)


if __name__ == "__main__":
    main()
