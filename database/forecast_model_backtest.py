#!/usr/bin/env python3
"""Forecast model backtester (analog-day and lag-based ML).

This helper runs rolling/expanding backtests over historical DAY data to
compare two families:
  - Analog-day: similar schedule/weekday cohort with YOY growth factor.
  - Lag-based ML: regression on lag/seasonal features, per-horizon.

It prints per-horizon metrics (MAE, RMSE, sMAPE) and recommends a config.

Notes
- Keeps dependencies aligned with existing helpers (pandas, scikit-learn).
- Uses only information available up to each split date to avoid leakage.
- Defaults are conservative for runtime; tune CLI flags for deeper sweeps.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:  # lightweight, friendly import guard
    import pandas as pd  # type: ignore
    import numpy as np  # type: ignore
    from sklearn.compose import ColumnTransformer  # type: ignore
    from sklearn.impute import SimpleImputer  # type: ignore
    from sklearn.pipeline import Pipeline  # type: ignore
    from sklearn.preprocessing import OneHotEncoder  # type: ignore
    from sklearn.linear_model import ElasticNet  # type: ignore
    from sklearn.ensemble import GradientBoostingRegressor  # type: ignore
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "This tool requires pandas and scikit-learn. Install with:\n"
        "  pip install pandas scikit-learn\n"
        f"Import error: {type(e).__name__}: {e}"
    )

import sys
from pathlib import Path as _P
_HERE = _P(__file__).resolve()
_BIN_DIR = _HERE.parent.parent  # .../TagTracker/bin
if str(_BIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BIN_DIR))
try:
    import web.web_base_config as wcfg  # type: ignore
except Exception:  # pragma: no cover - fall back if not importable
    class _W:  # type: ignore
        DB_FILENAME = ""
    wcfg = _W()  # type: ignore


TARGETS = ("num_parked_combined", "num_fullest_combined")
DEFAULT_HORIZONS = (2, 7, 14, 28, 56, 84)
# Include a long seasonal anchor (365) by default
DEFAULT_LAGS = (2, 4, 7, 14, 28, 56, 365)


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

    # Preprocess: schedule_label, weekday/month, days_since_start, operating_hours
    s_open = df["time_open"].astype("string").fillna("Missing").str[:5]
    s_close = df["time_closed"].astype("string").fillna("Missing").str[:5]
    df["schedule_label"] = s_open + "-" + s_close
    df["weekday_index"] = df["date"].dt.weekday
    df["month"] = df["date"].dt.month
    df["days_since_start"] = (df["date"] - df["date"].min()).dt.days

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

    return df.reset_index(drop=True)


def add_lag_features(df: pd.DataFrame, target: str, lags: Iterable[int]) -> pd.DataFrame:
    out = df.copy()
    # Shift by lag days (using the same orgsite_id series; single site here)
    for lag in lags:
        out[f"{target}_lag_{int(lag)}"] = out[target].shift(int(lag))
    # Rolling stats (shifted by 1 to avoid peeking at t)
    out[f"{target}_roll7_mean"] = out[target].shift(1).rolling(7, min_periods=3).mean()
    out[f"{target}_roll28_mean"] = out[target].shift(1).rolling(28, min_periods=7).mean()
    return out


def _resolve_gbr_loss(loss: str) -> str:
    aliases = {"squared_error": "ls", "absolute_error": "lad"}
    return aliases.get(loss, loss)


def build_ml_pipeline(cat_cols: List[str], num_cols: List[str], model: str = "gbr", *, loss: str = "huber") -> Pipeline:
    cat_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse=False)),
        ]
    )
    num_pipe = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
    pre = ColumnTransformer(
        transformers=[("categorical", cat_pipe, cat_cols), ("numeric", num_pipe, num_cols)]
    )
    if model == "elasticnet":
        reg = ElasticNet(alpha=0.01, l1_ratio=0.2, random_state=42)
    else:
        reg = GradientBoostingRegressor(loss=_resolve_gbr_loss(loss), alpha=0.9, random_state=42)
    return Pipeline(steps=[("preprocess", pre), ("model", reg)])


def smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    num = np.abs(y_true - y_pred)
    den = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    m = np.isfinite(num) & np.isfinite(den) & (den > 0)
    if not np.any(m):
        return float("nan")
    return float(np.mean(num[m] / den[m]))


def compute_growth_index(train_df: pd.DataFrame, asof_idx: int, target: str, *, months: int = 3, alpha: float = 0.5, cap_low: float = 0.7, cap_high: float = 1.3) -> float:
    asof_date = train_df.iloc[asof_idx]["date"]
    # Build month keys
    df = train_df.iloc[: asof_idx + 1].copy()
    df["ym"] = df["date"].dt.to_period("M")
    last_months = list(df["ym"].unique())[-months:]
    if len(last_months) < months:
        return 1.0
    this = df[df["ym"].isin(last_months)][target].median()
    last_year_months = [p - 12 for p in last_months]
    prev = df[df["ym"].isin(last_year_months)][target].median()
    if not np.isfinite(this) or not np.isfinite(prev) or prev == 0 or np.isnan(prev):
        return 1.0
    ratio = float(this / prev)
    ratio = max(cap_low, min(cap_high, ratio))
    return float(ratio ** alpha)


@dataclass
class AnalogParams:
    lookback_months: int = 18
    require_same_weekday: bool = True
    require_same_schedule: bool = True
    agg: str = "median"  # or "trimmed"
    trim_frac: float = 0.1
    growth_alpha: float = 0.5
    cap_low: float = 0.7
    cap_high: float = 1.3
    # Weather K-NN: if k>0 and future weather is available, select top-K similar
    k: int = 0
    temp_weight: float = 2.0
    precip_weight: float = 1.0


def analog_predict(
    train_df: pd.DataFrame,
    target_row: pd.Series,
    target: str,
    asof_idx: int,
    params: AnalogParams,
    *,
    future_weather_mode: str = "actual",
) -> float:
    # Candidate pool: last N months up to asof_idx
    asof_date = train_df.iloc[asof_idx]["date"]
    start_date = asof_date - pd.DateOffset(months=params.lookback_months)
    pool = train_df[(train_df["date"] > start_date) & (train_df.index <= asof_idx)]
    if params.require_same_schedule:
        pool = pool[pool["schedule_label"] == target_row["schedule_label"]]
    if params.require_same_weekday:
        pool = pool[pool["weekday_index"] == int(target_row["weekday_index"])]
    vals = pool[target].dropna().to_numpy()
    base: float
    # Weather-aware KNN if configured and future weather is available
    use_weather = (params.k and params.k > 0 and future_weather_mode == "actual")
    if use_weather and (pd.notna(target_row.get("max_temperature")) or pd.notna(target_row.get("precipitation"))):
        # Compute simple weighted L1 distance on weather fields
        tw = float(max(0.0, params.temp_weight))
        pw = float(max(0.0, params.precip_weight))
        cand = pool[["max_temperature", "precipitation", target]].dropna()
        if not cand.empty:
            dt = float(target_row.get("max_temperature")) if pd.notna(target_row.get("max_temperature")) else 0.0
            dp = float(target_row.get("precipitation")) if pd.notna(target_row.get("precipitation")) else 0.0
            # Normalize by robust scales within pool (IQR)
            def _scale(s: pd.Series) -> float:
                q1 = s.quantile(0.25)
                q3 = s.quantile(0.75)
                iqr = float(q3 - q1)
                return max(1.0, iqr)  # avoid divide-by-zero; unit fallback
            tscale = _scale(cand["max_temperature"]) if tw > 0 else 1.0
            pscale = _scale(cand["precipitation"]) if pw > 0 else 1.0
            dist = (
                tw * (cand["max_temperature"].to_numpy() - dt) / tscale
            ).__abs__() + (
                pw * (cand["precipitation"].to_numpy() - dp) / pscale
            ).__abs__()
            order = np.argsort(dist)
            k = int(min(len(order), max(1, int(params.k))))
            top_vals = cand[target].to_numpy()[order[:k]]
            if params.agg == "trimmed" and len(top_vals) >= 10:
                cut = int(max(1, math.floor(params.trim_frac * len(top_vals))))
                top_vals = np.sort(top_vals)[cut: len(top_vals) - cut]
            base = float(np.median(top_vals)) if len(top_vals) else float(np.median(vals)) if len(vals) else float(train_df.iloc[: asof_idx + 1][target].median())
        else:
            base = float(np.median(vals)) if len(vals) else float(train_df.iloc[: asof_idx + 1][target].median())
    else:
        if vals.size == 0:
            base = float(train_df.iloc[: asof_idx + 1][target].median())
        else:
            if params.agg == "trimmed" and vals.size >= 10:
                k = int(max(1, math.floor(params.trim_frac * vals.size)))
                vals = np.sort(vals)[k: vals.size - k]
            base = float(np.median(vals))
    growth = compute_growth_index(train_df, asof_idx, target, alpha=params.growth_alpha, cap_low=params.cap_low, cap_high=params.cap_high)
    return float(base * growth)


@dataclass
class MLParams:
    lags: Tuple[int, ...] = tuple(DEFAULT_LAGS)
    use_roll: bool = True
    model: str = "gbr"  # or "elasticnet"
    loss: str = "huber"  # for GBR
    multi_horizon: bool = False


def build_feature_views(df: pd.DataFrame, target: str, params: MLParams) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """Return DF with features added and the cat/num lists."""
    fdf = add_lag_features(df, target, params.lags)
    cats = ["schedule_label"]
    # Add weather features explicitly
    nums = [
        "weekday_index",
        "month",
        "days_since_start",
        "operating_hours",
        "max_temperature",
        "precipitation",
    ]
    for lag in params.lags:
        nums.append(f"{target}_lag_{int(lag)}")
    if params.use_roll:
        nums += [f"{target}_roll7_mean", f"{target}_roll28_mean"]
    if params.multi_horizon:
        # Ensure the column exists so selection with cats+nums works
        if "horizon" not in fdf.columns:
            fdf = fdf.copy()
            fdf["horizon"] = np.nan
        nums.append("horizon")
    return fdf, cats, nums


def backtest(
    df: pd.DataFrame,
    target: str,
    horizons: Sequence[int],
    min_train_days: int,
    step_days: int,
    analog_params: AnalogParams,
    ml_params_grid: List[MLParams],
    *,
    future_weather_mode: str = "actual",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Run expanding-window backtest. Returns (analog_results, ml_results).

    Strategy: use one origin per split (every step_days), predict for each
    horizon h, accumulate errors. Keeps runtime reasonable while still
    comparing options.
    """
    df = df.sort_values("date").reset_index(drop=True)
    n = len(df)
    origins: List[int] = []
    i = int(min_train_days)
    last_needed_h = int(max(horizons))
    while i + last_needed_h < n:
        origins.append(i)
        i += int(step_days)

    # Precompute feature views for ML grids (one per grid config)
    ml_views: Dict[str, Tuple[pd.DataFrame, List[str], List[str]]] = {}
    for mp in ml_params_grid:
        key = f"lags={','.join(map(str, mp.lags))}|roll={int(mp.use_roll)}|model={mp.model}|loss={mp.loss}|mh={int(mp.multi_horizon)}"
        ml_views[key] = build_feature_views(df, target, mp)

    # Results collectors
    a_rows: List[Dict[str, object]] = []
    m_rows: List[Dict[str, object]] = []

    for asof_idx in origins:
        # Cache the as-of row for growth indexing
        for h in horizons:
            tgt_idx = asof_idx + int(h)
            tgt_row = df.iloc[tgt_idx]
            # Analog prediction
            pred_a = analog_predict(
                df, tgt_row, target, asof_idx, analog_params, future_weather_mode=future_weather_mode
            )
            err_a = float(tgt_row[target]) - float(pred_a)
            a_rows.append({
                "asof": str(df.iloc[asof_idx]["date"].date()),
                "h": int(h),
                "y_true": float(tgt_row[target]),
                "y_pred": float(pred_a),
                "model": "analog",
            })

            # ML predictions for each grid config
            for key, (fdf, cats, nums) in ml_views.items():
                # Identify params for this key
                mp = next(
                    (m for m in ml_params_grid if key.startswith(f"lags={','.join(map(str, m.lags))}|roll={int(m.use_roll)}|model={m.model}|loss={m.loss}|mh={int(m.multi_horizon)}")),
                    ml_params_grid[0],
                )

                # Compute max lag for safety
                try:
                    max_lag = max(int(x) for x in mp.lags)
                except Exception:
                    max_lag = 0

                # Build training set
                if mp.multi_horizon:
                    rows_list: List[pd.DataFrame] = []
                    y_list: List[float] = []
                    for idx in range(max_lag, asof_idx - min(horizons)):
                        for hh in horizons:
                            tgt_i = idx + int(hh)
                            if tgt_i >= asof_idx:
                                break
                            r = fdf.iloc[[idx]][cats + nums].copy()
                            if "horizon" in r.columns:
                                r.loc[:, "horizon"] = float(hh)
                            rows_list.append(r)
                            y_list.append(float(df.iloc[tgt_i][target]))
                    if not rows_list:
                        continue
                    X_train = pd.concat(rows_list, ignore_index=True)
                    y_train = np.array(y_list, dtype=float)
                else:
                    # Direct per-horizon
                    X_train_parts: List[pd.DataFrame] = []
                    y_train_list: List[float] = []
                    for idx in range(max_lag, asof_idx - int(h)):
                        r = fdf.iloc[[idx]][cats + nums].copy()
                        if "horizon" in r.columns:
                            r.loc[:, "horizon"] = float(h)
                        y_val = float(df.iloc[idx + int(h)][target])
                        if not np.isfinite(y_val):
                            continue
                        X_train_parts.append(r)
                        y_train_list.append(y_val)
                    if not X_train_parts:
                        continue
                    X_train = pd.concat(X_train_parts, ignore_index=True)
                    y_train = np.array(y_train_list, dtype=float)

                pipe = build_ml_pipeline(cats, nums, model=mp.model, loss=mp.loss)
                pipe.fit(X_train, y_train)

                X_test = fdf.iloc[[asof_idx]][cats + nums].copy()
                if "horizon" in X_test.columns:
                    X_test.loc[:, "horizon"] = float(h)
                if future_weather_mode != "actual":
                    # Simulate unknown future weather at origin by masking
                    for col in ("max_temperature", "precipitation"):
                        if col in X_test.columns:
                            X_test.loc[:, col] = np.nan
                y_pred = float(pipe.predict(X_test)[0])
                m_rows.append({
                    "asof": str(df.iloc[asof_idx]["date"].date()),
                    "h": int(h),
                    "y_true": float(tgt_row[target]),
                    "y_pred": float(y_pred),
                    "model": key,
                })

    a_df = pd.DataFrame(a_rows)
    m_df = pd.DataFrame(m_rows)
    return a_df, m_df


def summarize_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    def _agg(g: pd.DataFrame) -> pd.Series:
        y = g["y_true"].to_numpy()
        yhat = g["y_pred"].to_numpy()
        mae = float(np.mean(np.abs(y - yhat)))
        rmse = float(np.sqrt(np.mean((y - yhat) ** 2)))
        sm = smape(y, yhat)
        return pd.Series({"mae": mae, "rmse": rmse, "smape": sm})
    out = df.groupby(["model", "h"]).apply(_agg).reset_index()
    return out.sort_values(["h", "rmse", "mae"]).reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backtest analog-day and lag-ML forecast models")
    p.add_argument("--db", dest="db_path", default=getattr(wcfg, "DB_FILENAME", ""))
    p.add_argument("--orgsite-id", type=int, default=1)
    p.add_argument("--target", choices=list(TARGETS), default="num_parked_combined")
    p.add_argument("--horizons", type=int, nargs="*", default=list(DEFAULT_HORIZONS))
    p.add_argument("--min-train-days", type=int, default=540, help="Minimum days before first split")
    p.add_argument("--step-days", type=int, default=28, help="Days between split origins")

    # Analog params
    p.add_argument("--analog-lookback", type=int, default=18, help="Lookback months")
    p.add_argument("--analog-agg", choices=["median", "trimmed"], default="median")
    p.add_argument("--analog-trim-frac", type=float, default=0.1)
    p.add_argument("--growth-alpha", type=float, default=0.5)
    p.add_argument("--growth-cap-low", type=float, default=0.7)
    p.add_argument("--growth-cap-high", type=float, default=1.3)
    p.add_argument("--analog-k", type=int, default=0, help="Top-K weather neighbors (0=disable)")
    p.add_argument("--temp-weight", type=float, default=2.0, help="Weight for temperature distance")
    p.add_argument("--precip-weight", type=float, default=1.0, help="Weight for precipitation distance")

    # ML grid (simple)
    p.add_argument("--ml-models", nargs="*", default=["gbr", "elasticnet"], help="Models to try")
    p.add_argument("--ml-loss", choices=["squared_error", "absolute_error", "huber"], default="huber")
    p.add_argument("--lags-sets", nargs="*", default=["2,4,7,14,28,56,365", "7,14,28,56,365"], help="Lag sets to try")
    p.add_argument("--no-roll", action="store_true", help="Disable rolling mean features")
    p.add_argument("--multi-horizon", action="store_true", help="Train a single model per split with horizon feature")

    # Future weather availability for backtests (actual=best case; none=unknown)
    p.add_argument("--future-weather", choices=["actual", "none"], default="actual")

    p.add_argument("--csv", dest="csv_path", default="", help="Optional CSV output path (summary)")
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
        return 2

    df = load_day_df(db_path, args.orgsite_id)

    analog = AnalogParams(
        lookback_months=int(args.analog_lookback),
        agg=str(args.analog_agg),
        trim_frac=float(args.analog_trim_frac),
        growth_alpha=float(args.growth_alpha),
        cap_low=float(args.growth_cap_low),
        cap_high=float(args.growth_cap_high),
        k=int(args.analog_k),
        temp_weight=float(args.temp_weight),
        precip_weight=float(args.precip_weight),
    )

    ml_grid: List[MLParams] = []
    for lagset in args.lags_sets:
        lags = tuple(int(x) for x in str(lagset).split(",") if str(x).strip())
        for mdl in args.ml_models:
            ml_grid.append(
                MLParams(
                    lags=lags,
                    use_roll=not args.no_roll,
                    model=str(mdl),
                    loss=str(args.ml_loss),
                    multi_horizon=bool(args.multi_horizon),
                )
            )

    a_raw, m_raw = backtest(
        df,
        args.target,
        horizons=[int(h) for h in args.horizons],
        min_train_days=int(args.min_train_days),
        step_days=int(args.step_days),
        analog_params=analog,
        ml_params_grid=ml_grid,
        future_weather_mode=str(args.future_weather),
    )

    a_sum = summarize_results(a_raw)
    m_sum = summarize_results(m_raw)

    # Pretty print summary
    def _print_df(name: str, sdf: pd.DataFrame) -> None:
        if sdf.empty:
            print(f"\n{name}: (no results)")
            return
        print(f"\n{name} (sorted by h, rmse):")
        cols = ["model", "h", "mae", "rmse", "smape"]
        sdf = sdf[cols]
        with pd.option_context("display.max_columns", None, "display.width", 120):
            print(sdf.to_string(index=False))

    _print_df("Analog-day summary", a_sum)
    _print_df("Lag-ML summary", m_sum)

    # Recommend per-horizon best ML config, and analog baseline
    try:
        recs = []
        if not m_sum.empty:
            for h in sorted(m_sum["h"].unique()):
                sub = m_sum[m_sum["h"] == h].sort_values(["rmse", "mae"]).head(1)
                if not sub.empty:
                    r = sub.iloc[0]
                    recs.append(f"h={int(h)}: ML -> {r['model']} | RMSE={r['rmse']:.2f}, MAE={r['mae']:.2f}")
        if not a_sum.empty:
            for h in sorted(a_sum["h"].unique()):
                sub = a_sum[a_sum["h"] == h].head(1)
                if not sub.empty:
                    r = sub.iloc[0]
                    recs.append(f"h={int(h)}: Analog baseline | RMSE={r['rmse']:.2f}, MAE={r['mae']:.2f}")
        if recs:
            print("\nRecommendations:")
            for line in recs:
                print("  ", line)
    except Exception:
        pass

    if args.csv_path:
        out = pd.concat([
            a_sum.assign(family="analog"),
            m_sum.assign(family="ml"),
        ], ignore_index=True)
        Path(args.csv_path).parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(args.csv_path, index=False)
        print(f"\nWrote CSV: {args.csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
