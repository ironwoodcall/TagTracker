#!/usr/bin/env python3
"""Estimate how many more bikes to expect.

CGI parameters:
    bikes_so_far: current bike count (as of now).
    opening_time: service opening time for today (HHMM or HH:MM).
    closing_time: service closing time for today (HHMM or HH:MM).
    estimation_type: optional; values include
        "standard" (default)
        "verbose" (detailed output),
        "quick" (skip Random Forest), and
        "schedule" (REC model only; requires opening and closing times).
    what: alias for estimation_type.

Estimates assume the request is for today at "now" and rely on the provided opening and closing times.

Copyright (C) 2023-2025 Julias Hocking & Todd Glover

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

import urllib.request
import urllib.parse
import traceback as _tb
from web_estimator_calibration import (
    load_calibration as _calib_load,
    bin_label as _calib_bin_label,
    residual_band as _calib_residual_band,
    probability_lookup as _calib_probability,
)
from web_estimator_selection import dispatch_select as _select_dispatch
import os
import sys
import time
from typing import Optional

sys.path.append("../")
sys.path.append("./")

# pylint: disable=wrong-import-position
import web_base_config as wcfg
import web_common as cc
import common.tt_util as ut
from common.tt_time import VTime
import common.tt_dbutil as db

# import client_base_config as cfg
import web.web_estimator_rf as rf
from web_estimator_models import SimpleModel as SimpleModelNew, LRModel as LRModelNew
from web_estimator_render import render_tables as _render_tables

# pylint: enable=wrong-import-position

# These are model states
INCOMPLETE = "incomplete"  # initialized but not ready to use
READY = "ready"  # model is ready to use
OK = "ok"  # model has been used to create a guess OK
ERROR = "error"  # the model is unusable, in an error state


# New estimator that provides a concise estimation table
class Estimator:
    """New estimator producing a compact table of key metrics and probabilities.

    Outputs four items:
      - Further bikes today (remainder)
      - Max full today (count)
      - Max full today time (HH:MM)
      - Events in the next hour (ins+outs)
    """

    orgsite_id = 1  # FIXME: hardwired orgsite (kept consistent with old)

    # --- Model names (centralized) ---
    # NB: These codes must exactly match the codes used in the calibration script
    MODEL_SM = "SM"
    MODEL_LR = "LR"
    MODEL_REC = "REC"
    MODEL_RF = "RF"

    MODEL_LONG_NAMES = {
        MODEL_SM: "Similar-Day Median",
        MODEL_LR: "Linear Regression",
        MODEL_REC: "Schedule-Only (Recent Days)",
        MODEL_RF: "Random Forest",
    }

    # Measure label strings (edit here to change table text)
    MEAS_ACTIVITY_TEMPLATE = "Activity, now to {end_time}"
    MEAS_FURTHER = "Further bikes"
    MEAS_TIME_MAX = "Time most bikes onsite"
    MEAS_MAX = "Most bikes onsite"

    # Table headers (centralized)
    HEADER_MIXED = ["Measure", "Value", "Range (90%)", "Probability", "Model"]
    HEADER_FULL = ["Measure", "Value", "Range (90%)", "Probability", ""]

    def _activity_label(self, t_end: VTime) -> str:
        return self.MEAS_ACTIVITY_TEMPLATE.format(end_time=t_end.tidy)

    def _further_measure_label(self, further_val: int | float | str) -> str:
        """Return the dynamic label for the 'further bikes' measure."""
        total = int(self.bikes_so_far)
        try:
            addl = int(round(float(str(further_val))))
            total += addl
        except Exception:
            # Keep current bikes-only total if parsing fails.
            pass
        base = getattr(self, "MEAS_FURTHER", "Further bikes")
        return f"{base} (for day total {total})"

    # Static cache for calibration JSON
    _CALIB_CACHE = None

    def __init__(
        self,
        bikes_so_far: str = "",
        opening_time: str = "",
        closing_time: str = "",
        estimation_type: str = "",
    ) -> None:
        self.state = INCOMPLETE
        self.error = ""
        self.database = None
        self.estimation_type = (estimation_type or "").strip().lower()
        self.verbose = bool(self.estimation_type == "verbose")
        raw_open_param = (opening_time or "").strip()
        raw_close_param = (closing_time or "").strip()
        # has_open_param = bool(raw_open_param)
        # has_close_param = bool(raw_close_param)

        # if self.estimation_type == "schedule" and not (
        #     has_open_param and has_close_param
        # ):
        #     self.error = "Please provide both opening_time and closing_time when estimation_type=schedule."
        #     self.state = ERROR
        #     return

        self._allowed_models = {
            self.MODEL_SM,
            self.MODEL_LR,
            self.MODEL_REC,
            self.MODEL_RF,
        }
        if self.estimation_type == "schedule":
            self._allowed_models = {self.MODEL_REC}
        elif self.estimation_type == "quick":
            self._allowed_models = {self.MODEL_SM, self.MODEL_LR, self.MODEL_REC}

        DBFILE = wcfg.DB_FILENAME
        if not os.path.exists(DBFILE):
            self.error = "Database not found"
            self.state = ERROR
            return
        self.database = db.db_connect(DBFILE)

        bikes_input = str(bikes_so_far or "").strip()
        if self.estimation_type != "schedule":
            if not bikes_input:
                fetched = self._bikes_right_now()
                bikes_input = str(fetched).strip() if fetched is not None else ""
            if not bikes_input or not bikes_input.isdigit():
                self.error = "Missing or bad bikes_so_far parameter."
                self.state = ERROR
                return
        else:
            if bikes_input and not bikes_input.isdigit():
                self.error = "Bad bikes_so_far parameter."
                self.state = ERROR
                return
            if not bikes_input:
                bikes_input = "0"
        self.bikes_so_far = int(bikes_input)

        self.as_of_when = VTime("now")
        if not self.as_of_when:
            self.error = "Bad current time."
            self.state = ERROR
            return

        today_date = ut.date_str("today")
        self.dow = ut.dow_int(today_date)

        opening_candidate = raw_open_param.strip()
        closing_candidate = raw_close_param.strip()
        if not opening_candidate or not closing_candidate:
            db_open, db_close = self._fetch_today_schedule()
            if not opening_candidate and db_open:
                opening_candidate = str(db_open).strip()
            if not closing_candidate and db_close:
                closing_candidate = str(db_close).strip()

        if not opening_candidate or not closing_candidate:
            self.error = "Unable to determine opening_time and closing_time for today."
            self.state = ERROR
            return

        self.time_open = VTime(opening_candidate)
        self.time_closed = VTime(closing_candidate)
        if not self.time_open:
            self.error = f"Invalid opening_time '{opening_candidate}'."
            self.state = ERROR
            return
        if not self.time_closed:
            self.error = f"Invalid closing_time '{closing_candidate}'."
            self.state = ERROR
            return

        # Data buffers
        self.similar_dates: list[str] = []
        self.befores: list[int] = []
        self.afters: list[int] = []
        # Configurable matching and trimming
        self.VARIANCE = getattr(wcfg, "EST_VARIANCE", 15)
        self.Z_CUTOFF = getattr(wcfg, "EST_Z_CUTOFF", 2.5)
        self.MATCH_OPEN_TOL = int(getattr(wcfg, "EST_MATCH_OPEN_TOL", 15))
        self.MATCH_CLOSE_TOL = int(getattr(wcfg, "EST_MATCH_CLOSE_TOL", 15))
        self._match_note = ""
        # Load calibration once if configured
        self._calib = None
        self._calib_bins = None
        self._calib_best = None
        self._calib_debug: list[str] = []
        self._maybe_load_calibration()
        self._fetch_raw_data()
        if self.state == ERROR:
            return

        # Build SimpleModel for remainder
        self.simple_model = SimpleModelNew()
        self.simple_model.create_model(
            self.similar_dates, self.befores, self.afters, self.VARIANCE, self.Z_CUTOFF
        )
        self.simple_model.guess(self.bikes_so_far)

        self.table_rows: list[tuple[str, str, str]] = []

    def _bikes_right_now(self) -> int:
        today = ut.date_str("today")
        cursor = self.database.cursor()
        day_id = db.fetch_day_id(
            cursor=cursor, date=today, maybe_orgsite_id=self.orgsite_id
        )
        if not day_id:
            return 0
        rows = db.db_fetch(
            self.database,
            f"select count(time_in) as cnt from visit where day_id = {day_id} and time_in > ''",
            ["cnt"],
        )
        return int(rows[0].cnt) if rows else 0

    def _fetch_today_schedule(self) -> tuple[str | None, str | None]:
        today = ut.date_str("today")
        cursor = self.database.cursor()
        day_id = db.fetch_day_id(
            cursor=cursor, date=today, maybe_orgsite_id=self.orgsite_id
        )
        if not day_id:
            return None, None
        rows = db.db_fetch(
            self.database,
            f"SELECT time_open, time_closed FROM day WHERE id = {day_id}",
            ["time_open", "time_closed"],
        )
        if rows:
            return rows[0].time_open, rows[0].time_closed
        return None, None

    def _time_bounds(self, base: VTime, tol_min: int) -> tuple[str, str]:
        base_num = base.num if base and base.num is not None else 0
        lo = max(0, base_num - max(0, int(tol_min)))
        hi = min(24 * 60, base_num + max(0, int(tol_min)))
        return VTime(lo), VTime(hi)

    def _sql_str(self, use_open: bool, use_close: bool) -> str:
        today = ut.date_str("today")
        where_parts = [
            f"D.orgsite_id = {self.orgsite_id}",
            f"D.date != '{today}'",
        ]
        if use_open:
            lo, hi = self._time_bounds(self.time_open, self.MATCH_OPEN_TOL)
            where_parts.append(f"D.time_open BETWEEN '{lo}' AND '{hi}'")
        if use_close:
            lo, hi = self._time_bounds(self.time_closed, self.MATCH_CLOSE_TOL)
            where_parts.append(f"D.time_closed BETWEEN '{lo}' AND '{hi}'")
        where_sql = " AND\n              ".join(where_parts)
        return f"""
            SELECT
                D.date,
                SUM(CASE WHEN V.time_in <= '{self.as_of_when}' THEN 1 ELSE 0 END) AS befores,
                SUM(CASE WHEN V.time_in > '{self.as_of_when}' THEN 1 ELSE 0 END) AS afters
            FROM DAY D
            JOIN VISIT V ON D.id = V.day_id
            WHERE {where_sql}
            GROUP BY D.date;
        """

    def _maybe_load_calibration(self) -> None:
        if Estimator._CALIB_CACHE is not None:
            self._calib = Estimator._CALIB_CACHE
            self._calib_debug.append("calibration: using cached JSON")
        else:
            calib, bins, best, dbg = _calib_load(wcfg, __file__)
            self._calib_debug.extend(dbg)
            if calib:
                Estimator._CALIB_CACHE = calib
                self._calib = calib
                self._calib_bins = bins
                self._calib_best = best
        # Parse bins for quick lookup
        if self._calib and isinstance(self._calib.get("time_bins", None), list):
            bins = []
            for s in self._calib["time_bins"]:
                try:
                    a, b = s.split("-", 1)
                    lo = float(a)
                    hi = float(b)
                    bins.append((lo, hi, s))
                except Exception:
                    continue
            self._calib_bins = bins or None
            self._calib_best = self._calib.get("best_model", None)

    def _bin_label(self, frac_elapsed: float) -> str | None:
        return _calib_bin_label(self._calib_bins, frac_elapsed)

    def _calib_residual_band(
        self, model: str, measure: str, frac_elapsed: float
    ) -> tuple[float, float] | None:
        return _calib_residual_band(
            self._calib, self._calib_bins, model, measure, frac_elapsed
        )

    def _fetch_raw_data(self) -> None:
        # Try: match both opening and closing times within tolerance
        sql = self._sql_str(use_open=True, use_close=True)
        data_rows = db.db_fetch(self.database, sql, ["date", "before", "after"])
        if data_rows:
            self._match_note = "matched on open+close"
        # Backoff 1: match closing time only
        if not data_rows:
            sql = self._sql_str(use_open=False, use_close=True)
            data_rows = db.db_fetch(self.database, sql, ["date", "before", "after"])
            if data_rows:
                self._match_note = "matched on close only"
        # Backoff 2: no time constraints (orgsite only)
        if not data_rows:
            sql = self._sql_str(use_open=False, use_close=False)
            data_rows = db.db_fetch(self.database, sql, ["date", "before", "after"])
            if data_rows:
                self._match_note = "matched without time filters"
        if not data_rows:
            self.error = "no data returned from database."
            self.state = ERROR
            return
        self.befores = [int(r.before) for r in data_rows]
        self.afters = [int(r.after) for r in data_rows]
        self.similar_dates = [r.date for r in data_rows]

    def _matched_dates(self) -> list[str]:
        out: list[str] = []
        for i, b in enumerate(self.befores):
            if abs(int(b) - int(self.bikes_so_far)) <= self.VARIANCE:
                out.append(self.similar_dates[i])
        return out

    def _visits_for_date(self, date_str: str) -> list[tuple[VTime, Optional[VTime]]]:
        day_id = db.fetch_day_id(
            cursor=self.database.cursor(),
            date=date_str,
            maybe_orgsite_id=self.orgsite_id,
        )
        if not day_id:
            return []
        rows = db.db_fetch(
            self.database,
            f"SELECT time_in, time_out FROM VISIT WHERE day_id = {day_id} ORDER BY time_in",
            ["time_in", "time_out"],
        )
        out = []
        for r in rows:
            tin = VTime(r.time_in)
            tout = VTime(r.time_out) if r.time_out else None
            out.append((tin, tout))
        return out

    @staticmethod
    def _counts_for_time(
        visits: list[tuple[VTime, Optional[VTime]]], t: VTime
    ) -> tuple[int, int, int, int, int]:
        t_end = VTime(min(t.num + 60, 24 * 60))
        before_ins = sum(1 for tin, _ in visits if tin and tin <= t)
        after_ins = sum(1 for tin, _ in visits if tin and tin > t)
        outs_up_to_t = sum(1 for _, tout in visits if tout and tout <= t)
        ins_next = sum(1 for tin, _ in visits if tin and t < tin <= t_end)
        outs_next = sum(1 for _, tout in visits if tout and t < tout <= t_end)
        return before_ins, after_ins, outs_up_to_t, ins_next, outs_next

    @staticmethod
    def _peak_future_occupancy(
        visits: list[tuple[VTime, Optional[VTime]]], t: VTime, close: VTime
    ) -> tuple[int, VTime]:
        occ_now = sum(1 for tin, _ in visits if tin and tin <= t) - sum(
            1 for _, tout in visits if tout and tout <= t
        )
        events: list[tuple[int, int]] = []
        for tin, tout in visits:
            if tin and t < tin <= close:
                events.append((int(VTime(tin).num), +1))
            if tout and t < tout <= close:
                events.append((int(VTime(tout).num), -1))
        events.sort(key=lambda x: (x[0], -x[1]))
        peak = occ_now
        peak_time = t
        occ = occ_now
        for tm, delta in events:
            occ += delta
            if occ > peak:
                peak = occ
                peak_time = VTime(tm)
        return peak, peak_time

    @staticmethod
    def _peak_all_day_occupancy(
        visits: list[tuple[VTime, Optional[VTime]]],
    ) -> tuple[int, VTime]:
        """Compute the maximum occupancy and when it occurs over the entire day.

        Uses all visit events (ins as +1, outs as -1) from the day's data
        without restricting to times after now. Assumes occupancy is zero
        before the first event of the day.
        """
        events: list[tuple[int, int]] = []
        for tin, tout in visits:
            if tin:
                events.append((int(VTime(tin).num), +1))
            if tout:
                events.append((int(VTime(tout).num), -1))
        if not events:
            return 0, VTime("00:00")
        events.sort(key=lambda x: (x[0], -x[1]))
        occ = 0
        peak = 0
        peak_time = VTime(events[0][0])
        for tm, delta in events:
            occ += delta
            if occ > peak:
                peak = occ
                peak_time = VTime(tm)
        return peak, peak_time

    def _confidence_level(self, n: int, frac_elapsed: float) -> str:
        cfg = getattr(wcfg, "EST_CONF_THRESHOLDS", None)
        high = {"min_n": 12, "min_frac": 0.4}
        med = {"min_n": 8, "min_frac": 0.2}
        if isinstance(cfg, dict):
            high = cfg.get("High", high)
            med = cfg.get("Medium", med)
        if n >= int(high.get("min_n", 12)) and frac_elapsed >= float(
            high.get("min_frac", 0.4)
        ):
            return "High"
        if n >= int(med.get("min_n", 8)) and frac_elapsed >= float(
            med.get("min_frac", 0.2)
        ):
            return "Medium"
        return "Low"

    def _band(self, level: str, kind: str) -> int:
        # kind in {remainder, activity, peak, peaktime}
        bands = getattr(wcfg, "EST_BANDS", None)
        default = {
            "remainder": {"High": 10, "Medium": 18, "Low": 30},
            "activity": {"High": 8, "Medium": 12, "Low": 16},
            "peak": {"High": 10, "Medium": 15, "Low": 25},
            "peaktime": {"High": 20, "Medium": 30, "Low": 60},
        }
        table = default.get(kind, {})
        if isinstance(bands, dict):
            table = bands.get(kind, table)
        return int(table.get(level, 0) or 0)

    def _band_scaled(self, base: int, n: int, frac_elapsed: float, kind: str) -> int:
        """Scale a base band width by day progress and sample size.

        - Earlier in the day -> wider margins; later -> tighter margins.
        - More matched days -> tighter margins (sqrt-law capped).
        Configurable via optional wcfg values:
            EST_BAND_N_REF, EST_BAND_MIN_SCALE, EST_BAND_MAX_SCALE
        """
        try:
            n_ref = int(getattr(wcfg, "EST_BAND_N_REF", 10))
        except Exception:
            n_ref = 10
        try:
            min_scale = float(getattr(wcfg, "EST_BAND_MIN_SCALE", 0.5))
            max_scale = float(getattr(wcfg, "EST_BAND_MAX_SCALE", 1.25))
        except Exception:
            min_scale, max_scale = 0.5, 1.25

        # Progress factor: 1.3 at open, 0.8 at close (linear)
        pf = 1.30 - 0.50 * max(0.0, min(1.0, frac_elapsed))
        # Sample-size factor: sqrt scaling around n_ref; capped to reasonable bounds
        nn = max(1, int(n))
        import math

        sf = math.sqrt(n_ref / nn)
        sf = max(0.70, min(1.15, sf))

        scale = max(min_scale, min(max_scale, pf * sf))
        return max(0, int(round(base * scale)))

    @staticmethod
    def _percentiles(
        values: list[int], p_lo: float = 0.05, p_hi: float = 0.95
    ) -> tuple[int, int]:
        """Compute (low, high) empirical percentiles as integers without numpy."""
        vals = sorted(int(v) for v in values)
        n = len(vals)
        if n == 0:
            return None, None  # type: ignore[return-value]
        if n == 1:
            return vals[0], vals[0]

        def q_at(p: float) -> int:
            p = max(0.0, min(1.0, float(p)))
            pos = p * (n - 1)
            i = int(pos)
            frac = pos - i
            if i >= n - 1:
                return vals[-1]
            return int(round(vals[i] * (1 - frac) + vals[i + 1] * frac))

        return q_at(p_lo), q_at(p_hi)

    @staticmethod
    def _clamp01(x: float) -> float:
        return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

    def _smooth_conf(
        self,
        n: int,
        frac_elapsed: float,
        spread: float | None,
        denom: float | None,
        n_ref: int = 12,
    ) -> float:
        """Compute the heuristic confidence score (0-100).

        - Time-of-day factor pf grows linearly from 0.3 at open to 1.0 at close.
        - Sample-size factor nf grows with sqrt(n/n_ref), clipped to [0,1].
        - Variation factor vf = 1 - clamp(spread/denom), where denom is a
          scale for the measure (e.g., median or day span). If spread/denom
          is small, vf is near 1 (high confidence); if large, vf is near 0.
        Returns a score in [0, 100].
        """
        # Time-of-day
        pf = 0.30 + 0.70 * self._clamp01(frac_elapsed)
        # Sample size
        try:
            nf = (max(0, int(n)) / max(1, int(n_ref))) ** 0.5
        except Exception:
            nf = 0.0
        nf = self._clamp01(nf)
        # Variation
        if spread is None or denom is None or denom <= 0:
            vf = 0.5  # neutral if unknown
        else:
            vf = 1.0 - self._clamp01(float(spread) / float(denom))
        # Blend
        score = 100.0 * (0.40 * pf + 0.30 * nf + 0.30 * vf)
        score = max(0.0, min(100.0, score))
        return score

    def guess(self) -> None:
        """Top-level coordinator for estimate generation."""
        if self.state == ERROR:
            return

        # --- Time window & progress ---
        open_num, close_num, total_span, frac_elapsed = self._elapsed_fraction()
        t_end = self._clamp_time_plus(self.as_of_when, minutes=60)

        # --- Cohorts & simple remainder baseline ---
        matched = self._matched_dates()
        n = len(matched)

        remainder = self._prepare_remainder_default()

        # --- Stats over matched & similar cohorts ---
        nxh_acts, peaks = self._collect_stats_for_dates(matched)
        all_acts, all_peaks, all_ptimes = self._collect_all_stats_for_similar()

        # --- Point estimates from matched or fallbacks ---
        nxh_activity, peak_val, peak_time = self._point_estimates_from(
            matched, nxh_acts, peaks
        )

        # --- Confidence level & base bands (scaled later per model) ---
        level = self._confidence_level(n, frac_elapsed)
        rem_band, act_band, peak_band, ptime_band = self._base_bands(
            level, n, frac_elapsed
        )

        # --- Empirical 90% ranges from samples (Simple) ---
        (rem_lo, rem_hi), (act_lo, act_hi), (pk_lo, pk_hi), (ptime_lo, ptime_hi) = (
            self._simple_percentile_ranges(nxh_acts, peaks)
        )

        # --- Smooth confidences (Simple) ---
        conf_rem, conf_act, conf_pk, conf_pt = self._simple_confidences(
            remainder,
            nxh_activity,
            peak_val,
            (ptime_lo, ptime_hi),
            total_span,
            (rem_lo, rem_hi),
            (act_lo, act_hi),
            (pk_lo, pk_hi),
            n,
            frac_elapsed,
        )

        # --- SIMPLE rows (with calibration applied) ---
        simple_rows = []
        if self._model_enabled(self.MODEL_SM):
            simple_rows = self._build_simple_rows(
                t_end,
                nxh_activity,
                remainder,
                peak_time,
                peak_val,
                (act_band, rem_band, peak_band, ptime_band),
                (act_lo, act_hi),
                (rem_lo, rem_hi),
                (pk_lo, pk_hi),
                (ptime_lo, ptime_hi),
                (conf_act, conf_rem, conf_pt, conf_pk),
                frac_elapsed,
            )

        # --- LINEAR REGRESSION rows (with calibration & residual ranges) ---
        lr_rows = []
        if self._model_enabled(self.MODEL_LR):
            lr_rows = self._build_lr_rows(
                t_end,
                remainder,
                nxh_activity,
                peak_val,
                peak_time,
                all_acts,
                all_peaks,
                (act_band, rem_band, peak_band, ptime_band),
                (act_lo, act_hi),
                (rem_lo, rem_hi),
                (pk_lo, pk_hi),
                (ptime_lo, ptime_hi),
                frac_elapsed,
            )

        # --- RECENT (schedule-only) rows (with calibration) ---
        rec_rows = []
        if self._model_enabled(self.MODEL_REC):
            rec_rows = self._build_recent_rows(
                t_end,
                remainder,
                nxh_activity,
                peak_val,
                peak_time,
                (act_band, rem_band, peak_band, ptime_band),
                frac_elapsed,
            )

        # --- RANDOM FOREST rows (if available; with calibration) ---
        rf_rows = []
        if self._model_enabled(self.MODEL_RF):
            rf_rows = self._build_rf_rows(
                t_end,
                remainder,
                nxh_activity,
                peak_val,
                peak_time,
                (act_band, rem_band, peak_band, ptime_band),
                (act_lo, act_hi),
                (rem_lo, rem_hi),
                (pk_lo, pk_hi),
                (ptime_lo, ptime_hi),
                frac_elapsed,
            )

        # --- Mixed selection across models per measure ---
        tables_by_model: dict[str, list[tuple[str, str, str, str, str]]] = {}
        if simple_rows:
            tables_by_model[self.MODEL_SM] = simple_rows
        if lr_rows:
            tables_by_model[self.MODEL_LR] = lr_rows
        if rec_rows:
            tables_by_model[self.MODEL_REC] = rec_rows
        if rf_rows:
            tables_by_model[self.MODEL_RF] = rf_rows

        if not tables_by_model:
            self.error = (
                "No estimation models were available for the requested estimation_type."
            )
            self.state = ERROR
            return

        mixed_rows, mixed_models, selected_by_model, selection_info = self._select_rows(
            t_end, tables_by_model, frac_elapsed, n
        )
        if self.estimation_type == "schedule":
            selection_info.insert(0, "estimation_type=schedule: REC model only")
        elif self.estimation_type == "quick":
            selection_info.insert(0, "estimation_type=quick: Random Forest skipped")
        self._selection_info = selection_info

        # --- Final table packaging (Mixed first) ---
        if self.estimation_type == "quick":
            self.tables = [
                ("Quick Best Guess Estimates", mixed_rows, None),
            ]
        else:
            self.tables = [
                ("Best Guess Estimates", mixed_rows, None),
            ]
        if simple_rows:
            self.tables.append(
                (
                    f"Estimation - {self.MODEL_LONG_NAMES[self.MODEL_SM]} Model",
                    simple_rows,
                    self.MODEL_SM,
                )
            )
        elif self._model_enabled(self.MODEL_SM):
            self.tables.append(
                (
                    f"Estimation - {self.MODEL_LONG_NAMES[self.MODEL_SM]} Model",
                    [("No estimates available", "", "", "--")],
                    None,
                )
            )
        if lr_rows:
            self.tables.append(
                (
                    f"Estimation - {self.MODEL_LONG_NAMES[self.MODEL_LR]} Model",
                    lr_rows,
                    self.MODEL_LR,
                )
            )
        elif self._model_enabled(self.MODEL_LR):
            self.tables.append(
                (
                    f"Estimation - {self.MODEL_LONG_NAMES[self.MODEL_LR]} Model",
                    [("No estimates available", "", "", "--")],
                    None,
                )
            )
        if rec_rows:
            self.tables.append(
                (
                    f"Estimation - {self.MODEL_LONG_NAMES[self.MODEL_REC]} Model",
                    rec_rows,
                    self.MODEL_REC,
                )
            )
        else:
            self.tables.append(
                (
                    f"Estimation - {self.MODEL_LONG_NAMES[self.MODEL_REC]} Model",
                    [("No estimates available", "", "", "--")],
                    None,
                )
            )
        if self._model_enabled(self.MODEL_RF):
            if rf_rows:
                self.tables.append(
                    (
                        f"Estimation - {self.MODEL_LONG_NAMES[self.MODEL_RF]} Model",
                        rf_rows,
                        self.MODEL_RF,
                    )
                )

        # Book-keeping
        self._mixed_models = mixed_models
        self._selected_by_model = selected_by_model

        # Legacy min/max for callers expecting prior API
        self.min = max(0, int(remainder) - rem_band)
        self.max = int(remainder) + rem_band
        self.state = OK

    def _model_enabled(self, model_code: str) -> bool:
        return model_code in self._allowed_models

    # =========================
    #         HELPERS
    # =========================

    def _elapsed_fraction(self) -> tuple[int, int, int, float]:
        open_num = (
            self.time_open.num
            if self.time_open and self.time_open.num is not None
            else 0
        )
        close_num = (
            self.time_closed.num
            if self.time_closed and self.time_closed.num is not None
            else 24 * 60
        )
        # Ensure positive span
        if close_num <= open_num:
            close_num = max(open_num + 60, 24 * 60)
        total_span = max(1, close_num - open_num)
        frac_elapsed = max(0.0, min(1.0, (self.as_of_when.num - open_num) / total_span))
        return open_num, close_num, total_span, frac_elapsed

    def _clamp_time_plus(self, t: "VTime", minutes: int) -> "VTime":
        return VTime(min(t.num + minutes, 24 * 60))

    def _prepare_remainder_default(self) -> int:
        remainder = None
        if getattr(self, "simple_model", None) and self.simple_model.state == OK:
            remainder = self.simple_model.median
        return int(remainder if remainder is not None else 0)

    def _collect_stats_for_dates(
        self, dates
    ) -> tuple[list[int], list[tuple[int, "VTime"]]]:
        nxh_acts: list[int] = []
        peaks: list[tuple[int, VTime]] = []
        for d in dates:
            vlist = self._visits_for_date(d)
            _b, _a, _outs_to_t, ins_nxh, outs_nxh = self._counts_for_time(
                vlist, self.as_of_when
            )
            nxh_acts.append(int(ins_nxh + outs_nxh))
            p, pt = self._peak_all_day_occupancy(vlist)
            peaks.append((int(p), pt))
        return nxh_acts, peaks

    def _collect_all_stats_for_similar(
        self,
    ) -> tuple[list[int], list[int], list["VTime"]]:
        all_acts: list[int] = []
        all_peaks: list[int] = []
        all_ptimes: list[VTime] = []
        for d in self.similar_dates:
            vlist = self._visits_for_date(d)
            _b2, _a2, _outs2, ins2, outs2 = self._counts_for_time(
                vlist, self.as_of_when
            )
            all_acts.append(int(ins2 + outs2))
            p2, pt2 = self._peak_all_day_occupancy(vlist)
            all_peaks.append(int(p2))
            all_ptimes.append(pt2)
        return all_acts, all_peaks, all_ptimes

    def _point_estimates_from(
        self, matched_dates, nxh_acts, peaks
    ) -> tuple[int, int, "VTime"]:
        import statistics

        nxh_activity = int(statistics.median(nxh_acts)) if nxh_acts else 0
        if peaks:
            peak_val = int(statistics.median([p for p, _ in peaks]))
            times = [pt.num for _p, pt in peaks]
            peak_time = VTime(int(statistics.median(times)))
        else:
            peak_val = self.bikes_so_far
            peak_time = self.as_of_when
        return nxh_activity, peak_val, peak_time

    def _base_bands(
        self, level: int, n: int, frac_elapsed: float
    ) -> tuple[int, int, int, int]:
        rem_band = self._band_scaled(
            self._band(level, "remainder"), n, frac_elapsed, "remainder"
        )
        act_band = self._band_scaled(
            self._band(level, "activity"), n, frac_elapsed, "activity"
        )
        peak_band = self._band_scaled(
            self._band(level, "peak"), n, frac_elapsed, "peak"
        )
        ptime_band = self._band_scaled(
            self._band(level, "peaktime"), n, frac_elapsed, "peaktime"
        )
        return rem_band, act_band, peak_band, ptime_band

    def _percentiles_or_none(self, data: list[int], lo: float, hi: float):
        if not data:
            return (None, None)
        return self._percentiles(data, lo, hi)

    def _simple_percentile_ranges(self, nxh_acts, peaks):
        # Remainder from simple_model trimmed_afters (if any)
        rem_lo = rem_hi = None
        if (
            getattr(self, "simple_model", None)
            and self.simple_model.state == OK
            and self.simple_model.trimmed_afters
        ):
            rem_lo, rem_hi = self._percentiles(
                self.simple_model.trimmed_afters, 0.05, 0.95
            )

        act_lo, act_hi = self._percentiles_or_none(nxh_acts, 0.05, 0.95)

        pk_lo = pk_hi = None
        ptime_lo = ptime_hi = None
        if peaks:
            pvals = [int(p) for p, _ in peaks]
            ptmins = [int(pt.num) for _p, pt in peaks]
            pk_lo, pk_hi = self._percentiles(pvals, 0.05, 0.95)
            tlo, thi = self._percentiles(ptmins, 0.05, 0.95)
            ptime_lo, ptime_hi = VTime(tlo), VTime(thi)

        return (rem_lo, rem_hi), (act_lo, act_hi), (pk_lo, pk_hi), (ptime_lo, ptime_hi)

    def _rng_str(self, lo, hi, is_time: bool = False) -> str:
        if lo is None or hi is None:
            return ""
        if is_time:
            return f"{lo.short}-{hi.short}"
        try:
            lo_i = max(0, int(lo))
            hi_i = int(hi)
        except Exception:
            return ""
        return f"{lo_i}-{hi_i}"

    def _smooth_conf_wrapper(self, n: int, frac_elapsed: float, spread, scale):
        return self._smooth_conf(n, frac_elapsed, spread, scale)

    def _probability_from_score(
        self,
        model_code: str,
        measure_code: str,
        frac_elapsed: float,
        score: float | None,
    ) -> float | None:
        if score is None:
            return None
        try:
            score_val = max(0.0, min(100.0, float(score)))
        except Exception:
            return None
        prob = _calib_probability(
            self._calib,
            self._calib_bins,
            model_code,
            measure_code,
            frac_elapsed,
            score_val,
        )
        if prob is None:
            prob = score_val / 100.0
        return max(0.0, min(1.0, float(prob)))

    def _probability_label(
        self,
        model_code: str,
        measure_code: str,
        frac_elapsed: float,
        score: float | None,
    ) -> str:
        prob = self._probability_from_score(model_code, measure_code, frac_elapsed, score)
        if prob is None:
            return "--"
        pct = int(round(max(0.0, min(1.0, prob)) * 100.0))
        pct = max(0, min(100, pct))
        return f"{pct}%"

    def _simple_confidences(
        self,
        remainder: int,
        nxh_activity: int,
        peak_val: int,
        ptime_bounds: tuple["VTime|None", "VTime|None"],
        total_span: int,
        rem_bounds,
        act_bounds,
        pk_bounds,
        n: int,
        frac_elapsed: float,
    ):
        rem_lo, rem_hi = rem_bounds
        act_lo, act_hi = act_bounds
        pk_lo, pk_hi = pk_bounds
        ptime_lo, ptime_hi = ptime_bounds

        rem_spread = (
            (rem_hi - rem_lo) if (rem_lo is not None and rem_hi is not None) else None
        )
        rem_scale = (
            max(1.0, float(remainder), float(rem_hi or 0))
            if rem_spread is not None
            else None
        )
        conf_rem = self._smooth_conf_wrapper(n, frac_elapsed, rem_spread, rem_scale)

        act_spread = (
            (act_hi - act_lo) if (act_lo is not None and act_hi is not None) else None
        )
        act_scale = (
            max(1.0, float(nxh_activity), float(act_hi or 0))
            if act_spread is not None
            else None
        )
        conf_act = self._smooth_conf_wrapper(n, frac_elapsed, act_spread, act_scale)

        pk_spread = (
            (pk_hi - pk_lo) if (pk_lo is not None and pk_hi is not None) else None
        )
        pk_scale = (
            max(1.0, float(peak_val), float(pk_hi or 0))
            if pk_spread is not None
            else None
        )
        conf_pk = self._smooth_conf_wrapper(n, frac_elapsed, pk_spread, pk_scale)

        pt_spread = (
            (ptime_hi.num - ptime_lo.num)
            if (ptime_lo is not None and ptime_hi is not None)
            else None
        )
        pt_scale = float(total_span) if pt_spread is not None else None
        conf_pt = self._smooth_conf_wrapper(n, frac_elapsed, pt_spread, pt_scale)

        return conf_rem, conf_act, conf_pk, conf_pt

    def _apply_calib(
        self,
        model_code: str,
        measure_code: str,
        point_val: int,
        base_band: int,
        frac_elapsed: float,
    ):
        """Apply calibration residual band if available; return (range_str, adjusted_band)."""
        band = base_band
        rstr = ""
        calib = self._calib_residual_band(model_code, measure_code, frac_elapsed)
        if calib:
            q05, q95 = calib
            half = int(round(max(0.0, (q95 - q05) / 2.0)))
            band = max(base_band, half)
            rstr = self._rng_str(int(point_val + q05), int(point_val + q95), False)
        return rstr, band

    def _build_simple_rows(
        self,
        t_end: "VTime",
        nxh_activity: int,
        remainder: int,
        peak_time: "VTime",
        peak_val: int,
        bands: tuple[int, int, int, int],
        act_bounds,
        rem_bounds,
        pk_bounds,
        ptime_bounds,
        scores: tuple[float | None, float | None, float | None, float | None],
        frac_elapsed: float,
    ):
        act_band, rem_band, peak_band, ptime_band = bands
        act_lo, act_hi = act_bounds
        rem_lo, rem_hi = rem_bounds
        pk_lo, pk_hi = pk_bounds
        ptime_lo, ptime_hi = ptime_bounds
        score_act, score_rem, score_pt, score_pk = scores

        sm_act_rng, sm_act_band = self._apply_calib(
            self.MODEL_SM, "act", int(nxh_activity), act_band, frac_elapsed
        )
        sm_fut_rng, sm_fut_band = self._apply_calib(
            self.MODEL_SM, "fut", int(remainder), rem_band, frac_elapsed
        )
        sm_pk_rng, sm_pk_band = self._apply_calib(
            self.MODEL_SM, "peak", int(peak_val), peak_band, frac_elapsed
        )

        rows = [
            (
                self._activity_label(t_end),
                f"{int(nxh_activity)}",
                sm_act_rng or self._rng_str(act_lo, act_hi, False),
                self._probability_label(
                    self.MODEL_SM, "act", frac_elapsed, score_act
                ),
            ),
            (
                self._further_measure_label(remainder),
                f"{int(remainder)}",
                sm_fut_rng or self._rng_str(rem_lo, rem_hi, False),
                self._probability_label(
                    self.MODEL_SM, "fut", frac_elapsed, score_rem
                ),
            ),
            (
                self.MEAS_TIME_MAX,
                f"{peak_time.short}",
                self._rng_str(ptime_lo, ptime_hi, True),
                self._probability_label(
                    self.MODEL_SM, "ptime", frac_elapsed, score_pt
                ),
            ),
            (
                self.MEAS_MAX,
                f"{int(peak_val)}",
                sm_pk_rng or self._rng_str(pk_lo, pk_hi, False),
                self._probability_label(
                    self.MODEL_SM, "peak", frac_elapsed, score_pk
                ),
            ),
        ]
        return rows

    def _linreg(self, xs: list[float], ys: list[float]):
        npts = len(xs)
        if npts < 2:
            return None
        sx = sum(xs)
        sy = sum(ys)
        sxx = sum(x * x for x in xs)
        sxy = sum(x * y for x, y in zip(xs, ys))
        denom = npts * sxx - sx * sx
        if denom == 0:
            return None
        a = (npts * sxy - sx * sy) / denom
        b = (sy - a * sx) / npts
        return a, b

    def _residual_ranges(self, xs: list[int], ys: list[int], coeff):
        if not coeff:
            return (None, None)
        a, b = coeff
        resids = [int(y - (a * float(x) + b)) for x, y in zip(xs, ys)]
        if not resids:
            return (None, None)
        lo, hi = self._percentiles(resids, 0.05, 0.95)
        return int(lo), int(hi)

    def _rng_from_res(self, point: int, lo_res, hi_res) -> str:
        if lo_res is None or hi_res is None:
            return ""
        return self._rng_str(point + lo_res, point + hi_res, False)

    def _scale_band(
        self, base: int, model_width: int | None, ref_width: int | None
    ) -> int:
        if model_width is None or ref_width is None or ref_width <= 0:
            return base
        import math

        sf = math.sqrt(max(1, model_width) / max(1, ref_width))
        sf = max(0.5, min(2.0, sf))
        return int(round(base * sf))

    def _build_lr_rows(
        self,
        t_end: "VTime",
        remainder: int,
        nxh_activity: int,
        peak_val: int,
        peak_time: "VTime",
        all_acts: list[int],
        all_peaks: list[int],
        bands: tuple[int, int, int, int],
        act_bounds,
        rem_bounds,
        pk_bounds,
        ptime_bounds,
        frac_elapsed: float,
    ):
        act_band, rem_band, peak_band, ptime_band = bands
        act_lo, act_hi = act_bounds
        rem_lo, rem_hi = rem_bounds
        pk_lo, pk_hi = pk_bounds
        ptime_lo, ptime_hi = ptime_bounds

        # Remainder via LR model class (if available)
        lr_remainder = int(remainder)
        try:
            lr = LRModelNew()
            lr.calculate_model(list(zip(self.befores, self.afters)))
            lr.guess(self.bikes_so_far)
            if lr.state == OK and isinstance(lr.further_bikes, int):
                lr_remainder = int(lr.further_bikes)
        except Exception:
            pass

        # Activity via hand LR
        coeff_act = self._linreg(
            [float(x) for x in self.befores], [float(y) for y in all_acts]
        )
        lr_act_val = int(nxh_activity)
        if coeff_act:
            a, b = coeff_act
            lr_act_val = max(0, int(round(a * float(self.bikes_so_far) + b)))

        # Peak via hand LR
        coeff_pk = self._linreg(
            [float(x) for x in self.befores], [float(y) for y in all_peaks]
        )
        lr_peak_val = int(peak_val)
        if coeff_pk:
            ap, bp = coeff_pk
            lr_peak_val = max(0, int(round(ap * float(self.bikes_so_far) + bp)))

        # Residual ranges
        rem_lo_res, rem_hi_res = self._residual_ranges(
            self.befores,
            self.afters,
            self._linreg(
                [float(x) for x in self.befores], [float(y) for y in self.afters]
            ),
        )
        act_lo_res, act_hi_res = self._residual_ranges(
            self.befores, all_acts, coeff_act
        )
        pk_lo_res, pk_hi_res = self._residual_ranges(self.befores, all_peaks, coeff_pk)

        # Reference widths (Simple)
        rem_w_ref = (
            (rem_hi - rem_lo) if (rem_lo is not None and rem_hi is not None) else None
        )
        act_w_ref = (
            (act_hi - act_lo) if (act_lo is not None and act_hi is not None) else None
        )
        pk_w_ref = (
            (pk_hi - pk_lo) if (pk_lo is not None and pk_hi is not None) else None
        )

        # LR widths
        rem_w_lr = (
            (rem_hi_res - rem_lo_res)
            if (rem_lo_res is not None and rem_hi_res is not None)
            else None
        )
        act_w_lr = (
            (act_hi_res - act_lo_res)
            if (act_lo_res is not None and act_hi_res is not None)
            else None
        )
        pk_w_lr = (
            (pk_hi_res - pk_lo_res)
            if (pk_lo_res is not None and pk_hi_res is not None)
            else None
        )

        # Model-specific bands (scaled) + calibration
        lr_act_rng, act_band_lr = self._apply_calib(
            self.MODEL_LR,
            "act",
            lr_act_val,
            self._scale_band(act_band, act_w_lr, act_w_ref),
            frac_elapsed,
        )
        lr_rem_rng, rem_band_lr = self._apply_calib(
            self.MODEL_LR,
            "fut",
            lr_remainder,
            self._scale_band(rem_band, rem_w_lr, rem_w_ref),
            frac_elapsed,
        )
        lr_pk_rng, pk_band_lr = self._apply_calib(
            self.MODEL_LR,
            "peak",
            lr_peak_val,
            self._scale_band(peak_band, pk_w_lr, pk_w_ref),
            frac_elapsed,
        )
        pt_band_lr = ptime_band  # time kept same

        # Confidences
        conf_rem_lr = self._smooth_conf(
            len(self.befores), frac_elapsed, rem_w_lr, max(1.0, float(lr_remainder))
        )
        conf_act_lr = self._smooth_conf(
            len(self.befores), frac_elapsed, act_w_lr, max(1.0, float(lr_act_val))
        )
        conf_pk_lr = self._smooth_conf(
            len(self.befores), frac_elapsed, pk_w_lr, max(1.0, float(lr_peak_val))
        )
        conf_pt_lr = self._smooth_conf(
            len(self.befores), frac_elapsed, None, None
        )  # same as simple

        rows = [
            (
                self._activity_label(t_end),
                f"{lr_act_val}",
                lr_act_rng or self._rng_from_res(lr_act_val, act_lo_res, act_hi_res),
                self._probability_label(
                    self.MODEL_LR, "act", frac_elapsed, conf_act_lr
                ),
            ),
            (
                self._further_measure_label(lr_remainder),
                f"{lr_remainder}",
                lr_rem_rng or self._rng_from_res(lr_remainder, rem_lo_res, rem_hi_res),
                self._probability_label(
                    self.MODEL_LR, "fut", frac_elapsed, conf_rem_lr
                ),
            ),
            (
                self.MEAS_TIME_MAX,
                f"{peak_time.short}",
                self._rng_str(ptime_lo, ptime_hi, True),
                self._probability_label(
                    self.MODEL_LR, "ptime", frac_elapsed, conf_pt_lr
                ),
            ),
            (
                self.MEAS_MAX,
                f"{lr_peak_val}",
                lr_pk_rng or self._rng_from_res(lr_peak_val, pk_lo_res, pk_hi_res),
                self._probability_label(
                    self.MODEL_LR, "peak", frac_elapsed, conf_pk_lr
                ),
            ),
        ]
        return rows

    def _build_recent_rows(
        self,
        t_end: "VTime",
        remainder_baseline: int,
        nxh_activity_baseline: int,
        peak_val_baseline: int,
        peak_time_baseline: "VTime",
        bands: tuple[int, int, int, int],
        frac_elapsed: float,
    ):
        import statistics as _st

        act_band, rem_band, peak_band, ptime_band = bands

        # recent_n defaults
        recent_n = (
            int(getattr(wcfg, "EST_RECENT_DAYS", 30)) if "wcfg" in globals() else 30
        )

        # Map date -> after (proxy) from pre-aggregated self.afters
        date_to_after = {
            d: int(self.afters[i])
            for i, d in enumerate(self.similar_dates)
            if i < len(self.afters)
        }
        rec_dates = sorted(self.similar_dates, reverse=True)[:recent_n]

        rec_acts, rec_afters, rec_peaks, rec_ptimes = [], [], [], []
        for d in rec_dates:
            vlist = self._visits_for_date(d)
            _b3, _a3, _o3, ins3, outs3 = self._counts_for_time(vlist, self.as_of_when)
            rec_acts.append(int(ins3 + outs3))
            if d in date_to_after:
                rec_afters.append(int(date_to_after[d]))
            else:
                _btmp, _atmp, *_ = self._counts_for_time(vlist, self.as_of_when)
                rec_afters.append(int(_atmp))
            p3, pt3 = self._peak_all_day_occupancy(vlist)
            rec_peaks.append(int(p3))
            rec_ptimes.append(int(pt3.num))

        rec_act_val = (
            int(_st.median(rec_acts)) if rec_acts else int(nxh_activity_baseline)
        )
        rec_rem_val = (
            int(_st.median(rec_afters)) if rec_afters else int(remainder_baseline)
        )
        rec_peak_val = (
            int(_st.median(rec_peaks)) if rec_peaks else int(peak_val_baseline)
        )
        rec_ptime_val = (
            VTime(int(_st.median(rec_ptimes))) if rec_ptimes else peak_time_baseline
        )

        # 90% ranges
        r_act_lo, r_act_hi = (
            self._percentiles(rec_acts, 0.05, 0.95) if rec_acts else (None, None)
        )
        r_rem_lo, r_rem_hi = (
            self._percentiles(rec_afters, 0.05, 0.95) if rec_afters else (None, None)
        )
        r_pk_lo, r_pk_hi = (
            self._percentiles(rec_peaks, 0.05, 0.95) if rec_peaks else (None, None)
        )
        _pt_lo, _pt_hi = (
            self._percentiles(rec_ptimes, 0.05, 0.95) if rec_ptimes else (None, None)
        )
        r_pt_lo, r_pt_hi = (
            (VTime(_pt_lo), VTime(_pt_hi))
            if (_pt_lo is not None and _pt_hi is not None)
            else (None, None)
        )

        # Widths
        r_act_w = (
            (r_act_hi - r_act_lo)
            if (r_act_lo is not None and r_act_hi is not None)
            else None
        )
        r_rem_w = (
            (r_rem_hi - r_rem_lo)
            if (r_rem_lo is not None and r_rem_hi is not None)
            else None
        )
        r_pk_w = (
            (r_pk_hi - r_pk_lo)
            if (r_pk_lo is not None and r_pk_hi is not None)
            else None
        )

        # Reference widths from simple for scaling; if missing, fall back to recent widths
        # (They’ll be used only in _scale_band guard-railed.)
        # We'll re-compute simple widths here safely from precomputed simple quantiles (not passed).
        # If you want exact scaling vs simple, pass those widths in from caller.
        act_w_ref = r_act_w
        rem_w_ref = r_rem_w
        pk_w_ref = r_pk_w

        # Apply calibration & scaling
        rec_act_rng, act_band_rec = self._apply_calib(
            self.MODEL_REC,
            "act",
            rec_act_val,
            self._scale_band(act_band, r_act_w, act_w_ref),
            frac_elapsed,
        )
        rec_rem_rng, rem_band_rec = self._apply_calib(
            self.MODEL_REC,
            "fut",
            rec_rem_val,
            self._scale_band(rem_band, r_rem_w, rem_w_ref),
            frac_elapsed,
        )
        rec_pk_rng, pk_band_rec = self._apply_calib(
            self.MODEL_REC,
            "peak",
            rec_peak_val,
            self._scale_band(peak_band, r_pk_w, pk_w_ref),
            frac_elapsed,
        )
        pt_band_rec = ptime_band

        # Confidences (n = # recent dates)
        conf_act_rec = self._smooth_conf(
            len(rec_dates), frac_elapsed, r_act_w, max(1.0, float(rec_act_val))
        )
        conf_rem_rec = self._smooth_conf(
            len(rec_dates), frac_elapsed, r_rem_w, max(1.0, float(rec_rem_val))
        )
        conf_pk_rec = self._smooth_conf(
            len(rec_dates), frac_elapsed, r_pk_w, max(1.0, float(rec_peak_val))
        )
        conf_pt_rec = self._smooth_conf(len(rec_dates), frac_elapsed, None, None)

        rows = [
            (
                self._activity_label(t_end),
                f"{rec_act_val}",
                rec_act_rng or self._rng_str(r_act_lo, r_act_hi, False),
                self._probability_label(
                    self.MODEL_REC, "act", frac_elapsed, conf_act_rec
                ),
            ),
            (
                self._further_measure_label(rec_rem_val),
                f"{rec_rem_val}",
                rec_rem_rng or self._rng_str(r_rem_lo, r_rem_hi, False),
                self._probability_label(
                    self.MODEL_REC, "fut", frac_elapsed, conf_rem_rec
                ),
            ),
            (
                self.MEAS_TIME_MAX,
                f"{rec_ptime_val.short}",
                self._rng_str(r_pt_lo, r_pt_hi, True),
                self._probability_label(
                    self.MODEL_REC, "ptime", frac_elapsed, conf_pt_rec
                ),
            ),
            (
                self.MEAS_MAX,
                f"{rec_peak_val}",
                rec_pk_rng or self._rng_str(r_pk_lo, r_pk_hi, False),
                self._probability_label(
                    self.MODEL_REC, "peak", frac_elapsed, conf_pk_rec
                ),
            ),
        ]
        return rows

    def _rf_possible(self) -> bool:
        return "rf" in globals() and getattr(rf, "POSSIBLE", False)

    def _build_rf_rows(
        self,
        t_end: "VTime",
        remainder_baseline: int,
        nxh_activity_baseline: int,
        peak_val_baseline: int,
        peak_time: "VTime",
        bands: tuple[int, int, int, int],
        act_bounds,
        rem_bounds,
        pk_bounds,
        ptime_bounds,
        frac_elapsed: float,
    ):
        if not self._rf_possible():
            return []

        act_band, rem_band, peak_band, ptime_band = bands
        act_lo, act_hi = act_bounds
        rem_lo, rem_hi = rem_bounds
        pk_lo, pk_hi = pk_bounds
        ptime_lo, ptime_hi = ptime_bounds

        import numpy as _np

        # Train RF models
        rf_fut = rf.RandomForestRegressorModel()
        rf_fut.create_model(self.similar_dates, self.befores, self.afters)
        rf_fut.guess(self.bikes_so_far)
        rf_remainder = (
            int(rf_fut.further_bikes)
            if rf_fut.state == OK and rf_fut.further_bikes is not None
            else int(remainder_baseline)
        )

        # activity
        # Build all_acts from similar dates for consistency
        all_acts, all_peaks, _ = self._collect_all_stats_for_similar()
        rf_act = rf.RandomForestRegressorModel()
        rf_act.create_model(self.similar_dates, self.befores, all_acts)
        rf_act.guess(self.bikes_so_far)
        rf_act_val = (
            int(rf_act.further_bikes)
            if rf_act.state == OK and rf_act.further_bikes is not None
            else int(nxh_activity_baseline)
        )

        # peak
        rf_pk = rf.RandomForestRegressorModel()
        rf_pk.create_model(self.similar_dates, self.befores, all_peaks)
        rf_pk.guess(self.bikes_so_far)
        rf_peak_val = (
            int(rf_pk.further_bikes)
            if rf_pk.state == OK and rf_pk.further_bikes is not None
            else int(peak_val_baseline)
        )

        def _rf_residuals(model, y_true: list[int]):
            try:
                preds = model.rf_model.predict(_np.array(self.befores).reshape(-1, 1))
                res = [int(y - int(round(p))) for y, p in zip(y_true, preds)]
                if not res:
                    return None, None, None
                lo, hi = self._percentiles(res, 0.05, 0.95)
                return int(lo), int(hi), int(hi - lo)
            except Exception:
                return None, None, None

        fut_lo_res, fut_hi_res, fut_w = _rf_residuals(rf_fut, self.afters)
        act_lo_res, act_hi_res, act_w = _rf_residuals(rf_act, all_acts)
        pk_lo_res, pk_hi_res, pk_w = _rf_residuals(rf_pk, all_peaks)

        # Bands scaled & calibrated
        rf_rem_rng = self._rng_from_res(rf_remainder, fut_lo_res, fut_hi_res)
        rf_act_rng = self._rng_from_res(rf_act_val, act_lo_res, act_hi_res)
        rf_pk_rng = self._rng_from_res(rf_peak_val, pk_lo_res, pk_hi_res)

        rem_band_rf = self._scale_band(rem_band, fut_w, None)
        act_band_rf = self._scale_band(act_band, act_w, None)
        pk_band_rf = self._scale_band(peak_band, pk_w, None)

        cal_act_rng, act_band_rf = self._apply_calib(
            self.MODEL_RF, "act", rf_act_val, act_band_rf, frac_elapsed
        )
        cal_fut_rng, rem_band_rf = self._apply_calib(
            self.MODEL_RF, "fut", rf_remainder, rem_band_rf, frac_elapsed
        )
        cal_pk_rng, pk_band_rf = self._apply_calib(
            self.MODEL_RF, "peak", rf_peak_val, pk_band_rf, frac_elapsed
        )

        if cal_act_rng:
            rf_act_rng = cal_act_rng
        if cal_fut_rng:
            rf_rem_rng = cal_fut_rng
        if cal_pk_rng:
            rf_pk_rng = cal_pk_rng

        conf_rem_rf = self._smooth_conf(
            len(self.befores), frac_elapsed, fut_w, max(1.0, float(rf_remainder))
        )
        conf_act_rf = self._smooth_conf(
            len(self.befores), frac_elapsed, act_w, max(1.0, float(rf_act_val))
        )
        conf_pk_rf = self._smooth_conf(
            len(self.befores), frac_elapsed, pk_w, max(1.0, float(rf_peak_val))
        )
        conf_pt = self._smooth_conf(len(self.befores), frac_elapsed, None, None)

        rows = [
            (
                self._activity_label(t_end),
                f"{rf_act_val}",
                rf_act_rng or self._rng_str(act_lo, act_hi, False),
                self._probability_label(
                    self.MODEL_RF, "act", frac_elapsed, conf_act_rf
                ),
            ),
            (
                self._further_measure_label(rf_remainder),
                f"{rf_remainder}",
                rf_rem_rng or self._rng_str(rem_lo, rem_hi, False),
                self._probability_label(
                    self.MODEL_RF, "fut", frac_elapsed, conf_rem_rf
                ),
            ),
            (
                self.MEAS_TIME_MAX,
                f"{peak_time.short}",
                self._rng_str(ptime_lo, ptime_hi, True),
                self._probability_label(
                    self.MODEL_RF, "ptime", frac_elapsed, conf_pt
                ),
            ),
            (
                self.MEAS_MAX,
                f"{rf_peak_val}",
                rf_pk_rng or self._rng_str(pk_lo, pk_hi, False),
                self._probability_label(
                    self.MODEL_RF, "peak", frac_elapsed, conf_pk_rf
                ),
            ),
        ]
        return rows

    def _parse_prob(self, pct: str) -> int:
        try:
            return int(str(pct).strip().strip("%"))
        except Exception:
            return 0

    def _range_width(self, rng: str, is_time: bool) -> int:
        if not rng:
            return 10**9
        try:
            a, b = rng.split("-", 1)
            if is_time:
                va = VTime(a.strip())
                vb = VTime(b.strip())
                if not va or not vb:
                    return 10**9
                return max(0, int(vb.num) - int(va.num))
            return abs(int(str(b).strip()) - int(str(a).strip()))
        except Exception:
            return 10**9

    def _measure_key_by_index(self, i: int) -> str | None:
        mapping = {0: "act", 1: "fut", 2: "ptime", 3: "peak"}
        return mapping.get(i)

    def _select_by_probability_then_width(
        self, cands: list[tuple[int, int, str, tuple]]
    ):
        # Sort by highest probability first (stored as negative), then by range width
        cands.sort(key=lambda item: (item[1], item[0]))
        return cands[0]

    def _select_by_width_then_probability(
        self, cands: list[tuple[int, int, str, tuple]]
    ):
        # Sort by narrowest range width, then highest probability
        cands.sort(key=lambda item: (item[0], item[1]))
        return cands[0]

    def _best_candidate_accuracy_first(self, i: int, cands, frac: float, cohort_n: int):
        meas_key = self._measure_key_by_index(i)
        # Try calibration-best model
        if getattr(self, "_calib_best", None) and meas_key:
            lbl = self._bin_label(frac)
            try:
                pref = self._calib_best.get(meas_key, {}).get(lbl)
            except Exception:
                pref = None
            if pref:
                for cand in cands:
                    if cand[2] == pref:
                        return cand, f"calibrated best_model {pref} for bin {lbl}"
        # Guardrail: prefer robust SM/REC with tiny cohort or missing calib
        guard_min = (
            int(getattr(wcfg, "EST_MIN_COHORT_FOR_SELECTION", 4))
            if "wcfg" in globals()
            else 4
        )
        if cohort_n < guard_min or not getattr(self, "_calib_best", None):
            for target in [self.MODEL_SM, self.MODEL_REC]:
                for cand in cands:
                    if cand[2] == target:
                        return cand, f"guardrail: n={cohort_n}; prefer {target}"
        # Fallback: highest probability, then narrowest range
        best = self._select_by_probability_then_width(cands)
        width, neg_prob, mdl, _row = best
        prob_pct = -neg_prob
        return best, f"probability-first: prob {prob_pct}%; width {width}"

    def _select_dispatch(self, mode: str, i: int, cands, frac: float, cohort_n: int):
        mode = str(mode or "accuracy_first").strip().lower()
        if mode == "range_first":
            best = self._select_by_width_then_probability(cands)
            width, neg_prob, mdl, _row = best
            prob_pct = -neg_prob
            return (
                best,
                f"range-first: width {width}; prob {prob_pct}%",
            )
        return self._best_candidate_accuracy_first(i, cands, frac, cohort_n)

    def _select_rows(
        self, t_end: "VTime", tables_by_model: dict, frac_elapsed: float, cohort_n: int
    ):
        mixed_rows: list[tuple[str, str, str, str]] = []
        mixed_models: list[str] = []
        selected_by_model: dict[str, set[int]] = {
            self.MODEL_SM: set(),
            self.MODEL_LR: set(),
            self.MODEL_REC: set(),
            self.MODEL_RF: set(),
        }
        selection_info: list[str] = []

        measure_count = 4
        for idx in range(measure_count):
            # Gather candidates across models
            candidates = []
            for mdl_code, rows in tables_by_model.items():
                if idx >= len(rows):
                    continue
                r = rows[idx]  # (measure, value, range, probability)
                rng = r[2]
                is_time = idx == 2
                width = self._range_width(rng, is_time)
                probv = self._parse_prob(r[3])
                candidates.append((width, -probv, mdl_code, r))
            if not candidates:
                continue

            sel_mode = (
                str(getattr(wcfg, "EST_SELECTION_MODE", "accuracy_first"))
                if "wcfg" in globals()
                else "accuracy_first"
            )
            best, why = self._select_dispatch(
                sel_mode, idx, candidates, frac_elapsed, cohort_n
            )
            mixed_rows.append(best[3])
            mixed_models.append(best[2])
            if best[2] in selected_by_model:
                selected_by_model[best[2]].add(idx)
            label_txt = best[3][0]
            selection_info.append(
                f"Chosen: {best[2]} for '{label_txt}' ({why})"
            )

        return mixed_rows, mixed_models, selected_by_model, selection_info

    def result_msg(self, as_html: bool = False) -> list[str]:
        if self.state == ERROR:
            if as_html:
                import html as _html

                return [
                    f"<p>Can't estimate because: {_html.escape(str(self.error))}</p>"
                ]
            return [f"Can't estimate because: {self.error}"]
        lines = _render_tables(
            as_of_when=self.as_of_when,
            verbose=self.verbose,
            tables=getattr(self, "tables", []) or [],
            header_mixed=self.HEADER_MIXED,
            header_full=self.HEADER_FULL,
            mixed_models=getattr(self, "_mixed_models", None),
            selected_by_model=getattr(self, "_selected_by_model", None),
            selection_info=getattr(self, "_selection_info", None),
            calib=getattr(self, "_calib", None),
            calib_debug=getattr(self, "_calib_debug", None),
            as_html=as_html,
        )
        # Append extended details that were present before refactor
        if self.verbose:
            try:
                open_num = (
                    self.time_open.num
                    if self.time_open and self.time_open.num is not None
                    else 0
                )
                close_num = (
                    self.time_closed.num
                    if self.time_closed and self.time_closed.num is not None
                    else 24 * 60
                )
                span = max(1, close_num - open_num)
                frac_elapsed = max(
                    0.0, min(1.0, (self.as_of_when.num - open_num) / span)
                )
                similar_count = len(getattr(self, "similar_dates", []) or [])
                match_note = getattr(self, "_match_note", "")
                variance = getattr(self, "VARIANCE", "")
                zcut = getattr(self, "Z_CUTOFF", "")
                sm = getattr(self, "simple_model", None)
                matched = self._matched_dates()
                level = self._confidence_level(len(matched), frac_elapsed)
                rb = self._band(level, "remainder")
                ab = self._band(level, "activity")
                pb = self._band(level, "peak")
                tb = self._band(level, "peaktime")
                rbs = self._band_scaled(rb, len(matched), frac_elapsed, "remainder")
                abs_ = self._band_scaled(ab, len(matched), frac_elapsed, "activity")
                pbs = self._band_scaled(pb, len(matched), frac_elapsed, "peak")
                tbs = self._band_scaled(tb, len(matched), frac_elapsed, "peaktime")

                if as_html:
                    import html as _html

                    lines.append("<div class=\"estimator-extra\">")
                    lines.append("<h4>Inputs</h4>")
                    lines.append(
                        f"<li>Bikes so far: {_html.escape(str(self.bikes_so_far))}<br>"
                    )
                    lines.append(
                        f"<li>Open/Close: {_html.escape(str(self.time_open))} - {_html.escape(str(self.time_closed))}<br>"
                    )
                    lines.append(
                        f"<li>Day progress: {int(frac_elapsed*100)}% (span {span} minutes)<br>"
                    )
                    lines.append(
                        f"<li>Similar-day rows: {similar_count} {_html.escape(f'({match_note})' if match_note else '')}<br>"
                    )
                    lines.append(
                        f"<li>Match tolerance (VARIANCE): {_html.escape(str(variance))}<br>"
                    )
                    lines.append(
                        f"<li>Outlier Z cutoff: {_html.escape(str(zcut))}<br>"
                    )
                    if sm and getattr(sm, "state", None) == OK:
                        lines.append("<div class=\"estimator-simple-model\">")
                        lines.append("<h4>Simple model (similar days)</h4>")
                        lines.append(
                            f"<li>Points matched: {_html.escape(str(getattr(sm, 'num_points', '')))}<br>"
                        )
                        lines.append(
                            f"<li>Discarded as outliers: {_html.escape(str(getattr(sm, 'num_discarded', '')))}<br>"
                        )
                        lines.append(
                            f"<li>Min/Median/Mean/Max: {_html.escape(str(sm.min))}/"
                            f"{_html.escape(str(sm.median))}/{_html.escape(str(sm.mean))}/"
                            f"{_html.escape(str(sm.max))}<br>"
                        )
                        lines.append("</div>")
                    lines.append(
                        f"<li>Confidence level: {_html.escape(level)}<br>"
                    )
                    lines.append(
                        f"<li>Bands used (remainder/activity/peak/peaktime): {rbs}/{abs_}/{pbs}/{tbs}<br>"
                    )
                    lines.append(
                        f"<li>Base bands (before scaling): {rb}/{ab}/{pb}/{tb}<br>"
                    )
                    lines.append("</div>")
                else:
                    lines.append("")
                    lines.append(f"Bikes so far: {self.bikes_so_far}")
                    lines.append(f"Open/Close: {self.time_open} - {self.time_closed}")
                    lines.append(
                        f"Day progress: {int(frac_elapsed*100)}% (span {span} minutes)"
                    )
                    lines.append(
                        f"Similar-day rows: {similar_count} ({match_note})"
                    )
                    lines.append(
                        f"Match tolerance (VARIANCE): {variance}"
                    )
                    lines.append(f"Outlier Z cutoff: {zcut}")
                    if sm and getattr(sm, "state", None) == OK:
                        lines.append("")
                        lines.append("Simple model (similar days)")
                        lines.append(f"  Points matched: {getattr(sm, 'num_points', '')}")
                        lines.append(
                            f"  Discarded as outliers: {getattr(sm, 'num_discarded', '')}"
                        )
                        lines.append(
                            f"  Min/Median/Mean/Max: {sm.min}/{sm.median}/{sm.mean}/{sm.max}"
                        )
                    lines.append(f"Confidence level: {level}")
                    lines.append(
                        f"Bands used (remainder/activity/peak/peaktime): {rbs}/{abs_}/{pbs}/{tbs}"
                    )
                    lines.append(
                        f"Base bands (before scaling): {rb}/{ab}/{pb}/{tb}"
                    )
            except Exception:
                # Do not fail rendering on details
                pass
        return lines


if __name__ == "__main__":
    try:
        # Parse CGI inputs for the estimator
        def _init_from_cgi() -> tuple[Estimator, str]:
            query_str = ut.untaint(os.environ.get("QUERY_STRING", ""))
            query_parms = urllib.parse.parse_qs(query_str)
            bikes_so_far = query_parms.get("bikes_so_far", [""])[0]
            opening_time = query_parms.get("opening_time", [""])[0]
            closing_time = query_parms.get("closing_time", [""])[0]
            estimation_type = (
                (query_parms.get("estimation_type", [""])[0] or "").strip().lower()
            )
            if not estimation_type:
                estimation_type = (
                    (query_parms.get("what", [""])[0] or "").strip().lower()
                )
            render_format = (
                (query_parms.get("format", ["plain"])[0] or "plain").strip().lower()
            )
            est = Estimator(
                bikes_so_far=bikes_so_far,
                opening_time=opening_time,
                closing_time=closing_time,
                estimation_type=estimation_type,
            )
            return est, render_format

        start_time = time.perf_counter()
        estimate_any = None
        is_cgi = bool(os.environ.get("REQUEST_METHOD"))
        render_format = "plain"
        render_html = False
        if is_cgi:
            estimate_any, render_format = _init_from_cgi()
            render_html = render_format == "html"
            mime = "text/html" if render_html else "text/plain"
            print(f"Content-type: {mime}\n")
            if render_html:
                print(cc.style())
        else:
            print("Must use CGI interface")
            exit()

        if estimate_any.state != ERROR:
            estimate_any.guess()

        output_lines = estimate_any.result_msg(as_html=render_html)
        for line in output_lines:
            print(line)
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        if render_html:
            print(f"<p class=\"estimator-query-time\">Query took {elapsed_time:.1f} seconds.</p>")
        else:
            print(f"\n\nQuery took {elapsed_time:.1f} seconds.")
    except Exception as e:  # pylint:disable=broad-except
        # Always emit something helpful rather than a blank page
        is_cgi = bool(os.environ.get("REQUEST_METHOD"))
        try:
            render_html
        except NameError:
            render_html = False
        if is_cgi:
            try:
                mime = "text/html" if render_html else "text/plain"
                print(f"Content-type: {mime}\n")
            except Exception:  # pylint:disable=broad-except
                pass
        if render_html:
            import html as _html

            print(f"<p>Estimator error: {_html.escape(str(e))}</p>")
            try:
                tb_html = "<br>".join(
                    _html.escape(line.rstrip("\n"))
                    for line in _tb.format_exception(type(e), e, e.__traceback__)
                )
                print(f"<pre>{tb_html}</pre>")
            except Exception:  # pylint:disable=broad-except
                pass
            raise SystemExit(1)

        print(f"Estimator error: {e}")
        try:
            print("\n".join(_tb.format_exception(type(e), e, e.__traceback__)))
        except Exception:  # pylint:disable=broad-except
            pass
