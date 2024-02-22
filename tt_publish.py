"""TagTracker by Julias Hocking.

Report & data publishing functions for tagtracker

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
import pathlib

from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
from tt_time import VTime
import tt_util as ut
from tt_trackerday import TrackerDay
import tt_datafile as df
import tt_printer as pr
import tt_reports as rep
import tt_audit_report as aud

import tt_conf as cfg


class Publisher:
    """Keep track of publishing activity."""

    def __init__(self, destination: str, frequency: int) -> None:
        self.last_publish = "00:00"
        self.able_to_publish = True
        self.frequency = frequency
        self.destination = destination
        if not os.path.exists(destination):
            self.able_to_publish = False
            pr.iprint()
            pr.iprint(
                f"Publication folder '{cfg.REPORTS_FOLDER}' not found, "
                "will not try to Publish",
                style=cfg.ERROR_STYLE,
            )

    def publish(self, day: TrackerDay, as_of_when: str = "") -> None:
        """Publish."""
        if not self.able_to_publish:
            return
        if not self.publish_datafile(day, self.destination):
            pr.iprint("ERROR PUBLISHING DATAFILE", style=cfg.ERROR_STYLE)
            pr.iprint("REPORT PUBLISHING TURNED OFF", style=cfg.ERROR_STYLE)
            self.able_to_publish = False
            return

        self.publish_reports(day, [as_of_when])
        self.last_publish = VTime("now")

    def maybe_publish(self, day: TrackerDay, as_of_when: str = "") -> bool:
        """Maybe publish.  Return T if did a publish."""
        if not self.able_to_publish:
            return
        timenow = VTime("now")
        time_since_last = ut.time_int(timenow) - ut.time_int(self.last_publish)
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
        aud.audit_report(day, args)
        pr.set_output()

    def publish_datafile(self, day: TrackerDay, destination: str) -> bool:
        """Publish a copy of today's datafile.
        Returns False if failed.
        """
        if not self.able_to_publish:
            return
        filepath = df.datafile_name(destination, day.date)
        if not filepath:
            return False
        result = df.write_datafile(filepath, day)
        if not result:
            return False
        # Now save a copy to "latest.dat" in the same folder
        latestpath = f"{pathlib.Path(filepath).parent}/latest.dat"
        return df.write_datafile(latestpath, day)

    def publish_city_report(
        self, day: TrackerDay, as_of_when: MaybeTime = "now"
    ) -> None:
        """Publish a report for daily insight to the City."""
        if not self.able_to_publish:
            return
        as_of_when: VTime = VTime(as_of_when)
        fullfn = os.path.join(cfg.REPORTS_FOLDER, "city.txt")
        if not pr.set_output(fullfn):
            return
        pr.iprint(f"Overall valet report for {day.date}")
        pr.iprint(f"Generated {ut.date_str('today')} {ut.get_time()}")

        rep.day_end_report(day, [as_of_when])
        pr.iprint()
        rep.busyness_report(day, [as_of_when])
        pr.iprint()
        rep.busy_graph(day, as_of_when=as_of_when)
        pr.iprint()
        rep.fullness_graph(day, as_of_when=as_of_when)
        pr.iprint()
        rep.full_chart(day, as_of_when=as_of_when)
        pr.set_output()

    def publish_reports(self, day: TrackerDay, args: list = None) -> None:
        """Publish reports to the PUBLISH directory."""
        if not self.able_to_publish:
            return
        as_of_when = (args + [None])[0]
        if not as_of_when:
            as_of_when = "now"
        as_of_when: VTime = VTime(as_of_when)
        self.publish_audit(day, [as_of_when])
        self.publish_city_report(day, as_of_when=as_of_when)

        fn = "day_end.txt"
        day_end_fn = os.path.join(cfg.REPORTS_FOLDER, fn)
        if not pr.set_output(day_end_fn):
            return

        pr.iprint(ut.date_str(day.date, long_date=True))
        pr.iprint(f"Report generated {ut.date_str('today')} {VTime('now')}")
        rep.day_end_report(day, [as_of_when])
        pr.set_output()
