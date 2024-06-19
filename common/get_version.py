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
from datetime import datetime


def _get_git_root():
    try:
        git_root = (
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.STDOUT
            )
            .strip()
            .decode("utf-8")
        )
        return git_root
    except subprocess.CalledProcessError:
        return None


def _get_git_info():
    git_root = _get_git_root()
    if git_root is None:
        return None

    try:
        # Get the current branch name
        branch = (
            subprocess.check_output(
                [
                    "git",
                    "--git-dir",
                    os.path.join(git_root, ".git"),
                    "--work-tree",
                    git_root,
                    "rev-parse",
                    "--abbrev-ref",
                    "HEAD",
                ]
            )
            .strip()
            .decode("utf-8")
        )

        # Get the latest commit hash (last 7 characters)
        commit_hash = (
            subprocess.check_output(
                [
                    "git",
                    "--git-dir",
                    os.path.join(git_root, ".git"),
                    "--work-tree",
                    git_root,
                    "rev-parse",
                    "HEAD",
                ]
            )
            .strip()
            .decode("utf-8")[-7:]
        )

        # Get the latest commit date and format it manually
        commit_date_raw = (
            subprocess.check_output(
                [
                    "git",
                    "--git-dir",
                    os.path.join(git_root, ".git"),
                    "--work-tree",
                    git_root,
                    "log",
                    "-1",
                    "--format=%cd",
                    "--date=iso",
                ]
            )
            .strip()
            .decode("utf-8")
        )
        commit_date = datetime.strptime(
            commit_date_raw[:-6], "%Y-%m-%d %H:%M:%S"
        ).strftime("%Y-%m-%d %H:%M")

        s = f"{branch} ({commit_hash}: {commit_date})"
        return s
    except subprocess.CalledProcessError:
        return None


def _get_latest_file_date():
    latest_date = None
    for root, dirs, files in os.walk("."):
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


def get_version_info():
    git_info = _get_git_info()
    if git_info:
        return git_info
    else:
        latest_file_date = _get_latest_file_date()
        return f"has latest file date {latest_file_date}"


if __name__ == "__main__":
    version_info = get_version_info()
    print(version_info)
