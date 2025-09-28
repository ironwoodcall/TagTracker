#!/usr/bin/env python3
"""Model calibration and selection backtest for TagTracker estimator.

This script:
  1) Calibrates residual percentiles (e.g., 5th/95th) per time-of-day bin
     for each measure and model, to support ~90% coverage bands.
  2) Assesses, per time-of-day (frac_elapsed bin), which of the implemented
     models is the best predictor (by MAE/median-abs-error), for each measure.

Models mirrored here (aligned with web/web_estimator.py):
  - Simple (Similar-Days Median): median among matched-by-before within VARIANCE.
  - Linear Regression: y = a*x + b trained on similar days (x=before), per measure.
  - Schedule-Only (Recent): ignores bikes_so_far; median over most recent N similar days.

Measures:
  - fut: Further bikes today (remainder)
  - act: Activity in the next hour (ins + outs)
  - peak: Max bikes onsite (daily max occupancy)
  - peaktime: Time of max bikes onsite

Output:
  - Prints summary tables of residual quantiles (Q05, Q50, Q95) per frac_elapsed bin and model.
  - Prints per-bin best model (lowest MAE) per measure.
  - Optional CSVs for per-sample and per-bin summaries.

Usage:
  python helpers/estimator_calibrate_models.py --db </path/to/db.sqlite> \
      --start 2024-01-01 --end 2025-12-31 --step-min 30 --variance 15 \
      --zcut 2.5 --open-tol 15 --close-tol 15 --recent-days 30 \
      --time-bins 0-0.2,0.2-0.4,0.4-0.6,0.6-0.8,0.8-1.0 \
      --per-sample-csv helpers/calib_samples.csv \
      --summary-csv helpers/calib_summary.csv

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

from __future__ import annotations

import argparse
import sys
import shlex
import time
import subprocess
import csv
import os
import sqlite3
import statistics
from dataclasses import dataclass
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Optional acceleration / numeric helpers
try:  # pragma: no cover
    import numpy as np  # type: ignore # pylint:disable=import-error

    HAVE_NP = True
except Exception:  # pragma: no cover
    HAVE_NP = False

# Optional RandomForest
try:  # pragma: no cover
    from sklearn.ensemble import RandomForestRegressor  # type: ignore # pylint:disable=import-error

    HAVE_RF = True
except Exception:  # pragma: no cover
    HAVE_RF = False

PROB_BIN_SIZE = 10


# Lightweight time helper compatible with HH:MM strings
class VTime:
    def __init__(self, val: Optional[object] = None):
        self.num: int = -1
        if val is None:
            return
        if isinstance(val, VTime):
            self.num = val.num
        elif isinstance(val, int):
            self.num = max(0, min(24 * 60, int(val)))
        elif isinstance(val, str):
            s = val.strip()
            # HH:MM[:SS]
            try:
                parts = s.split(":")
                if len(parts) >= 2:
                    hh = int(parts[0])
                    mm = int(parts[1])
                    if 0 <= hh <= 24 and 0 <= mm <= 59:
                        self.num = min(hh * 60 + mm, 24 * 60)
                elif len(s) in (3, 4) and s.isdigit():  # HMM or HHMM
                    hh = int(s[:-2])
                    mm = int(s[-2:])
                    if 0 <= hh <= 24 and 0 <= mm <= 59:
                        self.num = min(hh * 60 + mm, 24 * 60)
            except Exception:
                self.num = -1

    def __bool__(self) -> bool:
        return 0 <= self.num <= 24 * 60

    def __str__(self) -> str:
        if not self:
            return ""
        hh = self.num // 60
        mm = self.num % 60
        return f"{hh:02d}:{mm:02d}"

    @property
    def short(self) -> str:
        return str(self)

    # Support rich comparisons by minute value
    def __lt__(self, other: "VTime") -> bool:  # type: ignore[override]
        return int(self.num) < int(VTime(other).num)

    def __le__(self, other: "VTime") -> bool:  # type: ignore[override]
        return int(self.num) <= int(VTime(other).num)

    def __gt__(self, other: "VTime") -> bool:  # type: ignore[override]
        return int(self.num) > int(VTime(other).num)

    def __ge__(self, other: "VTime") -> bool:  # type: ignore[override]
        return int(self.num) >= int(VTime(other).num)

    def __eq__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, VTime):
            try:
                other = VTime(other)  # type: ignore[arg-type]
            except Exception:
                return False
        return int(self.num) == int(other.num)

    def __ne__(self, other: object) -> bool:  # type: ignore[override]
        return not self.__eq__(other)


@dataclass
class DayMeta:
    id: int
    date: str
    time_open: VTime
    time_closed: VTime


def db_connect(dbfile: Optional[str]) -> sqlite3.Connection:
    """Open SQLite database in read-only mode (always)."""
    if not dbfile or not os.path.exists(dbfile):
        raise SystemExit(f"Database not found: {dbfile}")
    uri = f"file:{dbfile}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_days(conn: sqlite3.Connection, start: str, end: str) -> List[DayMeta]:
    cur = conn.execute(
        "SELECT id,date,time_open,time_closed FROM DAY WHERE date >= ? AND date <= ? ORDER BY date",
        (start, end),
    )
    out: List[DayMeta] = []
    for r in cur.fetchall():
        out.append(
            DayMeta(
                id=int(r["id"]),
                date=r["date"],
                time_open=VTime(r["time_open"]),
                time_closed=VTime(r["time_closed"]),
            )
        )
    return out


def fetch_visits_by_day(
    conn: sqlite3.Connection, days: List[DayMeta]
) -> Dict[int, List[Tuple[VTime, Optional[VTime]]]]:
    by_day: Dict[int, List[Tuple[VTime, Optional[VTime]]]] = {}
    if not days:
        return by_day
    ids = [d.id for d in days]
    qmarks = ",".join(["?"] * len(ids))
    cur = conn.execute(
        f"SELECT day_id,time_in,time_out FROM VISIT WHERE day_id IN ({qmarks}) ORDER BY day_id, time_in",
        ids,
    )
    for row in cur.fetchall():
        did = int(row["day_id"]) if isinstance(row, sqlite3.Row) else int(row[0])
        tin = VTime(row["time_in"]) if isinstance(row, sqlite3.Row) else VTime(row[1])
        tout_raw = row["time_out"] if isinstance(row, sqlite3.Row) else row[2]
        tout = VTime(tout_raw) if tout_raw else None
        by_day.setdefault(did, []).append((tin, tout))
    return by_day


def counts_for_time(
    visits: List[Tuple[VTime, Optional[VTime]]], t: VTime
) -> Tuple[int, int, int, int, int]:
    t_end = VTime(min(t.num + 60, 24 * 60))
    before_ins = sum(1 for tin, _ in visits if tin and tin <= t)
    after_ins = sum(1 for tin, _ in visits if tin and tin > t)
    outs_up_to_t = sum(1 for _, tout in visits if tout and tout <= t)
    ins_next = sum(1 for tin, _ in visits if tin and t < tin <= t_end)
    outs_next = sum(1 for _, tout in visits if tout and t < tout <= t_end)
    return before_ins, after_ins, outs_up_to_t, ins_next, outs_next


def peak_all_day(visits: List[Tuple[VTime, Optional[VTime]]]) -> Tuple[int, VTime]:
    events: List[Tuple[int, int]] = []
    for tin, tout in visits:
        if tin:
            events.append((int(tin.num), +1))
        if tout:
            events.append((int(tout.num), -1))
    if not events:
        return 0, VTime("00:00")
    events.sort(key=lambda x: (x[0], -x[1]))
    occ = 0
    peak = 0
    pt = VTime(events[0][0])
    for tm, d in events:
        occ += d
        if occ > peak:
            peak = occ
            pt = VTime(tm)
    return peak, pt


def percentiles(vals: List[float], plo=0.05, phi=0.95) -> Tuple[float, float]:
    if not vals:
        return None, None  # type: ignore[return-value]
    xs = sorted(float(v) for v in vals)
    n = len(xs)
    if n == 1:
        return xs[0], xs[0]

    def q(p: float) -> float:
        p = max(0.0, min(1.0, p))
        pos = p * (n - 1)
        i = int(pos)
        f = pos - i
        if i >= n - 1:
            return xs[-1]
        return xs[i] * (1 - f) + xs[i + 1] * f

    return q(plo), q(phi)


def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def smooth_conf_score(
    n: int,
    frac_elapsed: float,
    spread: Optional[float],
    denom: Optional[float],
    n_ref: int = 12,
) -> float:
    pf = 0.30 + 0.70 * clamp01(float(frac_elapsed))
    try:
        nf = (max(0, int(n)) / max(1, int(n_ref))) ** 0.5
    except Exception:
        nf = 0.0
    nf = clamp01(nf)
    if spread is None or denom is None or denom <= 0:
        vf = 0.5
    else:
        vf = 1.0 - clamp01(float(spread) / float(denom))
    score = 100.0 * (0.40 * pf + 0.30 * nf + 0.30 * vf)
    return max(0.0, min(100.0, score))


def record_prob_sample(
    store: Dict[Tuple[str, str, str], List[Tuple[float, int]]],
    key: Tuple[str, str, str],
    score: Optional[float],
    lo: Optional[float],
    hi: Optional[float],
    truth: Optional[float],
) -> None:
    if score is None or lo is None or hi is None or truth is None:
        return
    lo_f = float(lo)
    hi_f = float(hi)
    if hi_f < lo_f:
        lo_f, hi_f = hi_f, lo_f
    hit = 1 if lo_f <= float(truth) <= hi_f else 0
    store.setdefault(key, []).append((float(score), hit))


def build_probability_bins(
    samples: List[Tuple[float, int]],
    bin_size: int = 10,
) -> List[Dict[str, float]]:
    if not samples:
        return []
    buckets: List[Dict[str, float]] = []
    for start in range(0, 100, bin_size):
        end = 100 if start + bin_size >= 100 else start + bin_size
        hits: List[int] = [
            hit
            for score, hit in samples
            if (score >= start and (score < end or (start == 90 and score <= 100)))
        ]
        if not hits:
            continue
        prob = sum(hits) / len(hits)
        buckets.append(
            {
                "min": float(start),
                "max": float(end),
                "prob": round(prob, 4),
                "count": len(hits),
            }
        )
    return buckets


def parse_bins(spec: str) -> List[Tuple[float, float, str]]:
    out: List[Tuple[float, float, str]] = []
    for part in (s.strip() for s in spec.split(",") if s.strip()):
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                lo = float(a)
                hi = float(b)
                lbl = f"{lo:.2f}-{hi:.2f}"
                out.append((lo, hi, lbl))
            except Exception:
                continue
    if not out:
        out = [
            (0.0, 0.2, "0.00-0.20"),
            (0.2, 0.4, "0.20-0.40"),
            (0.4, 0.6, "0.40-0.60"),
            (0.6, 0.8, "0.60-0.80"),
            (0.8, 1.01, "0.80-1.00"),
        ]
    return out


def similar_days(
    days: List[DayMeta], target: DayMeta, open_tol: int, close_tol: int
) -> List[DayMeta]:
    out: List[DayMeta] = []
    for d in days:
        if d.date >= target.date:
            break
        if (
            abs(d.time_open.num - target.time_open.num) <= open_tol
            and abs(d.time_closed.num - target.time_closed.num) <= close_tol
        ):
            out.append(d)
    return out


def linreg(xs: List[float], ys: List[float]) -> Optional[Tuple[float, float]]:
    n = len(xs)
    if n < 2:
        return None
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    a = (n * sxy - sx * sy) / denom
    b = (sy - a * sx) / n
    return a, b


def main():
    ap = argparse.ArgumentParser(description="Estimator model calibration backtest")
    ap.add_argument("--db", required=True, help="Path to TagTracker SQLite database")
    ap.add_argument("--start", default="0000-00-00")
    ap.add_argument("--end", default="9999-12-31")
    ap.add_argument("--step-min", type=int, default=30)
    ap.add_argument(
        "--variance",
        type=int,
        default=15,
        help="Match tolerance for simple model (befores)",
    )
    ap.add_argument(
        "--zcut", type=float, default=2.5, help="Z-score trim for simple model"
    )
    ap.add_argument("--open-tol", type=int, default=15)
    ap.add_argument("--close-tol", type=int, default=15)
    ap.add_argument(
        "--recent-days",
        type=int,
        default=30,
        help="Recent window size for schedule-only model",
    )
    ap.add_argument("--time-bins", default="0-0.2,0.2-0.4,0.4-0.6,0.6-0.8,0.8-1.0")
    ap.add_argument(
        "--per-sample-csv", default="", help="Optional CSV path for per-sample outputs"
    )
    ap.add_argument(
        "--summary-csv", default="", help="Optional CSV path for per-bin summary"
    )
    ap.add_argument(
        "--output", default="", help="Write recommended JSON to this path (atomic)"
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout; only write JSON if --output is set",
    )
    ap.add_argument(
        "--recommended",
        action="store_true",
        help="Use recommended defaults and emit calibration JSON",
    )
    ap.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate DB reachability and schema, then exit 0/1",
    )
    ap.add_argument(
        "--backup",
        type=int,
        default=0,
        help="Keep N rotated backups of the JSON (file.json.1..N) before replace",
    )
    args = ap.parse_args()

    # Recommended-mode nudges
    if args.recommended:
        # If caller left some knobs at defaults, keep sensible recommended values
        if not args.time_bins:
            args.time_bins = "0-0.2,0.2-0.4,0.4-0.6,0.6-0.8,0.8-1.0"
        if not args.step_min:
            args.step_min = 30
        if not args.variance:
            args.variance = 15
        if not args.zcut:
            args.zcut = 2.5
        if not args.open_tol:
            args.open_tol = 15
        if not args.close_tol:
            args.close_tol = 15
        if not args.recent_days:
            args.recent_days = 30
        # Default lookback: 12 months if start/end not provided (left at full-range defaults)
        if (args.start == "0000-00-00" or not args.start) and (
            args.end == "9999-12-31" or not args.end
        ):
            today = datetime.now().date()
            start_dt = today - timedelta(days=365)
            args.start = start_dt.strftime("%Y-%m-%d")
            args.end = today.strftime("%Y-%m-%d")

    # If running in quiet mode without an output path, refuse to proceed
    if args.quiet and not args.output:
        print("(error) --quiet requires --output to be specified", file=sys.stderr)
        sys.exit(2)

    start_run = time.perf_counter()

    # Validate-only mode: check DB and schema, exit 0/1
    if args.validate_only:
        try:
            conn = db_connect(args.db)
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('DAY','VISIT')"
            )
            have = {r[0].upper() for r in cur.fetchall()}
            ok = "DAY" in have and "VISIT" in have
            conn.close()
            if not ok:
                print(
                    "(error) required tables DAY and VISIT not both present",
                    file=sys.stderr,
                )
                sys.exit(1)
            if not args.quiet:
                print("Validation OK: DB reachable and schema present (DAY, VISIT)")
            sys.exit(0)
        except SystemExit:
            raise
        except Exception as e:  # pylint:disable=broad-except
            print(f"(error) validation failed: {e}", file=sys.stderr)
            sys.exit(1)

    conn = db_connect(args.db)
    days = fetch_days(conn, args.start, args.end)
    visits_by_day = fetch_visits_by_day(conn, days)
    bins = parse_bins(args.time_bins)

    # Collect residuals per model/measure/bin
    # Key: (model, measure, bin_lbl) -> list of residuals
    resids: Dict[Tuple[str, str, str], List[float]] = {}
    # Also MAEs per model/measure/bin
    abserrs: Dict[Tuple[str, str, str], List[float]] = {}
    # Probability calibration samples: (score, hit) per key
    prob_samples: Dict[Tuple[str, str, str], List[Tuple[float, int]]] = {}

    # Optional per-sample writer
    sample_writer = None
    if args.per_sample_csv:
        try:
            fh = open(args.per_sample_csv, "w", newline="", encoding="utf-8")
            sample_writer = csv.writer(fh)
            sample_writer.writerow(
                [
                    "date",
                    "time",
                    "frac",
                    "model",
                    "measure",
                    "pred",
                    "truth",
                    "resid",
                    "abs_err",
                ]
            )
        except Exception as e:
            print(f"(warning) could not open per-sample CSV: {e}")
            sample_writer = None

    for idx, tgt in enumerate(days):
        # Rolling: similar days must be strictly earlier
        sims = similar_days(days[:idx], tgt, args.open_tol, args.close_tol)
        if not sims:
            continue
        v_tgt = visits_by_day.get(tgt.id, [])
        t = VTime(tgt.time_open.num)
        while t.num < tgt.time_closed.num:
            before, after_true, outs_to_t, ins_next_true, outs_next_true = (
                counts_for_time(v_tgt, t)
            )
            # Observed measures
            act_true = ins_next_true + outs_next_true
            peak_true, ptime_true = peak_all_day(v_tgt)
            # Frac elapsed
            span = max(1, tgt.time_closed.num - tgt.time_open.num)
            frac = max(0.0, min(1.0, (t.num - tgt.time_open.num) / span))
            # Which bin?
            bin_lbl = None
            for lo, hi, lbl in bins:
                if lo <= frac < hi:
                    bin_lbl = lbl
                    break
            if not bin_lbl:
                bin_lbl = bins[-1][2]

            # Build training arrays from sims at same wall-clock t
            befores: List[int] = []
            afters: List[int] = []
            acts: List[int] = []
            peaks: List[int] = []
            ptimes: List[int] = []
            for d in sims:
                v = visits_by_day.get(d.id, [])
                b, a, _o, insn, outn = counts_for_time(v, t)
                befores.append(int(b))
                afters.append(int(a))
                acts.append(int(insn + outn))
                p, pt = peak_all_day(v)
                peaks.append(int(p))
                ptimes.append(int(pt.num))

            def percentile_bounds_int(
                values: List[int],
            ) -> Tuple[Optional[int], Optional[int]]:
                if not values:
                    return None, None
                lo, hi = percentiles(values, 0.05, 0.95)
                if lo is None or hi is None:
                    return None, None
                return int(round(lo)), int(round(hi))

            rem_lo_sm, rem_hi_sm = percentile_bounds_int(afters)
            act_lo_sm, act_hi_sm = percentile_bounds_int(acts)
            peak_lo_sm, peak_hi_sm = percentile_bounds_int(peaks)
            pt_lo_sm, pt_hi_sm = percentile_bounds_int(ptimes)

            # Model 1: Similar-Days Median (with matching on |before - x| <= variance)
            def match_idxs(x: int) -> List[int]:
                return [
                    i
                    for i, b in enumerate(befores)
                    if abs(int(b) - int(x)) <= int(args.variance)
                ]

            midx = match_idxs(before)

            def med_at(idxs: List[int], arr: List[int]) -> Optional[int]:
                if not idxs:
                    return None
                vals = [arr[i] for i in idxs]
                return int(statistics.median(vals))

            pred_fut_sm = med_at(midx, afters)
            pred_act_sm = med_at(midx, acts)
            pred_peak_sm = med_at(midx, peaks)
            pred_ptime_sm = med_at(midx, ptimes)
            if pred_fut_sm is None and afters:
                pred_fut_sm = int(statistics.median(afters))
            if pred_act_sm is None and acts:
                pred_act_sm = int(statistics.median(acts))
            if pred_peak_sm is None and peaks:
                pred_peak_sm = int(statistics.median(peaks))
            if pred_ptime_sm is None and ptimes:
                pred_ptime_sm = int(statistics.median(ptimes))

            # Model 2: Linear Regression on sims
            fut_coeff_lr = linreg(
                [float(x) for x in befores], [float(y) for y in afters]
            )
            pred_fut_lr = None
            fut_res_lr: List[int] = []
            if fut_coeff_lr:
                a, b = fut_coeff_lr
                pred_fut_lr = int(round(a * float(before) + b))
                fut_res_lr = [
                    int(round(float(truth) - (a * float(x) + b)))
                    for x, truth in zip(befores, afters)
                ]

            act_coeff_lr = linreg([float(x) for x in befores], [float(y) for y in acts])
            pred_act_lr = None
            act_res_lr: List[int] = []
            if act_coeff_lr:
                a_act, b_act = act_coeff_lr
                pred_act_lr = int(round(a_act * float(before) + b_act))
                act_res_lr = [
                    int(round(float(truth) - (a_act * float(x) + b_act)))
                    for x, truth in zip(befores, acts)
                ]

            peak_coeff_lr = linreg(
                [float(x) for x in befores], [float(y) for y in peaks]
            )
            pred_peak_lr = None
            peak_res_lr: List[int] = []
            if peak_coeff_lr:
                a_pk, b_pk = peak_coeff_lr
                pred_peak_lr = int(round(a_pk * float(before) + b_pk))
                peak_res_lr = [
                    int(round(float(truth) - (a_pk * float(x) + b_pk)))
                    for x, truth in zip(befores, peaks)
                ]

            pred_ptime_lr = pred_ptime_sm

            # Model 3: Schedule-Only Recent (ignores before)
            rec_days = (
                sims[-args.recent_days :] if len(sims) > args.recent_days else sims[:]
            )

            rec_afters_vals: List[int] = []
            rec_acts_vals: List[int] = []
            rec_peaks_vals: List[int] = []
            rec_ptimes_vals: List[int] = []
            for d in rec_days:
                v = visits_by_day.get(d.id, [])
                _b_r, a_r, _o_r, ins_r, out_r = counts_for_time(v, t)
                rec_afters_vals.append(int(a_r))
                rec_acts_vals.append(int(ins_r + out_r))
                p_r, pt_r = peak_all_day(v)
                rec_peaks_vals.append(int(p_r))
                rec_ptimes_vals.append(int(pt_r.num))

            def med_recent(arr: List[int]) -> Optional[int]:
                return int(statistics.median(arr)) if arr else None

            pred_fut_rec = med_recent(rec_afters_vals)
            pred_act_rec = med_recent(rec_acts_vals)
            pred_peak_rec = med_recent(rec_peaks_vals)
            pred_ptime_rec = med_recent(rec_ptimes_vals)

            if pred_ptime_rec is None and rec_ptimes_vals:
                pred_ptime_rec = int(statistics.median(rec_ptimes_vals))

            if pred_fut_rec is None and pred_fut_sm is not None:
                pred_fut_rec = pred_fut_sm
            if pred_act_rec is None and pred_act_sm is not None:
                pred_act_rec = pred_act_sm
            if pred_peak_rec is None and pred_peak_sm is not None:
                pred_peak_rec = pred_peak_sm
            if pred_ptime_rec is None and pred_ptime_sm is not None:
                pred_ptime_rec = pred_ptime_sm

            # Model 4: Random Forest (if available and sufficient data)
            def rf_pred_with_res(
                xs: List[int], ys: List[int], x0: int
            ) -> Tuple[Optional[int], List[int]]:
                if not HAVE_RF or len(xs) < 2:
                    return None, []
                try:
                    X = (
                        np.array(xs, dtype=float).reshape(-1, 1)
                        if HAVE_NP
                        else [[float(x)] for x in xs]
                    )
                    y = np.array(ys, dtype=float) if HAVE_NP else [float(v) for v in ys]
                    model = RandomForestRegressor(
                        n_estimators=100,
                        random_state=0,
                        n_jobs=-1,
                    )
                    model.fit(X, y)
                    x0_arr = (
                        np.array([[float(x0)]], dtype=float)
                        if HAVE_NP
                        else [[float(x0)]]
                    )
                    pred = model.predict(x0_arr)[0]
                    preds_train = model.predict(X)
                    residuals = [
                        int(round(float(truth) - float(pred_hat)))
                        for truth, pred_hat in zip(ys, preds_train)
                    ]
                    return int(round(float(pred))), residuals
                except Exception:
                    return None, []

            pred_fut_rf, fut_res_rf = rf_pred_with_res(befores, afters, before)
            pred_act_rf, act_res_rf = rf_pred_with_res(befores, acts, before)
            pred_peak_rf, peak_res_rf = rf_pred_with_res(befores, peaks, before)

            # Utility for residual-based ranges
            def residual_bounds(
                residuals: List[int],
            ) -> Tuple[Optional[int], Optional[int]]:
                if not residuals:
                    return None, None
                lo, hi = percentiles(residuals, 0.05, 0.95)
                if lo is None or hi is None:
                    return None, None
                return int(round(lo)), int(round(hi))

            rem_lo_lr, rem_hi_lr = residual_bounds(fut_res_lr)
            act_lo_lr, act_hi_lr = residual_bounds(act_res_lr)
            peak_lo_lr, peak_hi_lr = residual_bounds(peak_res_lr)

            rem_lo_rf, rem_hi_rf = residual_bounds(fut_res_rf)
            act_lo_rf, act_hi_rf = residual_bounds(act_res_rf)
            peak_lo_rf, peak_hi_rf = residual_bounds(peak_res_rf)

            # Collect residuals per model/measure and probability samples
            def push(model: str, measure: str, pred: Optional[int], truth: int) -> None:
                if pred is None:
                    return
                key = (model, measure, bin_lbl)
                resid = float(pred - truth)
                resids.setdefault(key, []).append(resid)
                abserrs.setdefault(key, []).append(abs(resid))
                if sample_writer:
                    sample_writer.writerow(
                        [
                            tgt.date,
                            str(t),
                            f"{frac:.3f}",
                            model,
                            measure,
                            pred,
                            truth,
                            resid,
                            abs(resid),
                        ]
                    )

            # SM probability samples
            sm_n = len(sims)
            record_prob_sample(
                prob_samples,
                ("SM", "fut", bin_lbl),
                smooth_conf_score(
                    sm_n,
                    frac,
                    (
                        (rem_hi_sm - rem_lo_sm)
                        if (rem_hi_sm is not None and rem_lo_sm is not None)
                        else None
                    ),
                    (
                        max(
                            1.0,
                            float(
                                pred_fut_sm
                                if pred_fut_sm is not None
                                else rem_hi_sm or 0
                            ),
                        )
                        if rem_hi_sm is not None and rem_lo_sm is not None
                        else None
                    ),
                ),
                rem_lo_sm,
                rem_hi_sm,
                int(after_true),
            )
            record_prob_sample(
                prob_samples,
                ("SM", "act", bin_lbl),
                smooth_conf_score(
                    sm_n,
                    frac,
                    (
                        (act_hi_sm - act_lo_sm)
                        if (act_hi_sm is not None and act_lo_sm is not None)
                        else None
                    ),
                    (
                        max(
                            1.0,
                            float(
                                pred_act_sm
                                if pred_act_sm is not None
                                else act_hi_sm or 0
                            ),
                        )
                        if act_hi_sm is not None and act_lo_sm is not None
                        else None
                    ),
                ),
                act_lo_sm,
                act_hi_sm,
                int(act_true),
            )
            record_prob_sample(
                prob_samples,
                ("SM", "peak", bin_lbl),
                smooth_conf_score(
                    sm_n,
                    frac,
                    (
                        (peak_hi_sm - peak_lo_sm)
                        if (peak_hi_sm is not None and peak_lo_sm is not None)
                        else None
                    ),
                    (
                        max(
                            1.0,
                            float(
                                pred_peak_sm
                                if pred_peak_sm is not None
                                else peak_hi_sm or 0
                            ),
                        )
                        if peak_hi_sm is not None and peak_lo_sm is not None
                        else None
                    ),
                ),
                peak_lo_sm,
                peak_hi_sm,
                int(peak_true),
            )

            ptime_true_min = int(ptime_true.num) if ptime_true else None
            record_prob_sample(
                prob_samples,
                ("SM", "ptime", bin_lbl),
                smooth_conf_score(
                    sm_n,
                    frac,
                    (
                        (pt_hi_sm - pt_lo_sm)
                        if (pt_hi_sm is not None and pt_lo_sm is not None)
                        else None
                    ),
                    (
                        float(span)
                        if (pt_hi_sm is not None and pt_lo_sm is not None)
                        else None
                    ),
                ),
                pt_lo_sm,
                pt_hi_sm,
                ptime_true_min,
            )

            # LR probability samples
            lr_n = len(befores)
            record_prob_sample(
                prob_samples,
                ("LR", "fut", bin_lbl),
                smooth_conf_score(
                    lr_n,
                    frac,
                    (
                        (rem_hi_lr - rem_lo_lr)
                        if (rem_hi_lr is not None and rem_lo_lr is not None)
                        else None
                    ),
                    max(1.0, float(pred_fut_lr)) if pred_fut_lr is not None else None,
                ),
                (
                    (pred_fut_lr + rem_lo_lr)
                    if (pred_fut_lr is not None and rem_lo_lr is not None)
                    else None
                ),
                (
                    (pred_fut_lr + rem_hi_lr)
                    if (pred_fut_lr is not None and rem_hi_lr is not None)
                    else None
                ),
                int(after_true),
            )
            record_prob_sample(
                prob_samples,
                ("LR", "act", bin_lbl),
                smooth_conf_score(
                    lr_n,
                    frac,
                    (
                        (act_hi_lr - act_lo_lr)
                        if (act_hi_lr is not None and act_lo_lr is not None)
                        else None
                    ),
                    max(1.0, float(pred_act_lr)) if pred_act_lr is not None else None,
                ),
                (
                    (pred_act_lr + act_lo_lr)
                    if (pred_act_lr is not None and act_lo_lr is not None)
                    else None
                ),
                (
                    (pred_act_lr + act_hi_lr)
                    if (pred_act_lr is not None and act_hi_lr is not None)
                    else None
                ),
                int(act_true),
            )
            record_prob_sample(
                prob_samples,
                ("LR", "peak", bin_lbl),
                smooth_conf_score(
                    lr_n,
                    frac,
                    (
                        (peak_hi_lr - peak_lo_lr)
                        if (peak_hi_lr is not None and peak_lo_lr is not None)
                        else None
                    ),
                    max(1.0, float(pred_peak_lr)) if pred_peak_lr is not None else None,
                ),
                (
                    (pred_peak_lr + peak_lo_lr)
                    if (pred_peak_lr is not None and peak_lo_lr is not None)
                    else None
                ),
                (
                    (pred_peak_lr + peak_hi_lr)
                    if (pred_peak_lr is not None and peak_hi_lr is not None)
                    else None
                ),
                int(peak_true),
            )
            record_prob_sample(
                prob_samples,
                ("LR", "ptime", bin_lbl),
                smooth_conf_score(lr_n, frac, None, None),
                pt_lo_sm,
                pt_hi_sm,
                ptime_true_min,
            )

            # REC probability samples
            rec_n = len(rec_days)
            r_act_lo, r_act_hi = percentile_bounds_int(rec_acts_vals)
            r_rem_lo, r_rem_hi = percentile_bounds_int(rec_afters_vals)
            r_peak_lo, r_peak_hi = percentile_bounds_int(rec_peaks_vals)
            r_pt_lo, r_pt_hi = percentile_bounds_int(rec_ptimes_vals)

            record_prob_sample(
                prob_samples,
                ("REC", "fut", bin_lbl),
                smooth_conf_score(
                    rec_n,
                    frac,
                    (
                        (r_rem_hi - r_rem_lo)
                        if (r_rem_hi is not None and r_rem_lo is not None)
                        else None
                    ),
                    max(1.0, float(pred_fut_rec)) if pred_fut_rec is not None else None,
                ),
                r_rem_lo,
                r_rem_hi,
                int(after_true),
            )
            record_prob_sample(
                prob_samples,
                ("REC", "act", bin_lbl),
                smooth_conf_score(
                    rec_n,
                    frac,
                    (
                        (r_act_hi - r_act_lo)
                        if (r_act_hi is not None and r_act_lo is not None)
                        else None
                    ),
                    max(1.0, float(pred_act_rec)) if pred_act_rec is not None else None,
                ),
                r_act_lo,
                r_act_hi,
                int(act_true),
            )
            record_prob_sample(
                prob_samples,
                ("REC", "peak", bin_lbl),
                smooth_conf_score(
                    rec_n,
                    frac,
                    (
                        (r_peak_hi - r_peak_lo)
                        if (r_peak_hi is not None and r_peak_lo is not None)
                        else None
                    ),
                    (
                        max(1.0, float(pred_peak_rec))
                        if pred_peak_rec is not None
                        else None
                    ),
                ),
                r_peak_lo,
                r_peak_hi,
                int(peak_true),
            )
            record_prob_sample(
                prob_samples,
                ("REC", "ptime", bin_lbl),
                smooth_conf_score(
                    rec_n,
                    frac,
                    (
                        (r_pt_hi - r_pt_lo)
                        if (r_pt_hi is not None and r_pt_lo is not None)
                        else None
                    ),
                    (
                        float(span)
                        if (r_pt_hi is not None and r_pt_lo is not None)
                        else None
                    ),
                ),
                r_pt_lo,
                r_pt_hi,
                ptime_true_min,
            )

            # RF probability samples
            rf_n = len(befores)
            record_prob_sample(
                prob_samples,
                ("RF", "fut", bin_lbl),
                smooth_conf_score(
                    rf_n,
                    frac,
                    (
                        (rem_hi_rf - rem_lo_rf)
                        if (rem_hi_rf is not None and rem_lo_rf is not None)
                        else None
                    ),
                    max(1.0, float(pred_fut_rf)) if pred_fut_rf is not None else None,
                ),
                (
                    (pred_fut_rf + rem_lo_rf)
                    if (pred_fut_rf is not None and rem_lo_rf is not None)
                    else None
                ),
                (
                    (pred_fut_rf + rem_hi_rf)
                    if (pred_fut_rf is not None and rem_hi_rf is not None)
                    else None
                ),
                int(after_true),
            )
            record_prob_sample(
                prob_samples,
                ("RF", "act", bin_lbl),
                smooth_conf_score(
                    rf_n,
                    frac,
                    (
                        (act_hi_rf - act_lo_rf)
                        if (act_hi_rf is not None and act_lo_rf is not None)
                        else None
                    ),
                    max(1.0, float(pred_act_rf)) if pred_act_rf is not None else None,
                ),
                (
                    (pred_act_rf + act_lo_rf)
                    if (pred_act_rf is not None and act_lo_rf is not None)
                    else None
                ),
                (
                    (pred_act_rf + act_hi_rf)
                    if (pred_act_rf is not None and act_hi_rf is not None)
                    else None
                ),
                int(act_true),
            )
            record_prob_sample(
                prob_samples,
                ("RF", "peak", bin_lbl),
                smooth_conf_score(
                    rf_n,
                    frac,
                    (
                        (peak_hi_rf - peak_lo_rf)
                        if (peak_hi_rf is not None and peak_lo_rf is not None)
                        else None
                    ),
                    max(1.0, float(pred_peak_rf)) if pred_peak_rf is not None else None,
                ),
                (
                    (pred_peak_rf + peak_lo_rf)
                    if (pred_peak_rf is not None and peak_lo_rf is not None)
                    else None
                ),
                (
                    (pred_peak_rf + peak_hi_rf)
                    if (pred_peak_rf is not None and peak_hi_rf is not None)
                    else None
                ),
                int(peak_true),
            )
            record_prob_sample(
                prob_samples,
                ("RF", "ptime", bin_lbl),
                smooth_conf_score(rf_n, frac, None, None),
                pt_lo_sm,
                pt_hi_sm,
                ptime_true_min,
            )

            push("SM", "fut", pred_fut_sm, int(after_true))
            push("SM", "act", pred_act_sm, int(act_true))
            push("SM", "peak", pred_peak_sm, int(peak_true))

            push("LR", "fut", pred_fut_lr, int(after_true))
            push("LR", "act", pred_act_lr, int(act_true))
            push("LR", "peak", pred_peak_lr, int(peak_true))

            push("REC", "fut", pred_fut_rec, int(after_true))
            push("REC", "act", pred_act_rec, int(act_true))
            push("REC", "peak", pred_peak_rec, int(peak_true))

            push("RF", "fut", pred_fut_rf, int(after_true))
            push("RF", "act", pred_act_rf, int(act_true))
            push("RF", "peak", pred_peak_rf, int(peak_true))

            t = VTime(t.num + args.step_min)

    # Close sample file
    # noinspection PyBroadException
    try:
        if sample_writer and hasattr(sample_writer, "writerow"):
            fh = sample_writer  # type: ignore[assignment]
            pass
    except Exception:
        pass

    # Summaries per bin/model/measure
    measures = ["fut", "act", "peak"]
    models = ["SM", "LR", "REC", "RF"]

    # Optional summary CSV
    summ_writer = None
    if args.summary_csv:
        try:
            fh2 = open(args.summary_csv, "w", newline="", encoding="utf-8")
            summ_writer = csv.writer(fh2)
            summ_writer.writerow(
                ["bin", "model", "measure", "n", "MAE", "Q05", "Q50", "Q95"]
            )
        except Exception as e:
            print(f"(warning) could not open summary CSV: {e}")
            summ_writer = None

    if not args.quiet:
        print("\nResidual calibration by frac_elapsed bin (per model/measure):")
    for lo, hi, lbl in bins:
        if not args.quiet:
            print(f"\n== Bin {lbl} ==")
        for meas in measures:
            for mdl in models:
                k = (mdl, meas, lbl)
                errs = resids.get(k, [])
                if not errs:
                    if not args.quiet:
                        print(f"  {mdl}-{meas}: n=0")
                    if summ_writer:
                        summ_writer.writerow([lbl, mdl, meas, 0, "", "", "", ""])
                    continue
                mae = statistics.mean(abs(e) for e in errs)
                q05, q95 = percentiles(errs, 0.05, 0.95)
                q50 = statistics.median(errs)
                if not args.quiet:
                    print(
                        f"  {mdl}-{meas}: n={len(errs)}  MAE={mae:.2f}  Q05={q05:.2f}  Q50={q50:.2f}  Q95={q95:.2f}"
                    )
                if summ_writer:
                    summ_writer.writerow(
                        [
                            lbl,
                            mdl,
                            meas,
                            len(errs),
                            f"{mae:.3f}",
                            f"{q05:.3f}",
                            f"{q50:.3f}",
                            f"{q95:.3f}",
                        ]
                    )

        # Best model per measure for this bin
        if not args.quiet:
            print("  Best model (by MAE):")
        for meas in measures:
            best = None
            best_mae = 1e18
            for mdl in models:
                k = (mdl, meas, lbl)
                errs = abserrs.get(k, [])
                if not errs:
                    continue
                mae = statistics.mean(errs)
                if mae < best_mae:
                    best_mae = mae
                    best = mdl
            if best is None:
                if not args.quiet:
                    print(f"    {meas}: n=0")
            else:
                if not args.quiet:
                    print(f"    {meas}: {best} (MAE={best_mae:.2f})")

    # Close summary file
    # noinspection PyBroadException
    try:
        if summ_writer and hasattr(summ_writer, "writerow"):
            fh2.close()  # type: ignore[name-defined]
    except Exception:
        pass

    # In recommended mode, emit a suggested configuration JSON (filled for empty bins)
    if args.recommended:

        def fill_bin(values_map: Dict[Tuple[str, str, str], List[float]], bins_list):
            # For each (model,measure), ensure every bin has some proxy by borrowing nearest neighbor
            models = ["SM", "LR", "REC", "RF"]
            measures = ["fut", "act", "peak"]
            for mdl in models:
                for meas in measures:
                    # Collect indices with data
                    have = {
                        i
                        for i, (_lo, _hi, lbl) in enumerate(bins_list)
                        if values_map.get((mdl, meas, lbl))
                    }
                    if len(have) == len(bins_list):
                        continue
                    for i, (_lo, _hi, lbl) in enumerate(bins_list):
                        if (mdl, meas, lbl) in values_map and values_map[
                            (mdl, meas, lbl)
                        ]:
                            continue
                        # search outward
                        left = right = None
                        # left
                        for j in range(i - 1, -1, -1):
                            lbl2 = bins_list[j][2]
                            if values_map.get((mdl, meas, lbl2)):
                                left = lbl2
                                break
                        # right
                        for j in range(i + 1, len(bins_list)):
                            lbl2 = bins_list[j][2]
                            if values_map.get((mdl, meas, lbl2)):
                                right = lbl2
                                break
                        if left and right:
                            # average residual lists by simple concatenation
                            values_map[(mdl, meas, lbl)] = (
                                values_map[(mdl, meas, left)]
                                + values_map[(mdl, meas, right)]
                            )
                        elif left:
                            values_map[(mdl, meas, lbl)] = values_map[(mdl, meas, left)]
                        elif right:
                            values_map[(mdl, meas, lbl)] = values_map[
                                (mdl, meas, right)
                            ]
                        else:
                            # nothing anywhere: put empty to avoid KeyErrors
                            values_map[(mdl, meas, lbl)] = []

        # Make a working copy of residuals to fill
        res_work: Dict[Tuple[str, str, str], List[float]] = {
            k: list(v) for k, v in resids.items()
        }
        fill_bin(res_work, bins)

        # Build recommended config structure
        # Include the exact command-line args used in 'comment'
        _argv = " ".join(shlex.quote(a) for a in sys.argv[1:])
        # Git metadata (best-effort)
        git_commit = git_branch = None
        try:
            git_commit = (
                subprocess.check_output(
                    ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
                )
                .decode()
                .strip()
            )
            git_branch = (
                subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
        except Exception:
            pass
        duration_seconds = round(time.perf_counter() - start_run, 3)
        reco = {
            "time_bins": [lbl for _lo, _hi, lbl in bins],
            "models": ["SM", "LR", "REC", "RF"],
            "residual_bands": {},
            "best_model": {"fut": {}, "act": {}, "peak": {}},
            "probability_map": {},
            "probability_meta": {"bin_size": PROB_BIN_SIZE, "version": 1},
            "creation_date": datetime.now().isoformat(timespec="seconds"),
            "comment": f"helpers/estimator_calibrate_models.py args: {_argv}",
            "db_path": args.db,
            "window": {"start": args.start, "end": args.end},
            "duration_seconds": duration_seconds,
            "git": {"commit": git_commit, "branch": git_branch},
            "workers": getattr(args, "workers", 0),
        }
        # Residual bands per model/measure/bin
        for mdl in ["SM", "LR", "REC", "RF"]:
            reco["residual_bands"][mdl] = {}
            for meas in ["fut", "act", "peak"]:
                reco["residual_bands"][mdl][meas] = {}
                for _lo, _hi, lbl in bins:
                    errs = res_work.get((mdl, meas, lbl), [])
                    if errs:
                        q05, q95 = percentiles(errs, 0.05, 0.95)
                        reco["residual_bands"][mdl][meas][lbl] = {
                            "q05": round(q05, 2),
                            "q95": round(q95, 2),
                        }
                    else:
                        reco["residual_bands"][mdl][meas][lbl] = {
                            "q05": None,
                            "q95": None,
                        }
        # Best model per measure/bin by MAE (filled similarly)
        abs_work: Dict[Tuple[str, str, str], List[float]] = {
            k: list(v) for k, v in abserrs.items()
        }
        # Fill empties by borrowing neighbors
        fill_bin(abs_work, bins)
        for meas in ["fut", "act", "peak"]:
            for _lo, _hi, lbl in bins:
                best = None
                best_mae = 1e18
                for mdl in ["SM", "LR", "REC", "RF"]:
                    errs = abs_work.get((mdl, meas, lbl), [])
                    if not errs:
                        continue
                    mae = statistics.mean(errs)
                    if mae < best_mae:
                        best_mae = mae
                        best = mdl
                reco["best_model"][meas][lbl] = best

        prob_measures = ["fut", "act", "peak", "ptime"]
        for mdl in ["SM", "LR", "REC", "RF"]:
            reco["probability_map"][mdl] = {}
            for meas in prob_measures:
                reco["probability_map"][mdl][meas] = {}
                for _lo, _hi, lbl in bins:
                    samples = prob_samples.get((mdl, meas, lbl), [])
                    buckets = build_probability_bins(samples, bin_size=PROB_BIN_SIZE)
                    if buckets:
                        reco["probability_map"][mdl][meas][lbl] = buckets

        # Emit JSON: to file if --output given; else to stdout (unless --quiet)
        try:
            if args.output:
                out_tmp = args.output + ".new"
                # Write JSON
                with open(out_tmp, "w", encoding="utf-8") as fh:
                    json.dump(reco, fh, indent=2)
                # Validate JSON by re-opening
                with open(out_tmp, "r", encoding="utf-8") as fh:
                    _ = json.load(fh)
                # Rotate backups if requested
                if args.backup and os.path.exists(args.output):
                    try:
                        n = int(args.backup)
                        for i in range(n - 1, 0, -1):
                            older = f"{args.output}.{i}"
                            newer = f"{args.output}.{i+1}"
                            if os.path.exists(older):
                                os.replace(older, newer)
                        os.replace(args.output, f"{args.output}.1")
                    except Exception:
                        # Non-fatal; continue with replace
                        pass
                # Atomically publish
                os.replace(out_tmp, args.output)
            elif not args.quiet:
                print("\nBEGIN RECOMMENDED CONFIG JSON")
                print(json.dumps(reco, indent=2))
                print("END RECOMMENDED CONFIG JSON\n")
        except Exception as e:  # pylint:disable=broad-except
            print(f"(error) writing JSON: {e}")
            raise


if __name__ == "__main__":
    main()
