"""NoiseMaker class to play sounds for TagTracker.

Copyright (C) 2023 Julias Hocking

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

import os
import subprocess

# import tt_globals
import tt_globals as g
import tt_util as ut
import tt_conf as cfg
import tt_printer as pr


class NoiseMaker:
    """Make system sounds for TagTracker."""

    # Class attributes
    player = cfg.SOUND_PLAYER
    bike_in = cfg.SOUND_BIKE_IN
    bike_out = cfg.SOUND_BIKE_OUT
    alert = cfg.SOUND_ALERT
    enabled = cfg.SOUND_ENABLED
    _initialized = False

    @classmethod
    def init_check(cls):
        """Check if the class is initialized, try to initialize if not.

        If initialization fails prints an error message & returns False.
        Also returns False
        """
        if not cls.enabled:
            return False
        if cls._initialized:
            return True

        # Check that the player & sound files exist
        if not all(
            [
                ut.find_on_path(cls.player),
                os.path.exists(cls.bike_in),
                os.path.exists(cls.bike_out),
                os.path.exists(cls.alert),
            ]
        ):
            pr.iprint(
                "Missing sound-player or sound file(s), sounds disabled",
                style=cfg.ERROR_STYLE,
            )
            cls.enabled = False
            return False

        cls._initialized = True
        return True

    @classmethod
    def play(cls, *sounds):
        """Play the sounds (which are sound filenames)."""
        if not cls.init_check():
            return
        for sound in list(set(sounds)):
            if not os.path.exists(sound):
                pr.iprint(
                    f"Sound file {sound} not found",
                    style=cfg.ERROR_STYLE,
                )

        # Rather brutally try to play the sound, ignoring any or all errors
        command = [cls.player] + sounds
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

