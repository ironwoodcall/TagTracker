"""TagTracker by Julias Hocking.

Shared per-tag outcome reporting for multi-tag commands (RETIRE/UNRETIRE,
HOLD/UNHOLD, and similar): each of these commands evaluates a list of tags
independently, one outcome per tag, then prints them all as a
tag-column-aligned block. This module holds that common shape so it's
defined once instead of separately in each command's module.

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

from dataclasses import dataclass
from typing import Sequence

from common.tt_tag import TagID
import tt_printer as pr


@dataclass
class TagOutcome:
    """One tag's result from a multi-tag command.

    Commands with extra per-outcome state (e.g. RETIRE's retire_today/
    add_to_config flags) should subclass this and add fields -- dataclass
    inheritance requires those extra fields to all have defaults, same as
    here.
    """

    tag: TagID
    message: str
    style: str


def print_outcomes(
    outcomes: Sequence[TagOutcome], banner: str = "", banner_style: str = ""
) -> None:
    """Print one aligned line per outcome: tag column, then its message.

    The tag column is left-padded to fit the widest tag in this batch
    (minimum 4, so short batches still line up reasonably). banner, if
    given, is printed first in banner_style -- e.g. RETIRE's "Use this
    command with care!" warning when there's something to confirm.
    """
    width = max((len(str(o.tag)) for o in outcomes), default=4)
    pr.iprint()
    if banner:
        pr.iprint(banner, style=banner_style)
    for outcome in outcomes:
        pr.iprint(
            f"{str(outcome.tag):<{width}}  {outcome.message}",
            style=outcome.style,
            num_indents=2,
        )
