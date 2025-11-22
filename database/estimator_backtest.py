#!/usr/bin/env python3
"""Estimator backtesting framework for TagTracker.

This script evaluates several simple prediction models against the
historical SQLite database and reports reliability metrics for:
  - Further bikes (rest of day) given bikes_so_far at a time
  - Next-hour busyness (ins, outs, net)
  - Peak fullness (max occupancy from now until close)

It intentionally mirrors the logic used by web/web_estimator.py
but runs in a rolling backtest: each target day/time is predicted
using only prior days.

Usage:
  See the argument description in describe_args() below,
  or run the script with no arguments to print a short guide
  and the argparse help.

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
import csv
import math
import os
import re
import statistics
import sys
import sqlite3
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Callable
from datetime import datetime, timedelta, date

# Optional acceleration / numeric helpers
try:
    import numpy as np  # type: ignore
    HAVE_NP = True
except Exception:  # pragma: no cover
    HAVE_NP = False


@dataclass
class DayMeta:
    date: str
    time_open: "VTime"
    time_closed: "VTime"
    day_id: int


class VTime:
    """Simple HH:MM wrapper storing minutes since midnight with comparisons."""

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
            # Accept HH:MM or HH:MM:SS
            m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", s)
            if m:
                hh = int(m.group(1))
                mm = int(m.group(2))
                if 0 <= hh <= 24 and 0 <= mm <= 59:
                    self.num = min(hh * 60 + mm, 24 * 60)
            else:
                # allow HMM or HHMM
                m2 = re.fullmatch(r"(\d{1,2})(\d{2})", s)
                if m2:
                    hh = int(m2.group(1))
                    mm = int(m2.group(2))
                    if 0 <= hh <= 24 and 0 <= mm <= 59:
                        self.num = min(hh * 60 + mm, 24 * 60)
        # else leave as invalid (-1)

    def __bool__(self) -> bool:
        return 0 <= self.num <= 24 * 60

    def __lt__(self, other: "VTime") -> bool:
        return self.num < VTime(other).num

    def __le__(self, other: "VTime") -> bool:
        return self.num <= VTime(other).num

    def __gt__(self, other: "VTime") -> bool:
        return self.num > VTime(other).num

    def __ge__(self, other: "VTime") -> bool:
        return self.num >= VTime(other).num

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VTime):
            other = VTime(other)  # type: ignore[arg-type]
        return self.num == other.num

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __str__(self) -> str:
        if not self:
            return ""
        hh = self.num // 60
        mm = self.num % 60
        return f"{hh:02d}:{mm:02d}"

    @property
    def short(self) -> str:
        return str(self)


def db_connect(default_db: Optional[str]) -> sqlite3.Connection:
    dbfile = default_db or os.getenv("TAGTRACKER_DB")
    if not dbfile:
        print("Please provide --db path or set TAGTRACKER_DB environment variable", file=sys.stderr)
        sys.exit(2)
    if not os.path.exists(dbfile):
        print(f"Database file not found: {dbfile}", file=sys.stderr)
        sys.exit(2)
    try:
        conn = sqlite3.connect(dbfile)
        conn.row_factory = sqlite3.Row
        # sanity: ensure there is at least one table
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        _ = cur.fetchall()
    except sqlite3.Error as e:
        print(f"SQLite error opening DB: {e}", file=sys.stderr)
        sys.exit(2)
    return conn


def fetch_days(conn: sqlite3.Connection, start: str, end: str) -> List[DayMeta]:
    """Fetch candidate days with open/close times and ids within range."""
    sql = (
        "SELECT id, date, time_open, time_closed FROM DAY "
        "WHERE date >= ? AND date <= ? ORDER BY date ASC"
    )
    cur = conn.execute(sql, (start, end))
    out: List[DayMeta] = []
    for r in cur.fetchall():
        out.append(
            DayMeta(
                date=r["date"],
                time_open=VTime(r["time_open"]),
                time_closed=VTime(r["time_closed"]),
                day_id=int(r["id"]),
            )
        )
    return out


def fetch_visits(conn: sqlite3.Connection, day_id: int) -> List[Tuple[VTime, Optional[VTime]]]:
    """Return visits for a given day_id as (time_in, time_out) pairs."""
    sql = (
        "SELECT time_in, time_out FROM VISIT WHERE day_id = ? ORDER BY time_in ASC"
    )
    cur = conn.execute(sql, (day_id,))
    visits: List[Tuple[VTime, Optional[VTime]]] = []
    for r in cur.fetchall():
        tin = VTime(r["time_in"])
        tout = VTime(r["time_out"]) if r["time_out"] else None
        visits.append((tin, tout))
    return visits


def load_visits_for_days(
    conn: sqlite3.Connection, days: List["DayMeta"]
) -> Dict[int, List[Tuple[VTime, Optional[VTime]]]]:
    """Load visits for all days into memory once.

    This avoids per-target repeated database queries and greatly speeds up
    multi-suite runs.
    """
    by_day: Dict[int, List[Tuple[VTime, Optional[VTime]]]] = {}
    # Use a single query to pull all visits then bucket by day_id
    try:
        ids = tuple(d.day_id for d in days)
        if not ids:
            return by_day
        # SQLite cannot handle empty IN clauses; build safely
        qmarks = ",".join(["?"] * len(ids))
        sql = f"SELECT day_id, time_in, time_out FROM VISIT WHERE day_id IN ({qmarks}) ORDER BY day_id, time_in"
        cur = conn.execute(sql, ids)
        for row in cur.fetchall():
            did = int(row["day_id"]) if isinstance(row, sqlite3.Row) else int(row[0])
            tin = VTime(row["time_in"]) if isinstance(row, sqlite3.Row) else VTime(row[1])
            tout_raw = row["time_out"] if isinstance(row, sqlite3.Row) else row[2]
            tout = VTime(tout_raw) if tout_raw else None
            by_day.setdefault(did, []).append((tin, tout))
        return by_day
    except sqlite3.Error:
        # Fallback to per-day queries if the bulk query fails for any reason
        for d in days:
            by_day[d.day_id] = fetch_visits(conn, d.day_id)
        return by_day


def counts_for_time(visits: List[Tuple[VTime, Optional[VTime]]], t: VTime) -> Tuple[int, int, int, int, int]:
    """Compute counts relative to time t.

    Returns tuple:
      before_ins, after_ins, outs_up_to_t, ins_next_hr, outs_next_hr
    """
    t_end = VTime(min(t.num + 60, 24 * 60))
    before_ins = sum(1 for tin, _ in visits if tin and tin <= t)
    after_ins = sum(1 for tin, _ in visits if tin and tin > t)
    outs_up_to_t = sum(1 for _, tout in visits if tout and tout <= t)
    ins_next = sum(1 for tin, _ in visits if tin and t < tin <= t_end)
    outs_next = sum(1 for _, tout in visits if tout and t < tout <= t_end)
    return before_ins, after_ins, outs_up_to_t, ins_next, outs_next


def peak_future_occupancy(visits: List[Tuple[VTime, Optional[VTime]]], t: VTime, close: VTime) -> Tuple[int, VTime]:
    """Compute max occupancy from t to close and when it occurs.

    Occupancy at t is (#in<=t - #out<=t). Then walk events in (t, close].
    """
    occ_now = sum(1 for tin, _ in visits if tin and tin <= t) - sum(
        1 for _, tout in visits if tout and tout <= t
    )
    # Build event stream between t and close
    events: List[Tuple[int, int]] = []  # (time_min, delta)
    for tin, tout in visits:
        if tin and t < tin <= close:
            events.append((int(VTime(tin).num), +1))
        if tout and t < tout <= close:
            events.append((int(VTime(tout).num), -1))
    events.sort(key=lambda x: (x[0], -x[1]))  # ins before outs at same minute

    peak = occ_now
    peak_time = t
    occ = occ_now
    for tm, delta in events:
        occ += delta
        if occ > peak:
            peak = occ
            peak_time = VTime(tm)
    return peak, peak_time


def simple_match_prediction(
    train_pairs: List[Tuple[int, int]],  # (before, after)
    x: int,
    variance: int,
    zcut: float,
) -> Tuple[Optional[int], Optional[int], int, int]:
    """Predict further bikes with simple matching and trimming.

    Returns (mean, median, matched_count, trimmed_count_discarded)
    """
    matched = [after for before, after in train_pairs if abs(before - x) <= variance]
    n = len(matched)
    if n == 0:
        return None, None, 0, 0
    if n <= 2:
        mmean = int(statistics.mean(matched))
        mmed = int(statistics.median(matched))
        return mmean, mmed, n, 0
    mean = statistics.mean(matched)
    std = statistics.pstdev(matched) or 0.0
    if std == 0.0:
        trimmed = matched
    else:
        trimmed = [v for v in matched if abs((v - mean) / std) <= zcut]
    mmean = int(statistics.mean(trimmed)) if trimmed else int(mean)
    mmed = int(statistics.median(trimmed)) if trimmed else int(statistics.median(matched))
    return mmean, mmed, n, n - len(trimmed)


def lr_fit(train_pairs: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    """Fit y = a*x + b; return (a, b) or None if degenerate."""
    n = len(train_pairs)
    if n < 2:
        return None
    xs = [p[0] for p in train_pairs]
    ys = [p[1] for p in train_pairs]
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in train_pairs)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    a = (n * sxy - sx * sy) / denom
    b = (sy - a * sx) / n
    return a, b


def lr_predict(coeffs: Optional[Tuple[float, float]], x: float) -> Optional[int]:
    if not coeffs:
        return None
    a, b = coeffs
    return int(round(a * x + b))


def lr_fit_ridge(train_pairs: List[Tuple[float, float]], l2: float) -> Optional[Tuple[float, float]]:
    """Fit ridge regression y = a*x + b using centered variables.

    Uses closed-form with L2 on slope only: a = cov(x,y) / (var(x) + l2), b = ybar - a*xbar.
    """
    n = len(train_pairs)
    if n < 2:
        return None
    xs = [p[0] for p in train_pairs]
    ys = [p[1] for p in train_pairs]
    xbar = sum(xs) / n
    ybar = sum(ys) / n
    sxx = sum((x - xbar) * (x - xbar) for x in xs)
    sxy = sum((x - xbar) * (y - ybar) for x, y in train_pairs)
    denom = sxx + max(0.0, float(l2))
    if denom == 0:
        return None
    a = sxy / denom
    b = ybar - a * xbar
    return a, b


def summarize(writer: Callable[[str], None], name: str, errors: List[int]) -> None:
    """Write summary metrics for a list of absolute errors using writer."""
    if not errors:
        writer(f"{name}: no samples")
        return
    if HAVE_NP:
        arr = np.array(errors, dtype=float)
        mae = float(arr.mean())
        p50 = float(np.median(arr))
        p75 = float(np.quantile(arr, 0.75))
        p90 = float(np.quantile(arr, 0.90))
    else:
        mae = statistics.mean(errors)
        p50 = statistics.median(errors)
        try:
            p75 = statistics.quantiles(errors, n=4)[2]
        except Exception:
            p75 = p50
        try:
            p90 = statistics.quantiles(errors, n=10)[8]
        except Exception:
            p90 = p75
    writer(f"{name}: N={len(errors)}  MAE={mae:.2f}  Med={p50:.1f}  P75={p75:.1f}  P90={p90:.1f}")


def parse_time_bins(spec: Optional[str]) -> Optional[List[float]]:
    """Parse comma-separated fractional edges into a sorted list within [0,1]."""
    if not spec:
        return None
    try:
        edges = [float(s.strip()) for s in spec.split(",") if s.strip() != ""]
        edges = sorted(set(edges))
        if edges[0] > 0.0:
            edges = [0.0] + edges
        if edges[-1] < 1.0:
            edges = edges + [1.0]
        # Clamp within [0,1]
        edges = [max(0.0, min(1.0, e)) for e in edges]
        # Ensure strictly increasing
        out: List[float] = []
        for e in edges:
            if not out or e > out[-1]:
                out.append(e)
        if len(out) < 2:
            return None
        return out
    except Exception:
        return None


def bin_label(frac: float, edges: List[float]) -> str:
    """Return a label like '00-20' for bin containing frac in [0,1]."""
    f = max(0.0, min(1.0, float(frac)))
    for i in range(1, len(edges)):
        lo = edges[i - 1]
        hi = edges[i]
        # include lo, exclude hi except final bin
        if (f >= lo and f < hi) or (i == len(edges) - 1 and f == hi):
            return f"{int(round(lo*100)):02d}-{int(round(hi*100)):02d}"
    return "00-100"


def describe_args() -> str:
    """Return a human-friendly overview of key arguments and defaults."""
    lines = [
        "Core selection:",
        "  --db PATH             SQLite DB file (or TAGTRACKER_DB env var)",
        "  --start, --end       Date window YYYY-MM-DD (inclusive)",
        "  --step-min INT       Step in minutes between evaluations (default 60)",
        "  --variance INT       Similarity window on bikes_so_far (default 10)",
        "  --zcut FLOAT         Z-score trim cutoff for SM matching (default 2.5)",
        "  --schedule-exact     Match both open and close times (default: close only)",
        "  --lookback-days INT  Use only prior N days (0=all prior)",
        "  --compare-time-feature  Add 2D LR with time fraction",
        "",
        "Sweeps and output:",
        "  --lookback-grid CSV  Comma-separated lookbacks to run as a grid",
        "  --recommended        Run the preconfigured suite over the last year",
        "  --out-file PATH      Save suite output to a file (tee)",
        "",
        "Stability and diagnostics (optional; off by default):",
        "  --lr-min-n INT       Min matched cohort size for LR-before (e.g., 8)",
        "  --lr2-min-n INT      Min N for LR+time (e.g., 12)",
        "  --ridge-l2 FLOAT     L2 for LR slope (e.g., 1.0)",
        "  --ridge2-l2 FLOAT    L2 for LR+time slopes (e.g., 1.0)",
        "  --bound-preds        Clamp remainder/activity >= 0; peak <= capacity",
        "  --capacity INT       Capacity cap when bounding (default 180)",
        "  --time-bins CSV      Fraction edges for time bins, e.g., 0,0.2,0.4,0.6,0.8,1",
        "  --weekend-split      Print separate weekend vs weekday summaries",
        "  --per-sample-csv PATH  Write per-sample rows (single-run mode)",
    ]
    return "\n".join(lines)


def backtest(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    step_min: int,
    variance: int,
    zcut: float,
    schedule_exact: bool = True,
    lookback_days: Optional[int] = None,
    compare_time_feature: bool = False,
    result_writer: Optional[Callable[[str], None]] = None,
    visits_by_day: Optional[Dict[int, List[Tuple[VTime, Optional[VTime]]]]] = None,
    # New optional controls (default off to preserve behavior)
    lr_min_n: int = 0,
    lr2_min_n: int = 0,
    ridge_l2: float = 0.0,
    ridge2_l2: float = 0.0,
    bound_preds: bool = False,
    capacity: int = 180,
    time_bins: Optional[List[float]] = None,
    weekend_split: bool = False,
    per_sample_csv: Optional[str] = None,
) -> None:
    days = fetch_days(conn, start, end)
    if not days:
        print("No days in range")
        return
    # Preload visits for target days and all potential training days if not supplied
    if visits_by_day is None:
        visits_by_day = load_visits_for_days(conn, days)
    # Default result writer prints to screen when not provided
    if result_writer is None:
        def result_writer(s: str = "") -> None:  # type: ignore[no-redef]
            print(s)

    # Accumulators for overall metrics
    fut_abs_errs_sm: List[int] = []
    fut_abs_errs_lr1: List[int] = []
    fut_abs_errs_lr2: List[int] = []
    nxh_net_abs_errs: List[int] = []
    nxh_act_abs_errs_sm: List[int] = []
    nxh_act_abs_errs_lr1: List[int] = []
    nxh_act_abs_errs_lr2: List[int] = []
    peak_abs_errs_sm: List[int] = []
    peak_abs_errs_lr1: List[int] = []
    peak_abs_errs_lr2: List[int] = []
    cohort_sizes: List[int] = []
    samples = 0

    # Weekend/weekday splits
    fut_sm_we: List[int] = []; fut_sm_wd: List[int] = []
    fut_lr1_we: List[int] = []; fut_lr1_wd: List[int] = []
    fut_lr2_we: List[int] = []; fut_lr2_wd: List[int] = []
    nxh_net_we: List[int] = []; nxh_net_wd: List[int] = []
    nxh_act_sm_we: List[int] = []; nxh_act_sm_wd: List[int] = []
    nxh_act_lr1_we: List[int] = []; nxh_act_lr1_wd: List[int] = []
    nxh_act_lr2_we: List[int] = []; nxh_act_lr2_wd: List[int] = []
    peak_sm_we: List[int] = []; peak_sm_wd: List[int] = []
    peak_lr1_we: List[int] = []; peak_lr1_wd: List[int] = []
    peak_lr2_we: List[int] = []; peak_lr2_wd: List[int] = []

    # Time-bin error buckets
    def new_bin_dict() -> Dict[str, List[int]]:
        return {}
    fut_sm_bins: Dict[str, List[int]] = new_bin_dict()
    fut_lr1_bins: Dict[str, List[int]] = new_bin_dict()
    fut_lr2_bins: Dict[str, List[int]] = new_bin_dict()
    nxh_net_bins: Dict[str, List[int]] = new_bin_dict()
    nxh_act_sm_bins: Dict[str, List[int]] = new_bin_dict()
    nxh_act_lr1_bins: Dict[str, List[int]] = new_bin_dict()
    nxh_act_lr2_bins: Dict[str, List[int]] = new_bin_dict()
    peak_sm_bins: Dict[str, List[int]] = new_bin_dict()
    peak_lr1_bins: Dict[str, List[int]] = new_bin_dict()
    peak_lr2_bins: Dict[str, List[int]] = new_bin_dict()

    # Optional CSV writer
    csv_writer = None
    csv_file = None
    if per_sample_csv:
        try:
            csv_file = open(per_sample_csv, 'w', newline='', encoding='utf-8')
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow([
                'date','time','weekday','is_weekend','frac_elapsed','frac_bin',
                'before','after_true','nxh_net_true','nxh_act_true','peak_true',
                'pred_fut_sm','pred_fut_lr','pred_fut_lr2',
                'pred_act_sm','pred_act_lr','pred_act_lr2',
                'pred_peak_sm','pred_peak_lr','pred_peak_lr2',
                'N','lookback_days','variance','step_min','schedule_exact','time_feature'
            ])
        except Exception as e:
            print(f"(Warning) Could not open per-sample CSV '{per_sample_csv}': {e}")
            csv_writer = None

    for i, target in enumerate(days):
        # rolling training set: prior days only
        train_days = days[:i]
        # apply lookback window if provided
        if lookback_days and lookback_days > 0:
            try:
                tgt_dt = datetime.strptime(target.date, "%Y-%m-%d").date()
                cutoff = tgt_dt - timedelta(days=lookback_days)
                train_days = [d for d in train_days if datetime.strptime(d.date, "%Y-%m-%d").date() >= cutoff]
            except Exception:
                # If a date fails to parse, skip lookback filtering safely
                pass
        if not train_days:
            continue

        # Schedule filter: identical close (and open if required)
        def same_schedule(dm: DayMeta) -> bool:
            if schedule_exact:
                return dm.time_closed == target.time_closed and dm.time_open == target.time_open
            return dm.time_closed == target.time_closed

        train_days = [d for d in train_days if same_schedule(d)]
        if not train_days:
            continue

        # Fetch visits for train & target from cache
        target_visits = visits_by_day.get(target.day_id, [])

        t = VTime(target.time_open)
        while t < target.time_closed:
            # counts for target
            before, after_true, outs_to_t, ins_next_true, outs_next_true = counts_for_time(target_visits, t)
            frac_elapsed = 0.0
            total_span = max(1, target.time_closed.num - target.time_open.num)
            if t.num >= target.time_open.num:
                frac_elapsed = (t.num - target.time_open.num) / total_span
            # Build training pairs for further bikes
            train_pairs = []  # (before, after)
            nxh_pairs_net = []  # (before, next_hour_net)
            nxh_pairs_act = []  # (before, next_hour_activity)
            peaks_pairs = []  # (before, peak_future)
            train_pairs_2d = []  # ((before, frac_elapsed), after)
            nxh_pairs_act_2d = []  # ((before, frac_elapsed), activity)
            peaks_pairs_2d = []  # ((before, frac_elapsed), peak)
            for d in train_days:
                vlist = visits_by_day.get(d.day_id, [])
                b, a, _, ins_nxh, outs_nxh = counts_for_time(vlist, t)
                # compute fraction elapsed relative to that day's schedule
                tot = max(1, d.time_closed.num - d.time_open.num)
                f = 0.0
                if t.num >= d.time_open.num:
                    f = (t.num - d.time_open.num) / tot
                train_pairs.append((b, a))
                nxh_pairs_net.append((b, ins_nxh - outs_nxh))
                nxh_pairs_act.append((b, ins_nxh + outs_nxh))
                # peak future for that day
                p, _pt = peak_future_occupancy(vlist, t, d.time_closed)
                peaks_pairs.append((b, p))
                if compare_time_feature:
                    train_pairs_2d.append(((float(b), float(f)), float(a)))
                    nxh_pairs_act_2d.append(((float(b), float(f)), float(ins_nxh + outs_nxh)))
                    peaks_pairs_2d.append(((float(b), float(f)), float(p)))

            # Simple model
            sm_mean, sm_med, nmatch, _ = simple_match_prediction(train_pairs, before, variance, zcut)
            cohort_sizes.append(nmatch)

            # Linear regression (before -> after) with optional gating/ridge
            lr_pred = None
            if nmatch is not None and nmatch >= lr_min_n:
                coeffs1 = None
                if ridge_l2 and ridge_l2 > 0:
                    coeffs1 = lr_fit_ridge([(float(b), float(a)) for b, a in train_pairs], ridge_l2)
                else:
                    coeffs1 = lr_fit([(float(b), float(a)) for b, a in train_pairs])
                lr_pred = lr_predict(coeffs1, float(before))
            # 2D LR with time feature if requested
            lr2_pred = None
            if compare_time_feature and train_pairs_2d and (nmatch is not None and nmatch >= lr2_min_n):
                coeffs2 = None
                if ridge2_l2 and ridge2_l2 > 0:
                    coeffs2 = lr2_fit_ridge(train_pairs_2d, ridge2_l2)
                else:
                    coeffs2 = lr2_fit(train_pairs_2d)
                lr2_pred = lr2_predict(coeffs2, (float(before), float(frac_elapsed)))

            # Record model-specific errors
            # Optional bounds/clamps
            def clamp_nonneg(v: Optional[int]) -> Optional[int]:
                if v is None:
                    return None
                return max(0, int(v))
            def cap_peak(v: Optional[int]) -> Optional[int]:
                if v is None:
                    return None
                return min(int(v), int(capacity))

            # Determine weekend/weekday and time-bin label
            try:
                is_weekend = datetime.strptime(target.date, "%Y-%m-%d").weekday() >= 5
            except Exception:
                is_weekend = False
            bin_lbl = bin_label(frac_elapsed, time_bins) if time_bins else None

            # Further-bikes errors
            pf_sm = clamp_nonneg(sm_med) if bound_preds else (int(sm_med) if sm_med is not None else None)
            if pf_sm is not None:
                e = abs(pf_sm - int(after_true))
                fut_abs_errs_sm.append(e)
                if weekend_split:
                    (fut_sm_we if is_weekend else fut_sm_wd).append(e)
                if bin_lbl is not None:
                    fut_sm_bins.setdefault(bin_lbl, []).append(e)
            if lr_pred is not None:
                pf_lr = clamp_nonneg(lr_pred) if bound_preds else int(lr_pred)
                e = abs(pf_lr - int(after_true))
                fut_abs_errs_lr1.append(e)
                if weekend_split:
                    (fut_lr1_we if is_weekend else fut_lr1_wd).append(e)
                if bin_lbl is not None:
                    fut_lr1_bins.setdefault(bin_lbl, []).append(e)
            if lr2_pred is not None:
                pf_lr2 = clamp_nonneg(lr2_pred) if bound_preds else int(lr2_pred)
                e = abs(pf_lr2 - int(after_true))
                fut_abs_errs_lr2.append(e)
                if weekend_split:
                    (fut_lr2_we if is_weekend else fut_lr2_wd).append(e)
                if bin_lbl is not None:
                    fut_lr2_bins.setdefault(bin_lbl, []).append(e)

            # Next-hour predictions (net and activity)
            nxh_matched_net = [net for b, net in nxh_pairs_net if abs(b - before) <= variance]
            nxh_matched_act = [act for b, act in nxh_pairs_act if abs(b - before) <= variance]
            if nxh_matched_net:
                pred_net = int(statistics.median(nxh_matched_net))
                e = abs(pred_net - (ins_next_true - outs_next_true))
                nxh_net_abs_errs.append(e)
                if weekend_split:
                    (nxh_net_we if is_weekend else nxh_net_wd).append(e)
                if bin_lbl is not None:
                    nxh_net_bins.setdefault(bin_lbl, []).append(e)
            if nxh_matched_act:
                pred_act_sm = int(statistics.median(nxh_matched_act))
                if bound_preds:
                    pred_act_sm = max(0, pred_act_sm)
                e = abs(pred_act_sm - (ins_next_true + outs_next_true))
                nxh_act_abs_errs_sm.append(e)
                if weekend_split:
                    (nxh_act_sm_we if is_weekend else nxh_act_sm_wd).append(e)
                if bin_lbl is not None:
                    nxh_act_sm_bins.setdefault(bin_lbl, []).append(e)
            # LR for activity
            lr_act = lr_fit([(float(b), float(a)) for b, a in nxh_pairs_act])
            pred_act_lr1 = lr_predict(lr_act, float(before))
            if pred_act_lr1 is not None:
                if bound_preds:
                    pred_act_lr1 = max(0, int(pred_act_lr1))
                e = abs(int(pred_act_lr1) - (ins_next_true + outs_next_true))
                nxh_act_abs_errs_lr1.append(e)
                if weekend_split:
                    (nxh_act_lr1_we if is_weekend else nxh_act_lr1_wd).append(e)
                if bin_lbl is not None:
                    nxh_act_lr1_bins.setdefault(bin_lbl, []).append(e)
            if compare_time_feature and nxh_pairs_act_2d:
                lr2_act = lr2_fit(nxh_pairs_act_2d)
                pred_act_lr2 = lr2_predict(lr2_act, (float(before), float(frac_elapsed)))
                if pred_act_lr2 is not None:
                    if bound_preds:
                        pred_act_lr2 = max(0, int(pred_act_lr2))
                    e = abs(int(pred_act_lr2) - (ins_next_true + outs_next_true))
                    nxh_act_abs_errs_lr2.append(e)
                    if weekend_split:
                        (nxh_act_lr2_we if is_weekend else nxh_act_lr2_wd).append(e)
                    if bin_lbl is not None:
                        nxh_act_lr2_bins.setdefault(bin_lbl, []).append(e)

            # Peak fullness from now to close (median across matched days)
            # Compute target peak
            peak_true, _ = peak_future_occupancy(target_visits, t, target.time_closed)
            # Compute per-day peaks for matched days
            peaks = []
            for d in train_days:
                vlist = visits_by_day.get(d.day_id, [])
                b, _a, *_rest = counts_for_time(vlist, t)
                if abs(b - before) <= variance:
                    p, _pt = peak_future_occupancy(vlist, t, d.time_closed)
                    peaks.append(p)
            if peaks:
                pred_peak_sm = int(statistics.median(peaks))
                if bound_preds:
                    pred_peak_sm = cap_peak(pred_peak_sm)
                e = abs(pred_peak_sm - peak_true)
                peak_abs_errs_sm.append(e)
                if weekend_split:
                    (peak_sm_we if is_weekend else peak_sm_wd).append(e)
                if bin_lbl is not None:
                    peak_sm_bins.setdefault(bin_lbl, []).append(e)
            # LR1 for peak
            lr_peak = lr_fit([(float(b), float(p)) for b, p in peaks_pairs])
            pred_peak_lr1 = lr_predict(lr_peak, float(before))
            if pred_peak_lr1 is not None:
                pp1 = int(pred_peak_lr1)
                if bound_preds:
                    pp1 = cap_peak(pp1)
                e = abs(pp1 - peak_true)
                peak_abs_errs_lr1.append(e)
                if weekend_split:
                    (peak_lr1_we if is_weekend else peak_lr1_wd).append(e)
                if bin_lbl is not None:
                    peak_lr1_bins.setdefault(bin_lbl, []).append(e)
            if compare_time_feature and peaks_pairs_2d:
                lr2_peak = lr2_fit(peaks_pairs_2d)
                pred_peak_lr2 = lr2_predict(lr2_peak, (float(before), float(frac_elapsed)))
                if pred_peak_lr2 is not None:
                    pp2 = int(pred_peak_lr2)
                    if bound_preds:
                        pp2 = cap_peak(pp2)
                    e = abs(pp2 - peak_true)
                    peak_abs_errs_lr2.append(e)
                    if weekend_split:
                        (peak_lr2_we if is_weekend else peak_lr2_wd).append(e)
                    if bin_lbl is not None:
                        peak_lr2_bins.setdefault(bin_lbl, []).append(e)

            # CSV row
            if csv_writer is not None:
                hh = t.num // 60; mm = t.num % 60
                csv_writer.writerow([
                    target.date, f"{hh:02d}:{mm:02d}",
                    datetime.strptime(target.date, "%Y-%m-%d").weekday() + 1,
                    1 if is_weekend else 0,
                    round(frac_elapsed, 4), bin_lbl or "",
                    before, int(after_true), int(ins_next_true - outs_next_true), int(ins_next_true + outs_next_true), int(peak_true),
                    pf_sm if pf_sm is not None else "",
                    (clamp_nonneg(lr_pred) if (bound_preds and lr_pred is not None) else (int(lr_pred) if lr_pred is not None else "")),
                    (clamp_nonneg(lr2_pred) if (bound_preds and lr2_pred is not None) else (int(lr2_pred) if lr2_pred is not None else "")),
                    (max(0, pred_act_sm) if (nxh_matched_act and bound_preds) else (pred_act_sm if nxh_matched_act else "")),
                    (max(0, int(pred_act_lr1)) if (pred_act_lr1 is not None and bound_preds) else (int(pred_act_lr1) if pred_act_lr1 is not None else "")),
                    (max(0, int(pred_act_lr2)) if (compare_time_feature and 'pred_act_lr2' in locals() and pred_act_lr2 is not None and bound_preds) else (int(pred_act_lr2) if (compare_time_feature and 'pred_act_lr2' in locals() and pred_act_lr2 is not None) else "")),
                    pred_peak_sm if peaks else "",
                    (pp1 if 'pp1' in locals() and pred_peak_lr1 is not None else (int(pred_peak_lr1) if pred_peak_lr1 is not None else "")),
                    (pp2 if 'pp2' in locals() and pred_peak_lr2 is not None else (int(pred_peak_lr2) if pred_peak_lr2 is not None else "")),
                    nmatch, (lookback_days or 0), variance, step_min, int(bool(schedule_exact)), int(bool(compare_time_feature))
                ])

            samples += 1
            t = VTime(min(t.num + step_min, target.time_closed.num))

        # Lightweight progress within backtest per target day
        if (i + 1) % 20 == 0 or (i + 1) == len(days):
            print(f"  ... processed {i+1}/{len(days)} target days in this suite")

    # -----------------
    # Write results out
    result_writer(f"Samples evaluated: {samples}")
    if cohort_sizes:
        try:
            med_n = statistics.median(cohort_sizes)
            p25_n = statistics.quantiles(cohort_sizes, n=4)[0]
            p75_n = statistics.quantiles(cohort_sizes, n=4)[2]
            result_writer(f"Matched cohort size (N) per sample: Med={med_n:.0f}  P25={p25_n:.0f}  P75={p75_n:.0f}")
        except Exception:
            pass

    result_writer("")
    result_writer("Further-bikes absolute error (rest of day):")
    summarize(result_writer, "  SM median", fut_abs_errs_sm)
    summarize(result_writer, "  LR before", fut_abs_errs_lr1)
    if compare_time_feature:
        summarize(result_writer, "  LR before+time", fut_abs_errs_lr2)

    result_writer("")
    result_writer("Next-hour predictions (net and activity):")
    summarize(result_writer, "  Next-hour net (SM median)", nxh_net_abs_errs)
    summarize(result_writer, "  Activity (SM median)", nxh_act_abs_errs_sm)
    summarize(result_writer, "  Activity (LR before)", nxh_act_abs_errs_lr1)
    if compare_time_feature:
        summarize(result_writer, "  Activity (LR before+time)", nxh_act_abs_errs_lr2)

    result_writer("")
    result_writer("Peak-future occupancy absolute error (from now to close):")
    summarize(result_writer, "  SM median", peak_abs_errs_sm)
    summarize(result_writer, "  LR before", peak_abs_errs_lr1)
    if compare_time_feature:
        summarize(result_writer, "  LR before+time", peak_abs_errs_lr2)

    # Optional weekend/weekday splits
    if weekend_split:
        result_writer("")
        result_writer("Weekend vs Weekday splits:")
        summarize(result_writer, "  Further SM (WE)", fut_sm_we)
        summarize(result_writer, "  Further SM (WD)", fut_sm_wd)
        summarize(result_writer, "  Further LR (WE)", fut_lr1_we)
        summarize(result_writer, "  Further LR (WD)", fut_lr1_wd)
        if compare_time_feature:
            summarize(result_writer, "  Further LR+time (WE)", fut_lr2_we)
            summarize(result_writer, "  Further LR+time (WD)", fut_lr2_wd)
        summarize(result_writer, "  Next-hour net (WE)", nxh_net_we)
        summarize(result_writer, "  Next-hour net (WD)", nxh_net_wd)
        summarize(result_writer, "  Activity SM (WE)", nxh_act_sm_we)
        summarize(result_writer, "  Activity SM (WD)", nxh_act_sm_wd)
        summarize(result_writer, "  Activity LR (WE)", nxh_act_lr1_we)
        summarize(result_writer, "  Activity LR (WD)", nxh_act_lr1_wd)
        if compare_time_feature:
            summarize(result_writer, "  Activity LR+time (WE)", nxh_act_lr2_we)
            summarize(result_writer, "  Activity LR+time (WD)", nxh_act_lr2_wd)
        summarize(result_writer, "  Peak SM (WE)", peak_sm_we)
        summarize(result_writer, "  Peak SM (WD)", peak_sm_wd)
        summarize(result_writer, "  Peak LR (WE)", peak_lr1_we)
        summarize(result_writer, "  Peak LR (WD)", peak_lr1_wd)
        if compare_time_feature:
            summarize(result_writer, "  Peak LR+time (WE)", peak_lr2_we)
            summarize(result_writer, "  Peak LR+time (WD)", peak_lr2_wd)

    # Optional time-bin summaries
    if time_bins:
        result_writer("")
        result_writer("Time-of-day bin summaries:")
        labels = sorted(set(list(fut_sm_bins.keys()) + list(fut_lr1_bins.keys()) + list(fut_lr2_bins.keys()) +
                             list(nxh_net_bins.keys()) + list(nxh_act_sm_bins.keys()) + list(nxh_act_lr1_bins.keys()) + list(nxh_act_lr2_bins.keys()) +
                             list(peak_sm_bins.keys()) + list(peak_lr1_bins.keys()) + list(peak_lr2_bins.keys())))
        for lbl in labels:
            result_writer("")
            result_writer(f"  Bin {lbl}:")
            summarize(result_writer, "    Further SM", fut_sm_bins.get(lbl, []))
            summarize(result_writer, "    Further LR", fut_lr1_bins.get(lbl, []))
            if compare_time_feature:
                summarize(result_writer, "    Further LR+time", fut_lr2_bins.get(lbl, []))
            summarize(result_writer, "    Next-hour net", nxh_net_bins.get(lbl, []))
            summarize(result_writer, "    Activity SM", nxh_act_sm_bins.get(lbl, []))
            summarize(result_writer, "    Activity LR", nxh_act_lr1_bins.get(lbl, []))
            if compare_time_feature:
                summarize(result_writer, "    Activity LR+time", nxh_act_lr2_bins.get(lbl, []))
            summarize(result_writer, "    Peak SM", peak_sm_bins.get(lbl, []))
            summarize(result_writer, "    Peak LR", peak_lr1_bins.get(lbl, []))
            if compare_time_feature:
                summarize(result_writer, "    Peak LR+time", peak_lr2_bins.get(lbl, []))

    # Close CSV if in use
    try:
        if csv_file:
            csv_file.flush(); csv_file.close()
    except Exception:
        pass




def main():
    parser = argparse.ArgumentParser(description="Backtest TagTracker estimator models")
    parser.add_argument("--db", required=False, help="SQLite DB file (or set TAGTRACKER_DB env var)")
    parser.add_argument("--start", default="0000-00-00", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="9999-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--step-min", type=int, default=60, help="Step minutes between evaluations (default 60)")
    parser.add_argument("--variance", type=int, default=10, help="Similarity window on bikes_so_far (default 10)")
    parser.add_argument("--zcut", type=float, default=2.5, help="Z-score cut-off for trimming (default 2.5)")
    parser.add_argument("--schedule-exact", action="store_true", help="Match both open and close times (default: close only)")
    parser.add_argument("--lookback-days", type=int, default=0, help="Only use training data within N days before each target day (0=all prior)")
    parser.add_argument("--compare-time-feature", action="store_true", help="Fit additional 2D LR using (before, fraction_elapsed)")
    parser.add_argument("--lookback-grid", type=str, default="", help="Comma-separated list of lookback-days values to compare (overrides --lookback-days)")
    parser.add_argument("--recommended", action="store_true", help="Run the recommended test suite for model/parameter assessment")
    parser.add_argument("--out-file", default="", help="Path to save full output (tee to screen and file)")
    # New optional controls (default off to preserve behavior)
    parser.add_argument("--lr-min-n", type=int, default=0, help="Minimum matched cohort size to fit/predict LR (default 0=disabled)")
    parser.add_argument("--lr2-min-n", type=int, default=0, help="Minimum matched cohort size to fit/predict LR+time (default 0=disabled)")
    parser.add_argument("--ridge-l2", type=float, default=0.0, help="L2 regularization for LR slope (default 0.0)")
    parser.add_argument("--ridge2-l2", type=float, default=0.0, help="L2 regularization for LR+time slopes (default 0.0)")
    parser.add_argument("--bound-preds", action="store_true", help="Clamp predictions (remainder/activity >= 0; peak <= capacity)")
    parser.add_argument("--capacity", type=int, default=180, help="Capacity cap used when --bound-preds is set (default 180)")
    parser.add_argument("--time-bins", type=str, default="", help="Comma-separated fractional edges in [0,1] for time-of-day bins (e.g., 0,0.2,0.4,0.6,0.8,1)")
    parser.add_argument("--per-sample-csv", type=str, default="", help="Write per-sample CSV to this path (single-run mode)")
    parser.add_argument("--weekend-split", action="store_true", help="Also print weekend vs weekday summaries")
    # If run with no args, print a short guide and argparse help
    if len(sys.argv) == 1:
        print("Estimator Backtest — argument overview:\n")
        print(describe_args())
        print("\nArgparse help:\n")
        parser.print_help()
        return

    args = parser.parse_args()

    # Recommended test suite: fixed DB + date window and several parameter sweeps
    if args.recommended:
        # Fixed inputs per request
        dbfile = args.db or "bikedata.db"
        conn = db_connect(dbfile)
        start = "2024-09-11"
        end = "2025-09-10"

        # Results output file; progress remains on screen
        out_path = args.out_file or f"estimator_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            f_out = open(out_path, 'w', encoding='utf-8')
            def outln(s: str = "") -> None:
                f_out.write(s + "\n"); f_out.flush()
            print(f"Output will be saved to: {out_path}")
        except Exception as e:
            print(f"(Warning) Could not open out-file '{out_path}': {e}")
            f_out = None
            def outln(s: str = "") -> None:
                pass

        # Report DB and window record counts
        try:
            total_days = conn.execute("SELECT COUNT(*) FROM DAY").fetchone()[0]
        except sqlite3.Error:
            total_days = 0
        try:
            total_visits = conn.execute("SELECT COUNT(*) FROM VISIT").fetchone()[0]
        except sqlite3.Error:
            total_visits = 0
        try:
            win_days = conn.execute(
                "SELECT COUNT(*) FROM DAY WHERE date >= ? AND date <= ?",
                (start, end),
            ).fetchone()[0]
        except sqlite3.Error:
            win_days = 0
        try:
            win_visits = conn.execute(
                "SELECT COUNT(*) FROM VISIT WHERE day_id IN (SELECT id FROM DAY WHERE date >= ? AND date <= ?)",
                (start, end),
            ).fetchone()[0]
        except sqlite3.Error:
            win_visits = 0

        outln(f"Database totals: {total_days} days, {total_visits} visits")
        outln(f"Testing window {start}..{end}: {win_days} days, {win_visits} visits")

        # Recommended: single suite for faster run
        # step=60, variance=15, lookback=365, schedule_exact=YES, time_feature=ON
        print("\n" + "#" * 80)
        print("Recommended suite | step=60 | variance=15 | schedule_exact=YES | lookback=365 | time_feature=ON")

        outln("")
        outln("#" * 80)
        outln("Recommended suite | step=60 | variance=15 | schedule_exact=YES | lookback=365 | time_feature=ON")
        outln("=" * 72)
        outln("Single fixed configuration as above")

        # Preload visits once for this window and reuse
        days_window = fetch_days(conn, start, end)
        visits_cache = load_visits_for_days(conn, days_window)

        backtest(
            conn,
            start=start,
            end=end,
            step_min=60,
            variance=15,
            zcut=args.zcut,
            schedule_exact=True,
            lookback_days=365,
            compare_time_feature=True,
            result_writer=outln,
            visits_by_day=visits_cache,
            lr_min_n=args.lr_min_n,
            lr2_min_n=args.lr2_min_n,
            ridge_l2=args.ridge_l2,
            ridge2_l2=args.ridge2_l2,
            bound_preds=args.bound_preds,
            capacity=args.capacity,
            time_bins=parse_time_bins(args.time_bins),
            weekend_split=args.weekend_split,
        )
        # Restore stdout if we teed it
        try:
            if f_out:
                f_out.flush(); f_out.close()
        except Exception:
            pass
        return

    # Normal single/grid run path
    conn = db_connect(args.db)
    start = normalize_date(args.start) or "0000-00-00"
    end = normalize_date(args.end) or "9999-12-31"

    # Report DB and window record counts
    try:
        total_days = conn.execute("SELECT COUNT(*) FROM DAY").fetchone()[0]
    except sqlite3.Error:
        total_days = 0
    try:
        total_visits = conn.execute("SELECT COUNT(*) FROM VISIT").fetchone()[0]
    except sqlite3.Error:
        total_visits = 0
    try:
        win_days = conn.execute(
            "SELECT COUNT(*) FROM DAY WHERE date >= ? AND date <= ?",
            (start, end),
        ).fetchone()[0]
    except sqlite3.Error:
        win_days = 0
    try:
        win_visits = conn.execute(
            "SELECT COUNT(*) FROM VISIT WHERE day_id IN (SELECT id FROM DAY WHERE date >= ? AND date <= ?)",
            (start, end),
        ).fetchone()[0]
    except sqlite3.Error:
        win_visits = 0

    print(f"Database totals: {total_days} days, {total_visits} visits")
    print(f"Testing window {start}..{end}: {win_days} days, {win_visits} visits")
    grid = [v for v in (s.strip() for s in args.lookback_grid.split(",")) if v]
    if grid:
        print(f"Comparing lookback windows: {', '.join(grid)} (days)")
        for gb in grid:
            try:
                lb = int(gb)
            except ValueError:
                print(f"  Skipping invalid lookback '{gb}'")
                continue
            print("\n" + "=" * 72)
            print(f"Lookback {lb} days  |  schedule_exact={'yes' if args.schedule_exact else 'no'}  |  time_feature={'on' if args.compare_time_feature else 'off'}")
            backtest(
                conn,
                start=start,
                end=end,
                step_min=args.step_min,
                variance=args.variance,
                zcut=args.zcut,
                schedule_exact=args.schedule_exact,
                lookback_days=lb,
                compare_time_feature=args.compare_time_feature,
                lr_min_n=args.lr_min_n,
                lr2_min_n=args.lr2_min_n,
                ridge_l2=args.ridge_l2,
                ridge2_l2=args.ridge2_l2,
                bound_preds=args.bound_preds,
                capacity=args.capacity,
                time_bins=parse_time_bins(args.time_bins),
                weekend_split=args.weekend_split,
                per_sample_csv=(args.per_sample_csv or None),
            )
    else:
        backtest(
            conn,
            start=start,
            end=end,
            step_min=args.step_min,
            variance=args.variance,
            zcut=args.zcut,
            schedule_exact=args.schedule_exact,
            lookback_days=args.lookback_days,
            compare_time_feature=args.compare_time_feature,
            lr_min_n=args.lr_min_n,
            lr2_min_n=args.lr2_min_n,
            ridge_l2=args.ridge_l2,
            ridge2_l2=args.ridge2_l2,
            bound_preds=args.bound_preds,
            capacity=args.capacity,
            time_bins=parse_time_bins(args.time_bins),
            weekend_split=args.weekend_split,
            per_sample_csv=(args.per_sample_csv or None),
        )


# --- Multiple linear regression (2D) helpers (standalone, no numpy) ---
def lr2_fit(pairs: List[Tuple[Tuple[float, float], float]]) -> Optional[Tuple[float, float, float]]:
    """Fit y = a*x + b*z + c using normal equations.

    Returns (a, b, c) or None if degenerate.
    """
    n = len(pairs)
    if n < 3:
        return None
    sx = sum(x for (x, _), _y in pairs)
    sz = sum(z for (_, z), _y in pairs)
    sy = sum(y for _xz, y in pairs)
    sxx = sum(x * x for (x, _), _y in pairs)
    szz = sum(z * z for (_, z), _y in pairs)
    sxz = sum(x * z for (x, z), _y in pairs)
    sxy = sum(x * y for (x, _), y in pairs)
    szy = sum(z * y for (_, z), y in pairs)
    # Solve the 3x3 linear system:
    # [ sxx  sxz  sx ] [a] = [sxy]
    # [ sxz  szz  sz ] [b]   [szy]
    # [ sx   sz   n  ] [c]   [ sy]
    # via Cramer's rule or manual adjugate (keep it simple):
    det = (
        sxx * (szz * n - sz * sz)
        - sxz * (sxz * n - sx * sz)
        + sx * (sxz * sz - szz * sx)
    )
    if det == 0:
        return None
    det_a = (
        sxy * (szz * n - sz * sz)
        - sxz * (szy * n - sy * sz)
        + sx * (szy * sz - szz * sy)
    )
    det_b = (
        sxx * (szy * n - sy * sz)
        - sxy * (sxz * n - sx * sz)
        + sx * (sxz * sy - sxy * sz)
    )
    det_c = (
        sxx * (szz * sy - szy * sz)
        - sxz * (sxz * sy - sxy * sz)
        + sxy * (sxz * sz - szz * sx)
    )
    a = det_a / det
    b = det_b / det
    c = det_c / det
    return a, b, c


def lr2_predict(coeffs: Optional[Tuple[float, float, float]], xz: Tuple[float, float]) -> Optional[int]:
    if not coeffs:
        return None
    a, b, c = coeffs
    x, z = xz
    return int(round(a * x + b * z + c))


def lr2_fit_ridge(
    pairs: List[Tuple[Tuple[float, float], float]], l2: float
) -> Optional[Tuple[float, float, float]]:
    """Fit y = a*x + b*z + c with L2 on a and b via modified normal equations.

    Adds l2 to diagonal terms for a and b (not intercept c).
    """
    n = len(pairs)
    if n < 3:
        return None
    sx = sum(x for (x, _), _y in pairs)
    sz = sum(z for (_, z), _y in pairs)
    sy = sum(y for _xz, y in pairs)
    sxx = sum(x * x for (x, _), _y in pairs) + max(0.0, float(l2))
    szz = sum(z * z for (_, z), _y in pairs) + max(0.0, float(l2))
    sxz = sum(x * z for (x, z), _y in pairs)
    sxy = sum(x * y for (x, _), y in pairs)
    szy = sum(z * y for (_, z), y in pairs)
    det = (
        sxx * (szz * n - sz * sz)
        - sxz * (sxz * n - sx * sz)
        + sx * (sxz * sz - szz * sx)
    )
    if det == 0:
        return None
    det_a = (
        sxy * (szz * n - sz * sz)
        - sxz * (szy * n - sy * sz)
        + sx * (szy * sz - szz * sy)
    )
    det_b = (
        sxx * (szy * n - sy * sz)
        - sxy * (sxz * n - sx * sz)
        + sx * (sxz * sy - sxy * sz)
    )
    det_c = (
        sxx * (szz * sy - szy * sz)
        - sxz * (sxz * sy - sxy * sz)
        + sxy * (sxz * sz - szz * sx)
    )
    a = det_a / det
    b = det_b / det
    c = det_c / det
    return a, b, c


def normalize_date(s: Optional[str]) -> Optional[str]:
    """Return YYYY-MM-DD or None if invalid; accept 'today'/'yesterday' shortcuts."""
    if not s:
        return None
    s = s.strip().lower()
    if s in ("0000-00-00", "9999-12-31"):
        return s
    if s in ("today",):
        return date.today().strftime("%Y-%m-%d")
    if s in ("yesterday",):
        return (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    m = re.fullmatch(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})", s)
    if not m:
        return None
    try:
        dt = datetime.strptime(f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


if __name__ == "__main__":
    main()
