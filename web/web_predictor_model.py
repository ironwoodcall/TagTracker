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

The actual ML logic is intentionally minimal here; you can replace the
placeholder with the migrated implementation from ../blind-estimator.
"""

from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# Local imports kept late to avoid circularities during bootstrap
import web_base_config as wcfg


DEFAULT_MODEL_FILENAME = "model.pkl"  # legacy single-file (unused by schedule-driven)
DEFAULT_META_FILENAME = "meta.json"
TARGETS = ("num_parked_combined", "num_fullest_combined")


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

        self.ready = loaded > 0

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
            # days_since_start uses each model's train_start_date; we'll take parked model's
            meta0 = self._payloads.get("num_parked_combined", {}).get("metadata", {})
            train_start = str(meta0.get("train_start_date", f"{y:04d}-{mo:02d}-01"))
            try:
                import datetime as _dt
                start_dt = _dt.datetime.strptime(train_start, "%Y-%m-%d")
                cur_dt = _dt.datetime.strptime(date, "%Y-%m-%d")
                days_since_start = (cur_dt.date() - start_dt.date()).days
            except Exception:
                days_since_start = 0

            row = {
                "schedule_label": schedule_label,
                "month": int(mo),
                "days_since_start": float(days_since_start),
                "max_temperature": float(temperature or 0.0),
                "precipitation": float(precip or 0.0),
            }
            X = pd.DataFrame([row])

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


__all__ = [
    "PredictorModel",
    "PredictorOutput",
]
