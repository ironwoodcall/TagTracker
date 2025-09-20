#!/usr/bin/env python3
"""Calibration loader and helpers for web_estimator.

Provides functions to:
  - Load and cache calibration JSON
  - Compute bin labels for a given fraction elapsed
  - Fetch residual bands for a model/measure/bin

Kept lightweight to avoid altering estimator logic.

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

import json
import os
from typing import Any, Dict, List, Optional, Tuple


_CACHE: Optional[Dict[str, Any]] = None
_CACHE_BINS: Optional[List[Tuple[float, float, str]]] = None
_CACHE_BEST: Optional[Dict[str, Dict[str, str]]] = None


def load_calibration(wcfg_module, module_file: str) -> Tuple[Optional[dict], Optional[List[Tuple[float, float, str]]], Optional[dict], List[str]]:
    """Load calibration JSON and parse bins/best_model.

    Returns (calib_dict, bins_list, best_model_map, debug_messages)
    """
    debug: List[str] = []
    global _CACHE, _CACHE_BINS, _CACHE_BEST
    if _CACHE is not None:
        debug.append("calibration: using cached JSON")
        return _CACHE, _CACHE_BINS, _CACHE_BEST, debug

    calib = None
    bins = None
    best = None
    path_cfg = getattr(wcfg_module, "EST_CALIBRATION_FILE", "")
    tried: List[Tuple[str, bool, str]] = []
    candidates: List[str] = []
    if path_cfg:
        candidates.append(path_cfg)
        if not os.path.isabs(path_cfg):
            # Try absolute from cwd and module directory
            candidates.append(os.path.abspath(path_cfg))
            mod_dir = os.path.dirname(os.path.abspath(module_file))
            candidates.append(os.path.join(mod_dir, path_cfg))
    for p in candidates:
        exists = os.path.exists(p)
        tried.append((p, exists, "exists" if exists else "missing"))
        if not exists:
            continue
        try:
            with open(p, "r", encoding="utf-8") as fh:
                calib = json.load(fh)
                debug.append(f"calibration: loaded '{p}'")
                break
        except Exception as e:  # pylint:disable=broad-except
            debug.append(f"calibration: failed to load '{p}': {e}")
    if calib is None:
        if not path_cfg:
            debug.append("calibration: EST_CALIBRATION_FILE not set")
        else:
            for pth, _exi, note in tried:
                debug.append(f"calibration: tried '{pth}' -> {note}")
        return None, None, None, debug

    # Parse bins
    bins_list: List[Tuple[float, float, str]] = []
    try:
        for s in calib.get("time_bins", []) or []:
            a, b = s.split("-", 1)
            lo = float(a); hi = float(b)
            bins_list.append((lo, hi, s))
    except Exception:  # pylint:disable=broad-except
        bins_list = []

    best_model = calib.get("best_model", None)
    _CACHE, _CACHE_BINS, _CACHE_BEST = calib, (bins_list or None), best_model
    return _CACHE, _CACHE_BINS, _CACHE_BEST, debug


def bin_label(bins: Optional[List[Tuple[float, float, str]]], frac_elapsed: float) -> Optional[str]:
    if not bins:
        return None
    f = max(0.0, min(1.0, float(frac_elapsed)))
    for lo, hi, lbl in bins:
        if lo <= f < hi:
            return lbl
    return bins[-1][2]


def residual_band(calib: Optional[dict], bins: Optional[List[Tuple[float, float, str]]],
                  model: str, measure: str, frac_elapsed: float) -> Optional[Tuple[float, float]]:
    if not calib:
        return None
    lbl = bin_label(bins, frac_elapsed)
    try:
        ent = calib["residual_bands"][model][measure][lbl]
        q05 = ent.get("q05", None)
        q95 = ent.get("q95", None)
        if q05 is None or q95 is None:
            return None
        return float(q05), float(q95)
    except Exception:  # pylint:disable=broad-except
        return None

