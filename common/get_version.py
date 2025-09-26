"""TagTracker by Julias Hocking.

Return a string describing the version/date for the codebase.

For this to work in the CGI environment (we reporting), the tagtracker
repo folder must be set as a safe.directory at the system level.
Edit /etc/gitconfig or sudo git config --system --add safe.directory /...<path-to-repo>

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
from datetime import datetime
from typing import Optional


_REPORTED_ERRORS: set[str] = set()


def _git_env(*paths: str):
    """Return an environment dict that marks the provided paths as safe."""

    paths = [os.path.realpath(p) for p in paths if p]
    if not paths:
        return None

    env = os.environ.copy()
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        count = 0

    for path in paths:
        key = f"GIT_CONFIG_KEY_{count}"
        value = f"GIT_CONFIG_VALUE_{count}"
        env[key] = "safe.directory"
        env[value] = path
        count += 1

    env["GIT_CONFIG_COUNT"] = str(count)
    return env


def _ancestors(path: str):
    """Yield path and its parent directories up to filesystem root."""

    current = os.path.realpath(path)
    seen = set()
    while current and current not in seen:
        yield current
        seen.add(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent


def _get_git_root(start_dir: Optional[str] = None):
    """Return the git repo root, using start_dir as the search base."""

    # Default to the directory this module resides in so callers do not have to
    # know where the repository lives relative to their current working dir.
    if start_dir is None:
        start_dir = os.path.dirname(os.path.abspath(__file__))
    else:
        start_dir = os.path.abspath(start_dir)

    # First, walk up the tree looking for a .git directory/file. This avoids
    # triggering git's "dubious ownership" safety check when run by a different
    # OS user (common for CGI environments).
    current_dir = start_dir
    while True:
        git_dir = os.path.join(current_dir, ".git")
        if os.path.isdir(git_dir) or os.path.isfile(git_dir):
            return current_dir
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir

    # Fallback to asking git directly if the marker directory could not be
    # located. This uses a safe-directory override for every ancestor of the
    # starting directory so git trusts the tree even under another OS user.
    try:
        git_root = (
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                stderr=subprocess.STDOUT,
                cwd=start_dir,
                env=_git_env(*_ancestors(start_dir)),
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

    return None


def _get_git_info(git_root: Optional[str]):
    if git_root is None:
        return None
    git_root = os.path.realpath(git_root)

    try:
        # Get the current branch name
        git_safe_arg = f"safe.directory={git_root}"

        env = _git_env(git_root)

        branch = (
            subprocess.check_output(
                ["git", "-c", git_safe_arg, "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.STDOUT,
                cwd=git_root,
                env=env,
            )
            .strip()
            .decode("utf-8")
        )

        # Get the latest commit hash (last 7 characters)
        commit_hash = (
            subprocess.check_output(
                ["git", "-c", git_safe_arg, "rev-parse", "HEAD"],
                stderr=subprocess.STDOUT,
                cwd=git_root,
                env=env,
            )
            .strip()
            .decode("utf-8")[-7:]
        )

        # Get the latest commit date and format it manually
        commit_date_raw = (
            subprocess.check_output(
                ["git", "-c", git_safe_arg, "log", "-1", "--format=%cd", "--date=iso"],
                stderr=subprocess.STDOUT,
                cwd=git_root,
                env=env,
            )
            .strip()
            .decode("utf-8")
        )
        commit_date = datetime.strptime(
            commit_date_raw[:-6], "%Y-%m-%d %H:%M:%S"
        ).strftime("%Y-%m-%d %H:%M")

        s = f"{branch} ({commit_hash}: {commit_date})"
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


def get_version_info(base_dir: Optional[str] = None):
    git_root = _get_git_root(base_dir)
    if git_root:
        git_root = os.path.realpath(git_root)
    git_info = _get_git_info(git_root)
    if git_info:
        return git_info

    latest_file_date = _get_latest_file_date(base_dir or git_root)
    return f"has latest file date {latest_file_date}"


if __name__ == "__main__":
    version_info = get_version_info()
    print(version_info)
