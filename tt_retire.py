"""RETIRE/UNRETIRE command helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import client_base_config as cfg
import common.tt_constants as k
from common.tt_biketag import BikeTag
from common.tt_tag import TagID
from common.tt_trackerday import TrackerDay
import common.tt_util as ut
import tt_printer as pr


_CONFIG_FILE = Path(__file__).resolve().parent / "client_local_config.py"
_CONFIG_PATTERN = re.compile(
    r'(RETIRED_TAGS\s*=\s*""")(?P<body>.*?)(""")',
    re.DOTALL,
)


@dataclass
class TagOutcome:
    tag: TagID
    message: str
    style: str
    retire_today: bool = False
    unretire_today: bool = False
    add_to_config: bool = False
    remove_from_config: bool = False

    @property
    def needs_change(self) -> bool:
        return (
            self.retire_today
            or self.unretire_today
            or self.add_to_config
            or self.remove_from_config
        )


class _Operation:
    RETIRE = "retire"
    UNRETIRE = "unretire"


def retire(today: TrackerDay, tags: Sequence[TagID]) -> bool:
    """Handle RETIRE command; returns True if TrackerDay changed."""
    return _process(today=today, tags=tags, mode=_Operation.RETIRE)


def unretire(today: TrackerDay, tags: Sequence[TagID]) -> bool:
    """Handle UNRETIRE command; returns True if TrackerDay changed."""
    return _process(today=today, tags=tags, mode=_Operation.UNRETIRE)


def _process(today: TrackerDay, tags: Sequence[TagID], mode: str) -> bool:
    """Process the retire or unretire command.
    On entry:
        tags is a list of valid tagids to process
    """
    if not tags:
        pr.iprint("No tags supplied.", style=k.WARNING_STYLE)
        return False
    try:
        config_text, match, config_tags = _load_config_state()
    except RuntimeError as exc:
        pr.iprint(str(exc), style=k.ERROR_STYLE)
        return False

    outcomes = [_evaluate_tag(TagID(tag), today, config_tags, mode) for tag in tags]
    _display_outcomes(outcomes)

    actionable = [outcome for outcome in outcomes if outcome.needs_change]
    if not actionable:
        pr.iprint("Nothing to change.", style=k.SUBTITLE_STYLE)
        return False

    if not _confirm(len(actionable)):
        pr.iprint("No changes made.", style=k.WARNING_STYLE)
        return False

    try:
        today_changed, config_changed, config_delta = _apply_changes(
            today, config_tags, config_text, match, actionable
        )
    except RuntimeError as exc:
        pr.iprint(str(exc), style=k.ERROR_STYLE)
        return False

    if config_changed or today_changed:
        _summarize_changes(today_changed, config_delta)
    else:
        pr.iprint("Nothing needed changing.", style=k.SUBTITLE_STYLE)

    return today_changed


def _load_config_state() -> tuple[str, re.Match[str], set[TagID]]:
    try:
        text = _CONFIG_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Unable to read {_CONFIG_FILE.name}: {exc}") from exc

    match = _CONFIG_PATTERN.search(text)
    if not match:
        raise RuntimeError(
            "Could not locate RETIRED_TAGS block in client_local_config.py."
        )

    body = match.group("body")
    tags, errors = TagID.parse_tagids_str(body, "RETIRED_TAGS configuration")
    if errors:
        for err in errors:
            pr.iprint(err, style=k.ERROR_STYLE)
        raise RuntimeError("Unable to parse RETIRED_TAGS configuration.")

    return text, match, tags


def _display_outcomes(outcomes: Sequence[TagOutcome]) -> None:
    width = max((len(str(o.tag)) for o in outcomes), default=4)
    pr.iprint()
    for outcome in outcomes:
        pr.iprint(
            f"{str(outcome.tag):<{width}}  {outcome.message}",
            style=outcome.style,
            num_indents=2,
        )


def _confirm(count: int) -> bool:
    pr.iprint(
        f"Enter 'y' to confirm changing {count} tag{'s' if count != 1 else ''}: ",
        end="",
        style=k.PROMPT_STYLE,
    )
    reply = pr.tt_inp("").strip().lower()
    return reply == "y"


def _apply_changes(
    today: TrackerDay,
    config_tags: set[TagID],
    config_text: str,
    match: re.Match[str],
    actionable: Sequence[TagOutcome],
) -> tuple[bool, bool, tuple[int, int]]:
    add_tags: set[TagID] = set()
    remove_tags: set[TagID] = set()

    for outcome in actionable:
        if outcome.add_to_config:
            add_tags.add(TagID(outcome.tag))
        if outcome.remove_from_config:
            remove_tags.add(TagID(outcome.tag))

    new_config = set(config_tags)
    if add_tags:
        new_config.update(add_tags)
    if remove_tags:
        new_config.difference_update(remove_tags)

    config_changed = new_config != config_tags
    if config_changed:
        _write_config_state(config_text, match, new_config)

    today_changed = False
    for outcome in actionable:
        if outcome.retire_today and today.retire_tag(outcome.tag):
            today_changed = True
        if outcome.unretire_today and today.unretire_tag(outcome.tag):
            today_changed = True

    delta = (len(new_config - config_tags), len(config_tags - new_config))
    return today_changed, config_changed, delta


def _write_config_state(
    original_text: str, match: re.Match[str], tags: Iterable[TagID]
) -> None:
    body = _format_body(tags)
    new_text = f"{original_text[:match.start('body')]}{body}{original_text[match.end('body'):]}"
    temp_path = _CONFIG_FILE.with_suffix(".tmp")
    try:
        temp_path.write_text(new_text, encoding="utf-8")
        temp_path.replace(_CONFIG_FILE)
    except OSError as exc:
        raise RuntimeError(f"Unable to update {_CONFIG_FILE.name}: {exc}") from exc
    cfg.RETIRED_TAGS = body


def _format_body(tags: Iterable[TagID]) -> str:
    # tokens = sorted({TagID(tag).canon.upper() for tag in tags})
    tokens = [tag.canon.upper() for tag in sorted({TagID(tag) for tag in tags})]

    if not tokens:
        return "\n\n"
    lines = []
    for idx in range(0, len(tokens), 12):
        lines.append(" ".join(tokens[idx : idx + 12]))
    return "\n" + "\n".join(lines) + "\n"


def _evaluate_tag(
    tag: TagID, today: TrackerDay, config_tags: set[TagID], mode: str
) -> TagOutcome:
    biketag = today.biketags.get(tag)
    if not biketag:
        return TagOutcome(
            tag=tag,
            message="Is not available for use (ignoring)",
            style=k.ANSWER_STYLE,
        )

    in_config = tag in config_tags

    if mode == _Operation.RETIRE:
        return _evaluate_retire(tag, biketag, in_config)
    return _evaluate_unretire(tag, biketag, in_config)


def _evaluate_retire(tag: TagID, biketag: BikeTag, in_config: bool) -> TagOutcome:
    if biketag.status == BikeTag.RETIRED:
        if in_config:
            return TagOutcome(tag, "is already retired", k.ANSWER_STYLE)
        return TagOutcome(
            tag,
            "Will be retired in the config file",
            k.ANSWER_STYLE,
            add_to_config=True,
        )

    used_today = bool(biketag.visits)
    if in_config:
        if used_today:
            return TagOutcome(
                tag,
                "Is already marked as retired, starting tomorrow",
                k.ANSWER_STYLE,
            )
        return TagOutcome(
            tag,
            "Will be retired [and is already retired in config]",
            k.ANSWER_STYLE,
            retire_today=True,
        )

    if used_today:
        return TagOutcome(
            tag,
            "Will be marked for retirement starting tomorrow (already used today)",
            k.ANSWER_STYLE,
            add_to_config=True,
        )
    return TagOutcome(
        tag,
        "Will be retired",
        k.ANSWER_STYLE,
        retire_today=True,
        add_to_config=True,
    )


def _evaluate_unretire(tag: TagID, biketag: BikeTag, in_config: bool) -> TagOutcome:
    if biketag.status == BikeTag.RETIRED:
        if in_config:
            return TagOutcome(
                tag,
                "Will be unretired",
                k.ANSWER_STYLE,
                unretire_today=True,
                remove_from_config=True,
            )
        return TagOutcome(
            tag,
            "Will be unretired [and is already unretired in config]",
            k.ANSWER_STYLE,
            unretire_today=True,
        )

    if in_config:
        return TagOutcome(
            tag,
            "Will be unretired in config",
            k.ANSWER_STYLE,
            remove_from_config=True,
        )
    return TagOutcome(tag, "Is already unretired", k.ANSWER_STYLE)


def _summarize_changes(today_changed: bool, config_delta: tuple[int, int]) -> None:
    added, removed = config_delta
    parts = []
    if today_changed:
        parts.append("updated today's tracker data")
    if added:
        parts.append(f"added {added} {ut.plural(added,'tag')} to config file")
    if removed:
        parts.append(f"removed {removed} {ut.plural(removed,'tag')} from config file")

    summary = (
        "Changes applied."
        if not parts
        else "Changes applied: " + ", and ".join(parts) + "."
    )
    pr.iprint(summary, style=k.SUBTITLE_STYLE)
