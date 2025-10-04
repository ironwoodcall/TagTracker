"""Compact summaries for the TagTracker dump command."""

from __future__ import annotations

import os
from collections import Counter
from typing import Iterable, TYPE_CHECKING

import client_base_config as cfg
import common.tt_constants as k
from common.tt_biketag import BikeTag
from common.tt_time import VTime
from tt_notes import NOTE_ACTIVE, NOTE_AUTO_DELETED, NOTE_HAND_RECOVERED

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from common.tt_bikevisit import BikeVisit
    from common.tt_trackerday import TrackerDay


_TYPE_CODES = {
    k.REGULAR: "R",
    k.OVERSIZE: "O",
}


def build_dump(today: "TrackerDay", detailed: bool = False) -> list[str]:
    """Return a compact textual summary of today's state."""

    header = _day_header(today)
    flow_line = _flow_summary(today)
    tag_line = _tag_summary(today)
    notes_line = _notes_summary(today)
    config_lines = _config_summary(today)

    lines: list[str] = [header, flow_line, tag_line, notes_line]
    lines.extend(config_lines)

    if detailed:
        lines.extend(_detailed_lines(today))

    return [line for line in lines if line]


def _day_header(today: "TrackerDay") -> str:
    date = today.date or "unknown"
    open_time = _format_time(today.time_open)
    close_time = _format_time(today.time_closed)
    site = today.site_name or "-"
    handle = today.site_handle or "-"
    filepath = today.filepath or ""
    filebit = f" | file {os.path.basename(filepath)}" if filepath else ""
    return (
        f"TrackerDay {date} {open_time}-{close_time}"
        f" | site {site} ({handle})"
        f"{filebit}"
    )


def _flow_summary(today: "TrackerDay") -> str:
    visits = today.all_visits()
    visit_type_counts = Counter()
    finished: list["BikeVisit"] = []
    for visit in visits:
        bike_type = today.biketags.get(visit.tagid)
        type_code = _type_code(bike_type.bike_type) if bike_type else "?"
        visit_type_counts[type_code] += 1
        if visit.time_out:
            finished.append(visit)

    total_visits = len(visits)
    visit_bit = _format_type_counts(total_visits, visit_type_counts)

    parked_total, parked_reg, parked_ovr = today.num_bikes_parked("now")
    parked_bit = _format_type_counts(
        parked_total,
        Counter({"R": parked_reg, "O": parked_ovr}),
        label="parked",
    )

    returned_total, returned_reg, returned_ovr = today.num_bikes_returned("now")
    returned_bit = _format_type_counts(
        returned_total,
        Counter({"R": returned_reg, "O": returned_ovr}),
        label="returned",
    )

    in_use_tags = today.tags_in_use("now")
    in_use_counts = Counter()
    for tag in in_use_tags:
        bike = today.biketags.get(tag)
        in_use_counts[_type_code(bike.bike_type) if bike else "?"] += 1
    in_use_bit = _format_type_counts(
        len(in_use_tags),
        in_use_counts,
        label="on_site",
    )

    max_load, max_time = today.max_bikes_up_to_time("now")
    max_bit = (
        f"max {max_load}@{_format_time(max_time)}" if max_load else "max 0"
    )

    latest = _format_time(today.latest_event("now"))

    return f"Flow {visit_bit} | {parked_bit} | {returned_bit} | {in_use_bit} | {max_bit} | latest {latest}"


def _tag_summary(today: "TrackerDay") -> str:
    reg = len(today.regular_tagids)
    ovr = len(today.oversize_tagids)
    retired = len(today.retired_tagids)
    usable = len(today.all_usable_tags())

    status_counts = Counter(b.status for b in today.biketags.values())
    status_bit = _format_status_counts(status_counts)

    conformity = today.tagids_conform
    if conformity is None:
        conformity = today.determine_tagids_conformity()
    conform_bit = "yes" if conformity else "no"

    return (
        f"Tags R:{reg} O:{ovr} Ret:{retired} usable:{usable}"
        f" | status {status_bit} | ids_conform {conform_bit}"
    )


def _notes_summary(today: "TrackerDay") -> str:
    notes = getattr(today.notes, "notes", [])
    total = len(notes)
    counters = Counter(note.status for note in notes)
    status_bits = []
    for status, label in (
        (NOTE_ACTIVE, "A"),
        (NOTE_HAND_RECOVERED, "R"),
        (NOTE_AUTO_DELETED, "D"),
    ):
        count = counters.get(status, 0)
        if count:
            status_bits.append(f"{label}:{count}")

    note_bit = f"notes {total}"
    if status_bits:
        note_bit += " (" + " ".join(status_bits) + ")"

    regs = getattr(today.registrations, "num_registrations", 0)

    return f"{note_bit} | registrations {regs}"


def _config_summary(today: "TrackerDay") -> list[str]:
    publish_freq = cfg.PUBLISH_FREQUENCY
    publish_bit = f"publish {publish_freq}m" if publish_freq else "publish off"
    estimator_bit = "estimator on" if cfg.ESTIMATOR_URL_BASE else "estimator off"
    monitor_freq = cfg.INTERNET_MONITORING_FREQUENCY
    monitor_bit = f"net_check {monitor_freq}m" if monitor_freq else "net_check off"
    sounds_bit = "sounds on" if cfg.SOUND_ENABLED else "sounds off"
    if cfg.SOUND_ENABLED and cfg.SOUND_PLAYER:
        sounds_bit = f"{sounds_bit} ({cfg.SOUND_PLAYER})"
    data_bit = f"data {cfg.DATA_FOLDER}"
    reports_bit = f"reports {cfg.REPORTS_FOLDER}"

    ui_bits = [
        f"width {cfg.SCREEN_WIDTH}",
        f"prompt '{cfg.CURSOR.strip() or cfg.CURSOR}'",
        "prompt_time on" if cfg.INCLUDE_TIME_IN_PROMPT else "prompt_time off",
        "tags_uppercase on" if cfg.TAGS_UPPERCASE else "tags_uppercase off",
        "echo on" if cfg.ECHO else "echo off",
    ]
    if cfg.ECHO and cfg.ECHO_FOLDER:
        ui_bits.append(f"echo_dir {cfg.ECHO_FOLDER}")

    first_line = (
        f"Config {data_bit} | {reports_bit} | {publish_bit}"
        f" | {estimator_bit} | {monitor_bit} | {sounds_bit}"
    )

    second_line = "UI " + " | ".join(ui_bits)

    return [first_line, second_line]


def _detailed_lines(today: "TrackerDay") -> list[str]:
    lines: list[str] = []

    in_use_tags = today.tags_in_use("now")
    in_use_detail = _describe_open_visits(today, in_use_tags)
    lines.append(f"In_use {in_use_detail if in_use_detail else 'none'}")

    recent = _recent_returns(today)
    lines.append(f"Recent_returns {recent if recent else 'none'}")

    lines.append(_tagset_detail("Regular", today.regular_tagids))
    lines.append(_tagset_detail("Oversize", today.oversize_tagids))
    if today.retired_tagids:
        lines.append(_tagset_detail("Retired", today.retired_tagids))

    return [line for line in lines if line]


def _describe_open_visits(today: "TrackerDay", tags: Iterable[str]) -> str:
    details = []
    for tag in sorted(tags):
        bike = today.biketags.get(tag)
        visit = bike.latest_visit() if bike else None
        start = _format_time(visit.time_in) if visit else "--:--"
        details.append(f"{tag}:{start}")
    return _join_limited(details, limit=12)


def _recent_returns(today: "TrackerDay") -> str:
    finished = [
        v
        for v in today.all_visits()
        if v.time_out
    ]
    finished.sort(key=lambda v: v.time_out, reverse=True)
    details = [
        f"{visit.tagid}:{_format_time(visit.time_in)}-{_format_time(visit.time_out)}"
        for visit in finished[:8]
    ]
    return _join_limited(details, limit=8)


def _tagset_detail(label: str, tags: Iterable[str]) -> str:
    tags_list = sorted(str(tag) for tag in tags)
    if not tags_list:
        return ""
    return f"{label} tags {len(tags_list)} [{_join_limited(tags_list, limit=12)}]"


def _format_type_counts(
    total: int,
    counts: Counter,
    label: str = "visits",
) -> str:
    parts = [f"{label} {total}"]
    type_bits = []
    for code in ("R", "O", "?"):
        count = counts.get(code, 0)
        if count:
            type_bits.append(f"{code}:{count}")
    if type_bits:
        parts.append("(" + " ".join(type_bits) + ")")
    return " ".join(parts)


def _format_status_counts(status_counts: Counter) -> str:
    mapping = {
        BikeTag.UNUSED: "U",
        BikeTag.IN_USE: "I",
        BikeTag.DONE: "D",
        BikeTag.RETIRED: "Ret",
    }
    bits = []
    for status in (BikeTag.UNUSED, BikeTag.IN_USE, BikeTag.DONE, BikeTag.RETIRED):
        bits.append(f"{mapping[status]}:{status_counts.get(status, 0)}")
    return " ".join(bits)


def _format_time(value: VTime | str | None) -> str:
    if not value:
        return "--:--"
    return str(value)


def _type_code(bike_type: str | None) -> str:
    return _TYPE_CODES.get(bike_type, "?")


def _join_limited(values: Iterable[str], limit: int) -> str:
    values = list(values)
    if not values:
        return ""
    if len(values) <= limit:
        return ", ".join(values)
    shown = values[:limit]
    remaining = len(values) - limit
    return ", ".join(shown) + f", +{remaining} more"

