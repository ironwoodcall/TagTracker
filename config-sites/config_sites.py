#!/usr/bin/env python3
"""TagTracker set-up: the site config manager.

Serves config_sites.html on 127.0.0.1 only, plus a few JSON calls that
read and write site configs (site_<handle>_config.py in SITE_CONFIGS_FOLDER)
and the ACTIVE_SITE line in client_local_config.py. The page does all the
checking and wording; this server just reads and writes files, changing
only the items the manager owns and leaving every other line alone.

Usage:
    python3 config-sites/config_sites.py [--port N] [--no-browser]

Stops when the page is closed, after a period with no page open, or with
Ctrl+C. Uses only the Python standard library.

Copyright (C) 2023-2026 Todd Glover & Julias Hocking

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

import argparse
import http.server
import json
import os
import re
import shutil
import sys
import threading
import time
import webbrowser
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # the program folder, for tt_site_config

import tt_site_config as sc  # noqa: E402  pylint: disable=wrong-import-position

PAGE = os.path.join(HERE, "config_sites.html")
DEFAULT_PORT = 8765
PORTS_TO_TRY = 20

FIRST_VISIT_LIMIT = 10 * 60  # seconds to wait for the page to open at all
PAGE_GONE_LIMIT = 3 * 60  # no word from any page for this long: stop
BYE_GRACE = 15  # after the page says goodbye (it may just be reloading)

TAG_RE = re.compile(r"^[a-z][a-z]\d{1,2}$")

# Items read from the first two config layers.
LAYER_ITEMS = (
    "SITE_CONFIGS_FOLDER",
    "SITE_CONFIG_TEMPLATE",
    "DATA_FOLDER",
    "TAG_COLOUR_NAMES",
    "ACTIVE_SITE",
    "DATA_OWNER_NAME",
)

NEW_FILE_HEADER = '"""TagTracker site config, written by TagTracker set-up."""\n\n'
NEW_LOCAL_HEADER = '"""Local (organization) config for TagTracker."""\n\n'


class ApiError(Exception):
    """A request that can't be done. Args: (status, message)."""


class Manager:
    """Reads and writes the config files."""

    def __init__(self, local_config: str):
        self.base_config = os.path.join(sc.PROGRAM_FOLDER, "client_base_config.py")
        self.local_config = local_config
        self.lock = threading.Lock()

    # -- reading --------------------------------------------------------

    def layers(self) -> dict[str, Any]:
        """Values of LAYER_ITEMS from code defaults, then the organization config."""
        values: dict[str, Any] = {}
        for path in (self.base_config, self.local_config):
            cf = sc.read_config_file(path, quiet=True)
            for name in LAYER_ITEMS:
                value = sc.readable_value(cf, name)
                if value is not None:
                    values[name] = value
        return values

    def configs_folder(self, layers: dict) -> str:
        return sc.program_path(layers.get("SITE_CONFIGS_FOLDER", "../site_configs"))

    @staticmethod
    def data_folder(path: str) -> str:
        """DATA_FOLDER as TagTracker uses it: relative to the program folder."""
        return sc.program_path(path or "../data")

    def site_record(self, handle: str, path: str, archived: bool, layers: dict) -> dict:
        """What the page needs to know about one site config."""
        cf = sc.read_config_file(path, quiet=True)
        val = lambda name, default=None: sc.readable_value(cf, name, default)  # noqa: E731
        problems = sc.edit_problems(cf)
        in_file = sc.fold_handle(val("SITE_HANDLE", handle))
        if not cf.error and in_file != handle:
            problems.append(
                f"SITE_HANDLE in the file is '{in_file}', which doesn't match its name."
            )
        owner = val("DATA_OWNER", "")
        if isinstance(owner, (list, tuple)):
            owner = " ".join(str(x).strip() for x in owner)
        data_folder = self.data_folder(val("DATA_FOLDER", layers.get("DATA_FOLDER", "")))
        dates = sc.datafile_dates(handle, data_folder)
        today = sc.today_str()
        checkins = 0
        if today in dates:
            checkins = sc.checkins_in_datafile(os.path.join(data_folder, f"{handle}_{today}.json"))
        colours = val("TAG_COLOUR_NAMES", None)
        return {
            "handle": handle,
            "file": os.path.basename(path),
            "archived": archived,
            "name": str(val("SITE_NAME", "") or ""),
            "ownerName": str(val("DATA_OWNER_NAME", "") or ""),
            "ownerNoticeInFile": str(owner or ""),
            "eventMode": bool(val("EVENT_MODE", False)),
            "regular": sc.split_tags(val("REGULAR_TAGS", "")),
            "oversize": sc.split_tags(val("OVERSIZE_TAGS", "")),
            "colourNames": colours if isinstance(colours, dict) else None,
            "datafiles": dates,
            "checkinsToday": checkins,
            "mtime": cf.mtime,
            "problems": problems,
        }

    def template(self, layers: dict) -> dict:
        path = sc.program_path(layers.get("SITE_CONFIG_TEMPLATE", ""))
        cf = sc.read_config_file(path, quiet=True)
        problem = ""
        if not os.path.isfile(path):
            problem = f"Template {path} not found; new configs start empty."
        elif sc.edit_problems(cf):
            problem = f"Template {path}: " + " ".join(sc.edit_problems(cf))
        val = lambda name, default=None: sc.readable_value(cf, name, default)  # noqa: E731
        return {
            "path": path,
            "problem": problem,
            "ownerName": str(val("DATA_OWNER_NAME", "") or layers.get("DATA_OWNER_NAME", "") or ""),
            "eventMode": bool(val("EVENT_MODE", True)),
            "regular": sc.split_tags(val("REGULAR_TAGS", "")),
            "oversize": sc.split_tags(val("OVERSIZE_TAGS", "")),
        }

    def state(self) -> dict:
        layers = self.layers()
        folder = self.configs_folder(layers)
        sites = [
            self.site_record(h, p, False, layers) for h, p in sc.list_sites(folder).items()
        ] + [
            self.site_record(h, p, True, layers)
            for h, p in sc.list_sites(folder, archived=True).items()
        ]
        local = sc.read_config_file(self.local_config, quiet=True)
        active_problems = sc.edit_problems(local, [sc.ACTIVE_ITEM])
        colours = layers.get("TAG_COLOUR_NAMES") or {}
        checks = []
        data_folder = self.data_folder(layers.get("DATA_FOLDER", ""))
        if not os.path.isdir(data_folder):
            checks.append({"level": "err", "text": f"Data folder {data_folder} doesn't exist."})
        elif not os.access(data_folder, os.W_OK):
            checks.append({"level": "err", "text": f"Data folder {data_folder} isn't writable."})
        if not os.path.isdir(folder):
            checks.append(
                {"level": "ok", "text": f"Site configs folder {folder} will be created on first save."}
            )
        return {
            "today": sc.today_str(),
            "activeSite": sc.fold_handle(layers.get("ACTIVE_SITE", "")),
            "activeProblem": " ".join(active_problems),
            "localConfig": self.local_config,
            "configsFolder": folder,
            "colours": [[str(k).lower(), str(v)] for k, v in colours.items()]
            if isinstance(colours, dict)
            else [],
            "template": self.template(layers),
            "sites": sites,
            "checks": checks,
        }

    # -- writing --------------------------------------------------------

    def _find(self, folder: str, handle: str) -> tuple[str, bool]:
        """(path, archived) of a site config, or ("", False)."""
        if handle in sc.list_sites(folder):
            return sc.list_sites(folder)[handle], False
        if handle in sc.list_sites(folder, archived=True):
            return sc.list_sites(folder, archived=True)[handle], True
        return "", False

    @staticmethod
    def _clean_values(values: dict) -> dict:
        """Check the page's values (a backstop: the page checks them first)."""
        if not isinstance(values, dict):
            raise ApiError(400, "No values sent.")
        handle = sc.fold_handle(values.get("SITE_HANDLE"))
        if sc.handle_problem(handle):
            raise ApiError(400, sc.handle_problem(handle))
        name = str(values.get("SITE_NAME") or "").strip()
        if not name:
            raise ApiError(400, "SITE_NAME is empty.")
        tags = {}
        seen = set()
        for item in ("REGULAR_TAGS", "OVERSIZE_TAGS"):
            got = values.get(item) or []
            if not isinstance(got, list):
                raise ApiError(400, f"{item} must be a list.")
            tags[item] = [str(t).strip().lower() for t in got]
            for t in tags[item]:
                if not TAG_RE.match(t):
                    raise ApiError(400, f"'{t}' in {item} isn't a tag ID.")
                if t in seen:
                    raise ApiError(400, f"Tag '{t}' is listed twice.")
                seen.add(t)
        if not seen:
            raise ApiError(400, "No tags.")
        return {
            "SITE_NAME": name,
            "SITE_HANDLE": handle,
            "EVENT_MODE": bool(values.get("EVENT_MODE")),
            "DATA_OWNER_NAME": str(values.get("DATA_OWNER_NAME") or "").strip(),
            "DATA_OWNER": str(values.get("DATA_OWNER") or "").strip(),
            "REGULAR_TAGS": " ".join(tags["REGULAR_TAGS"]),
            "OVERSIZE_TAGS": " ".join(tags["OVERSIZE_TAGS"]),
        }

    def save(self, body: dict) -> dict:
        values = self._clean_values(body.get("values"))
        handle = values["SITE_HANDLE"]
        orig = sc.fold_handle(body.get("origHandle"))
        with self.lock:
            layers = self.layers()
            folder = self.configs_folder(layers)
            new_path = os.path.join(folder, sc.site_filename(handle))
            if orig:
                old_path, archived = self._find(folder, orig)
                if not old_path:
                    raise ApiError(409, f"{sc.site_filename(orig)} is no longer there.")
                if archived:
                    raise ApiError(409, f"'{orig}' is archived. Restore it first.")
                cf = sc.read_config_file(old_path)
                if body.get("mtime") is not None and cf.mtime != body.get("mtime"):
                    raise ApiError(
                        409,
                        f"{os.path.basename(old_path)} has changed since you opened it. "
                        "Go back to the list to see the latest version, then make your changes again.",
                    )
            else:
                old_path = ""
                tpath = sc.program_path(layers.get("SITE_CONFIG_TEMPLATE", ""))
                cf = sc.read_config_file(tpath, quiet=True)
                if cf.error or not cf.text:
                    cf = sc.parse_config_text(NEW_FILE_HEADER)
            if handle != orig and self._find(folder, handle)[0]:
                raise ApiError(409, f"There's already a site config for '{handle}'.")
            try:
                text = sc.update_text(cf, values)
                sc.write_atomically(new_path, text, keep_backup=bool(orig))
            except sc.ConfigFileError as e:
                raise ApiError(409, " ".join(e.args)) from e
            except OSError as e:
                raise ApiError(500, f"Couldn't write {new_path}: {e}") from e
            note = ""
            if old_path and handle != orig:
                os.replace(old_path, old_path + ".bak")  # kept, but no longer a site config
                if sc.fold_handle(layers.get("ACTIVE_SITE", "")) == orig:
                    self._write_active(handle)
                    note = f"It's still the default site, now as '{handle}'."
        return {"ok": True, "handle": handle, "note": note}

    def archive(self, body: dict) -> dict:
        handle = sc.fold_handle(body.get("handle"))
        with self.lock:
            layers = self.layers()
            folder = self.configs_folder(layers)
            path, archived = self._find(folder, handle)
            if not path or archived:
                raise ApiError(409, f"No current site config for '{handle}'.")
            if sc.fold_handle(layers.get("ACTIVE_SITE", "")) == handle:
                raise ApiError(409, "The default site can't be archived.")
            dest = os.path.join(folder, sc.ARCHIVE_SUBFOLDER, os.path.basename(path))
            if os.path.exists(dest):
                raise ApiError(409, f"{dest} already exists.")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(path, dest)
        return {"ok": True}

    def restore(self, body: dict) -> dict:
        handle = sc.fold_handle(body.get("handle"))
        with self.lock:
            folder = self.configs_folder(self.layers())
            path, archived = self._find(folder, handle)
            if not path or not archived:
                raise ApiError(409, f"No archived site config for '{handle}'.")
            dest = os.path.join(folder, os.path.basename(path))
            if os.path.exists(dest):
                raise ApiError(409, f"{dest} already exists.")
            shutil.move(path, dest)
        return {"ok": True}

    def _write_active(self, handle: str) -> None:
        cf = sc.read_config_file(self.local_config)
        if not cf.text:
            cf = sc.parse_config_text(NEW_LOCAL_HEADER, self.local_config)
        try:
            text = sc.update_text(cf, {sc.ACTIVE_ITEM: handle})
            sc.write_atomically(self.local_config, text)
        except sc.ConfigFileError as e:
            raise ApiError(
                409, f"Can't set ACTIVE_SITE in {self.local_config}: " + " ".join(e.args)
            ) from e
        except OSError as e:
            raise ApiError(500, f"Couldn't write {self.local_config}: {e}") from e

    def set_active(self, body: dict) -> dict:
        handle = sc.fold_handle(body.get("handle"))
        with self.lock:
            folder = self.configs_folder(self.layers())
            if handle and handle not in sc.list_sites(folder):
                raise ApiError(409, f"No current site config for '{handle}'.")
            self._write_active(handle)
        return {"ok": True}


class Watchdog:
    """Stops the server once no page has been in touch for a while."""

    def __init__(self):
        self.started = time.monotonic()
        self.last_seen = None
        self.bye_at = None

    def heard(self):
        self.last_seen = time.monotonic()
        self.bye_at = None

    def bye(self):
        self.bye_at = time.monotonic()

    def should_stop(self) -> bool:
        now = time.monotonic()
        if self.bye_at is not None and now - self.bye_at > BYE_GRACE:
            return True
        if self.last_seen is None:
            return now - self.started > FIRST_VISIT_LIMIT
        return now - self.last_seen > PAGE_GONE_LIMIT


def make_handler(manager: Manager, watchdog: Watchdog, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "TagTrackerSetup"

        def log_message(self, format, *args):  # pylint: disable=redefined-builtin
            pass  # quiet

        def _send(self, status: int, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data: dict):
            self._send(status, json.dumps(data).encode("utf-8"), "application/json")

        def _trusted(self) -> bool:
            # Only this machine's browser, on this page: guards against other
            # web pages (or DNS rebinding) reaching the server.
            if self.headers.get("Host") not in allowed_hosts:
                return False
            origin = self.headers.get("Origin")
            return origin is None or origin in allowed_origins

        def do_GET(self):  # pylint: disable=invalid-name
            if not self._trusted():
                return self._send(403, b"Forbidden", "text/plain")
            watchdog.heard()
            path = self.path.split("?")[0]
            if path in ("/", "/config_sites.html"):
                with open(PAGE, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path == "/api/state":
                try:
                    return self._json(200, manager.state())
                except Exception as e:  # pylint: disable=broad-exception-caught
                    return self._json(500, {"error": f"{type(e).__name__}: {e}"})
            return self._send(404, b"Not found", "text/plain")

        def do_POST(self):  # pylint: disable=invalid-name
            if not self._trusted():
                return self._send(403, b"Forbidden", "text/plain")
            path = self.path.split("?")[0]
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if path == "/api/ping":
                watchdog.heard()
                return self._json(200, {"ok": True})
            if path == "/api/bye":
                watchdog.bye()
                return self._json(200, {"ok": True})
            watchdog.heard()
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._json(415, {"error": "Expected JSON."})
            actions = {
                "/api/save": manager.save,
                "/api/archive": manager.archive,
                "/api/restore": manager.restore,
                "/api/active": manager.set_active,
            }
            if path not in actions:
                return self._send(404, b"Not found", "text/plain")
            try:
                body = json.loads(raw or b"{}")
                return self._json(200, actions[path](body if isinstance(body, dict) else {}))
            except ApiError as e:
                return self._json(e.args[0], {"error": e.args[1]})
            except ValueError:
                return self._json(400, {"error": "Bad JSON."})
            except Exception as e:  # pylint: disable=broad-exception-caught
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})

    return Handler


def bind(first_port: int):
    """A server on the first free port from first_port."""
    for port in range(first_port, first_port + PORTS_TO_TRY):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), None)
            return server, port
        except OSError:
            continue
    raise SystemExit(f"No free port from {first_port} to {first_port + PORTS_TO_TRY - 1}.")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="TagTracker set-up (site config manager)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="first port to try")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser")
    parser.add_argument(
        "--local-config",
        default=os.path.join(sc.PROGRAM_FOLDER, "client_local_config.py"),
        help="organization config file (default: client_local_config.py)",
    )
    args = parser.parse_args(argv)

    # Relative folders in the configs are from where TagTracker runs.
    os.chdir(sc.PROGRAM_FOLDER)

    server, port = bind(args.port)
    manager = Manager(os.path.abspath(args.local_config))
    watchdog = Watchdog()
    server.RequestHandlerClass = make_handler(manager, watchdog, port)
    server.daemon_threads = True

    def watch():
        while not watchdog.should_stop():
            time.sleep(2)
        print("No set-up page open; stopping.")
        server.shutdown()

    threading.Thread(target=watch, daemon=True).start()

    url = f"http://127.0.0.1:{port}/"
    print(f"TagTracker set-up is at {url}")
    print("Close the page (or press Ctrl+C here) to stop.")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # pylint: disable=broad-exception-caught
            print("Couldn't open a browser; open the address above.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
