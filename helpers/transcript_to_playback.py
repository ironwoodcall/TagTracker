#!/usr/bin/env python3
"""Build a 'playback' command script from a TagTracker ECHO transcript.

See docs/recreate-datafile-from-transcript.md for the design this
implements, and helpers/transcript_sim.py for the shared parser that does
the actual state reconstruction -- this file is just the renderer: it
maps a SimulatedDay onto a minimal sequence of `in`/`out`/`reg` commands
that, typed into a live `tagtracker.py` session, reproduce the same end
state.

Deliberately NOT a literal replay of the transcript: mistakes, retries,
and anything later undone are already resolved out by the simulator, so
what's emitted is the *minimal* command set for the final state -- not
a keystroke-for-keystroke reproduction of the original session. Tags
that share a direction and a timestamp are grouped onto one line (e.g.
`in bf1 bf6 ga7 09:47`), matching how `in`/`out` actually take a tag
list plus one trailing time.

Usage:
    helpers/transcript_to_playback.py /tmp/tt-transcripts/echo-2026-04-26.txt
    helpers/transcript_to_playback.py --out playback.txt one-transcript.txt
    helpers/transcript_to_playback.py --annotate --no-reg *.txt

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
import re
import sys
from pathlib import Path

HELPERS_DIR = Path(__file__).resolve().parent
if str(HELPERS_DIR) not in sys.path:
    sys.path.insert(0, str(HELPERS_DIR))

try:
    # Resolvable by static analysis (helpers/ is a package -- see
    # helpers/__init__.py), but fails at runtime when this file is run
    # directly as a script (no parent package then) -- that's the normal
    # case, handled by the flat import below via the sys.path tweak above.
    from .transcript_sim import SimulatedDay, canonical_tagid, simulate
except ImportError:
    from transcript_sim import SimulatedDay, canonical_tagid, simulate  # noqa: E402

_FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _tag_sort_key(tag: str):
    """Sort tags the way a person reading them would expect: bf2 before bf10."""
    m = re.match(r"^([a-z]{2})([0-9]+)$", tag)
    if not m:
        return (tag, 0)
    return (m.group(1), int(m.group(2)))


def render_playback(
    day: SimulatedDay, *, include_reg: bool = True
) -> tuple[list[str], set[str]]:
    """Render a SimulatedDay as a minimal in/out/reg command script.

    Returns (lines, unknown_tags) -- unknown_tags is reported separately
    (not as a '#' line in the command stream itself) so the returned
    lines stay safe to pipe straight into tagtracker.py even without
    --annotate.
    """
    # (time, direction) -> set of tags. direction is "in" or "out".
    groups: dict[tuple[str, str], set[str]] = {}
    unknown_tags: set[str] = set()
    for raw_tag, visits in day.visits.items():
        tagid = canonical_tagid(raw_tag)
        if tagid is None:
            unknown_tags.add(raw_tag)
            continue
        for visit in visits:
            if visit.time_in:
                groups.setdefault((visit.time_in, "in"), set()).add(tagid)
            if visit.time_out:
                groups.setdefault((visit.time_out, "out"), set()).add(tagid)

    # Out before in at the same timestamp -- needed for a same-minute
    # flip/reuse (check the tag out before checking it back in again).
    direction_rank = {"out": 0, "in": 1}
    ordered_keys = sorted(groups.keys(), key=lambda k: (k[0], direction_rank[k[1]]))

    lines = []
    for time_str, direction in ordered_keys:
        tags = sorted(groups[(time_str, direction)], key=_tag_sort_key)
        lines.append(f"{direction} {' '.join(tags)} {time_str}")

    if include_reg and day.registrations:
        lines.append(f"reg = {day.registrations}")

    return lines, unknown_tags


def resolve_date(day: SimulatedDay, transcript_path: Path, override: str | None) -> str | None:
    if override:
        return override
    if day.date:
        return day.date
    m = _FILENAME_DATE_RE.search(transcript_path.name)
    if m:
        return m.group(1)
    return None


def process_one(args, transcript_path: Path) -> bool:
    text = transcript_path.read_text(encoding="utf-8", errors="replace")
    day = simulate(text)
    date = resolve_date(day, transcript_path, args.date)

    lines, unknown_tags = render_playback(day, include_reg=not args.no_reg)
    n_in = sum(1 for l in lines if l.startswith("in "))
    n_out = sum(1 for l in lines if l.startswith("out "))

    all_warnings = list(day.warnings)
    if unknown_tags:
        all_warnings.append(
            f"{len(unknown_tags)} unparseable tag(s) skipped: {sorted(unknown_tags)}"
        )

    body = []
    if args.annotate:
        body.append(f"# playback for {date or '(unknown date)'}, from {transcript_path.name}")
        if day.time_open and day.time_closed:
            body.append(f"# original hours: {day.time_open} - {day.time_closed}")
        for w in all_warnings:
            body.append(f"# warning: {w}")
    body.extend(lines)

    print(f"== {transcript_path.name} ==", file=sys.stderr)
    print(
        f"  date={date}  in-lines={n_in}  out-lines={n_out}  "
        f"registrations={day.registrations}",
        file=sys.stderr,
    )
    for w in all_warnings:
        print(f"  warning: {w}", file=sys.stderr)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text("\n".join(body) + "\n", encoding="utf-8")
        print(f"  wrote {out_path}", file=sys.stderr)
    else:
        print("\n".join(body))

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("transcripts", nargs="+", type=Path, help="ECHO transcript file(s)")
    parser.add_argument("--out", type=Path, help="Write to this file instead of stdout (only with one transcript)")
    parser.add_argument("--date", help="Override the date (used only for the --annotate header)")
    parser.add_argument("--no-reg", action="store_true", help="Omit the trailing 'reg = N' line")
    parser.add_argument(
        "--annotate",
        action="store_true",
        help="Include '#' comment lines (date, hours, warnings). Off by "
        "default so the output is safe to pipe straight into tagtracker.py.",
    )
    args = parser.parse_args()

    if args.out and len(args.transcripts) > 1:
        parser.error("--out can only be used with a single transcript")

    ok = True
    for transcript_path in args.transcripts:
        if not transcript_path.exists():
            print(f"== {transcript_path} ==\n  ERROR: file not found.", file=sys.stderr)
            ok = False
            continue
        if not process_one(args, transcript_path):
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
