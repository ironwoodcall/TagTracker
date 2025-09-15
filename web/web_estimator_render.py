#!/usr/bin/env python3
"""Rendering helpers for web_estimator.

Builds human-readable table outputs for STANDARD and FULL views, including
headers, underline rows, and details sections. This module is pure formatting;
all computations are performed by the estimator core.
"""
from __future__ import annotations

from typing import List, Tuple, Optional

from common.tt_time import VTime


def _col_widths(rows: List[List[str]]) -> List[int]:
    return [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]


def _fmt_row(r: List[str], widths: List[int]) -> str:
    # Left-justify 1st, 3rd, 4th; right-justify 2nd and last by convention
    # Column count can vary; make a safe format with spacing between columns
    out: List[str] = []
    for i, s in enumerate(r):
        if i in (1, len(r) - 1):
            out.append(str(s).rjust(widths[i]))
        else:
            out.append(str(s).ljust(widths[i]))
    return "  ".join(out)


def render_tables(
    as_of_when: VTime,
    verbose: bool,
    tables: List[Tuple[str, List[Tuple[str, str, str, str, str]], Optional[str]]],
    header_mixed: List[str],
    header_full: List[str],
    mixed_models: Optional[List[str]] = None,
    selected_by_model: Optional[dict] = None,
    selection_info: Optional[List[str]] = None,
    calib: Optional[dict] = None,
    calib_debug: Optional[List[str]] = None,
) -> List[str]:
    lines: List[str] = []
    if not tables:
        return ["No estimates available"]

    if not verbose:
        # STANDARD: only mixed table with model column
        title_base, rows, _mc = tables[0]
        # Build rows including Model column from mixed_models list
        mixed_rows_disp: List[List[str]] = []
        for i, r in enumerate(rows):
            model = (mixed_models[i] if mixed_models and i < len(mixed_models) else "")
            mixed_rows_disp.append([r[0], r[1], r[3], r[4], model])
        header = list(header_mixed)
        width_rows = [header] + mixed_rows_disp
        widths = _col_widths(width_rows)
        title = f"{title_base} (as of {as_of_when.short})"
        lines.append(title)
        lines.append(_fmt_row(header, widths))
        # Underline row with dashes across all columns
        dash_row = ["-" * w for w in widths]
        lines.append(_fmt_row(dash_row, widths))
        for r in mixed_rows_disp:
            lines.append(_fmt_row(r, widths))
        return lines

    # FULL: page-level title then all model tables (skip mixed at index 0)
    lines.append("Detailed Estimation Information")
    lines.append("")
    for t_index, (title_base, rows, model_code) in enumerate(tables):
        if t_index == 0:
            continue
        # Build preview rows including far-right mark column
        header = list(header_full)
        preview_rows: List[List[str]] = []
        for idx, (m, v, c, r90, pc) in enumerate(rows):
            mark = ""
            if model_code and selected_by_model:
                try:
                    if idx in selected_by_model.get(model_code, set()):
                        mark = "*"
                except Exception:
                    mark = ""
            preview_rows.append([m, v, c, r90, pc, mark])

        width_rows = [header] + preview_rows
        widths = _col_widths(width_rows)
        title = f"{title_base} (as of {as_of_when.short})"
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(title)
        lines.append(_fmt_row(header, widths))
        # Build underline row, omitting dashes for empty header cells
        dash_row = [("-" * widths[i]) if header[i] else "" for i in range(len(header))]
        lines.append(_fmt_row(dash_row, widths))
        for row6 in preview_rows:
            lines.append(_fmt_row(row6, widths))

    # Details
    lines.append("")
    lines.append("Details")
    lines.append("-------")
    if selection_info:
        lines.append("Selection rationale:")
        for info in selection_info:
            lines.append(f"  {info}")
    # Calibration usage and metadata
    calib_msg = "Calibration JSON: used" if calib else "Calibration JSON: not used"
    lines.append(calib_msg)
    if calib:
        try:
            cdate = calib.get("creation_date")
            ccomment = calib.get("comment")
            if cdate:
                lines.append(f"  calibration creation_date: {cdate}")
            if ccomment:
                lines.append(f"  calibration comment: {ccomment}")
        except Exception:
            pass
    if calib_debug:
        for msg in calib_debug:
            lines.append(f"  {msg}")
    return lines

