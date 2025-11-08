#!/usr/bin/env python3
"""Experiment runner for the schedule-driven predictor.

Runs rolling backtests on DAY table data under different modeling options to
help choose a good configuration. Meant as a throwaway exploration tool.

Requirements: pandas, scikit-learn, joblib (optional for saving).

Examples:
  # Simple single-config run
  python helpers/schedule_model_sweep.py \
      --db ../data/dev3.db --orgsite-id 1 --target num_parked_combined \
      --min-train-days 365 --test-window 30 --step 30 \
      --include-oper-hours --include-month --loss huber --trim mad --trim-k 3

  # Sweep several options and print a summary table
  python helpers/schedule_model_sweep.py --db ../data/dev3.db --sweep
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import pandas as pd  # type: ignore
    import numpy as np  # type: ignore
    from sklearn.compose import ColumnTransformer  # type: ignore
    from sklearn.impute import SimpleImputer  # type: ignore
    from sklearn.pipeline import Pipeline  # type: ignore
    from sklearn.preprocessing import OneHotEncoder  # type: ignore
    from sklearn.ensemble import GradientBoostingRegressor  # type: ignore
    from sklearn.metrics import mean_absolute_error, mean_squared_error  # type: ignore
except Exception as e:  # pragma: no cover - friendly message for missing deps
    raise SystemExit(
        "This tool requires pandas and scikit-learn. Install with:\n"
        "  pip install pandas scikit-learn\n"
        f"Import error: {type(e).__name__}: {e}"
    )

# Local config import (robust pathing)
import sys
from pathlib import Path as _P
_HERE = _P(__file__).resolve()
_BIN_DIR = _HERE.parent.parent
if str(_BIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BIN_DIR))
try:
    import web.web_base_config as wcfg  # type: ignore
except Exception:
    # Fall back to defaults if config import fails
    class _W:  # type: ignore
        DB_FILENAME = ""
    wcfg = _W()


TARGETS = ("num_parked_combined", "num_fullest_combined")


def load_day_df(db_path: Path, orgsite_id: int) -> pd.DataFrame:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    with sqlite3.connect(str(db_path)) as conn:
        df = pd.read_sql_query(
            (
                "SELECT date, time_open, time_closed, "
                "max_temperature, precipitation, "
                "num_parked_combined, num_fullest_combined "
                "FROM DAY WHERE orgsite_id = ? ORDER BY date"
            ),
            conn,
            params=(orgsite_id,),
            parse_dates=["date"],
        )
    if df.empty:
        raise ValueError("DAY query returned no rows for given orgsite_id")

    # Basic preprocessing (aligned with trainer)
    s_open = df["time_open"].astype("string").fillna("Missing").str[:5]
    s_close = df["time_closed"].astype("string").fillna("Missing").str[:5]
    df["schedule_label"] = s_open + "-" + s_close
    df["month"] = df["date"].dt.month
    df["days_since_start"] = (df["date"] - df["date"].min()).dt.days

    # operating hours in hours (wrap not expected here, but guard anyway)
    def _to_minutes(x: str) -> Optional[int]:
        try:
            h, m = str(x)[:5].split(":", 1)
            hh = int(h); mm = int(m)
            return hh * 60 + mm
        except Exception:
            return None

    o_min = df["time_open"].map(_to_minutes)
    c_min = df["time_closed"].map(_to_minutes)
    dur_min = (c_min.fillna(0) - o_min.fillna(0)).astype(float)
    dur_min = dur_min.where(dur_min >= 0, dur_min + 24 * 60)
    df["operating_hours"] = dur_min / 60.0

    return df


def _resolve_gbr_loss(loss: str) -> str:
    """Map friendly loss names to sklearn-GBR supported tokens across versions.

    sklearn <1.0 used: 'ls' (least squares), 'lad' (least absolute dev), 'huber', 'quantile'.
    sklearn >=1.0 uses: 'squared_error', 'absolute_error', 'huber', 'quantile'.
    """
    aliases = {
        "squared_error": "ls",
        "absolute_error": "lad",
        # pass through 'huber' and 'quantile'
    }
    return aliases.get(loss, loss)


def build_pipeline(cat_cols: List[str], num_cols: List[str], *, loss: str = "squared_error", huber_alpha: float = 0.9) -> Pipeline:
    cat_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse=False)),
        ]
    )
    num_pipe = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
    pre = ColumnTransformer(
        transformers=[
            ("categorical", cat_pipe, cat_cols),
            ("numeric", num_pipe, num_cols),
        ]
    )
    model = GradientBoostingRegressor(loss=_resolve_gbr_loss(loss), alpha=huber_alpha, random_state=42)
    return Pipeline(steps=[("preprocess", pre), ("model", model)])


def mad_trim_mask(y: pd.Series, k: float) -> pd.Series:
    med = y.median()
    dev = (y - med).abs()
    mad = dev.median()
    if mad == 0:
        return pd.Series(False, index=y.index)
    z = 0.6745 * (y - med) / mad
    return z.abs() > k


def iqr_trim_mask(y: pd.Series, k: float) -> pd.Series:
    q1 = y.quantile(0.25)
    q3 = y.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return pd.Series(False, index=y.index)
    lo = q1 - k * iqr
    hi = q3 + k * iqr
    return (y < lo) | (y > hi)


def apply_group_trim(train_df: pd.DataFrame, target: str, *, by: str = "schedule_label", method: str = "none", k: float = 3.0, min_group_rows: int = 30) -> pd.DataFrame:
    if method == "none":
        return train_df
    out = []
    for key, grp in train_df.groupby(by):
        if len(grp) < min_group_rows:
            out.append(grp)
            continue
        if method == "mad":
            mask = mad_trim_mask(grp[target].astype(float), k)
        elif method == "iqr":
            mask = iqr_trim_mask(grp[target].astype(float), k)
        else:
            out.append(grp)
            continue
        trimmed = grp.loc[~mask]
        # Guardrail: if we over-trim, fall back to untrimmed
        if len(trimmed) < min_group_rows:
            out.append(grp)
        else:
            out.append(trimmed)
    return pd.concat(out).sort_index()


def rolling_backtest(
    df: pd.DataFrame,
    target: str,
    *,
    min_train_days: int,
    test_window: int,
    step: int,
    include_month: bool,
    include_oper_hours: bool,
    loss: str,
    trim: str,
    trim_k: float,
    min_group_rows: int,
) -> Dict[str, float]:
    df = df.sort_values("date").reset_index(drop=True)
    # Feature selection
    cats = ["schedule_label"]
    nums = ["days_since_start", "max_temperature", "precipitation"]
    if include_month:
        nums.append("month")
    if include_oper_hours:
        nums.append("operating_hours")

    X_all = df[cats + nums]
    y_all = df[target].astype(float)

    n = len(df)
    start_idx = min_train_days
    if start_idx + test_window > n:
        raise ValueError("Not enough rows for the requested train/test windows")

    records = []
    i = start_idx
    while i + test_window <= n:
        train_idx = slice(0, i)
        test_idx = slice(i, i + test_window)
        X_train, y_train = X_all.iloc[train_idx].copy(), y_all.iloc[train_idx].copy()
        X_test, y_test = X_all.iloc[test_idx].copy(), y_all.iloc[test_idx].copy()

        # Trim training by schedule label only (not month) for robustness
        train_df = df.iloc[train_idx].copy()
        train_df = apply_group_trim(train_df, target, by="schedule_label", method=trim, k=trim_k, min_group_rows=min_group_rows)
        # Rebuild X_train/y_train from trimmed indices
        X_train = train_df[cats + nums]
        y_train = train_df[target].astype(float)

        pipe = build_pipeline(cats, nums, loss=loss)
        pipe.fit(X_train, y_train)
        preds = pipe.predict(X_test)

        mae = float(mean_absolute_error(y_test, preds))
        rmse = float(math.sqrt(mean_squared_error(y_test, preds)))
        # MAPE (ignore zeros)
        with np.errstate(divide="ignore", invalid="ignore"):
            mape = np.abs((y_test.to_numpy() - preds) / y_test.to_numpy())
            mape = mape[np.isfinite(mape) & (y_test.to_numpy() != 0)]
            mape = float(np.mean(mape)) if len(mape) else float("nan")

        records.append({"mae": mae, "rmse": rmse, "mape": mape})
        i += step

    # Aggregate
    out = {k: float(np.nanmean([r[k] for r in records])) for k in ("mae", "rmse", "mape")}
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Schedule-driven model sweep/backtest")
    p.add_argument("--db", dest="db_path", default=getattr(wcfg, "DB_FILENAME", ""))
    p.add_argument("--orgsite-id", type=int, default=1)
    p.add_argument("--target", choices=list(TARGETS) + ["both"], default="both")
    p.add_argument("--min-train-days", type=int, default=365)
    p.add_argument("--test-window", type=int, default=30)
    p.add_argument("--step", type=int, default=30)

    p.add_argument("--include-month", action="store_true")
    p.add_argument("--include-oper-hours", action="store_true")
    p.add_argument("--loss", choices=["squared_error", "absolute_error", "huber"], default="squared_error")
    p.add_argument("--trim", choices=["none", "mad", "iqr"], default="none")
    p.add_argument("--trim-k", type=float, default=3.0)
    p.add_argument("--min-group-rows", type=int, default=30)

    p.add_argument("--sweep", action="store_true", help="Run a grid over common options")
    p.add_argument("--csv", dest="csv_path", default="", help="Write results to CSV path")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path) if args.db_path else Path(getattr(wcfg, "DB_FILENAME", ""))
    if not str(db_path):
        print("ERROR: DB path not provided and not set in config.")
        print("Hint: pass --db /path/to/your.sqlite (e.g., ../data/dev3.db)")
        return 2
    if not db_path.exists() or not db_path.is_file():
        print(f"ERROR: DB not found or not a file: {db_path}")
        print("Hint: pass --db /path/to/your.sqlite (e.g., ../data/dev3.db)")
        return 2

    df = load_day_df(db_path, args.orgsite_id)

    configs: List[Dict[str, object]] = []
    # Auto-enable sweep if user provided no modeling toggles
    user_specified = any([
        args.include_month,
        args.include_oper_hours,
        (args.loss != "squared_error"),
        (args.trim != "none"),
    ])
    do_sweep = args.sweep or not user_specified
    if do_sweep:
        trim_methods = ("none", "mad")
        trim_ks = (2.5, 3.0, 3.5)
        loss_opts = ("squared_error", "huber", "absolute_error")
        for include_month in (False, True):
            for include_oper in (False, True):
                for loss in loss_opts:
                    for trim in trim_methods:
                        for tk in trim_ks if trim != "none" else (args.trim_k,):
                            configs.append({
                                "include_month": include_month,
                                "include_oper_hours": include_oper,
                                "loss": loss,
                                "trim": trim,
                                "trim_k": float(tk),
                            })
    else:
        configs.append({
            "include_month": bool(args.include_month),
            "include_oper_hours": bool(args.include_oper_hours),
            "loss": str(args.loss),
            "trim": str(args.trim),
            "trim_k": float(args.trim_k),
        })

    targets = TARGETS if args.target == "both" else (args.target,)
    rows = []
    for cfg in configs:
        for tgt in targets:
            metrics = rolling_backtest(
                df,
                tgt,
                min_train_days=int(args.min_train_days),
                test_window=int(args.test_window),
                step=int(args.step),
                include_month=bool(cfg["include_month"]),
                include_oper_hours=bool(cfg["include_oper_hours"]),
                loss=str(cfg["loss"]),
                trim=str(cfg["trim"]),
                trim_k=float(cfg["trim_k"]),
                min_group_rows=int(args.min_group_rows),
            )
            rows.append({
                "target": tgt,
                **cfg,
                **metrics,
            })

    out_df = pd.DataFrame(rows)
    # Order columns
    col_order = [
        "target", "include_month", "include_oper_hours", "loss", "trim", "trim_k",
        "mae", "rmse", "mape",
    ]
    out_df = out_df[[c for c in col_order if c in out_df.columns]]

    # Pretty print sorted by RMSE then MAE
    out_df = out_df.sort_values(["target", "rmse", "mae"]).reset_index(drop=True)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 120)
    print(out_df.to_string(index=False))

    # Print recommendations per target (lowest RMSE then MAE)
    try:
        for tgt in targets:
            best = (
                out_df[out_df["target"] == tgt]
                .sort_values(["rmse", "mae"], ascending=True)
                .head(1)
            )
            if not best.empty:
                row = best.iloc[0]
                rec = (
                    f"Recommended for {tgt}: loss={row['loss']}, trim={row['trim']}"
                    f"(k={row['trim_k']}), include_month={row['include_month']},"
                    f" include_oper_hours={row['include_oper_hours']}"
                    f" | RMSE={row['rmse']:.2f}, MAE={row['mae']:.2f}, MAPE={row['mape']:.3f}"
                )
                print(rec)
    except Exception:
        pass

    if args.csv_path:
        Path(args.csv_path).parent.mkdir(parents=True, exist_ok=True)
        out_df.to_csv(args.csv_path, index=False)
        print(f"\nWrote CSV: {args.csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
