#!/usr/bin/env python3
"""Train the schedule-driven predictor model (scaffold).

This script reads training data from the TagTracker SQLite DB and writes a
trained artifact to database_base_config.TRAINED_MODEL_FOLDER. It is safe to run
from cron: it creates the output folder if needed and replaces the model
atomically (write temp then rename).

The ML bits are intentionally minimal placeholders so the migration can focus
on plumbing first. Replace the fit() stub with the migrated logic from
../blind-estimator.
"""

from __future__ import annotations

import argparse
import math
import datetime as _dt
import json
import os
import pickle
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - numpy is optional but recommended
    np = None  # fallback to simple means if numpy unavailable

# Optional heavy deps for schedule-driven pipeline
try:  # pragma: no cover - import guards
    import pandas as pd  # type: ignore
    from sklearn.compose import ColumnTransformer  # type: ignore
    from sklearn.impute import SimpleImputer  # type: ignore
    from sklearn.pipeline import Pipeline  # type: ignore
    from sklearn.preprocessing import OneHotEncoder  # type: ignore
    from sklearn.ensemble import GradientBoostingRegressor  # type: ignore
    import joblib  # type: ignore
    _SKLEARN_OK = True
except Exception:
    _SKLEARN_OK = False

from database.database_base_config import DB_FILENAME, TRAINED_MODEL_FOLDER

# Make the repository's bin directory importable when invoked from anywhere
_HERE = Path(__file__).resolve()
_BIN_DIR = _HERE.parent.parent  # .../TagTracker/bin
if str(_BIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BIN_DIR))

import database.tt_dbutil as db


DEFAULT_MODEL_FILENAME = "model.pkl"
DEFAULT_META_FILENAME = "meta.json"


def _iso_today() -> str:
    return _dt.date.today().isoformat()


def _ensure_folder(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=str(target.parent), delete=False) as tf:
        tmp = Path(tf.name)
        tf.write(data)
    tmp.replace(target)


def _gather_training_rows(conn) -> Tuple[int, str, str]:
    """Return (orgsite_id, min_date, max_date) for the default site.

    This scaffold mirrors other modules that default orgsite_id=1.
    Extend this to multiple sites or selection flags if needed.
    """
    orgsite_id = 1  # follows web_estimator default
    min_date, max_date = db.fetch_date_range_limits(conn, orgsite_id)
    return orgsite_id, (min_date or ""), (max_date or "")


def _hhmm_to_min(s: str | None) -> int | None:
    if not s:
        return None
    try:
        h, m = s.split(":", 1)
        hh = int(h)
        mm = int(m)
        if hh < 0 or hh > 24 or mm < 0 or mm > 59:
            return None
        return max(0, min(24 * 60, hh * 60 + mm))
    except Exception:
        return None


def _fit_linear(X: List[List[float]], y: List[float]) -> Tuple[List[float], float]:
    """Legacy helper (unused by schedule-driven); kept for reference."""
    n = len(y)
    if not X or not y or n != len(X):
        return [0.0], 0.0
    if np is None:
        mu = sum(y) / max(1, len(y))
        resid = [val - mu for val in y]
        sd = math.sqrt(sum(r * r for r in resid) / max(1, len(resid)))
        return [mu], sd
    Xmat = np.array(X, dtype=float)
    yvec = np.array(y, dtype=float)
    coeffs, *_ = np.linalg.lstsq(Xmat, yvec, rcond=None)
    yhat = Xmat @ coeffs
    resid = yvec - yhat
    sd = float(np.sqrt(np.mean(resid**2)))
    return [float(c) for c in coeffs.tolist()], sd


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Train schedule-driven predictor model")
    ap.add_argument(
        "--since",
        dest="since",
        default="",
        help="Only use data since YYYY-MM-DD (optional)",
    )
    ap.add_argument(
        "--debug",
        action="store_true",
        help="Print training diagnostics (row counts, feature stats, sample fits)",
    )
    args = ap.parse_args(argv)

    db_path = DB_FILENAME or ""
    out_dir_raw = TRAINED_MODEL_FOLDER or ""

    if not db_path:
        print("ERROR: No DB path configured (database_base_config.DB_FILENAME is empty).", file=sys.stderr)
        return 2
    if not os.path.exists(db_path):
        print(f"ERROR: DB file not found: {db_path}", file=sys.stderr)
        return 2

    if not out_dir_raw:
        print(
            "ERROR: TRAINED_MODEL_FOLDER not set (database_base_config.TRAINED_MODEL_FOLDER).",
            file=sys.stderr,
        )
        return 2
    out_dir = Path(out_dir_raw)
    _ensure_folder(out_dir)

    # Connect DB
    conn = db.db_connect(db_path)
    if conn is None:
        print("ERROR: Could not open DB.", file=sys.stderr)
        return 2

    # Determine training range
    orgsite_id, min_date, max_date = _gather_training_rows(conn)
    if args.since:
        min_date = max(min_date or args.since, args.since)

    # Build training rows for schedule-driven model
    cursor = conn.cursor()
    rows = db.db_fetch(
        cursor,
        f"""
        SELECT D.id as day_id,
               D.date,
               D.weekday,
               D.time_open,
               D.time_closed,
               D.max_temperature,
               D.precipitation,
               D.num_parked_combined,
               D.num_fullest_combined
          FROM day D
         WHERE orgsite_id = {orgsite_id}
           AND date BETWEEN '{min_date or '0000-00-00'}' AND '{max_date or _iso_today()}'
        ;
        """,
        [
            "day_id",
            "date",
            "weekday",
            "time_open",
            "time_closed",
            "max_temperature",
            "precipitation",
            "num_parked_combined",
            "num_fullest_combined",
        ],
    )

    if not _SKLEARN_OK:
        print(
            "ERROR: pandas and scikit-learn are required for schedule-driven training.",
            file=sys.stderr,
        )
        return 2

    # Convert to DataFrame
    data = {
        "date": [],
        "time_open": [],
        "time_closed": [],
        "max_temperature": [],
        "precipitation": [],
        "num_parked_combined": [],
        "num_fullest_combined": [],
    }
    n_rows = 0
    for r in rows:
        n_rows += 1
        data["date"].append(r.date)
        data["time_open"].append(r.time_open)
        data["time_closed"].append(r.time_closed)
        data["max_temperature"].append(r.max_temperature)
        data["precipitation"].append(r.precipitation)
        data["num_parked_combined"].append(r.num_parked_combined)
        data["num_fullest_combined"].append(r.num_fullest_combined)

    df = pd.DataFrame(data)
    # Minimal preprocessing as in blind-estimator
    df["date"] = pd.to_datetime(df["date"])  # type: ignore[attr-defined]
    df = df.sort_values("date").reset_index(drop=True)
    open_str = df["time_open"].astype("string").fillna("Missing").str[:5]
    close_str = df["time_closed"].astype("string").fillna("Missing").str[:5]
    df["schedule_label"] = open_str + "-" + close_str
    df["days_since_start"] = (df["date"] - df["date"].min()).dt.days
    # Operating hours (in hours), wrapping if close < open
    def _to_minutes(x: str) -> int | None:
        try:
            s = str(x)[:5]
            h, m = s.split(":", 1)
            return int(h) * 60 + int(m)
        except Exception:
            return None
    o_min = df["time_open"].map(_to_minutes)
    c_min = df["time_closed"].map(_to_minutes)
    dur_min = (c_min.fillna(0) - o_min.fillna(0)).astype(float)
    dur_min = dur_min.where(dur_min >= 0, dur_min + 24 * 60)
    df["operating_hours"] = dur_min / 60.0

    if args.debug:
        print("[DEBUG] Training diagnostics")
        print(f"[DEBUG]  orgsite_id={orgsite_id}  rows={n_rows}")
        print(f"[DEBUG]  date range: min={min_date or 'None'} max={max_date or _iso_today()} since_arg={args.since or 'None'}")
        print("[DEBUG]  schedule_label value counts (top 6):")
        try:
            vc = df["schedule_label"].value_counts().head(6)
            print(vc.to_string())
        except Exception as e:
            print(f"[DEBUG]   unable to compute value counts: {type(e).__name__}: {e}")
        try:
            stats = df[["days_since_start", "operating_hours", "max_temperature", "precipitation"]].describe()
            print("[DEBUG]  numeric feature summary:")
            print(stats.to_string())
        except Exception as e:
            print(f"[DEBUG]   unable to describe numeric features: {type(e).__name__}: {e}")

    # Best config from sweep: include operating_hours, exclude month
    cats = ["schedule_label"]
    nums = ["days_since_start", "max_temperature", "precipitation", "operating_hours"]

    def build_pipeline(cat_cols: List[str], num_cols: List[str]):
        # Handle scikit-learn API changes:
        # - Newer versions use sparse_output instead of sparse on OneHotEncoder.
        # - Loss name 'absolute_error' is preferred; older versions used 'lad'.
        try:
            ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        except TypeError:
            ohe = OneHotEncoder(handle_unknown="ignore", sparse=False)
        categorical_pipeline = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", ohe),
            ]
        )
        numeric_pipeline = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
        preprocessor = ColumnTransformer(
            transformers=[
                ("categorical", categorical_pipeline, cat_cols),
                ("numeric", numeric_pipeline, num_cols),
            ]
        )

        # Choose a loss compatible with the installed scikit-learn:
        # try 'absolute_error', and proactively run any available param
        # validation; if that fails, fall back to legacy 'lad'.
        try:
            model = GradientBoostingRegressor(loss="absolute_error", random_state=42)
            checker = getattr(model, "_validate_params", None) or getattr(
                model, "_check_params", None
            )
            if callable(checker):
                try:
                    checker()
                except Exception:
                    model = GradientBoostingRegressor(loss="lad", random_state=42)
        except Exception:
            model = GradientBoostingRegressor(loss="lad", random_state=42)

        return Pipeline(steps=[("preprocess", preprocessor), ("model", model)])

    artifacts: Dict[str, Dict[str, Any]] = {}
    for target in ("num_parked_combined", "num_fullest_combined"):
        y = df[target].astype(float)
        X = df[cats + nums]
        pipe = build_pipeline(cats, nums)
        pipe.fit(X, y)
        yhat = pipe.predict(X)
        if np is not None:
            rmse = float(np.sqrt(np.mean((y.to_numpy() - yhat) ** 2)))
        else:
            rmse = float(
                (sum((float(a) - float(b)) ** 2 for a, b in zip(y, yhat)) / max(1, len(y)))
                ** 0.5
            )
        if args.debug:
            print(f"[DEBUG]  target={target}")
            print(
                f"[DEBUG]   rmse={rmse:.3f} train_rows={len(X)} "
                f"train_start={df['date'].min().date()} train_end={df['date'].max().date()}"
            )
            sample_n = min(5, len(X))
            if sample_n > 0:
                sample = df.iloc[:sample_n]
                print("[DEBUG]   sample fits:")
                for i in range(sample_n):
                    print(
                        f"[DEBUG]    {i+1}: date={sample.iloc[i]['date'].date()} "
                        f"sched={sample.iloc[i]['schedule_label']} "
                        f"oper_hours={sample.iloc[i]['operating_hours']:.2f} "
                        f"y={float(y.iloc[i]):.2f} yhat={float(yhat[i]):.2f}"
                    )
        metadata = {
            "target": target,
            "variant": "schedule_driven",
            "lags": [],
            "train_rows": int(len(X)),
            "train_start_date": str(df["date"].min().date()),
            "train_end_date": str(df["date"].max().date()),
            "metrics": {"rmse": rmse},
            "feature_columns": {"categorical": cats, "numeric": nums},
        }
        artifacts[target] = {"model": pipe, "metadata": metadata}

    models_dir = out_dir / "models"
    _ensure_folder(models_dir)
    for tgt, payload in artifacts.items():
        joblib.dump(payload, models_dir / f"{tgt}_schedule_driven.joblib")

    meta: Dict[str, Any] = {
        "version": 1,
        "trained_on": _iso_today(),
        "db_path": os.path.abspath(db_path),
        "orgsite_id": orgsite_id,
        "min_date": min_date,
        "max_date": max_date,
        "n_rows": n_rows,
        "models": {tgt: {"train_rows": p["metadata"]["train_rows"]} for tgt, p in artifacts.items()},
    }
    _atomic_write_bytes(out_dir / DEFAULT_META_FILENAME, json.dumps(meta, indent=2).encode("utf-8"))

    print(f"Wrote schedule-driven models to {models_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
