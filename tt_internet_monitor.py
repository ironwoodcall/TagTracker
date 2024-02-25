"""TagTracker by Julias Hocking.

This will monitor the internet connection and print a message when no connection.

# Example usage
from tt_internet_monitor import InternetMonitor
InternetMonitor.start_monitor()
InternetMonitor.enable()
InternetMonitor.disable()
print(f"Internet Monitoring enabled? {InternetMonitor.enabled})
print(f"Internet Monitoring process {InternetMonitor.process})

Copyright (C) 2024 tevpg

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
import atexit
import time
import os
import sys
import signal
import urllib.request

import tt_printer as pr
import tt_conf as cfg


class InternetMonitorController:
    """Class for the main TT client program to use to control monitoring."""

    process = None  # a popen object
    enabled = False

    @staticmethod
    def ok_to_start() -> bool:
        """Checks if ok to start internet monitor.

        If not could be wrong O/S, disabled in config, or ....?
        """
        if not cfg.INTERNET_MONITORING_FREQUENCY:
            return False
        if not sys.platform.startswith("linux"):
            pr.iprint(
                "Not Linux, can not start internet monitor.", style=cfg.WARNING_STYLE
            )
            return False
        return True

    @classmethod
    def start_monitor(cls):
        """Launch the monitor as a separate process."""
        if not cls.ok_to_start():
            return
        # Figure out where and what to run.
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        script_name = os.path.basename(__file__)

        # Execute itself as a subprocess
        cls.process = subprocess.Popen([sys.executable, script_name], cwd=script_dir)
        pr.iprint()
        pr.iprint(
            "Checking internet connection "
            f"every {cfg.INTERNET_MONITORING_FREQUENCY} minutes.",
            style=cfg.HIGHLIGHT_STYLE,
        )
        # print(f"{sys.executable=}, {script_dir=}, {script_name=}")

        cls.register_cleanup()

    @classmethod
    def kill_monitor(cls):
        """Terminate the monitor process."""
        if cls.process:
            cls.process.terminate()
            print("Process terminated")
            cls.process = None

    @classmethod
    def cleanup(cls):
        """Clean up.  Register this for end-of-program cleanup."""
        cls.kill_monitor()

    @classmethod
    def register_cleanup(cls):
        """Register the cleanup method for program exit."""
        atexit.register(cls.cleanup)

    @classmethod
    def enable(cls):
        "Turn on monitoring (if it was off)."
        cls.start_monitor()
        cls.enabled = True

    @classmethod
    def disable(cls):
        """Turn off monitoring (if it was on)."""
        if cls.process:
            cls.kill_monitor()
        cls.enabled = False


class InternetMonitor:
    """This class monitors the internet connection as a separate process.

    It is to be used when called standalone.
    """

    @staticmethod
    def _must_be_main():
        if __name__ != "__main__":
            print(
                "Can not use this class as an import."
                " Did you mean InternetMonitorController?"
            )
            raise RuntimeError

    @staticmethod
    def _get_same_script_pids():
        """
        Retrieves a list of all process IDs (PIDs) associated with the given script name,
        excluding the PID of the current process and the PID of the pgrep command.
        """
        script_name = os.path.basename(__file__)
        current_pid = os.getpid()

        try:
            # Get list of same-named processes. Probably.
            ps_cmd = (
                f"ps -o pid,command|grep -E '\\b{script_name}\\b' "
                "|grep -E '\\bpython' | cut -d' ' -f1"
            )
            ps_output = subprocess.check_output(
                ps_cmd, shell=True, universal_newlines=True
            )

            # Extract PIDs from the output, excluding the current process's PID
            pids = [
                int(pid)
                for pid in ps_output.splitlines()
                if pid and pid.isdigit() and int(pid) != current_pid
            ]
            return pids
        except subprocess.CalledProcessError:
            return []

    @staticmethod
    def _signal_pids(pids, what_signal):
        """Send 'what_signal' to the list of pids."""
        if not pids:
            return
        for pid in pids:
            try:
                os.kill(pid, what_signal)
            except ProcessLookupError:
                # Don't care if this process is not (still) alive.
                pass
        time.sleep(3)

    @classmethod
    def _kill_other_instances(cls) -> int:
        """Terminate other instances of this script, return number remaining."""
        same_pids = cls._get_same_script_pids()
        cls._signal_pids(same_pids, signal.SIGTERM)
        same_pids = cls._get_same_script_pids()
        cls._signal_pids(same_pids, signal.SIGKILL)  # pylint:disable=no-member
        return len(cls._get_same_script_pids())

    @classmethod
    def _check_internet(cls) -> bool:
        """Test if connected to the internet."""
        try:
            urllib.request.urlopen("http://example.com", timeout=5)
            return True
        except urllib.request.URLError:
            return False

    @classmethod
    def run(cls):
        """Main process to start & run internet monitoring."""
        # Must only be run if this script is standalone (not imported).
        cls._must_be_main()
        # Only run if internet monitoring is enabled in config.
        if not cfg.INTERNET_MONITORING_FREQUENCY:
            return
        # pr.iprint()
        # pr.iprint(
        #     "Internet monitor started, checking connection every "
        #     f"{cfg.INTERNET_MONITORING_FREQUENCY} minutes",
        #     style=cfg.WARNING_STYLE,
        # )
        # Kill any other instances already running
        zombies = cls._kill_other_instances()
        if zombies:
            pr.iprint(
                f"Warning: unable to kill {zombies} other existing "
                "internet monitoring process(es)"
            )

        # Now run indefinitely, checking for an internet connection.
        # This will get killed by a signal sent from the main TT program.
        while True:
            time.sleep(cfg.INTERNET_MONITORING_FREQUENCY * 60)

            if not cls._check_internet():
                pr.text_alert("Open a web browser to check internet connection.",style=cfg.ALERT_STYLE)
            else:
                pr.text_alert("Internet connection ok.")


if __name__ == "__main__":
    # This is called as a subprocess to perform internet monitoring.
    InternetMonitor.run()
