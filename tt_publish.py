"""TagTracker by Julias Hocking.

Report & data publishing functions for tagtracker

Copyright (C) 2023 Julias Hocking

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


from tt_globals import *  # pylint:disable=unused-wildcard-import,wildcard-import
import tt_util as ut
import tt_event
import tt_trackerday as td
import tt_printer as pr
import tt_reports as rep

import tt_conf as cfg


def publish_audit(day: td.TrackerDay, args: list[str]) -> None:
    """Publish the audit report."""
    fn = "audit.txt"
    fullfn = os.path.join(cfg.REPORTS_FOLDER, fn)
    pr.set_output(fullfn)
    rep.audit_report(day, args)
    pr.set_output()


def publish_city_report(day: td.TrackerDay, as_of_when: str = "") -> None:
    """Publish a report for daily insight to the City."""
    as_of_when = as_of_when if as_of_when else ut.get_time()
    fullfn = os.path.join(cfg.REPORTS_FOLDER, "city.txt")
    pr.set_output(fullfn)
    rep.day_end_report(day, [as_of_when])
    pr.iprint()
    rep.more_stats_report(day, [as_of_when])
    pr.iprint()
    rep.busy_graph(day, as_of_when=as_of_when)
    pr.iprint()
    rep.fullness_graph(day, as_of_when=as_of_when)
    pr.iprint()
    rep.full_chart(day, as_of_when=as_of_when)
    pr.set_output()


def publish_reports(day: td.TrackerDay, args: list = None) -> None:
    """Publish reports to the PUBLISH directory."""
    as_of_when = (args + [None])[0]
    if not as_of_when:
        as_of_when = ut.get_time()

    publish_audit(day, [as_of_when])
    publish_city_report(day, as_of_when=as_of_when)

    fn = "fullness.txt"
    fullfn = os.path.join(cfg.REPORTS_FOLDER, fn)
    pr.set_output(fullfn)
    pr.iprint(ut.long_date(day.date))
    pr.iprint(f"Report generated {ut.get_date()} {ut.get_time()}")
    rep.highwater_report(tt_event.calc_events(day))
    pr.iprint()
    rep.fullness_graph(day, as_of_when)
    pr.set_output()

    fn = "busyness.txt"
    busyfn = os.path.join(cfg.REPORTS_FOLDER, fn)
    pr.set_output(busyfn)
    pr.iprint(ut.long_date(day.date))
    pr.iprint(f"Report generated {ut.get_date()} {ut.get_time()}")
    rep.inout_summary(day, as_of_when)
    pr.iprint()
    rep.busy_graph(day, as_of_when)
    pr.set_output()

    fn = "activity.txt"
    activity_fn = os.path.join(cfg.REPORTS_FOLDER, fn)
    pr.set_output(activity_fn)
    pr.iprint(ut.long_date(day.date))
    pr.iprint(f"Report generated {ut.get_date()} {ut.get_time()}")
    rep.full_chart(day, as_of_when=as_of_when)
    pr.set_output()

    fn = "day_end.txt"
    day_end_fn = os.path.join(cfg.REPORTS_FOLDER, fn)
    pr.set_output(day_end_fn)
    pr.iprint(ut.long_date(day.date))
    pr.iprint(f"Report generated {ut.get_date()} {ut.get_time()}")
    rep.day_end_report(day, [as_of_when])
    pr.set_output()

    fn = "dataform.txt"
    dataform_fn = os.path.join(cfg.REPORTS_FOLDER, fn)
    pr.set_output(dataform_fn)
    pr.iprint(ut.long_date(day.date))
    pr.iprint(f"Report generated {ut.get_date()} {ut.get_time()}")
    rep.dataform_report(day, [])
    pr.set_output()
