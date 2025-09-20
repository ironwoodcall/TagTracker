#!/usr/bin/env python3
"""Selection strategies for the estimator's best-guess rows.

Provides two strategies:
  - range_first: narrowest 90% range, then higher confidence (legacy)
  - accuracy_first: calibration best_model, else range_first (with guardrails)

Each candidate is a tuple: (width, -confidence_int, model_code, row_tuple)
Returns (best_candidate, rationale_str)

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

from typing import Dict, List, Tuple, Optional


def select_by_range_then_conf(cands: List[Tuple[int, int, str, tuple]]):
    cands.sort()  # width asc, then -conf asc
    return cands[0]


def _measure_key_by_index(i: int) -> Optional[str]:
    return 'act' if i == 0 else ('fut' if i == 1 else ('peak' if i == 3 else None))


def select_best_candidate(
    model_codes: Dict[str, bool],  # present for clarity, unused
    calib_best: Optional[Dict[str, Dict[str, str]]],
    idx: int,
    cands: List[Tuple[int, int, str, tuple]],
    frac_elapsed: float,
    cohort_n: int,
    guard_min: int = 4,
) -> Tuple[Tuple[int, int, str, tuple], str]:
    """Accuracy-first selection with guardrails.

    Returns (candidate, rationale)
    """
    meas_key = _measure_key_by_index(idx)
    # Prefer calibration recommendation
    try:
        if calib_best and meas_key:
            # caller must translate frac_elapsed to a bin label
            # defer to caller to provide one; here we scan candidates for any
            # matching preferred model
            # Better to pass bin label explicitly; kept simple for now.
            pass
    except Exception:
        pass

    # If cohort too small or no calibration, prefer SM then REC
    if cohort_n < max(1, int(guard_min)) or not calib_best:
        for target in ['SM', 'REC']:
            for cand in cands:
                if cand[2] == target:
                    return cand, f"guardrail: n={cohort_n}; prefer {target}"

    # Else: range then confidence
    best = select_by_range_then_conf(cands)
    width, neg_conf, mdl, _row = best
    return best, f"narrowest range width {width}; conf {abs(neg_conf)}%"


def dispatch_select(
    selection_mode: str,
    calib_best: Optional[Dict[str, Dict[str, str]]],
    idx: int,
    cands: List[Tuple[int, int, str, tuple]],
    frac_elapsed: float,
    cohort_n: int,
    guard_min: int = 4,
    preferred_model: Optional[str] = None,
    bin_label: Optional[str] = None,
) -> Tuple[Tuple[int, int, str, tuple], str]:
    mode = (selection_mode or "").strip().lower() or "accuracy_first"
    if mode == "range_first":
        best = select_by_range_then_conf(cands)
        width, neg_conf, mdl, _row = best
        return best, f"legacy: narrowest range width {width}; conf {abs(neg_conf)}%"

    # accuracy_first: prefer calibration best if available
    meas_key = _measure_key_by_index(idx)
    if calib_best and meas_key and bin_label:
        try:
            pref = calib_best.get(meas_key, {}).get(bin_label)
        except Exception:
            pref = None
        if pref:
            for cand in cands:
                if cand[2] == pref:
                    return cand, f"calibrated best_model {pref} for bin {bin_label}"

    return select_best_candidate({}, calib_best, idx, cands, frac_elapsed, cohort_n, guard_min)

