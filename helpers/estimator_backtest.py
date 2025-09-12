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

Usage examples:
  python helpers/estimator_backtest.py --start 2024-04-01 --end 2024-08-31 \
      --step-min 60 --variance 10 --zcut 2.5

Copyright (C) 2025 TagTracker authors
"""

from __future__ import annotations

import argparse
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

            # Linear regression (before -> after)
            lr_coeffs = lr_fit([(float(b), float(a)) for b, a in train_pairs])
            lr_pred = lr_predict(lr_coeffs, float(before))
            # 2D LR with time feature if requested
            lr2_pred = None
            if compare_time_feature and train_pairs_2d:
                lr2 = lr2_fit(train_pairs_2d)
                lr2_pred = lr2_predict(lr2, (float(before), float(frac_elapsed)))

            # Record model-specific errors
            if sm_med is not None:
                fut_abs_errs_sm.append(abs(int(sm_med) - int(after_true)))
            if lr_pred is not None:
                fut_abs_errs_lr1.append(abs(int(lr_pred) - int(after_true)))
            if lr2_pred is not None:
                fut_abs_errs_lr2.append(abs(int(lr2_pred) - int(after_true)))

            # Next-hour predictions (net and activity)
            nxh_matched_net = [net for b, net in nxh_pairs_net if abs(b - before) <= variance]
            nxh_matched_act = [act for b, act in nxh_pairs_act if abs(b - before) <= variance]
            if nxh_matched_net:
                pred_net = int(statistics.median(nxh_matched_net))
                nxh_net_abs_errs.append(abs(pred_net - (ins_next_true - outs_next_true)))
            if nxh_matched_act:
                pred_act_sm = int(statistics.median(nxh_matched_act))
                nxh_act_abs_errs_sm.append(abs(pred_act_sm - (ins_next_true + outs_next_true)))
            # LR for activity
            lr_act = lr_fit([(float(b), float(a)) for b, a in nxh_pairs_act])
            pred_act_lr1 = lr_predict(lr_act, float(before))
            if pred_act_lr1 is not None:
                nxh_act_abs_errs_lr1.append(abs(int(pred_act_lr1) - (ins_next_true + outs_next_true)))
            if compare_time_feature and nxh_pairs_act_2d:
                lr2_act = lr2_fit(nxh_pairs_act_2d)
                pred_act_lr2 = lr2_predict(lr2_act, (float(before), float(frac_elapsed)))
                if pred_act_lr2 is not None:
                    nxh_act_abs_errs_lr2.append(abs(int(pred_act_lr2) - (ins_next_true + outs_next_true)))

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
                peak_abs_errs_sm.append(abs(pred_peak_sm - peak_true))
            # LR1 for peak
            lr_peak = lr_fit([(float(b), float(p)) for b, p in peaks_pairs])
            pred_peak_lr1 = lr_predict(lr_peak, float(before))
            if pred_peak_lr1 is not None:
                peak_abs_errs_lr1.append(abs(int(pred_peak_lr1) - peak_true))
            if compare_time_feature and peaks_pairs_2d:
                lr2_peak = lr2_fit(peaks_pairs_2d)
                pred_peak_lr2 = lr2_predict(lr2_peak, (float(before), float(frac_elapsed)))
                if pred_peak_lr2 is not None:
                    peak_abs_errs_lr2.append(abs(int(pred_peak_lr2) - peak_true))

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

        # Parameter sweeps
        lookbacks = [90, 180, 365, 480, 720]
        variances = [10, 15, 20]
        print(f"Comparing lookback windows: {', '.join(str(lb) for lb in lookbacks)} (days)")

        # Determine total number of suites for progress display
        total_suites = len(variances) * len(lookbacks) + len(lookbacks) + len(lookbacks)
        suite_idx = 0

        # Preload visits once for this window and reuse across suites
        days_window = fetch_days(conn, start, end)
        visits_cache = load_visits_for_days(conn, days_window)

        # Sweep variances with schedule_exact OFF, step=60, compare_time_feature ON
        for var in variances:
            print("\n" + "#" * 80)
            print(f"Variance {var} | step=60 | schedule_exact=NO | time_feature=ON")
            for lb in lookbacks:
                suite_idx += 1
                print("\n" + "=" * 72)
                print(f"[{suite_idx}/{total_suites}] Lookback {lb} days  |  schedule_exact=no  |  time_feature=on")
                # Write suite header to file
                outln("")
                outln("#" * 80)
                outln(f"Variance {var} | step=60 | schedule_exact=NO | time_feature=ON")
                outln("=" * 72)
                outln(f"Lookback {lb} days  |  schedule_exact=no  |  time_feature=on")
                backtest(
                    conn,
                    start=start,
                    end=end,
                    step_min=60,
                    variance=var,
                    zcut=args.zcut,
                    schedule_exact=False,
                    lookback_days=lb,
                    compare_time_feature=True,
                    result_writer=outln,
                    visits_by_day=visits_cache,
                )

        # Schedule exact ON at variance=15 (representative), step=60
        print("\n" + "#" * 80)
        print("Variance 15 | step=60 | schedule_exact=YES | time_feature=ON")
        for lb in lookbacks:
            suite_idx += 1
            print("\n" + "=" * 72)
            print(f"[{suite_idx}/{total_suites}] Lookback {lb} days  |  schedule_exact=yes  |  time_feature=on")
            outln("")
            outln("#" * 80)
            outln("Variance 15 | step=60 | schedule_exact=YES | time_feature=ON")
            outln("=" * 72)
            outln(f"Lookback {lb} days  |  schedule_exact=yes  |  time_feature=on")
            backtest(
                conn,
                start=start,
                end=end,
                step_min=60,
                variance=15,
                zcut=args.zcut,
                schedule_exact=True,
                lookback_days=lb,
                compare_time_feature=True,
                result_writer=outln,
                visits_by_day=visits_cache,
            )

        # Stability check: step=120 at variance=15, schedule_exact OFF
        print("\n" + "#" * 80)
        print("Variance 15 | step=120 | schedule_exact=NO | time_feature=ON")
        for lb in lookbacks:
            suite_idx += 1
            print("\n" + "=" * 72)
            print(f"[{suite_idx}/{total_suites}] Lookback {lb} days  |  schedule_exact=no  |  time_feature=on")
            outln("")
            outln("#" * 80)
            outln("Variance 15 | step=120 | schedule_exact=NO | time_feature=ON")
            outln("=" * 72)
            outln(f"Lookback {lb} days  |  schedule_exact=no  |  time_feature=on")
            backtest(
                conn,
                start=start,
                end=end,
                step_min=120,
                variance=15,
                zcut=args.zcut,
                schedule_exact=False,
                lookback_days=lb,
                compare_time_feature=True,
                result_writer=outln,
                visits_by_day=visits_cache,
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
