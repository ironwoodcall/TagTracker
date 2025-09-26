"""TagTracker by Julias Hocking.

Return a string describing the version/date for the codebase.

Copyright (C) 2023-2024 Todd Glover & Julias Hocking

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

import subprocess
import os
import sys
import tempfile
from datetime import datetime
from typing import Optional


CACHE_FILENAME = ".tagtracker_version_info"
_REPORTED_ERRORS: set[str] = set()


def _get_git_root(start_dir: Optional[str] = None):
    """Return the git repo root, using start_dir as the search base."""

    # Default to the directory this module resides in so callers do not have to
    # know where the repository lives relative to their current working dir.
    if start_dir is None:
        start_dir = os.path.dirname(os.path.abspath(__file__))
    else:
        start_dir = os.path.abspath(start_dir)

    try:
        git_root = (
            subprocess.check_output(
                ["git", "-c", "safe.directory=*", "rev-parse", "--show-toplevel"],
                stderr=subprocess.STDOUT,
                cwd=start_dir,
            )
            .strip()
            .decode("utf-8")
        )
        return git_root
    except subprocess.CalledProcessError as err:
        msg = err.output.decode("utf-8", errors="ignore").strip()
        if msg and msg not in _REPORTED_ERRORS:
            print("get_version: git root discovery failed –", msg, file=sys.stderr)
            _REPORTED_ERRORS.add(msg)
        pass

    # Fallback: walk up the directory tree looking for a .git directory/file.
    current_dir = start_dir
    while True:
        git_dir = os.path.join(current_dir, ".git")
        if os.path.isdir(git_dir) or os.path.isfile(git_dir):
            return current_dir
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir

    return None


def _get_git_info(git_root: Optional[str]):
    if git_root is None:
        return None
    git_root = os.path.realpath(git_root)

    try:
        # Get the current branch name
        git_safe_arg = f"safe.directory={git_root}"

        branch = (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    git_safe_arg,
                    "rev-parse",
                    "--abbrev-ref",
                    "HEAD",
                ],
                cwd=git_root,
            )
            .strip()
            .decode("utf-8")
        )

        # Get the latest commit hash (last 7 characters)
        commit_hash = (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    git_safe_arg,
                    "rev-parse",
                    "HEAD",
                ],
                cwd=git_root,
            )
            .strip()
            .decode("utf-8")[-7:]
        )

        # Get the latest commit date and format it manually
        commit_date_raw = (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    git_safe_arg,
                    "log",
                    "-1",
                    "--format=%cd",
                    "--date=iso",
                ],
                cwd=git_root,
            )
            .strip()
            .decode("utf-8")
        )
        commit_date = datetime.strptime(
            commit_date_raw[:-6], "%Y-%m-%d %H:%M:%S"
        ).strftime("%Y-%m-%d %H:%M")

        s = f"{branch} ({commit_hash}: {commit_date})"
        _write_version_cache(git_root, s)
        return s
    except subprocess.CalledProcessError as err:
        msg = err.output.decode("utf-8", errors="ignore").strip()
        if msg and msg not in _REPORTED_ERRORS:
            print("get_version: git info lookup failed –", msg, file=sys.stderr)
            _REPORTED_ERRORS.add(msg)
        return None


def _get_latest_file_date(start_dir: Optional[str] = None):
    latest_date = None
    if start_dir is None:
        start_dir = os.getcwd()
    else:
        start_dir = os.path.abspath(start_dir)

    for root, dirs, files in os.walk(start_dir):
        # Exclude directories that start with 'tmp', '.', or '_'
        dirs[:] = [
            d
            for d in dirs
            if not (d.startswith("tmp") or d.startswith(".") or d.startswith("_"))
        ]

        for file in files:
            # Exclude files that start with 'tmp', '.', '_', or contain '_local_'
            if file.endswith(".py") and not (
                file.startswith("tmp")
                or file.startswith(".")
                or file.startswith("_")
                or "_local_" in file
            ):
                file_path = os.path.join(root, file)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if latest_date is None or file_mtime > latest_date:
                    latest_date = file_mtime
    return latest_date.strftime("%Y-%m-%d %H:%M") if latest_date else "Unknown"


def _cache_path(git_root: str) -> str:
    return os.path.join(git_root, CACHE_FILENAME)


def _read_cached_version(git_root: str) -> Optional[str]:
    cache_path = _cache_path(git_root)
    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = handle.readline().strip()
            return cached or None
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _write_version_cache(git_root: str, version_info: str) -> None:
    cache_path = _cache_path(git_root)
    try:
        existing = None
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as handle:
                existing = handle.readline().strip()
            if existing == version_info:
                return

        fd, tmp_path = tempfile.mkstemp(prefix=".tt_version_", dir=git_root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(version_info)
                handle.write("\n")
            os.replace(tmp_path, cache_path)
            os.chmod(cache_path, 0o664)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except OSError:
        pass


def get_version_info(base_dir: Optional[str] = None):
    git_root = _get_git_root(base_dir)
    if git_root:
        git_root = os.path.realpath(git_root)
    git_info = _get_git_info(git_root)
    if git_info:
        return git_info

    if git_root:
        cached = _read_cached_version(git_root)
        if cached:
            return cached

    latest_file_date = _get_latest_file_date(base_dir or git_root)
    return f"has latest file date {latest_file_date}"


if __name__ == "__main__":
    version_info = get_version_info()
    print(version_info)
