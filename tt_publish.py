"""TagTracker by Julias Hocking.

Report & data publishing functions for tagtracker

Copyright (C) 2023-2024 Julias Hocking & Todd Glover

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
#import pathlib

import common.tt_constants as k
from common.tt_time import VTime
import common.tt_util as ut
from common.tt_trackerday import TrackerDay
import tt_datafile as df
import tt_printer as pr
import tt_reports as rep
import tt_audit_report as aud

import client_base_config as cfg


class Publisher:
    """Keep track of publishing activity."""

    def __init__(self, destination: str, frequency: int) -> None:
        """Set up the Publisher object."""
        # If there's no reports folder set, just disable publishing
        if not frequency:
            self.able_to_publish = False
            return

        if not destination:
            self.able_to_publish = False
            pr.iprint()
            pr.iprint(
                "No reports folder configured, not publishing static reports.",
                style=k.HIGHLIGHT_STYLE,
            )
            return
        self.last_publish = "00:00"
        self.able_to_publish = True
        self.frequency = frequency
        self.destination = destination
        if not ut.writable_dir(destination):
            self.able_to_publish = False
            pr.iprint()
            pr.iprint(
                f"Publication folder '{cfg.REPORTS_FOLDER}' missing or not writable, "
                "publication disabled.",
                style=k.ERROR_STYLE,
            )

    def publish(self, day: TrackerDay, as_of_when: str = "") -> None:
        """Publish."""
        ut.squawk(f"Entering .publish with {self.able_to_publish=}",cfg.DEBUG)
        if not self.able_to_publish:
            return
        ut.squawk(f"{type(day)=}, {day.date=}",cfg.DEBUG)
        if not self.publish_datafile(day, self.destination):
            pr.iprint("ERROR PUBLISHING DATAFILE", style=k.ERROR_STYLE)
            pr.iprint("REPORT PUBLISHING TURNED OFF", style=k.ERROR_STYLE)
            self.able_to_publish = False
            return

        self.publish_reports(day, [as_of_when])
        self.last_publish = VTime("now")

    def maybe_publish(self, day: TrackerDay, as_of_when: str = "") -> bool:
        """Maybe publish.  Return T if did a publish."""
        if not self.able_to_publish:
            return
        timenow:VTime = VTime("now")
        time_since_last = timenow.num - VTime(self.last_publish).num
        if time_since_last >= self.frequency:
            self.publish(day, as_of_when)

    def publish_audit(self, day: TrackerDay, args: list[str]) -> None:
        """Publish the audit report."""
        if not self.able_to_publish:
            return
        fn = "audit.txt"
        fullfn = os.path.join(cfg.REPORTS_FOLDER, fn)
        if not pr.set_output(fullfn):
            return
        aud.audit_report(day, args, include_returns=True,retired_tag_str="<>")
        pr.set_output()

    def publish_datafile(self, day: TrackerDay, folder: str) -> bool:
        """Publish a copy of today's datafile.
        Returns False if failed.
        """
        if not self.able_to_publish:
            return
        filepath = df.datafile_name(folder, day.date)
        ut.squawk(f"Preparing to save to  {filepath=} based on {folder=} and {day.date=}",cfg.DEBUG)
        if not filepath:
            return False
        return day.save_to_file(filepath)

    def publish_reports(self, day: TrackerDay, args: list = None,mention:bool=False) -> None:
        """Publish reports to the PUBLISH directory."""
        if not self.able_to_publish:
            return
        as_of_when = (args + [None])[0]
        as_of_when: VTime = VTime(as_of_when or "now")
        if mention:
            pr.iprint(f"Publishing a copy of reports to {cfg.REPORTS_FOLDER}.",
                      style=k.SUBTITLE_STYLE)
        self.publish_audit(day, [as_of_when])

        fn = "summary.txt"
        day_end_fn = os.path.join(cfg.REPORTS_FOLDER, fn)
        if not pr.set_output(day_end_fn):
            return

        pr.iprint(ut.date_str(day.date, long_date=True))
        pr.iprint(f"Report generated {ut.date_str('today')} {VTime('now')}")
        rep.summary_report(day, [as_of_when])
        pr.set_output()
