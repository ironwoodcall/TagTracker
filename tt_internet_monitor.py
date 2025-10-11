"""TagTracker by Julias Hocking.

This will monitor the internet connection and print a message when no connection.

Diagnostic codes used in notifications:
    - `SOCKCONN01`: TCP connection to probe host failed (likely no network).
    - `DNSFAIL01`: Probe hostname could not be resolved.
    - `TIMEOUT001`: HTTP request to probe timed out waiting for response.
    - `TIMEOUT002`: HTTP request failed via URLError timeout.
    - `REMOTEDISC`: Remote server closed the connection unexpectedly.
    - `HTTPFAILXYZ`: HTTP response returned status code `XYZ` (three digits).
    - `URL<REASON>`: URLError occurred; suffix shows the abbreviated reason.
    - `SOCKREAD01`: Socket/transport error while reading HTTP response.
    - `HTMLMISS01`: HTTP succeeded but probe token missing (cache/captive portal).
    - `HTTPBARGS01`: httpbin JSON response missing expected echo token.
    - `HTTPBJSON01`: httpbin response JSON could not be parsed.
    - `DOHCONN01`: DNS-over-HTTPS request could not connect to Google endpoint.
    - `DOHHTTPXYZ`: Google DoH endpoint returned status code `XYZ`.
    - `DOHURL***`: URLError raised calling Google DoH (suffix abbreviates reason).
    - `DOHTIMEOUT`: DNS-over-HTTPS request timed out waiting for response.
    - `DOHJSON010`: DNS-over-HTTPS response was not valid JSON.
    - `DOHSTATUSXX`: DoH returned unexpected DNS status `XX`.
    - `DOHQUEST01`: DoH response question name mismatch.
    - `NETISSUE01`: Generic fallback when confirmation fails without detail.

# Example usage
from tt_internet_monitor import InternetMonitor
InternetMonitor.start_monitor()
InternetMonitor.enable()
InternetMonitor.disable()
print(f"Internet Monitoring enabled? {InternetMonitor.enabled})
print(f"Internet Monitoring process {InternetMonitor.process})

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

import subprocess
import atexit
import time
import os
import sys
import signal
import json
import argparse
import tempfile
import urllib.parse
import urllib.request
import urllib.error
import socket
import random
import string
import http.client
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import common.tt_constants as k
import client_base_config as cfg
import tt_printer as pr
from tt_sounds import NoiseMaker

# Set colour on/off from config.
pr.COLOUR_ACTIVE = cfg.USE_COLOUR


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROL_DIR = "/tmp"
RESUME_EPSILON_SECONDS = 2.0


def _default_control_file() -> str:
    """Return control file path namespaced by the current process."""
    parent_pid = os.getpid()
    return os.path.join(CONTROL_DIR, f"internet_monitor_state_{parent_pid}.json")


DEFAULT_CONTROL_FILE = _default_control_file()

DEBUG_MONITOR = True


def _debug(message: str):
    """Conditional debug output for the internet monitor."""
    if not DEBUG_MONITOR:
        return
    print(f"[MONITOR] {message}")


class InternetMonitorController:
    """Class for the main TT client program to use to control monitoring."""

    process = None  # a popen object
    enabled = False
    _control_file = DEFAULT_CONTROL_FILE
    _last_command_token: Optional[str] = None

    @classmethod
    def _read_control_state(cls) -> Optional[dict]:
        try:
            with open(cls._control_file_path(), encoding="utf-8") as ctl:
                return json.load(ctl)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    @classmethod
    def set_debug(cls, enabled: bool):
        """Toggle debug tracing for the monitor."""
        global DEBUG_MONITOR
        DEBUG_MONITOR = bool(enabled)
        _debug(f"Debug mode set to {DEBUG_MONITOR}")
        state = cls._read_control_state()
        suppress_until = time.time()
        if state and "suppress_until" in state:
            try:
                suppress_until = float(state.get("suppress_until", suppress_until))
            except (TypeError, ValueError):
                pass
        cls._write_control_state(suppress_until)
        cls._signal_monitor()

    @staticmethod
    def ok_to_start() -> bool:
        """Checks if ok to start internet monitor.

        If not could be wrong O/S, disabled in config, or ....?
        """
        if not cfg.INTERNET_MONITORING_FREQUENCY:
            return False
        if not sys.platform.startswith("linux"):
            pr.iprint(
                "Not Linux, can not start internet monitor.", style=k.WARNING_STYLE
            )
            return False
        return True

    @classmethod
    def _control_file_path(cls) -> str:
        """Return the filesystem path used for monitor control state."""
        return cls._control_file

    @classmethod
    def _write_control_state(cls, suppress_until: float) -> str:
        """Persist control state for the monitor, returning a token."""
        control_path = Path(cls._control_file_path())
        control_path.parent.mkdir(parents=True, exist_ok=True)

        # Use a simple token so the monitor can ignore already handled messages.
        token = f"{time.time():.6f}-{random.randint(1000, 9999)}"
        state = {
            "suppress_until": suppress_until,
            "command_token": token,
            "written_at": time.time(),
            "debug": DEBUG_MONITOR,
        }

        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(control_path.parent), prefix=control_path.name + ".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_file:
                json.dump(state, tmp_file)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_path, control_path)
        finally:
            # In case of exception after mkstemp, ensure temp file removed.
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except FileNotFoundError:
                    pass

        cls._last_command_token = token
        remaining = suppress_until - time.time()
        _debug(
            "Control state updated: suppress_until=%s (in %.0fs)"
            % (time.strftime("%H:%M:%S", time.localtime(suppress_until)), remaining)
        )
        return token

    @classmethod
    def _signal_monitor(cls):
        """Ping the monitor process so it reloads control state."""
        if not cls.process:
            _debug("No monitor process found when signalling.")
            return
        try:
            os.kill(cls.process.pid, signal.SIGUSR1)
            _debug(f"Sent SIGUSR1 to monitor pid={cls.process.pid}")
        except ProcessLookupError:
            _debug("Monitor process missing when signalling; clearing handle.")
            cls.process = None

    @classmethod
    def start_monitor(cls, initial_suppress_seconds: float = 0):
        """Launch the monitor as a separate process."""
        if not cls.ok_to_start():
            return
        # Figure out where and what to run.
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_name = os.path.basename(__file__)

        # Ensure initial control state reflects desired suppression window.
        suppress_until = time.time() + max(0, float(initial_suppress_seconds))
        cls._write_control_state(suppress_until)

        # Execute itself as a subprocess
        cmd = [
            sys.executable,
            script_name,
            "--control-file",
            cls._control_file_path(),
            "--initial-suppress",
            str(int(max(0, float(initial_suppress_seconds))))
        ]
        cls.process = subprocess.Popen(cmd, cwd=script_dir)
        _debug(
            "Started monitor subprocess pid=%s with initial suppress %.0fs"
            % (cls.process.pid if cls.process else "?", initial_suppress_seconds)
        )
        # pr.iprint(
        #     "Checking internet connection "
        #     f"every {cfg.INTERNET_MONITORING_FREQUENCY} minutes.",
        #     style=k.HIGHLIGHT_STYLE,
        # )
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

    @classmethod
    def monitor_off(cls, duration_minutes: float = 120):
        """Suppress notifications for the requested duration."""
        suppress_seconds = max(0, float(duration_minutes) * 60)
        _debug(
            f"Monitor OFF requested for {suppress_seconds:.0f}s (process active={bool(cls.process)})"
        )
        if not cls.process:
            cls.start_monitor(initial_suppress_seconds=suppress_seconds)
            cls.enabled = True
            return
        suppress_until = time.time() + suppress_seconds
        cls._write_control_state(suppress_until)
        cls._signal_monitor()

    @classmethod
    def monitor_on(cls):
        """Resume notifications immediately."""
        _debug(f"Monitor ON requested (process active={bool(cls.process)})")
        if not cls.process:
            cls.start_monitor(initial_suppress_seconds=0)
            cls.enabled = True
            return
        suppress_until = time.time() - RESUME_EPSILON_SECONDS
        cls._write_control_state(suppress_until)
        cls._signal_monitor()


@dataclass
class PendingAlert:
    timestamp: float
    diag: Optional[str]


class InternetMonitor:
    """This class monitors the internet connection as a separate process."""

    control_file_path = DEFAULT_CONTROL_FILE
    _suppress_until: float = 0.0
    _last_control_token: Optional[str] = None
    _control_reload_requested: bool = True
    _pending_alert: Optional[PendingAlert] = None
    _last_notification_ts: float = 0.0
    _running: bool = True
    _check_interval: float = 0.0
    _alert_cooldown: float = 0.0
    _first_cycle: bool = True

    CONFIRMATION_DELAY = 30.0  # seconds to wait before confirming lapse
    MINIMUM_SLEEP = 1.0
    SOCKET_TEST_TARGET = ("1.1.1.1", 53)

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
        """Return PIDs of other running copies of this script."""
        script_name = os.path.basename(__file__)
        current_pid = os.getpid()

        try:
            ps_cmd = (
                f"ps -o pid,command|grep -E '\\b{script_name}\\b' "
                "|grep -E '\\bpython' | cut -d' ' -f1"
            )
            ps_output = subprocess.check_output(
                ps_cmd, shell=True, universal_newlines=True
            )
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

    @staticmethod
    def _make_random_string(length=10) -> str:
        """Generate a random string of fixed length."""
        letters = string.ascii_lowercase
        return "".join(random.choice(letters) for i in range(length))

    @staticmethod
    def _create_httpbin_url(random_string: str) -> str:
        """Create the URL for the httpbin probe."""
        return f"https://httpbin.org/get?text={random_string}"

    @staticmethod
    def _create_doh_url(query_name: str) -> str:
        """Create the URL for the Google DoH confirmation probe."""
        return "https://dns.google/resolve?name={name}&type=1".format(
            name=urllib.parse.quote(query_name, safe="")
        )

    @staticmethod
    def _format_diag(prefix: str, detail: str = "") -> str:
        """Build a diagnostic code 10-12 chars long."""
        prefix = "".join(ch for ch in prefix.upper() if ch.isalnum())
        detail = "".join(ch for ch in detail.upper() if ch.isalnum())
        code = prefix + detail
        if len(code) < 10:
            code = code.ljust(10, "0")
        elif len(code) > 12:
            code = code[:12]
        return code

    @classmethod
    def _check_httpbin(cls) -> Tuple[bool, Optional[str]]:
        """Primary probe: call httpbin and confirm random token."""
        random_string = cls._make_random_string()
        url = cls._create_httpbin_url(random_string)
        host = urllib.parse.urlparse(url).hostname or ""

        _debug(f"httpbin probe starting token={random_string} url={url}")

        try:
            with socket.create_connection(cls.SOCKET_TEST_TARGET, timeout=3):
                pass
        except OSError:
            diag = cls._format_diag("SOCK", "CONN01")
            _debug(
                f"httpbin probe failed: TCP connect diag={diag} target={cls.SOCKET_TEST_TARGET}"
            )
            return False, diag

        try:
            socket.gethostbyname(host)
        except socket.gaierror:
            diag = cls._format_diag("DNS", "FAIL01")
            _debug(f"httpbin probe failed: DNS lookup diag={diag} host={host}")
            return False, diag

        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                raw_body = response.read()
                html = raw_body.decode("utf-8", errors="ignore")
                if DEBUG_MONITOR:
                    try:
                        _debug(
                            "httpbin probe response headers: %s"
                            % dict(response.headers.items())
                        )
                    except Exception:  # pragma: no cover - debug only
                        pass
        except socket.timeout:
            diag = cls._format_diag("TIMEOUT", "001")
            _debug(f"httpbin probe failed: socket timeout diag={diag} url={url}")
            return False, diag
        except http.client.RemoteDisconnected:
            diag = cls._format_diag("REMOTE", "DISC")
            _debug(f"httpbin probe failed: remote disconnect diag={diag} url={url}")
            return False, diag
        except urllib.error.HTTPError as err:
            diag = cls._format_diag("HTTPFAIL", f"{int(err.code):03d}")
            _debug(
                f"httpbin probe failed: HTTP status {err.code} diag={diag} url={url}"
            )
            return False, diag
        except urllib.error.URLError as err:
            if isinstance(err.reason, socket.timeout):
                diag = cls._format_diag("TIMEOUT", "002")
                _debug(
                    f"httpbin probe failed: urllib timeout diag={diag} url={url}"
                )
                return False, diag
            reason_name = getattr(err.reason, "__class__", type(err.reason)).__name__
            diag = cls._format_diag("URL", reason_name[:7])
            _debug(
                f"httpbin probe failed: URLError {reason_name} diag={diag} url={url} details={err}"
            )
            return False, diag
        except OSError as err:
            diag = cls._format_diag("SOCK", "READ01")
            _debug(
                f"httpbin probe failed: socket read diag={diag} url={url} details={err}"
            )
            return False, diag

        json_text_value = None
        json_error = None
        try:
            json_payload = json.loads(html)
            if isinstance(json_payload, dict):
                json_text_value = (json_payload.get("args") or {}).get("text")
        except json.JSONDecodeError as err:
            json_error = err

        if json_text_value == random_string:
            _debug("httpbin probe succeeded (json echo matched)")
            return True, None

        if random_string in html:
            _debug("httpbin probe succeeded (string search matched)")
            return True, None

        if json_error:
            diag = cls._format_diag("HTTPBJSON", "01")
            _debug(
                f"httpbin probe failed: JSON decode diag={diag} url={url} error={json_error} payload_sample={html[:120]!r}"
            )
            return False, diag

        diag = cls._format_diag("HTTPBARGS", "01")
        _debug(
            f"httpbin probe failed: args mismatch diag={diag} expected={random_string} actual={json_text_value} url={url} payload_sample={html[:120]!r}"
        )
        return False, diag

    @classmethod
    def _check_doh_confirmation(cls) -> Tuple[bool, Optional[str]]:
        """Confirmation probe: query Google DoH for a random name."""
        random_string = cls._make_random_string()
        query_name = f"{random_string}.invalid"
        url = cls._create_doh_url(query_name)

        _debug(f"DoH probe starting query={query_name} url={url}")

        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                payload = response.read().decode("utf-8", errors="ignore")
        except socket.timeout:
            diag = cls._format_diag("DOH", "TIMEOUT")
            _debug(f"DoH probe failed: socket timeout diag={diag} url={url}")
            return False, diag
        except urllib.error.HTTPError as err:
            diag = cls._format_diag("DOHHTTP", f"{int(err.code):03d}")
            _debug(
                f"DoH probe failed: HTTP status {err.code} diag={diag} url={url}"
            )
            return False, diag
        except urllib.error.URLError as err:
            reason = getattr(err.reason, "__class__", type(err.reason)).__name__
            diag = cls._format_diag("DOHURL", reason[:7])
            _debug(
                f"DoH probe failed: URLError {reason} diag={diag} url={url} details={err}"
            )
            return False, diag
        except OSError:
            diag = cls._format_diag("DOH", "CONN01")
            _debug(f"DoH probe failed: connection diag={diag} url={url}")
            return False, diag

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            diag = cls._format_diag("DOH", "JSON01")
            _debug(
                f"DoH probe failed: JSON decode diag={diag} url={url} payload_sample={payload[:120]!r}"
            )
            return False, diag

        status = data.get("Status")
        if status is None:
            diag = cls._format_diag("DOH", "STATUS99")
            _debug(f"DoH probe failed: missing status diag={diag} url={url}")
            return False, diag

        question = data.get("Question") or []
        if not question or not isinstance(question, list):
            diag = cls._format_diag("DOH", "QUEST01")
            _debug(f"DoH probe failed: question missing diag={diag} url={url}")
            return False, diag
        actual_name = str(question[0].get("name", "")).strip().rstrip(".")
        expected_name = query_name.rstrip(".")
        if actual_name.lower() != expected_name.lower():
            diag = cls._format_diag("DOH", "QUEST01")
            _debug(
                f"DoH probe failed: question mismatch actual={actual_name} expected={expected_name} diag={diag} url={url}"
            )
            return False, diag

        # Treat NXDOMAIN (3) or success (0) as healthy network responses.
        if int(status) in (0, 3):
            _debug(f"DoH probe succeeded with status {status}")
            return True, None

        diag = cls._format_diag("DOHSTATUS", f"{int(status):02d}")
        _debug(
            f"DoH probe failed: unexpected status {status} diag={diag} url={url} payload_sample={payload[:120]!r}"
        )
        return False, diag

    @classmethod
    def _parse_args(cls, argv):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--control-file", default=DEFAULT_CONTROL_FILE)
        parser.add_argument("--initial-suppress", type=float, default=0.0)
        args, _ = parser.parse_known_args(argv)

        cls.control_file_path = os.path.abspath(args.control_file)
        cls._suppress_until = time.time() + max(0.0, float(args.initial_suppress))
        cls._control_reload_requested = True

    @classmethod
    def _handle_state_update(cls, _signum, _frame):
        cls._control_reload_requested = True

    @classmethod
    def _handle_shutdown(cls, _signum, _frame):
        cls._running = False

    @classmethod
    def _install_signal_handlers(cls):
        signal.signal(signal.SIGUSR1, cls._handle_state_update)
        signal.signal(signal.SIGTERM, cls._handle_shutdown)
        signal.signal(signal.SIGINT, cls._handle_shutdown)

    @classmethod
    def _load_control_state(cls):
        try:
            with open(cls.control_file_path, encoding="utf-8") as control_file:
                data = json.load(control_file)
        except FileNotFoundError:
            cls._suppress_until = time.time()
            _debug("Control file missing; suppression reset")
            cls._control_reload_requested = False
            return
        except json.JSONDecodeError:
            _debug("Control file unreadable; ignoring contents")
            cls._control_reload_requested = False
            return

        token = data.get("command_token")
        if (
            token
            and token == cls._last_control_token
            and not cls._control_reload_requested
        ):
            _debug("Control token unchanged; no update applied")
            cls._control_reload_requested = False
            return

        cls._last_control_token = token
        debug_flag = data.get("debug")
        if debug_flag is not None:
            global DEBUG_MONITOR
            previous_debug = DEBUG_MONITOR
            DEBUG_MONITOR = bool(debug_flag)
            if DEBUG_MONITOR and not previous_debug:
                print("[MONITOR] Debug enabled")
            elif not DEBUG_MONITOR and previous_debug:
                print("[MONITOR] Debug disabled")
        suppress_until = data.get("suppress_until")
        if suppress_until is not None:
            cls._suppress_until = float(suppress_until)
            _debug(
                "Loaded suppress_until=%s"
                % time.strftime("%H:%M:%S", time.localtime(cls._suppress_until))
            )

        cls._control_reload_requested = False

    @classmethod
    def _sleep(cls, duration: float):
        if duration <= 0:
            return
        end_time = time.time() + duration
        _debug(f"Entering sleep for up to {duration:.1f}s")
        while cls._running:
            remaining = end_time - time.time()
            if remaining <= 0:
                _debug("Sleep completed full duration")
                break
            if cls._control_reload_requested:
                _debug("Sleep interrupted by control reload request")
                break
            try:
                time.sleep(min(remaining, cls.MINIMUM_SLEEP))
                if min(remaining, cls.MINIMUM_SLEEP) == remaining:
                    _debug("Sleep ended after chunk duration")
                    break
            except InterruptedError:
                if cls._control_reload_requested:
                    _debug("Sleep interrupted by signal")
                    break

    @classmethod
    def _send_notification(cls, diag_code: str):
        _debug(f"Triggering notification diag={diag_code}")
        NoiseMaker.play(k.ALERT)
        pr.text_alert(
            f"When convenient, open a web browser to check internet connection. [{diag_code}]",
            style=k.STRONG_ALERT_STYLE,
        )

    @classmethod
    def _confirm_pending_alert(cls, now: float):
        _debug("Running confirmation probe for pending alert")
        ok, diag = cls._check_doh_confirmation()
        if ok:
            cls._pending_alert = None
            _debug("Confirmation probe succeeded; pending alert cleared")
            return

        prior_diag = cls._pending_alert.diag if cls._pending_alert else None
        diag_code = diag or prior_diag or cls._format_diag("NET", "ISSUE01")
        if now - cls._last_notification_ts < cls._alert_cooldown:
            cls._pending_alert = PendingAlert(timestamp=now, diag=diag_code)
            _debug("Confirmation failed but within cooldown; alert rescheduled")
            return

        cls._send_notification(diag_code)
        cls._last_notification_ts = now
        cls._pending_alert = PendingAlert(timestamp=now, diag=diag_code)
        _debug("Confirmation failed; notification sent")

    @classmethod
    def run(cls, argv=None):
        """Main process to start & run internet monitoring."""
        cls._must_be_main()
        if not cfg.INTERNET_MONITORING_FREQUENCY:
            return

        cls._parse_args(argv or sys.argv[1:])
        cls._install_signal_handlers()
        cls._running = True
        cls._first_cycle = True

        zombies = cls._kill_other_instances()
        if zombies:
            pr.iprint(
                f"Warning: unable to kill {zombies} other existing internet monitoring process(es)"
            )

        cls._check_interval = max(
            float(cfg.INTERNET_MONITORING_FREQUENCY) * 60, cls.MINIMUM_SLEEP
        )
        cls._alert_cooldown = max(cls._check_interval, cls.CONFIRMATION_DELAY)

        _debug(
            "Monitor run loop setup: interval=%.0fs confirmation=%.0fs"
            % (cls._check_interval, cls.CONFIRMATION_DELAY)
        )

        cls._load_control_state()

        next_delay = 0.0
        while cls._running:
            _debug(f"Loop iteration starting; sleep for {next_delay:.1f}s")
            cls._sleep(next_delay)
            cls._load_control_state()
            now = time.time()

            if now < cls._suppress_until:
                cls._pending_alert = None
                _debug(
                    "Notifications suppressed for another %.0fs"
                    % (cls._suppress_until - now)
                )
                next_delay = max(
                    cls.MINIMUM_SLEEP,
                    min(cls._suppress_until - now, cls._check_interval),
                )
                continue

            if cls._first_cycle:
                cls._first_cycle = False
                next_delay = cls._check_interval
                _debug(
                    "Initial startup delay applied; next check in %.0fs"
                    % cls._check_interval
                )
                continue

            if cls._pending_alert and now - cls._pending_alert.timestamp >= cls.CONFIRMATION_DELAY:
                cls._confirm_pending_alert(now)
                next_delay = cls._check_interval
                continue

            ok, diag = cls._check_httpbin()
            if ok:
                cls._pending_alert = None
                _debug("Primary probe succeeded; no pending alert")
                next_delay = cls._check_interval
                continue

            if not cls._pending_alert:
                cls._pending_alert = PendingAlert(timestamp=now, diag=diag)
                _debug(f"Primary probe failed; confirmation scheduled diag={diag}")
            else:
                cls._pending_alert.diag = diag or cls._pending_alert.diag
                _debug(
                    "Primary probe failed again; diag updated to %s"
                    % cls._pending_alert.diag
                )

            elapsed = now - cls._pending_alert.timestamp
            remaining = max(0.0, cls.CONFIRMATION_DELAY - elapsed)
            next_delay = max(cls.MINIMUM_SLEEP, remaining)


if __name__ == "__main__":
    # This is called as a subprocess to perform internet monitoring.
    InternetMonitor.run()
