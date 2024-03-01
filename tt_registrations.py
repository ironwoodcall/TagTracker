"""Class to manage count of Bike Registrations (Project 529) for TagTracker.


Copyright (C) 2024 Julias Hocking

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

import tt_util as ut
import tt_conf as cfg
import tt_printer as pr
from tt_sounds import NoiseMaker
import tt_globals


class Registrations:
    """Manage the count of bike registrations.

    This uses only a class variable so there is only ever one instance.
    """

    # Initialize it only if it does not yet exist.
    try:
        # pylint: disable-next=used-before-assignment
        num_registrations
    except NameError:
        num_registrations = 0

    def __init__(self) -> None:
        """Do nothing; class initialization is done through import."""

    @classmethod
    def set_num_registrations(cls, num_registrations: int):
        """Set the registration count to a new value."""
        cls.num_registrations = num_registrations

    @classmethod
    def process_registration(cls, user_input: str):
        """Set registration value based on a user command."""
        user_input = user_input.strip()  # Remove leading and trailing whitespace

        if not user_input:
            cls.display_current_count()
        elif user_input[0] in ("+", "-", "="):
            cls.parse_registration_count(user_input)
        else:
            cls.display_error_message()

    @classmethod
    def parse_registration_count(cls, user_input: str):
        """Parse the command string and set registration count from it."""
        operator = user_input[0]
        number_str = user_input[1:].strip()  # Remove whitespace surrounding the number
        try:
            num = int(number_str)
        except ValueError:
            cls.display_error_message()
            return

        if operator == "+":
            new_count = cls.num_registrations + num
            NoiseMaker.play(g.BIKE_IN)
        elif operator == "-":
            new_count = cls.num_registrations - num
        elif operator == "=":
            new_count = num
        else:
            cls.display_error_message("")

        if new_count < 0:
            cls.display_error_message("Number of registrations can not be < 0")
            return

        cls.num_registrations = new_count
        cls.display_current_count()

    @classmethod
    def display_current_count(cls, style: str = None, num_indents: int = None):
        """Display the current count of user registrations."""
        pr.iprint(
            f"There {ut.plural(cls.num_registrations,'is','are')} "
            f"{cls.num_registrations} bike "
            f"{ut.plural(cls.num_registrations, 'registration')}.",
            style=style,
            num_indents=num_indents,
        )

    @classmethod
    def display_error_message(cls, error: str = ""):
        """Show an error message."""
        if error:
            pr.iprint(error, style=cfg.ERROR_STYLE)
        else:
            pr.iprint("Error: Invalid registration command.", style=cfg.ERROR_STYLE)
        pr.iprint(cls.usage_str(), style=cfg.ERROR_STYLE)

    @classmethod
    def usage_str(cls):
        """Return a string showing the REG command usage."""
        return "Usage: REG +/-/= {number}. E.g. 'REG +1', 'REG = 5'"
