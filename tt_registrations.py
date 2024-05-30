"""Class to manage count of Bike Registrations (e.g. Project 529) for TagTracker.


Copyright (C) 2023-2024 Julias Hocking and Todd Glover

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

import tt_constants as k
import tt_util as ut
import tt_printer as pr
from tt_sounds import NoiseMaker

# import client_base_config as cfg


class Registrations:
    """Manage the count of bike registrations.

    This uses only a class variable so there is only ever one instance.
    """

    def __init__(self, num_registrations: int = 0) -> None:
        self.num_registrations = num_registrations

    def __rep__(self):
        return f"{self.num_registrations}"

    def process_registration(self, user_input: str):
        """Set registration value based on a user command.

        Returns True if the count has changed, False otherwise.
        """
        current_reg = self.num_registrations
        user_input = user_input.strip()  # Remove leading and trailing whitespace

        if not user_input:
            self.display_current_count()
        elif user_input[0] in ("+", "-", "="):
            self.process_registration_update(user_input)
        else:
            self.display_error_message()
        # Indicate if the registration count has changed
        return current_reg != self.num_registrations

    def process_registration_update(self, user_input: str):
        """Parse the command string and set registration count from it."""
        operator = user_input[0]
        number_str = user_input[1:].strip()  # Remove whitespace surrounding the number
        try:
            num = int(number_str)
        except ValueError:
            self.display_error_message()
            return

        if operator == "+":
            new_count = self.num_registrations + num
            NoiseMaker.play(k.CHEER)
        elif operator == "-":
            new_count = self.num_registrations - num
        elif operator == "=":
            new_count = num
        else:
            self.display_error_message("")

        if new_count < 0:
            self.display_error_message("Number of registrations can not be < 0")
            return

        self.num_registrations = new_count
        self.display_current_count()

    def display_current_count(
        self, reg_count: int = None, style: str = None, num_indents: int = None
    ):
        """Display the current count of user registrations.

        If passed a specific count will use that, else will use
        the registration count stored as the class variable.
        """
        if reg_count is None:
            reg_count = self.num_registrations
        pr.iprint(
            f"There {ut.plural(reg_count,'is','are')} "
            f"{reg_count} bike "
            f"{ut.plural(reg_count, 'registration')}.",
            style=style,
            num_indents=num_indents,
        )

    @classmethod
    def display_error_message(cls, error: str = ""):
        """Show an error message."""
        if error:
            pr.iprint(error, style=k.ERROR_STYLE)
        else:
            pr.iprint("Error: Invalid registration command.", style=k.ERROR_STYLE)
        pr.iprint(cls.usage_str(), style=k.ERROR_STYLE)

    @classmethod
    def usage_str(cls):
        """Return a string showing the REG command usage."""
        return "Usage: REG +/-/= {number}. E.g. 'REG +1', 'REG = 5'"
