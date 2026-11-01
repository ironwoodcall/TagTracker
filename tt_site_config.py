"""Site configs for TagTracker: finding, choosing, loading and editing them.

Client config comes in three layers, each overriding the one before:
    client_base_config.py       code defaults (comes with the git clone)
    client_local_config.py      this organization / installation
    site_<handle>_config.py     one site, in SITE_CONFIGS_FOLDER

This module is shared by TagTracker's start-up (tagtracker.py) and the
site config manager (config-sites/config_sites.py). It never imports
client_base_config; where it needs config values they are passed in.

Copyright (C) 2023-2026 Todd Glover & Julias Hocking

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
import ast
import datetime
import importlib.util
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Any, Callable

PROGRAM_FOLDER = os.path.dirname(os.path.abspath(__file__))

HANDLE_MAX = 32
HANDLE_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")

FILE_PREFIX = "site_"
FILE_SUFFIX = "_config.py"
ARCHIVE_SUBFOLDER = "archived"

# Items the site config manager reads and writes in a site file.
# Everything else in the file is left exactly as it is.
MANAGED_ITEMS = (
    "SITE_NAME",
    "SITE_HANDLE",
    "EVENT_MODE",
    "DATA_OWNER_NAME",
    "DATA_OWNER",
    "REGULAR_TAGS",
    "OVERSIZE_TAGS",
)
# The one item the manager writes in the organization config.
ACTIVE_ITEM = "ACTIVE_SITE"

_ITEM_COMMENTS = {
    "EVENT_MODE": "True: event site (shorter command list, no network features)",
    "DATA_OWNER_NAME": "Read only by the site config manager; TagTracker shows DATA_OWNER",
    ACTIVE_ITEM: "Written by the site config manager (TagTracker set-up)",
}

_DATAFILE_RE = re.compile(r"^(?P<handle>.+)_(?P<date>\d{4}-\d{2}-\d{2})\.json$")
_TAG_SPLIT_RE = re.compile(r"[\s,]+")


class SiteConfigError(Exception):
    """A config problem TagTracker can't start with. Args are message lines."""


class SiteChoiceCancelled(Exception):
    """The person chose to exit rather than pick a site."""


class ConfigFileError(Exception):
    """A config file the site config manager can't safely read or change."""


# ---------------------------------------------------------------------------
# Handles, file names and folders
# ---------------------------------------------------------------------------


def fold_handle(handle: Any) -> str:
    """Handles aren't case-sensitive: fold to lowercase, trimmed."""
    return str(handle or "").strip().lower()


def handle_problem(handle: str) -> str:
    """Return why a (folded) handle isn't allowed, or "" if it's fine."""
    if not handle:
        return "SITE_HANDLE is not set."
    if len(handle) > HANDLE_MAX:
        return f"SITE_HANDLE '{handle}' is longer than {HANDLE_MAX} characters."
    if not HANDLE_RE.match(handle):
        return (
            f"SITE_HANDLE '{handle}' can use only letters, digits, hyphens, "
            "underscores and periods, and must start and end with a letter or digit."
        )
    return ""


def site_filename(handle: str) -> str:
    """File name for a site's config."""
    return f"{FILE_PREFIX}{handle}{FILE_SUFFIX}"


def handle_from_filename(name: str) -> str:
    """Handle from a site config file name, or "" if it isn't one."""
    if not (name.startswith(FILE_PREFIX) and name.endswith(FILE_SUFFIX)):
        return ""
    handle = name[len(FILE_PREFIX) : -len(FILE_SUFFIX)]
    return handle if not handle_problem(handle) else ""


def program_path(path: str) -> str:
    """Absolute path, with relative paths taken from the program folder."""
    path = os.path.expanduser(str(path or ""))
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(PROGRAM_FOLDER, path))


def list_sites(configs_folder: str, archived: bool = False) -> dict[str, str]:
    """Map handle -> file path for the site configs in a folder."""
    folder = os.path.join(configs_folder, ARCHIVE_SUBFOLDER) if archived else configs_folder
    sites = {}
    try:
        names = os.listdir(folder)
    except OSError:
        return {}
    for name in sorted(names):
        handle = handle_from_filename(name)
        path = os.path.join(folder, name)
        if handle and os.path.isfile(path):
            sites[handle] = path
    return sites


# ---------------------------------------------------------------------------
# Datafiles
# ---------------------------------------------------------------------------


def today_str() -> str:
    """Today's date as YYYY-MM-DD, from the device clock."""
    return datetime.date.today().isoformat()


def datafile_dates(handle: str, data_folder: str) -> list[str]:
    """Sorted dates of the datafiles for one site (<handle>_YYYY-MM-DD.json)."""
    pattern = re.compile(rf"^{re.escape(handle)}_(\d{{4}}-\d{{2}}-\d{{2}})\.json$")
    try:
        names = os.listdir(data_folder)
    except OSError:
        return []
    return sorted(m.group(1) for m in map(pattern.match, names) if m)


def handles_with_datafile_on(data_folder: str, date: str) -> set[str]:
    """Handles that have a datafile for the given date."""
    found = set()
    try:
        names = os.listdir(data_folder)
    except OSError:
        return found
    for name in names:
        m = _DATAFILE_RE.match(name)
        if m and m.group("date") == date and not handle_problem(m.group("handle")):
            found.add(m.group("handle"))
    return found


def checkins_in_datafile(path: str) -> int:
    """Number of bike visits in a datafile (read as plain JSON), 0 if unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            return len(json.load(f).get("bike_visits", []))
    except (OSError, ValueError, AttributeError):
        return 0


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def split_tags(value: Any) -> list[str]:
    """Tag IDs from a REGULAR_TAGS-style string (or list), lowercased."""
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(v) for v in value)
    return [t.lower() for t in _TAG_SPLIT_RE.split(str(value or "")) if t]


def format_tags(tags: list[str]) -> str:
    """Tag list as a triple-quoted string, one line per colour and letter."""
    lines: list[list[str]] = []
    for tag in tags:
        if lines and lines[-1][0][:2] == tag[:2]:
            lines[-1].append(tag)
        else:
            lines.append([tag])
    body = "\n".join(" ".join(line) for line in lines)
    return f'"""\n{body}\n"""' if body else '"""\n"""'


# ---------------------------------------------------------------------------
# Loading a site config into TagTracker (runs the file, like an import)
# ---------------------------------------------------------------------------


def load_site_values(path: str) -> dict[str, Any]:
    """Run a site config file and return its upper-case names."""
    try:
        spec = importlib.util.spec_from_file_location("tt_site_config_file", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:  # pylint: disable=broad-exception-caught
        raise SiteConfigError(
            f"Can't load site config {path}",
            f"{type(e).__name__}: {e}",
        ) from e
    return {k: v for k, v in vars(module).items() if k.isupper()}


def apply_site(cfg, values: dict[str, Any], handle: str) -> None:
    """Copy a site's values over the config module, then fix derived values."""
    for name, value in values.items():
        setattr(cfg, name, value)
    cfg.SITE_HANDLE = fold_handle(values.get("SITE_HANDLE", handle))
    cfg.DATA_BASENAME = f"{cfg.SITE_HANDLE}_"


def check_needed_values(cfg) -> list[str]:
    """Problems with the values TagTracker needs to run, if any."""
    problems = []
    handle = fold_handle(getattr(cfg, "SITE_HANDLE", ""))
    if handle_problem(handle):
        problems.append(handle_problem(handle))
    if not str(getattr(cfg, "SITE_NAME", "") or "").strip():
        problems.append("SITE_NAME is not set.")
    if not split_tags(getattr(cfg, "REGULAR_TAGS", "")) and not split_tags(
        getattr(cfg, "OVERSIZE_TAGS", "")
    ):
        problems.append("No tags: REGULAR_TAGS and OVERSIZE_TAGS are both empty.")
    return problems


# ---------------------------------------------------------------------------
# Choosing the site at start-up
# ---------------------------------------------------------------------------


@dataclass
class StartupChoice:
    """Which site TagTracker is using, and notices to show once the screen is up."""

    handle: str = ""
    path: str = ""
    notices: list[str] = field(default_factory=list)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """TagTracker's command line."""
    parser = argparse.ArgumentParser(
        prog="tagtracker.py",
        description="TagTracker bike valet data entry.",
    )
    parser.add_argument(
        "--site",
        metavar="HANDLE",
        help="use this site's config (site_HANDLE_config.py), overriding ACTIVE_SITE",
    )
    return parser.parse_args(argv)


def _site_label(handle: str, path: str, data_folder: str) -> str:
    """'Name (handle), last used <date>' for the site list."""
    cf = read_config_file(path, quiet=True)
    name = cf.values.get("SITE_NAME") if isinstance(cf.values.get("SITE_NAME"), str) else ""
    folder = cf.values.get("DATA_FOLDER") if isinstance(cf.values.get("DATA_FOLDER"), str) else data_folder
    dates = datafile_dates(handle, folder)
    used = f"last used {dates[-1]}" if dates else "never used"
    return f"{name} ({handle}), {used}" if name else f"{handle}, {used}"


def ask_which_site(
    choices: list[str],
    sites: dict[str, str],
    data_folder: str,
    question: str,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[..., None] = print,
) -> str:
    """Ask which of the listed sites to use. Returns its handle.

    Accepts a number, a handle or a site name (any case). Raises
    SiteChoiceCancelled if the person chooses to exit.
    """
    names = {}
    print_fn()
    print_fn(question)
    print_fn()
    for i, handle in enumerate(choices, 1):
        label = _site_label(handle, sites[handle], data_folder)
        names[label.split(" (")[0].strip().lower()] = handle
        print_fn(f"  {i:>2}. {label}")
    print_fn("   X. None of these: exit and get help")
    print_fn()
    while True:
        try:
            answer = input_fn(f"Type a number from 1 to {len(choices)}, or X: ").strip()
        except (EOFError, KeyboardInterrupt) as e:
            print_fn()
            raise SiteChoiceCancelled() from e
        folded = fold_handle(answer)
        if folded in ("x", "exit", "quit", "q"):
            raise SiteChoiceCancelled()
        if folded.isdigit() and 1 <= int(folded) <= len(choices):
            return choices[int(folded) - 1]
        if folded in choices:
            return folded
        if folded in names:
            return names[folded]
        if answer:
            print_fn(f"'{answer}' isn't one of the choices.")
        print_fn(f"Type a number from 1 to {len(choices)} (or a site's handle), or X to exit.")


def choose_site(
    cfg,
    argv: list[str],
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[..., None] = print,
) -> StartupChoice:
    """Decide which site config to use. Doesn't load it.

    1. --site HANDLE
    2. ACTIVE_SITE, from whichever config layer sets it
    3. today's datafile, if just one site has one (several: ask which)
    4. ask, from the site configs
    5. no site configs at all: carry on without one, with a warning
    """
    args = parse_args(argv)
    folder = program_path(getattr(cfg, "SITE_CONFIGS_FOLDER", ""))
    sites = list_sites(folder)

    wanted = fold_handle(args.site) or fold_handle(getattr(cfg, "ACTIVE_SITE", ""))
    if wanted:
        source = "--site" if args.site else "ACTIVE_SITE"
        if wanted in sites:
            return StartupChoice(wanted, sites[wanted])
        if wanted in list_sites(folder, archived=True):
            raise SiteConfigError(
                f"Site '{wanted}' (from {source}) is archived.",
                "Restore it in TagTracker set-up, or choose another site.",
            )
        raise SiteConfigError(
            f"No site config for '{wanted}' (from {source}).",
            f"Expected {os.path.join(folder, site_filename(wanted))}",
        )

    if not sites:
        return StartupChoice(
            notices=[
                f"No site configuration found (looked in {folder}).",
                "Carrying on without one, using client_local_config.py.",
            ]
        )

    data_folder = getattr(cfg, "DATA_FOLDER", "")
    todays = sorted(h for h in handles_with_datafile_on(data_folder, today_str()) if h in sites)
    if len(todays) == 1:
        return StartupChoice(todays[0], sites[todays[0]])
    if todays:
        question = "More than one site has a datafile for today. Which site is this?"
        choices = todays
    else:
        question = "Which site is this?"
        choices = sorted(sites)
    handle = ask_which_site(choices, sites, data_folder, question, input_fn, print_fn)
    return StartupChoice(handle, sites[handle])


def start_up(
    cfg,
    argv: list[str],
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[..., None] = print,
) -> StartupChoice:
    """Choose the site, load its config over cfg, and check the needed values.

    Raises SiteConfigError (can't start) or SiteChoiceCancelled.
    """
    choice = choose_site(cfg, argv, input_fn, print_fn)
    if choice.path:
        values = load_site_values(choice.path)
        in_file = fold_handle(values.get("SITE_HANDLE", choice.handle))
        if in_file != choice.handle:
            raise SiteConfigError(
                f"{choice.path} sets SITE_HANDLE = '{in_file}'.",
                f"It must match the file name ('{choice.handle}').",
            )
        apply_site(cfg, values, choice.handle)
    problems = check_needed_values(cfg)
    if problems:
        where = choice.path or "client_local_config.py"
        raise SiteConfigError(*problems, f"(Config in use: {where})")
    return choice


# ---------------------------------------------------------------------------
# Reading and changing config files without running them (site config manager)
# ---------------------------------------------------------------------------

_UNREADABLE = object()


@dataclass
class ConfigFile:
    """What's in a config file, read with ast (never run)."""

    path: str
    text: str = ""
    values: dict[str, Any] = field(default_factory=dict)  # literal top-level assignments
    spans: dict[str, list[tuple[int, int]]] = field(default_factory=dict)  # 1-based lines
    unsafe: set[str] = field(default_factory=set)  # assigned in a way we can't replace
    error: str = ""  # whole file unreadable
    mtime: str = ""  # changes when the file does


def _assigned_names(node) -> list[str]:
    """Names assigned by an assignment node."""
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    else:
        return []
    names = []
    for t in targets:
        for n in ast.walk(t):
            if isinstance(n, ast.Name):
                names.append(n.id)
    return names


def parse_config_text(text: str, path: str = "") -> ConfigFile:
    """Read a config file's top-level assignments without running it."""
    cf = ConfigFile(path=path, text=text)
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        cf.error = f"Python syntax error, line {e.lineno}: {e.msg}"
        return cf
    top_level = set()
    line_users: dict[int, int] = {}
    for node in tree.body:
        for line in range(node.lineno, node.end_lineno + 1):
            line_users[line] = line_users.get(line, 0) + 1
    for node in tree.body:
        names = _assigned_names(node)
        if not names:
            continue
        top_level.add(id(node))
        simple = (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ) or (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value)
        shares_line = any(
            line_users[line] > 1 for line in range(node.lineno, node.end_lineno + 1)
        )
        for name in names:
            if not simple or shares_line:
                cf.unsafe.add(name)
                continue
            cf.spans.setdefault(name, []).append((node.lineno, node.end_lineno))
            try:
                cf.values[name] = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                cf.values[name] = _UNREADABLE
    # Assignments inside if/try/def etc. can't be replaced safely.
    for node in ast.walk(tree):
        if id(node) not in top_level:
            cf.unsafe.update(_assigned_names(node))
    for name, spans in cf.spans.items():
        if len(spans) > 1:
            cf.unsafe.add(name)
    return cf


def read_config_file(path: str, quiet: bool = False) -> ConfigFile:
    """Read a config file with ast. A missing file reads as empty."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        mtime = str(os.stat(path).st_mtime_ns)
    except FileNotFoundError:
        return ConfigFile(path=path)
    except OSError as e:
        if quiet:
            return ConfigFile(path=path, error=str(e))
        raise ConfigFileError(f"Can't read {path}: {e}") from e
    cf = parse_config_text(text, path)
    cf.mtime = mtime
    return cf


def readable_value(cf: ConfigFile, name: str, default: Any = None) -> Any:
    """A literal value from the file, or default if absent or not a literal."""
    value = cf.values.get(name, default)
    return default if value is _UNREADABLE else value


def edit_problems(cf: ConfigFile, names=MANAGED_ITEMS) -> list[str]:
    """Why the manager can't edit these items in this file, if it can't."""
    if cf.error:
        return [cf.error]
    problems = []
    for name in names:
        if name in cf.unsafe:
            problems.append(f"{name} is set more than once, or inside other code.")
        elif cf.values.get(name, None) is _UNREADABLE:
            problems.append(f"{name} is built by code, not written out as a value.")
    return problems


def format_assignment(name: str, value: Any) -> str:
    """One assignment line (or block) as the manager writes it."""
    if name in ("REGULAR_TAGS", "OVERSIZE_TAGS"):
        literal = format_tags(split_tags(value))
    elif isinstance(value, bool):
        literal = "True" if value else "False"
    elif isinstance(value, str):
        literal = json.dumps(value, ensure_ascii=False)  # also a valid Python literal
    else:
        literal = repr(value)
    comment = _ITEM_COMMENTS.get(name)
    return f"{name} = {literal}" + (f"  # {comment}" if comment else "") + "\n"


def update_text(cf: ConfigFile, new_values: dict[str, Any]) -> str:
    """The file's text with these items replaced (or added); all else kept."""
    problems = edit_problems(cf, list(new_values))
    if problems:
        raise ConfigFileError(*problems)
    lines = cf.text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    edits = sorted(
        ((cf.spans[name][0], name) for name in new_values if name in cf.spans),
        reverse=True,
    )
    for (start, end), name in edits:
        lines[start - 1 : end] = [format_assignment(name, new_values[name])]
    missing = [name for name in new_values if name not in cf.spans]
    if missing:
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.extend(format_assignment(name, new_values[name]) for name in missing)
    text = "".join(lines)
    # Check the result reads back as intended.
    check = parse_config_text(text)
    for name, value in new_values.items():
        got = readable_value(check, name)
        if name in ("REGULAR_TAGS", "OVERSIZE_TAGS"):
            ok = split_tags(got) == split_tags(value)
        else:
            ok = got == value
        if check.error or not ok:
            raise ConfigFileError(f"Internal error: {name} didn't read back as written.")
    return text


def write_atomically(path: str, text: str, keep_backup: bool = True) -> None:
    """Write a file via a temporary file and rename, keeping <path>.bak."""
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".py", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if keep_backup and os.path.exists(path):
            with open(path, "rb") as src, open(path + ".bak", "wb") as dst:
                dst.write(src.read())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
