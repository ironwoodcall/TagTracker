#!/usr/bin/env python3
"""Build a TagTracker datafile (JSON) directly from an ECHO transcript.

See docs/recreate-datafile-from-transcript.md for the design this
implements, and helpers/transcript_sim.py for the shared parser that
does the actual state reconstruction -- this file is just the renderer:
it maps a SimulatedDay onto the current datafile JSON shape (the same
shape common/tt_trackerday.py's TrackerDay._day_to_json_dict() writes)
and saves it.

Usage:
    helpers/transcript_to_datafile.py /tmp/tt-transcripts/echo-2026-04-26.txt
    helpers/transcript_to_datafile.py --dry-run /tmp/tt-transcripts/echo-*.txt
    helpers/transcript_to_datafile.py --out /tmp/out.json one-transcript.txt
    helpers/transcript_to_datafile.py --config /path/to/other_client_local_config.py *.txt

Copyright (C) 2023-2026 Julias Hocking & Todd Glover

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HELPERS_DIR = Path(__file__).resolve().parent
BIN_DIR = HELPERS_DIR.parent
if str(BIN_DIR) not in sys.path:
    sys.path.insert(0, str(BIN_DIR))
if str(HELPERS_DIR) not in sys.path:
    sys.path.insert(0, str(HELPERS_DIR))

try:
    # Resolvable by static analysis (helpers/ is a package -- see
    # helpers/__init__.py), but fails at runtime when this file is run
    # directly as a script (no parent package then) -- that's the normal
    # case, handled by the flat import below via the sys.path tweak above.
    from .transcript_sim import SimulatedDay, canonical_tagid, parse_tagids_str, simulate
except ImportError:
    from transcript_sim import (  # noqa: E402
        SimulatedDay,
        canonical_tagid,
        parse_tagids_str,
        simulate,
    )

# These mirror client_base_config.py's own stub defaults -- used only as
# fallback for whatever a given client_local_config.py doesn't define.
_CONFIG_DEFAULTS = {
    "SITE_NAME": "Default Site",
    "SITE_HANDLE": "bikeparking",
    "DATA_FOLDER": "../data",
    "REGULAR_TAGS": "",
    "OVERSIZE_TAGS": "",
    "RETIRED_TAGS": "",
}

_FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def load_tag_config(config_path: Path) -> dict:
    """Exec a client_local_config.py-shaped file and pull out what we need.

    These files are plain assignments (string/dict literals), no imports
    or control flow -- see client_local_config.py -- so exec'ing them
    standalone is safe and avoids the real client_base_config.py's
    import-time side effects (sys.exit on misconfiguration, pulling in
    tt_printer/tt_sounds, etc.), none of which this script needs.
    """
    namespace = dict(_CONFIG_DEFAULTS)
    if config_path.exists():
        source = config_path.read_text(encoding="utf-8")
        exec(compile(source, str(config_path), "exec"), namespace)  # noqa: S102
    else:
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return namespace


def resolve_date(day: SimulatedDay, transcript_path: Path, override: str | None) -> str | None:
    if override:
        return override
    if day.date:
        return day.date
    m = _FILENAME_DATE_RE.search(transcript_path.name)
    if m:
        return m.group(1)
    return None


def build_datafile_dict(
    day: SimulatedDay,
    *,
    date: str,
    site_name: str,
    site_handle: str,
    regular_tagids: set[str],
    oversize_tagids: set[str],
    retired_tagids: set[str],
    include_notes: bool,
    unknown_tag_size: str,
    warn,
) -> dict:
    bike_visits = []
    unknown_tags = set()
    for raw_tag, visits in day.visits.items():
        tagid = canonical_tagid(raw_tag)
        if tagid is None:
            warn(f"Skipping unparseable tag '{raw_tag}' ({len(visits)} visit(s))")
            continue
        if tagid in oversize_tagids:
            bike_size = "oversize"
        elif tagid in regular_tagids:
            bike_size = "regular"
        else:
            unknown_tags.add(tagid)
            if unknown_tag_size == "skip":
                warn(
                    f"Tag '{tagid}' is not in the regular/oversize config -- "
                    f"skipping its {len(visits)} visit(s) (see --unknown-tag-size)"
                )
                continue
            bike_size = unknown_tag_size
        for visit in visits:
            bike_visits.append(
                {
                    "tagid": tagid,
                    "bike_size": bike_size,
                    "time_in": f"{visit.time_in}:00" if visit.time_in else "",
                    "time_out": f"{visit.time_out}:00" if visit.time_out else "",
                }
            )
    bike_visits.sort(key=lambda v: (v["tagid"], v["time_in"]))

    if unknown_tags:
        warn(
            f"{len(unknown_tags)} tag(s) seen in the transcript aren't in the "
            f"config's regular/oversize lists: {sorted(unknown_tags)}"
        )

    notes = []
    if include_notes:
        for time_str, text in day.notes:
            if not text:
                continue
            if re.match(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$", time_str or ""):
                notes.append(f"A|{time_str}|{text}")
            else:
                notes.append(f"A||{text}")

    return {
        "comment:": f"This is a TagTracker datafile for {site_handle} on {date}.",
        "site_name": site_name,
        "site_handle": site_handle,
        "date": date,
        "time_open": day.time_open or "",
        "time_closed": day.time_closed or "",
        "registrations": day.registrations,
        "bike_visits": bike_visits,
        "regular_tagids": sorted(regular_tagids),
        "oversize_tagids": sorted(oversize_tagids),
        "retired_tagids": sorted(retired_tagids),
        "held_tagids": [],
        "notes": notes,
    }


def verify_round_trip(data: dict, path: Path) -> list[str]:
    """Best-effort: load the just-written file with the real TrackerDay code.

    Not required for this script's core job (it would need the full
    TagTracker import graph, which this script otherwise avoids), but a
    good sanity check when it's available. Returns a list of problems
    (empty if it loaded cleanly, or if verification couldn't run at all).
    """
    try:
        from common.tt_trackerday import TrackerDay, TrackerDayError
    except Exception as e:  # pylint:disable=broad-exception-caught
        return [f"(verification skipped -- could not import TrackerDay: {e})"]
    try:
        loaded = TrackerDay.load_from_file(str(path))
    except TrackerDayError as e:
        return [f"TrackerDay rejected the file: {e}"]
    except Exception as e:  # pylint:disable=broad-exception-caught
        return [f"(verification skipped -- unexpected error: {e})"]
    problems = []
    if loaded.registrations.num_registrations != data["registrations"]:
        problems.append("registrations mismatch after round-trip load")
    return problems


def process_one(args, transcript_path: Path, tag_config: dict) -> bool:
    """Returns True on success (file written or dry-run would-write)."""
    print(f"== {transcript_path.name} ==")
    text = transcript_path.read_text(encoding="utf-8", errors="replace")
    day = simulate(text)

    def warn(msg: str) -> None:
        print(f"  warning: {msg}")

    date = resolve_date(day, transcript_path, args.date)
    if not date:
        print("  ERROR: could not determine the date (no 'Editing ...' line, "
              "no YYYY-MM-DD in filename, no --date given) -- skipping.")
        return False

    if not day.time_open or not day.time_closed:
        print(f"  ERROR: could not determine opening/closing hours for {date} "
              "-- skipping. Pass --time-open/--time-closed to override.")
        return False
    if args.time_open:
        day.time_open = args.time_open
    if args.time_closed:
        day.time_closed = args.time_closed

    site_name = args.site_name or tag_config["SITE_NAME"]
    site_handle = args.site_handle or tag_config["SITE_HANDLE"]

    data = build_datafile_dict(
        day,
        date=date,
        site_name=site_name,
        site_handle=site_handle,
        regular_tagids=tag_config["_regular_tagids"],
        oversize_tagids=tag_config["_oversize_tagids"],
        retired_tagids=tag_config["_retired_tagids"],
        include_notes=not args.no_notes,
        unknown_tag_size=args.unknown_tag_size,
        warn=warn,
    )

    for w in day.warnings:
        warn(w)

    n_visits = len(data["bike_visits"])
    n_open = sum(1 for v in data["bike_visits"] if not v["time_out"])
    print(
        f"  date={date}  hours={data['time_open']}-{data['time_closed']}  "
        f"registrations={data['registrations']}  visits={n_visits} "
        f"({n_open} still open)  notes={len(data['notes'])}"
    )

    if args.out:
        out_path = Path(args.out)
    else:
        basename = f"{site_handle}_"
        out_path = Path(args.data_folder or (BIN_DIR / tag_config["DATA_FOLDER"])) / f"{basename}{date}.json"
    out_path = out_path.resolve()

    if args.dry_run:
        print(f"  (dry-run) would write {out_path}")
        return True

    if out_path.exists() and not args.force:
        print(f"  ERROR: {out_path} already exists -- use --force to overwrite. Skipping.")
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    print(f"  wrote {out_path}")

    if args.verify:
        problems = verify_round_trip(data, out_path)
        for p in problems:
            warn(p)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("transcripts", nargs="+", type=Path, help="ECHO transcript file(s)")
    parser.add_argument(
        "--config",
        type=Path,
        default=BIN_DIR / "client_local_config.py",
        help="client_local_config.py to source the tag universe from "
        "(default: %(default)s)",
    )
    parser.add_argument("--data-folder", type=Path, help="Folder to write datafiles into")
    parser.add_argument("--out", type=Path, help="Exact output path (only with one transcript)")
    parser.add_argument("--date", help="Override the date (YYYY-MM-DD)")
    parser.add_argument("--time-open", help="Override the opening time (HH:MM)")
    parser.add_argument("--time-closed", help="Override the closing time (HH:MM)")
    parser.add_argument("--site-name", help="Override the site name")
    parser.add_argument("--site-handle", help="Override the site handle")
    parser.add_argument("--no-notes", action="store_true", help="Omit notes from the output")
    parser.add_argument(
        "--unknown-tag-size",
        choices=["skip", "regular", "oversize"],
        default="skip",
        help="How to handle a tag not found in the config's regular/oversize "
        "lists (default: skip -- drop its visits and warn)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing datafile")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report; write nothing")
    parser.add_argument(
        "--no-verify",
        dest="verify",
        action="store_false",
        default=True,
        help="Skip the best-effort TrackerDay round-trip load after writing",
    )
    args = parser.parse_args()

    if args.out and len(args.transcripts) > 1:
        parser.error("--out can only be used with a single transcript")

    try:
        raw_config = load_tag_config(args.config)
    except FileNotFoundError as e:
        parser.error(str(e))
        return 2

    tag_config = dict(raw_config)
    tag_config["_regular_tagids"] = parse_tagids_str(raw_config["REGULAR_TAGS"])
    tag_config["_oversize_tagids"] = parse_tagids_str(raw_config["OVERSIZE_TAGS"])
    tag_config["_retired_tagids"] = parse_tagids_str(raw_config["RETIRED_TAGS"])

    ok = True
    for transcript_path in args.transcripts:
        if not transcript_path.exists():
            print(f"== {transcript_path} ==\n  ERROR: file not found.")
            ok = False
            continue
        if not process_one(args, transcript_path, tag_config):
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
