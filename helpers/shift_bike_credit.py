import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from helpers.schedule_shift_parser import Shift

TeamKey = Tuple[str, ...]


@dataclass
class ShiftSpan:
    person: str
    day: date
    start: datetime
    end: datetime


@dataclass
class ActivityRecord:
    timestamp: datetime
    delta: int


def generate_unique_initials(
    names: Iterable[str],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    unique_names: List[str] = []
    seen = set()
    for name in names:
        if not name:
            continue
        stripped = name.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        unique_names.append(stripped)

    entries: List[Dict[str, object]] = []
    for idx, name in enumerate(unique_names):
        if not name.strip():
            continue
        parts = [part for part in name.split() if part]
        first = parts[0]
        last = parts[-1] if len(parts) > 1 else ""
        entries.append(
            {
                "index": idx,
                "name": name,
                "first": first,
                "last": last,
                "first_len": 1,
                "last_len": 1 if last else 0,
                "extra_suffix": None,
            }
        )

    if not entries:
        return {}, {}

    def build_abbr(entry: Dict[str, object]) -> str:
        first = entry["first"]
        first_len = entry["first_len"]
        first_part = first[:first_len] if first_len <= len(first) else first
        first_formatted = first_part.capitalize()

        last = entry["last"]
        last_len = entry["last_len"]
        last_part = ""
        if last:
            if last_len <= 0:
                last_len = 1
            last_slice = last[:last_len] if last_len <= len(last) else last
            last_part = last_slice[0].upper() + last_slice[1:].lower()

        suffix_value = entry.get("extra_suffix")
        suffix = str(suffix_value) if suffix_value else ""
        return f"{first_formatted}{last_part}{suffix}"

    while True:
        abbr_map: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        for entry in entries:
            abbr_map[build_abbr(entry)].append(entry)

        duplicates = [group for group in abbr_map.values() if len(group) > 1]
        if not duplicates:
            break

        for group in duplicates:
            for position, entry in enumerate(group):
                if entry["first_len"] < len(entry["first"]):
                    entry["first_len"] += 1
                elif entry["last"] and entry["last_len"] < len(entry["last"]):
                    entry["last_len"] += 1
                else:
                    current_suffix = entry.get("extra_suffix")
                    if current_suffix is None:
                        entry["extra_suffix"] = position + 1
                    else:
                        entry["extra_suffix"] = current_suffix * 10 + (position + 1)

    abbreviations = {entry["name"]: build_abbr(entry) for entry in entries}
    reverse_map = {abbr: name for name, abbr in abbreviations.items()}
    return abbreviations, reverse_map


def normalize_shifts(
    shifts: Iterable[Shift], aliases: Dict[str, str]
) -> List[ShiftSpan]:
    spans: List[ShiftSpan] = []
    for shift in shifts:
        try:
            shift_day = datetime.strptime(shift.date, "%Y-%m-%d").date()
            start_clock = datetime.strptime(shift.start_time, "%H:%M").time()
            end_clock = datetime.strptime(shift.end_time, "%H:%M").time()
        except ValueError as exc:
            raise ValueError(
                f"Invalid date/time in shift record for {shift.person}: {exc}"
            ) from exc

        start_dt = datetime.combine(shift_day, start_clock)
        end_dt = datetime.combine(shift_day, end_clock)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        spans.append(
            ShiftSpan(
                person=aliases.get(shift.person, shift.person),
                day=shift_day,
                start=start_dt,
                end=end_dt,
            )
        )
    return spans


def load_shift_schedule(path: Path) -> List[Shift]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required_fields = {"PERSON", "DATE", "START_TIME", "END_TIME"}
        if reader.fieldnames is None or not required_fields.issubset(
            set(name.strip() for name in reader.fieldnames)
        ):
            raise ValueError(
                "Input schedule CSV must contain PERSON,DATE,START_TIME,END_TIME columns."
            )
        shifts: List[Shift] = []
        for row in reader:
            person = row.get("PERSON", "").strip()
            shift_date = row.get("DATE", "").strip()
            start_time = row.get("START_TIME", "").strip()
            end_time = row.get("END_TIME", "").strip()
            if not all([person, shift_date, start_time, end_time]):
                continue
            shifts.append(
                Shift(
                    person=person,
                    date=shift_date,
                    start_time=start_time,
                    end_time=end_time,
                )
            )
    return shifts


def build_shift_index(spans: Iterable[ShiftSpan]) -> Dict[date, List[ShiftSpan]]:
    index: Dict[date, List[ShiftSpan]] = defaultdict(list)
    for span in spans:
        current_day = span.start.date()
        final_day = span.end.date()
        while current_day <= final_day:
            day_start = datetime.combine(current_day, time.min)
            day_end = day_start + timedelta(days=1)
            if span.end > day_start and span.start < day_end:
                index[current_day].append(span)
            current_day += timedelta(days=1)
    return index


def compute_shift_stats(
    spans: Iterable[ShiftSpan],
) -> Tuple[
    Dict[str, int],
    Dict[str, float],
    Dict[str, Dict[date, int]],
    Dict[str, Dict[date, float]],
]:
    person_shift_counts: Dict[str, int] = defaultdict(int)
    person_shift_hours: Dict[str, float] = defaultdict(float)
    person_date_shift_counts: Dict[str, Dict[date, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    person_date_shift_hours: Dict[str, Dict[date, float]] = defaultdict(
        lambda: defaultdict(float)
    )

    for span in spans:
        hours = (span.end - span.start).total_seconds() / 3600.0
        person_shift_counts[span.person] += 1
        person_shift_hours[span.person] += hours
        person_date_shift_counts[span.person][span.day] += 1
        person_date_shift_hours[span.person][span.day] += hours

    return (
        person_shift_counts,
        person_shift_hours,
        person_date_shift_counts,
        person_date_shift_hours,
    )


def compute_team_shift_stats(
    spans: Iterable[ShiftSpan],
) -> Tuple[
    Dict[TeamKey, int],
    Dict[TeamKey, float],
    Dict[TeamKey, Dict[date, int]],
    Dict[TeamKey, Dict[date, float]],
]:
    team_shift_counts: Dict[TeamKey, int] = defaultdict(int)
    team_shift_hours: Dict[TeamKey, float] = defaultdict(float)
    team_date_shift_counts: Dict[TeamKey, Dict[date, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    team_date_shift_hours: Dict[TeamKey, Dict[date, float]] = defaultdict(
        lambda: defaultdict(float)
    )

    day_entries: Dict[date, List[Tuple[datetime, datetime, str]]] = defaultdict(list)
    for span in spans:
        current_day = span.start.date()
        final_day = span.end.date()
        while current_day <= final_day:
            day_start = datetime.combine(current_day, time.min)
            day_end = day_start + timedelta(days=1)
            seg_start = max(span.start, day_start)
            seg_end = min(span.end, day_end)
            if seg_end > seg_start:
                day_entries[current_day].append((seg_start, seg_end, span.person))
            current_day += timedelta(days=1)

    for day, entries in day_entries.items():
        events: List[Tuple[datetime, int, str]] = []
        for seg_start, seg_end, person in entries:
            events.append((seg_start, 0, person))  # start
            events.append((seg_end, 1, person))  # end
        events.sort(key=lambda item: (item[0], item[1], item[2]))

        active = set()
        prev_time: Optional[datetime] = None
        prev_team: Optional[TeamKey] = None

        for timestamp, order, person in events:
            if prev_time is not None and timestamp > prev_time and prev_team:
                duration = (timestamp - prev_time).total_seconds() / 3600.0
                team_shift_counts[prev_team] += 1
                team_shift_hours[prev_team] += duration
                team_date_shift_counts[prev_team][day] += 1
                team_date_shift_hours[prev_team][day] += duration
            if order == 0:
                active.add(person)
            else:
                active.discard(person)

            prev_time = timestamp
            current_team = tuple(sorted(active)) if len(active) == 2 else None
            prev_team = current_team

    return (
        team_shift_counts,
        team_shift_hours,
        team_date_shift_counts,
        team_date_shift_hours,
    )


def parse_activity_log(path: Path) -> List[ActivityRecord]:
    records: List[ActivityRecord] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(
                f"Activity log {path} must contain DATE,TIME,REGISTRATIONS columns."
            )
        header_map = {field.strip().upper(): field for field in reader.fieldnames}
        expected_fields = {"DATE", "TIME", "REGISTRATIONS"}
        if not expected_fields.issubset(header_map.keys()):
            raise ValueError(
                f"Activity log {path} must contain DATE,TIME,REGISTRATIONS columns."
            )
        date_key = header_map["DATE"]
        time_key = header_map["TIME"]
        delta_key = header_map["REGISTRATIONS"]
        for row_number, row in enumerate(reader, start=2):
            if not row:
                continue
            try:
                date_text = row.get(date_key, "").strip()
                time_text = row.get(time_key, "").strip()
                delta_text = row.get(delta_key, "").strip()
            except AttributeError:
                raise ValueError(
                    f"Malformed row {row_number} in {path}: {row!r}"
                ) from None
            if not (date_text and time_text and delta_text):
                continue
            try:
                timestamp = datetime.strptime(
                    f"{date_text} {time_text}", "%Y-%m-%d %H:%M"
                )
            except ValueError as exc:
                raise ValueError(
                    f"Invalid date/time at row {row_number} in {path}: {exc}"
                ) from exc
            try:
                delta = int(delta_text)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid registrations value at row {row_number} in {path}: {delta_text!r}"
                ) from exc
            if delta == 0:
                continue
            records.append(ActivityRecord(timestamp=timestamp, delta=delta))
    return records


def find_active_workers(
    shift_index: Dict[date, List[ShiftSpan]],
    timestamp: datetime,
) -> List[str]:
    workers = []
    for span in shift_index.get(timestamp.date(), []):
        if span.start <= timestamp < span.end:
            workers.append(span.person)
    return workers


def aggregate_points(
    spans: Iterable[ShiftSpan],
    activities: Iterable[ActivityRecord],
) -> Tuple[
    Dict[str, int],
    Dict[str, Dict[date, int]],
    Dict[TeamKey, int],
    Dict[TeamKey, Dict[date, int]],
    List[Tuple[ActivityRecord, List[str]]],
    List[ActivityRecord],
]:
    shift_index = build_shift_index(spans)
    person_units: Dict[str, int] = defaultdict(int)
    person_date_units: Dict[str, Dict[date, int]] = defaultdict(lambda: defaultdict(int))
    team_units: Dict[TeamKey, int] = defaultdict(int)
    team_date_units: Dict[TeamKey, Dict[date, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    unassigned: List[ActivityRecord] = []
    assignments: List[Tuple[ActivityRecord, List[str]]] = []

    for act in activities:
        workers = find_active_workers(shift_index, act.timestamp)
        if not workers:
            unassigned.append(act)
            assignments.append((act, []))
            continue
        act_day = act.timestamp.date()
        workers_sorted = sorted(workers)
        for worker in workers:
            person_units[worker] += act.delta
            person_date_units[worker][act_day] += act.delta
        if len(workers_sorted) == 2:
            team_key: TeamKey = tuple(workers_sorted)
            team_units[team_key] += act.delta
            team_date_units[team_key][act_day] += act.delta
        assignments.append((act, workers_sorted))
    return (
        person_units,
        person_date_units,
        team_units,
        team_date_units,
        assignments,
        unassigned,
    )


def build_person_table(
    person_units: Dict[str, int],
    person_date_units: Dict[str, Dict[date, int]],
    person_shift_counts: Dict[str, int],
    person_shift_hours: Dict[str, float],
    person_date_shift_counts: Dict[str, Dict[date, int]],
    person_date_shift_hours: Dict[str, Dict[date, float]],
    alias_reverse_map: Dict[str, str],
    month: str | None = None,
) -> Tuple[List[str], List[List[str]]]:
    headers = [
        "PERSON",
        "POINTS",
        "NUM_SHIFTS",
        "SHIFT_HOURS",
        "REG_PER_HR",
        "FULL_NAME",
    ]
    rows: List[List[str]] = []
    all_people = (
        set(person_units.keys())
        | set(person_shift_counts.keys())
        | set(person_date_shift_counts.keys())
    )
    for person in sorted(all_people):
        points_total = 0.0
        num_shifts_total = 0
        shift_hours_total = 0.0
        if month is None:
            points_total = person_units.get(person, 0) * 0.5
            num_shifts_total = person_shift_counts.get(person, 0)
            shift_hours_total = person_shift_hours.get(person, 0.0)
        else:
            for day, units in person_date_units.get(person, {}).items():
                if day.strftime("%Y-%m") == month:
                    points_total += units * 0.5
            for day, count in person_date_shift_counts.get(person, {}).items():
                if day.strftime("%Y-%m") == month:
                    num_shifts_total += count
            for day, hours in person_date_shift_hours.get(person, {}).items():
                if day.strftime("%Y-%m") == month:
                    shift_hours_total += hours
        if points_total == 0 and num_shifts_total == 0 and shift_hours_total == 0:
            continue
        reg_per_hr = points_total / shift_hours_total if shift_hours_total else 0.0
        rows.append(
            [
                person,
                f"{points_total:.2f}",
                str(num_shifts_total),
                f"{shift_hours_total:.2f}",
                f"{reg_per_hr:.2f}",
                alias_reverse_map.get(person, ""),
            ]
        )
    return headers, rows


def build_team_table(
    team_units: Dict[TeamKey, int],
    team_date_units: Dict[TeamKey, Dict[date, int]],
    team_shift_hours: Dict[TeamKey, float],
    team_date_shift_hours: Dict[TeamKey, Dict[date, float]],
    month: str | None = None,
) -> Tuple[List[str], List[List[str]]]:
    rows: List[List[str]] = []
    names_set = set()
    if month is None:
        for team in team_units:
            names_set.update(team)
        for team in team_shift_hours:
            names_set.update(team)
    else:
        for team, day_map in team_date_units.items():
            if any(d.strftime("%Y-%m") == month for d in day_map.keys()):
                names_set.update(team)
        for team, day_map in team_date_shift_hours.items():
            if any(d.strftime("%Y-%m") == month for d in day_map.keys()):
                names_set.update(team)
    names = sorted(names_set)
    headers = ["PERSON"] + names
    for row_name in names:
        row = [row_name]
        for col_name in names:
            if row_name == col_name:
                row.append("")
                continue
            key = tuple(sorted((row_name, col_name)))
            if month is None:
                hours = team_shift_hours.get(key, 0.0)
                points = team_units.get(key, 0)
            else:
                hours = 0.0
                points = 0
                for day, value in team_date_shift_hours.get(key, {}).items():
                    if day.strftime("%Y-%m") == month:
                        hours += value
                for day, value in team_date_units.get(key, {}).items():
                    if day.strftime("%Y-%m") == month:
                        points += value
            if hours:
                row.append(f"{(points / hours):.2f}")
            else:
                row.append("")
        rows.append(row)
    return headers, rows


def build_registration_table(
    assignments: Iterable[Tuple[ActivityRecord, List[str]]],
    alias_reverse_map: Dict[str, str],
    month: str | None = None,
) -> Tuple[List[str], List[List[str]]]:
    headers = ["DATE", "TIME", "DELTA", "WORKERS"]
    rows: List[List[str]] = []
    for record, workers in assignments:
        if month is not None and record.timestamp.strftime("%Y-%m") != month:
            continue
        date_text = record.timestamp.date().isoformat()
        time_text = record.timestamp.strftime("%H:%M")
        if workers:
            full_names = [alias_reverse_map.get(worker, worker) for worker in workers]
            workers_text = "; ".join(
                f"{worker} ({full})" for worker, full in zip(workers, full_names)
            )
        else:
            workers_text = ""
        rows.append(
            [
                date_text,
                time_text,
                str(record.delta),
                workers_text,
            ]
        )
    return headers, rows


def prepare_tables(
    person_units: Dict[str, int],
    person_date_units: Dict[str, Dict[date, int]],
    person_shift_counts: Dict[str, int],
    person_shift_hours: Dict[str, float],
    person_date_shift_counts: Dict[str, Dict[date, int]],
    person_date_shift_hours: Dict[str, Dict[date, float]],
    team_units: Dict[TeamKey, int],
    team_date_units: Dict[TeamKey, Dict[date, int]],
    team_shift_hours: Dict[TeamKey, float],
    team_date_shift_hours: Dict[TeamKey, Dict[date, float]],
    alias_reverse_map: Dict[str, str],
    assignments: Iterable[Tuple[ActivityRecord, List[str]]],
    month: str | None = None,
) -> List[Tuple[str, List[str], List[List[str]]]]:
    person_headers, person_rows = build_person_table(
        person_units,
        person_date_units,
        person_shift_counts,
        person_shift_hours,
        person_date_shift_counts,
        person_date_shift_hours,
        alias_reverse_map,
        month,
    )
    team_headers, team_rows = build_team_table(
        team_units, team_date_units, team_shift_hours, team_date_shift_hours, month
    )
    registration_headers, registration_rows = build_registration_table(
        assignments, alias_reverse_map, month
    )
    return [
        ("person_metrics", person_headers, person_rows),
        ("team_metrics", team_headers, team_rows),
        ("registration_log", registration_headers, registration_rows),
    ]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Combine structured shift schedule data with bike registration activity "
            "logs to estimate bikes handled per worker and two-person team combinations. "
            "Each registration delta assigns ±0.5 points per worker and ±1 point per team."
        )
    )
    parser.add_argument("schedule_csv", type=Path, help="Shift schedule CSV produced by schedule_shift_parser.")
    parser.add_argument(
        "activity_log",
        type=Path,
        help="CSV activity log with DATE,TIME,REGISTRATIONS columns.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional destination CSV. Defaults to stdout.",
    )
    parser.add_argument(
        "--by-month",
        action="store_true",
        help="Emit separate tables for each month contained in the schedule.",
    )
    parser.add_argument(
        "--report-unassigned",
        action="store_true",
        help="Print lines with no matching shift to stderr for review.",
    )
    return parser


def main(argv: List[str] | None = None) -> None:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    raw_shifts = load_shift_schedule(args.schedule_csv)
    alias_map, alias_reverse_map = generate_unique_initials(
        shift.person for shift in raw_shifts
    )
    spans = normalize_shifts(raw_shifts, alias_map)
    activities = parse_activity_log(args.activity_log)

    (
        person_shift_counts,
        person_shift_hours,
        person_date_shift_counts,
        person_date_shift_hours,
    ) = compute_shift_stats(spans)
    (
        team_shift_counts,
        team_shift_hours,
        team_date_shift_counts,
        team_date_shift_hours,
    ) = compute_team_shift_stats(spans)
    (
        person_units,
        person_date_units,
        team_units,
        team_date_units,
        assignments,
        unassigned,
    ) = aggregate_points(spans, activities)

    months = sorted({span.day.strftime("%Y-%m") for span in spans})

    def export_tables(
        tables: List[Tuple[str, List[str], List[List[str]]]],
        directory: Path,
        stem: str,
        suffix: str,
        prefix: str | None = None,
    ) -> None:
        for index, (_, headers, rows) in enumerate(tables, start=1):
            if prefix:
                filename = f"{stem}_{prefix}_{index}{suffix}"
            else:
                filename = f"{stem}{index}{suffix}"
            output_path = directory / filename
            with output_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerows(rows)

    if args.by_month:
        if args.output is None:
            writer = csv.writer(sys.stdout)
            for month in months:
                tables = prepare_tables(
                    person_units,
                    person_date_units,
                    person_shift_counts,
                    person_shift_hours,
                    person_date_shift_counts,
                    person_date_shift_hours,
                    team_units,
                    team_date_units,
                    team_shift_hours,
                    team_date_shift_hours,
                    alias_reverse_map,
                    assignments,
                    month,
                )
                writer.writerow([f"MONTH", month])
                for table_index, (_, headers, rows) in enumerate(tables):
                    writer.writerow(headers)
                    writer.writerows(rows)
                    if table_index < len(tables) - 1:
                        writer.writerow([])
                writer.writerow([])
        else:
            base_path: Path = args.output
            base_path.parent.mkdir(parents=True, exist_ok=True)
            suffix = base_path.suffix or ".csv"
            stem = base_path.stem
            for month in months:
                tables = prepare_tables(
                    person_units,
                    person_date_units,
                    person_shift_counts,
                    person_shift_hours,
                    person_date_shift_counts,
                    person_date_shift_hours,
                    team_units,
                    team_date_units,
                    team_shift_hours,
                    team_date_shift_hours,
                    alias_reverse_map,
                    assignments,
                    month,
                )
                export_tables(tables, base_path.parent, stem, suffix, month)
    else:
        tables = prepare_tables(
            person_units,
            person_date_units,
            person_shift_counts,
            person_shift_hours,
            person_date_shift_counts,
            person_date_shift_hours,
            team_units,
            team_date_units,
            team_shift_hours,
            team_date_shift_hours,
            alias_reverse_map,
            assignments,
            None,
        )

        if args.output:
            base_path: Path = args.output
            base_path.parent.mkdir(parents=True, exist_ok=True)
            suffix = base_path.suffix or ".csv"
            stem = base_path.stem
            export_tables(tables, base_path.parent, stem, suffix, None)
        else:
            writer = csv.writer(sys.stdout)
            for table_index, (_, headers, rows) in enumerate(tables):
                writer.writerow(headers)
                writer.writerows(rows)
                if table_index < len(tables) - 1:
                    writer.writerow([])

    if args.report_unassigned and unassigned:
        for act in unassigned:
            print(
                f"No shift found for {act.timestamp.strftime('%Y-%m-%d %H:%M')} delta={act.delta}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
