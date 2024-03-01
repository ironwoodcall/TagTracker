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
import random

# import tt_globals
import tt_globals as g
import tt_util as ut
import tt_conf as cfg
import tt_printer as pr


class NoiseMaker:
    """Make system sounds for TagTracker."""

    # Class attributes
    player = cfg.SOUND_PLAYER
    enabled = cfg.SOUND_ENABLED
    _initialized = False

    # These can be files or folders full of sounds
    bike_in = cfg.SOUND_BIKE_IN
    bike_out = cfg.SOUND_BIKE_OUT
    alert = cfg.SOUND_ALERT
    cheer = cfg.SOUND_CHEER

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
                os.path.exists(cls.cheer)
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

    @staticmethod
    def _file_or_file_in_folder(filepath):
        extension = "mp3"
        # Check if the filepath exists
        if not os.path.exists(filepath):
            return None

        # Check if the filepath is a file
        if os.path.isfile(filepath):
            return filepath

        # If the filepath is a folder
        if os.path.isdir(filepath):
            # Get a list of files in the folder with the desired extension
            matching_files = [f for f in os.listdir(filepath) if f.lower().endswith(extension)]
            # If there are no matching files, return None
            if not matching_files:
                return None
            # Select a random file from the list
            random_file = random.choice(matching_files)
            # Return the filepath of the random file
            return os.path.join(filepath, random_file)

        # Not a file nor a folder
        return None

    @classmethod
    def get_sound_filepath(cls,code:str) -> str:
        """Fetch the soundfile for a given sound code."""

        if code == g.BIKE_IN:
            look_at = cls.bike_in
        elif code == g.BIKE_OUT:
            look_at = cls.bike_out
        elif code == g.ALERT:
            look_at = cls.alert
        elif code == g.CHEER:
            look_at = cls.cheer
        else:
            ut.squawk(f"sound type {code} not recognized")
            return None
        # Get the file or a file in folder if its a folder.
        return cls._file_or_file_in_folder(look_at)

    @classmethod
    def play(cls, *sound_codes):
        """Play the sounds (which are constants from globals).

        The sound_codes must be BIKE_IN, BIKE_OUT, or ALERT.
        """
        if not cls.init_check():
            return
        soundfiles = []
        for code in sound_codes:
            if code == g.BIKE_IN:
                soundfiles.append(cls.bike_in)
            elif code == g.BIKE_OUT:
                soundfiles.append(cls.bike_out)
            elif code == g.ALERT:
                soundfiles.append(cls.alert)
            elif code == g.CHEER:
                soundfiles.append(cls.cheer)
            else:
                ut.squawk(f"sound type {code} not recognized")
        for sound in soundfiles:
            if not sound:   # skip any non-files
                continue
            if not os.path.exists(sound):
                ut.squawk(f"sound file {sound} not found")

        # Try to play the sound, ignoring any or all errors
        command = [cls.player] + soundfiles
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

