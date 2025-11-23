#!/usr/bin/env python3
"""Schedule-driven predictor scaffold for TagTracker.

This module provides a light-weight, self-contained interface around a
schedule-driven ML model trained from the TagTracker database. It is kept
standalone so it can be invoked by other parts of the system (reports, CLI
tools, or background jobs) without coupling to web_estimator.

Responsibilities:
  - Load a trained model artifact from web_base_config.TRAINED_MODEL_FOLDER
  - Provide a simple .predict(...) API using weather and schedule inputs
  - Expose metadata about the trained model

The actual ML logic is intentionally minimal here.
"""

from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# Local imports kept late to avoid circularities during bootstrap
import web.web_base_config as wcfg
import sqlite3
from datetime import datetime

try:  # optional heavy deps
    import pandas as pd  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore
    np = None  # type: ignore


DEFAULT_MODEL_FILENAME = "model.pkl"  # legacy single-file (unused by schedule-driven)
DEFAULT_META_FILENAME = "meta.json"
TARGETS = ("num_parked_combined", "num_fullest_combined")

# Analog-day model configuration knobs (override by editing constants).
# In a future iteration these can be wired into web_base_config.
ANALOG_LOOKBACK_MONTHS = 18
ANALOG_K_NEIGHBORS = 40
ANALOG_TRIM_FRACTION = 0.10
ANALOG_TEMP_WEIGHT = 2.0
ANALOG_PRECIP_WEIGHT = 1.0
ANALOG_GROWTH_ALPHA = 0.5
ANALOG_GROWTH_CAP_LOW = 0.7
ANALOG_GROWTH_CAP_HIGH = 1.3


@dataclass
class PredictorOutput:
    """Unified output for the predictor model.

    Aligns with the four measures used broadly across TagTracker:
      - activity_next_hour: ins+outs in the next hour (int)
      - remainder: expected additional visits for the rest of the day (int)
      - peak: expected max bikes today (int)
      - peaktime: time of max bikes, minutes after midnight (int)

    Ranges and confidences can be left None if not available.
    """

    activity_next_hour: Optional[int]
    remainder: Optional[int]
    peak: Optional[int]
    peaktime: Optional[int]
    # Optional ranges (low, high)
    activity_range: Optional[tuple[int, int]] = None
    remainder_range: Optional[tuple[int, int]] = None
    peak_range: Optional[tuple[int, int]] = None
    peaktime_range: Optional[tuple[int, int]] = None
    # Optional confidence labels, e.g., "High" | "Medium" | "Low"
    activity_conf: Optional[str] = None
    remainder_conf: Optional[str] = None
    peak_conf: Optional[str] = None
    peaktime_conf: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activity_next_hour": self.activity_next_hour,
            "remainder": self.remainder,
            "peak": self.peak,
            "peaktime": self.peaktime,
            "activity_range": self.activity_range,
            "remainder_range": self.remainder_range,
            "peak_range": self.peak_range,
            "peaktime_range": self.peaktime_range,
            "activity_conf": self.activity_conf,
            "remainder_conf": self.remainder_conf,
            "peak_conf": self.peak_conf,
            "peaktime_conf": self.peaktime_conf,
        }


class PredictorModel:
    """Loader and predictor facade around a trained model artifact.

    Use .load() once, then .predict(...). If no model is present, .ready is
    False and .predict() raises a RuntimeError (caller can catch and degrade
    gracefully).
    """

    def __init__(self, model_dir: Optional[str | os.PathLike] = None) -> None:
        self.model_dir = Path(
            model_dir or getattr(wcfg, "TRAINED_MODEL_FOLDER", "") or ""
        )
        self.model_path = self.model_dir / DEFAULT_MODEL_FILENAME
        self.meta_path = self.model_dir / DEFAULT_META_FILENAME
        self.models_dir = self.model_dir / "models"
        self._model: Any = None  # legacy
        self._payloads: dict[str, Any] = {}
        self._meta: Dict[str, Any] = {}
        self.ready: bool = False
        self._analog: Optional["AnalogDayModel"] = None

    # ------------------------------ IO ---------------------------------
    def load(self) -> None:
        """Load model + metadata from TRAINED_MODEL_FOLDER; idempotent."""

        self.ready = False
        self._model = None
        self._meta = {}

        if not self.model_dir:
            return  # folder not configured

        # Preferred: schedule-driven joblib payloads per target
        loaded = 0
        if self.models_dir.exists():
            try:
                import joblib  # type: ignore
            except Exception as e:  # pragma: no cover
                self._meta = {"load_error": f"joblib missing: {type(e).__name__}: {e}"}
                return
            for tgt in TARGETS:
                p = self.models_dir / f"{tgt}_schedule_driven.joblib"
                if p.exists():
                    try:
                        self._payloads[tgt] = joblib.load(p)
                        loaded += 1
                    except Exception:
                        continue

        # Legacy fallback: single pickle file
        if loaded == 0 and self.model_path.exists():
            try:
                with self.model_path.open("rb") as f:
                    self._model = pickle.load(f)
                loaded = 1
            except Exception as e:  # pylint:disable=broad-exception-caught
                # Leave ready False; caller can decide how to proceed
                self._meta = {"load_error": f"{type(e).__name__}: {e}"}
                return

        try:
            if self.meta_path.exists():
                self._meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception:
            # metadata optional; ignore errors
            self._meta = {}

        # Initialize analog-day predictor as a fallback or companion
        try:
            db_path = getattr(wcfg, "DB_FILENAME", "") or ""
            if db_path:
                self._analog = AnalogDayModel(
                    db_path=db_path,
                    artifacts_dir=self.model_dir / "analog",
                    lookback_months=ANALOG_LOOKBACK_MONTHS,
                    k=ANALOG_K_NEIGHBORS,
                    trim_frac=ANALOG_TRIM_FRACTION,
                    temp_weight=ANALOG_TEMP_WEIGHT,
                    precip_weight=ANALOG_PRECIP_WEIGHT,
                    growth_alpha=ANALOG_GROWTH_ALPHA,
                    growth_cap_low=ANALOG_GROWTH_CAP_LOW,
                    growth_cap_high=ANALOG_GROWTH_CAP_HIGH,
                )
        except Exception:
            self._analog = None

        self.ready = (loaded > 0) or (self._analog is not None)

    def metadata(self) -> Dict[str, Any]:
        """Return training metadata if available."""
        return dict(self._meta)

    # ---------------------------- Predict -------------------------------
    def _parse_hhmm(self, s: str) -> Optional[int]:
        try:
            parts = str(s).strip().split(":", 1)
            if len(parts) != 2:
                return None
            h = int(parts[0])
            m = int(parts[1])
            if h < 0 or h > 24 or m < 0 or m > 59:
                return None
            return max(0, min(24 * 60, h * 60 + m))
        except Exception:
            return None

    def _date_parts(self, ymd: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
        try:
            y, mo, d = ymd.split("-", 2)
            return int(y), int(mo), int(d)
        except Exception:
            return None, None, None

    def _dow(self, y: int, m: int, d: int) -> int:
        # Zeller/weekday via datetime to keep simple
        import datetime as _dt

        return _dt.date(y, m, d).weekday()

    def _predict_linear(self, coeffs: list[float], feats: list[float]) -> float:
        # dot-product with intercept-first coeffs
        if not coeffs:
            return 0.0
        # Ensure feats includes intercept as first element 1.0
        v = 0.0
        for c, x in zip(coeffs, feats):
            v += float(c) * float(x)
        return v

    def predict(
        self,
        *,
        precip: float | None,
        temperature: float | None,
        date: str,
        opening_time: str,
        closing_time: str,
    ) -> PredictorOutput:
        """Run a prediction using the trained model.

        Args:
            precip: daily precipitation (e.g., mm)
            temperature: max temperature (e.g., C)
            date: ISO-8601 date (YYYY-MM-DD)
            opening_time: HH:MM or minutes since midnight
            closing_time: HH:MM or minutes since midnight

        Returns:
            PredictorOutput with values and optional ranges/confidence.
        """

        if not self.ready:
            raise RuntimeError("Predictor model is not loaded/ready.")

        # If schedule-driven models are present, use them
        if self._payloads:
            try:
                import pandas as pd  # type: ignore
            except Exception as e:  # pragma: no cover
                raise RuntimeError("pandas required for predictor usage") from e

            y, mo, d = self._date_parts(date)
            if not (y and mo and d):
                raise ValueError("Bad date; expected YYYY-MM-DD")
            # Schedule label HH:MM-HH:MM
            o_str = str(opening_time)[:5]
            c_str = str(closing_time)[:5]
            schedule_label = f"{o_str}-{c_str}"
            # days_since_start uses each model's train_start_date; prefer parked model's
            meta0 = self._payloads.get("num_parked_combined", {}).get("metadata", {})
            train_start = str(meta0.get("train_start_date", f"{y:04d}-{mo:02d}-01"))
            try:
                import datetime as _dt
                start_dt = _dt.datetime.strptime(train_start, "%Y-%m-%d")
                cur_dt = _dt.datetime.strptime(date, "%Y-%m-%d")
                days_since_start = (cur_dt.date() - start_dt.date()).days
            except Exception:
                days_since_start = 0

            # Build feature row based on payload metadata
            # Support both old models (with 'month') and new ones (with 'operating_hours')
            rows = {}
            for tgt, payload in self._payloads.items():
                md = payload.get("metadata", {})
                cat_cols = list((md.get("feature_columns", {}) or {}).get("categorical", []))
                num_cols = list((md.get("feature_columns", {}) or {}).get("numeric", []))
                for c in cat_cols:
                    if c == "schedule_label":
                        rows[c] = schedule_label
                    else:
                        rows.setdefault(c, "Missing")
                for n in num_cols:
                    if n == "days_since_start":
                        rows[n] = float(days_since_start)
                    elif n == "max_temperature":
                        rows[n] = float(temperature or 0.0)
                    elif n == "precipitation":
                        rows[n] = float(precip or 0.0)
                    elif n == "operating_hours":
                        # compute duration in hours
                        def _to_minutes(s: str) -> int:
                            try:
                                h, m = s[:5].split(":", 1)
                                return int(h) * 60 + int(m)
                            except Exception:
                                return 0
                        om = _to_minutes(o_str)
                        cm = _to_minutes(c_str)
                        dur = cm - om
                        if dur < 0:
                            dur += 24 * 60
                        rows[n] = float(dur) / 60.0
                    elif n == "month":
                        rows[n] = int(mo)
                    else:
                        rows.setdefault(n, float("nan"))

            if not rows:
                # Fallback to a minimal row to avoid crash
                rows = {
                    "schedule_label": schedule_label,
                    "days_since_start": float(days_since_start),
                    "max_temperature": float(temperature or 0.0),
                    "precipitation": float(precip or 0.0),
                }
            X = pd.DataFrame([rows])

            # Predict total visits and max bikes if available
            rem_val = pk_val = None
            rem_rng = pk_rng = None
            if "num_parked_combined" in self._payloads:
                p = self._payloads["num_parked_combined"]
                model = p["model"]
                yhat = float(model.predict(X)[0])
                rem_val = int(round(max(0.0, yhat)))
                rmse = float(p.get("metadata", {}).get("metrics", {}).get("rmse", 0.0) or 0.0)
                if rmse > 0:
                    w = 1.64 * rmse
                    rem_rng = (max(0, int(round(yhat - w))), int(round(yhat + w)))
            if "num_fullest_combined" in self._payloads:
                p2 = self._payloads["num_fullest_combined"]
                model2 = p2["model"]
                yhat2 = float(model2.predict(X)[0])
                pk_val = int(round(max(0.0, yhat2)))
                rmse2 = float(p2.get("metadata", {}).get("metrics", {}).get("rmse", 0.0) or 0.0)
                if rmse2 > 0:
                    w2 = 1.64 * rmse2
                    pk_rng = (max(0, int(round(yhat2 - w2))), int(round(yhat2 + w2)))

            return PredictorOutput(
                activity_next_hour=None,
                remainder=rem_val,
                peak=pk_val,
                peaktime=None,
                activity_range=None,
                remainder_range=rem_rng,
                peak_range=pk_rng,
                peaktime_range=None,
            )

        # Fallback to analog-day predictor if available
        if self._analog is not None:
            tot, tot_rng, peak, peak_rng = self._analog.predict(
                date=date,
                opening_time=opening_time,
                closing_time=closing_time,
                max_temperature=float(temperature or 0.0),
                precipitation=float(precip or 0.0),
            )
            return PredictorOutput(
                activity_next_hour=None,
                remainder=None if tot is None else int(round(max(0.0, float(tot)))),
                peak=None if peak is None else int(round(max(0.0, float(peak)))),
                peaktime=None,
                activity_range=None,
                remainder_range=None if tot_rng is None else (max(0, int(round(tot_rng[0]))), max(0, int(round(tot_rng[1])))),
                peak_range=None if peak_rng is None else (max(0, int(round(peak_rng[0]))), max(0, int(round(peak_rng[1])))),
                peaktime_range=None,
            )

        # Legacy single-file linear model fallback
        # Prepare feature vector consistent with legacy trainer
        y, mo, d = self._date_parts(date)
        if not (y and mo and d):
            raise ValueError("Bad date; expected YYYY-MM-DD")
        o_min = self._parse_hhmm(opening_time)
        c_min = self._parse_hhmm(closing_time)
        if o_min is None or c_min is None:
            raise ValueError("Bad opening/closing time; expected HH:MM")
        open_len = max(0, c_min - o_min)
        feats = [1.0, float(self._dow(y, mo, d)), float(mo), float(o_min), float(open_len), float(precip or 0.0), float(temperature or 0.0)]
        art = self._model if isinstance(self._model, dict) else {}
        coeffs = art.get("coeffs", {}) if isinstance(art, dict) else {}
        resid_std = art.get("resid_std", {}) if isinstance(art, dict) else {}
        def pred_key(key: str, lo: float, hi: float, clip: tuple[float, float] | None = None) -> tuple[int | None, tuple[int, int] | None]:
            cs = coeffs.get(key)
            if not cs:
                return None, None
            yhat = self._predict_linear(cs, feats)
            if clip:
                yhat = max(clip[0], min(clip[1], yhat))
            std = float(resid_std.get(key, 0.0) or 0.0)
            w = 1.64 * std if std > 0 else 0.0
            lo_v = int(max(lo, yhat - w))
            hi_v = int(min(hi, yhat + w))
            return int(round(yhat)), (lo_v, hi_v) if w > 0 else None
        act_val, act_rng = pred_key("activity", 0, 999999)
        rem_val, rem_rng = pred_key("remainder", 0, 999999)
        pk_val, pk_rng = pred_key("peak", 0, 999999)
        pt_val, pt_rng = pred_key("peaktime", 0, 24 * 60, (0, 24 * 60))
        return PredictorOutput(
            activity_next_hour=act_val,
            remainder=rem_val,
            peak=pk_val,
            peaktime=pt_val,
            activity_range=act_rng,
            remainder_range=rem_rng,
            peak_range=pk_rng,
            peaktime_range=pt_rng,
        )


class AnalogDayModel:
    """Analog-day predictor using schedule/weekday cohorts and weather K-NN.

    Implements:
      - Candidate pool: last 18 months up to as-of date
      - Filters: same schedule_label (fallback to similar operating_hours), same weekday
      - Weather K-NN: weighted L1 over max_temperature and precipitation (IQR-scaled)
      - Aggregation: median or trimmed mean
      - Growth factor: 3-month YOY median ratio, capped, exponent alpha
      - Ranges: empirical percentiles of neighbor values after growth
    """

    def __init__(
        self,
        *,
        db_path: str,
        artifacts_dir: Path,
        lookback_months: int = 18,
        k: int = 40,
        trim_frac: float = 0.10,
        temp_weight: float = 2.0,
        precip_weight: float = 1.0,
        growth_alpha: float = 0.5,
        growth_cap_low: float = 0.7,
        growth_cap_high: float = 1.3,
    ) -> None:
        self.db_path = db_path
        self.artifacts_dir = artifacts_dir
        self.lookback_months = int(lookback_months)
        self.k = int(max(0, k))
        self.trim_frac = float(max(0.0, min(0.49, trim_frac)))
        self.temp_weight = float(max(0.0, temp_weight))
        self.precip_weight = float(max(0.0, precip_weight))
        self.growth_alpha = float(max(0.0, growth_alpha))
        self.growth_cap_low = float(max(0.1, growth_cap_low))
        self.growth_cap_high = float(max(self.growth_cap_low, growth_cap_high))

    @staticmethod
    def _schedule_label(opening_time: str, closing_time: str) -> str:
        o = str(opening_time or "")[:5]
        c = str(closing_time or "")[:5]
        return f"{o}-{c}"

    @staticmethod
    def _operating_hours(opening_time: str, closing_time: str) -> float:
        try:
            oh, om = str(opening_time)[:5].split(":", 1)
            ch, cm = str(closing_time)[:5].split(":", 1)
            o_min = int(oh) * 60 + int(om)
            c_min = int(ch) * 60 + int(cm)
            dur = c_min - o_min
            if dur < 0:
                dur += 24 * 60
            return float(dur) / 60.0
        except Exception:
            return float("nan")

    def _load_pool(self, asof_date: str) -> "pd.DataFrame":
        if pd is None:
            raise RuntimeError("pandas is required for analog-day predictor")
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                (
                    "SELECT date, time_open, time_closed, max_temperature, precipitation, "
                    "num_parked_combined, num_fullest_combined "
                    "FROM DAY WHERE orgsite_id = 1 AND date <= ? AND date >= DATE(?, ?) ORDER BY date"
                ),
                conn,
                params=(asof_date, asof_date, f"-{self.lookback_months} months"),
                parse_dates=["date"],
            )
        # Derive helpers
        s_open = df["time_open"].astype("string").fillna("Missing").str[:5]
        s_close = df["time_closed"].astype("string").fillna("Missing").str[:5]
        df["schedule_label"] = s_open + "-" + s_close
        df["weekday_index"] = df["date"].dt.weekday
        df["month"] = df["date"].dt.month
        # operating hours
        def _to_minutes(x: str) -> Optional[int]:
            try:
                h, m = str(x)[:5].split(":", 1)
                return int(h) * 60 + int(m)
            except Exception:
                return None
        o_min = df["time_open"].map(_to_minutes)
        c_min = df["time_closed"].map(_to_minutes)
        dur_min = (c_min.fillna(0) - o_min.fillna(0)).astype(float)
        dur_min = dur_min.where(dur_min >= 0, dur_min + 24 * 60)
        df["operating_hours"] = dur_min / 60.0
        return df

    def _growth_index(self, pool: "pd.DataFrame", asof_date: str, target_col: str) -> float:
        # 3-month median vs same months last year
        sub = pool.copy()
        sub = sub[sub["date"] <= pd.to_datetime(asof_date)]
        sub["ym"] = sub["date"].dt.to_period("M")
        uniq = list(sub["ym"].unique())
        if len(uniq) < 4:
            return 1.0
        last = uniq[-3:]
        prev = [p - 12 for p in last]
        this_med = sub[sub["ym"].isin(last)][target_col].median()
        prev_med = sub[sub["ym"].isin(prev)][target_col].median()
        if not (np is not None and np.isfinite(this_med) and np.isfinite(prev_med)):
            try:
                this_med = float(this_med)
                prev_med = float(prev_med)
            except Exception:
                return 1.0
        if not prev_med or prev_med == 0:
            return 1.0
        ratio = float(this_med) / float(prev_med)
        ratio = max(self.growth_cap_low, min(self.growth_cap_high, ratio))
        return float(ratio ** self.growth_alpha)

    @staticmethod
    def _iqr_scale(s: "pd.Series") -> float:
        q1 = s.quantile(0.25)
        q3 = s.quantile(0.75)
        iqr = float(q3 - q1)
        return max(1.0, iqr)

    def _select_neighbors(
        self,
        pool: "pd.DataFrame",
        schedule_label: str,
        weekday_index: int,
        oper_hours: float,
        target_temp: float,
        target_precip: float,
    ) -> "pd.DataFrame":
        # base filters
        df = pool[pool["weekday_index"] == int(weekday_index)].copy()
        exact = df[df["schedule_label"] == schedule_label]
        if len(exact) >= max(12, min(20, self.k or 0)):
            df = exact
        else:
            # widen to similar operating hours (±0.5h)
            tol = 0.5
            df = df[(df["operating_hours"] - float(oper_hours)).abs() <= tol]
            # If still empty, fall back to weekday-only cohort
            if len(df) == 0:
                df = pool[pool["weekday_index"] == int(weekday_index)].copy()

        # ensure targets present
        df = df.dropna(subset=["num_parked_combined", "num_fullest_combined"])  # ensure targets
        if self.k <= 0:
            return df
        if (pd.isna(target_temp) and self.temp_weight > 0) and (pd.isna(target_precip) and self.precip_weight > 0):
            return df
        # weather distance (weighted L1 with IQR scaling)
        tscale = self._iqr_scale(df["max_temperature"]) if self.temp_weight > 0 else 1.0
        pscale = self._iqr_scale(df["precipitation"]) if self.precip_weight > 0 else 1.0
        tdiff = (df["max_temperature"].astype(float) - float(target_temp or 0.0)).abs() / float(tscale)
        pdiff = (df["precipitation"].astype(float) - float(target_precip or 0.0)).abs() / float(pscale)
        dist = self.temp_weight * tdiff + self.precip_weight * pdiff
        order = dist.argsort(kind="mergesort")
        k = int(min(len(order), max(1, self.k)))
        return df.iloc[order[:k]]

    def _aggregate(self, values: "np.ndarray") -> float:
        if values.size == 0:
            return float("nan")
        if self.trim_frac > 0 and values.size >= 10:
            cut = int(max(1, int(self.trim_frac * values.size)))
            vals = np.sort(values)[cut: values.size - cut]
            if vals.size:
                return float(np.median(vals))
        return float(np.median(values))

    def predict(
        self,
        *,
        date: str,
        opening_time: str,
        closing_time: str,
        max_temperature: float,
        precipitation: float,
    ) -> tuple[Optional[float], Optional[tuple[float, float]], Optional[float], Optional[tuple[float, float]]]:
        if pd is None or np is None:
            raise RuntimeError("pandas/numpy required for analog-day predictor")
        # FIXME: optionally return a neighbors explainer payload (top dates/values/distances)
        # to display in the prediction report for debugging transparency.
        # Load pool up to as-of
        asof = date
        pool = self._load_pool(asof)
        if pool.empty:
            return None, None, None, None
        # Exclude the target date itself if present to avoid trivial neighbor
        try:
            pool = pool[pool["date"] < pd.to_datetime(asof)]
        except Exception:
            pass

        # If the target date exists in DB with schedule, prefer its schedule for matching
        sched = self._schedule_label(opening_time, closing_time)
        oh = self._operating_hours(opening_time, closing_time)
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT time_open, time_closed FROM DAY WHERE orgsite_id = 1 AND date = ? LIMIT 1",
                    (date,),
                ).fetchone()
            if row and row[0] and row[1]:
                so = str(row[0])[:5]
                sc = str(row[1])[:5]
                sched = f"{so}-{sc}"
                oh = self._operating_hours(so, sc)
        except Exception:
            pass

        wh = int(datetime.strptime(date, "%Y-%m-%d").weekday())
        neigh = self._select_neighbors(
            pool, sched, wh, oh, float(max_temperature), float(precipitation)
        )
        if neigh.empty:
            return None, None, None, None
        # Growth index per target
        g_total = self._growth_index(pool, asof, "num_parked_combined")
        g_peak = self._growth_index(pool, asof, "num_fullest_combined")

        # Distributions (apply growth to each neighbor value, then aggregate)
        vals_total = neigh["num_parked_combined"].astype(float).to_numpy() * g_total
        vals_peak = neigh["num_fullest_combined"].astype(float).to_numpy() * g_peak
        pred_total = self._aggregate(vals_total)
        pred_peak = self._aggregate(vals_peak)
        # Percentile bands (approx 80–90%)
        try:
            lo_t, hi_t = float(np.percentile(vals_total, 10)), float(np.percentile(vals_total, 90))
            lo_p, hi_p = float(np.percentile(vals_peak, 10)), float(np.percentile(vals_peak, 90))
        except Exception:
            lo_t = hi_t = pred_total
            lo_p = hi_p = pred_peak
        return pred_total, (lo_t, hi_t), pred_peak, (lo_p, hi_p)


__all__ = [
    "PredictorModel",
    "PredictorOutput",
]
