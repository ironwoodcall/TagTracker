#!/usr/bin/env python3
"""Parse a user command into tokens.

Reads info from day-end-form (csv) or from other
sources (e.g. weather info from NRCan? tbd)

Copyright (C) 2023 Julias Hocking

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

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
from tt_tag import TagID
import tt_util as ut
import tt_conf as cfg


class CmdBits:
    """Parse and store user command input into its bits."""

    def __init__(
        self, user_input: str, retired_tags: list[str], all_tags: list[str]
    ) -> None:
        """Convert user input into parsed structure."""
        self.command = ""
        self.args = []
        self.tail = ""
        self._parse_command(user_input, retired_tags, all_tags)

    def _parse_command(
        self, user_input: str, retired_tags: list[str], all_tags: list[str]
    ) -> None:
        """Parse user's input into tag/command and args.

        Sets instance variables:
            .command is the command (if any) or a tag.  May also be:
                "" if there is no input
                cfg.CMD_TAG_RETIRED if a tag but is retired
                cfg.CMD_TAG_UNUSABLE if a tag but otherwise not usable
                cfg.CMD_UNKNOWN if not a tag & not a command
            .tail is anything following the command or tag, untainted but
                otherwise in its input format
            .args is the command tail, broken into a list of tokens
                (if .command is a tag, this is always an empty list)
        """
        # Throw away typical garbage characters
        clean_input = ut.untaint(user_input.strip("\\][ \t")).strip()

        # Special case - if user input starts with '/' or '?' add a space.
        if clean_input and clean_input[0] in ["/", "?"]:
            clean_input = f"{clean_input[0]} {clean_input[1:]}"

        # Break into first portion & remainder
        parts = clean_input.split(maxsplit=1)
        if len(parts) < 1:
            return
        if len(parts) > 1:
            self.tail = parts[1]
            self.args = self.tail.lower().split()

        # Test to see if a tag.
        maybetag = TagID(parts[0])
        if maybetag:
            # This appears to be a tag.  Usable?
            if maybetag in retired_tags:
                self.command = cfg.CMD_TAG_RETIRED
            elif maybetag not in all_tags:
                self.command = cfg.CMD_TAG_UNUSABLE
            else:
                # This appears to be a usable tag.
                self.command = maybetag
        else:
            # See if it is a recognized command.
            # cfg.command_aliases is dict of lists of aliases keyed by
            # canonical command name (e.g. {"edit":["ed","e","edi"], etc})
            command = None
            for c, aliases in cfg.COMMANDS.items():
                if parts[0] in aliases:
                    command = c
                    break
        # Is this an unrecognized command?
        if command:
            self.command = command
        else:
            self.command = cfg.CMD_UNKNOWN
