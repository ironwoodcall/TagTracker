#!/usr/bin/env python3
"""Rendering helpers for web_estimator.

Builds human-readable table outputs for STANDARD and FULL views, including
headers, underline rows, and details sections. This module is pure formatting;
all computations are performed by the estimator core.

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

from typing import List, Tuple, Optional

from common.tt_time import VTime


def _col_widths(rows: List[List[str]]) -> List[int]:
    return [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]


def _fmt_row(r: List[str], widths: List[int]) -> str:
    # Left-justify 1st, right-justify others
    # Column count can vary; make a safe format with spacing between columns
    out: List[str] = []
    for i, s in enumerate(r):
        if i in (0,):
            out.append(str(s).ljust(widths[i]))
        else:
            out.append(str(s).rjust(widths[i]))
    return "  ".join(out)


def render_tables(
    as_of_when: VTime,
    verbose: bool,
    tables: List[Tuple[str, List[Tuple[str, str, str, str]], Optional[str]]],
    header_mixed: List[str],
    header_full: List[str],
    mixed_models: Optional[List[str]] = None,
    selected_by_model: Optional[dict] = None,
    selection_info: Optional[List[str]] = None,
    calib: Optional[dict] = None,
    calib_debug: Optional[List[str]] = None,
    *,
    as_html: bool = False,
) -> List[str]:
    if as_html:
        return _render_tables_html(
            as_of_when,
            verbose,
            tables,
            header_mixed,
            header_full,
            mixed_models,
            selected_by_model,
            selection_info,
            calib,
            calib_debug,
        )
    return _render_tables_text(
        as_of_when,
        verbose,
        tables,
        header_mixed,
        header_full,
        mixed_models,
        selected_by_model,
        selection_info,
        calib,
        calib_debug,
    )


def _render_tables_text(
    as_of_when: VTime,
    verbose: bool,
    tables: List[Tuple[str, List[Tuple[str, str, str, str]], Optional[str]]],
    header_mixed: List[str],
    header_full: List[str],
    mixed_models: Optional[List[str]],
    selected_by_model: Optional[dict],
    selection_info: Optional[List[str]],
    calib: Optional[dict],
    calib_debug: Optional[List[str]],
) -> List[str]:
    lines: List[str] = []
    if not tables:
        return ["No estimates available"]

    if not verbose:
        title_base, rows, _mc = tables[0]
        mixed_rows_disp: List[List[str]] = []
        for i, r in enumerate(rows):
            model = (mixed_models[i] if mixed_models and i < len(mixed_models) else "")
            mixed_rows_disp.append([r[0], r[1], r[2], r[3], model])
        header = list(header_mixed)
        width_rows = [header] + mixed_rows_disp
        widths = _col_widths(width_rows)
        title = f"{title_base} (as of {as_of_when.short})"
        lines.append(title)
        lines.append(_fmt_row(header, widths))
        dash_row = ["-" * w for w in widths]
        lines.append(_fmt_row(dash_row, widths))
        for r in mixed_rows_disp:
            lines.append(_fmt_row(r, widths))
        return lines

    lines.append("Detailed Estimation Information")
    lines.append("")
    for t_index, (title_base, rows, model_code) in enumerate(tables):
        if t_index == 0:
            continue
        header = list(header_full)
        preview_rows: List[List[str]] = []
        for idx, (m, v, r90, prob) in enumerate(rows):
            mark = ""
            if model_code and selected_by_model:
                try:
                    if idx in selected_by_model.get(model_code, set()):
                        mark = "<--BEST"
                except Exception:
                    mark = ""
            preview_rows.append([m, v, r90, prob, mark])

        width_rows = [header] + preview_rows
        widths = _col_widths(width_rows)
        title = f"{title_base} (as of {as_of_when.short})"
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(title)
        lines.append(_fmt_row(header, widths))
        dash_row = [("-" * widths[i]) if header[i] else "" for i in range(len(header))]
        lines.append(_fmt_row(dash_row, widths))
        for row6 in preview_rows:
            lines.append(_fmt_row(row6, widths))

    lines.append("")
    lines.append("Details")
    lines.append("-------")
    if selection_info:
        lines.append("Selection rationale:")
        for info in selection_info:
            lines.append(f"  {info}")
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


def _render_tables_html(
    as_of_when: VTime,
    verbose: bool,
    tables: List[Tuple[str, List[Tuple[str, str, str, str]], Optional[str]]],
    header_mixed: List[str],
    header_full: List[str],
    mixed_models: Optional[List[str]],
    selected_by_model: Optional[dict],
    selection_info: Optional[List[str]],
    calib: Optional[dict],
    calib_debug: Optional[List[str]],
) -> List[str]:
    import html as _html

    if not tables:
        return ["<p>No estimates available</p>"]

    def _table_html(
        title: str,
        header: List[str],
        rows: List[List[str]],
    ) -> List[str]:
        out: List[str] = []
        colcount = len(header)
        out.append("<table class=\"general_table estimator_table\">")
        if title:
            out.append(
                f"<tr><th colspan={colcount}>{_html.escape(title)}</th></tr>"
            )
        if header:
            out.append("<tr>")
            for h in header:
                s = _html.escape(h) if h else "Best<br>Choice?"
                out.append(f"<th>{s}</th>")
            out.append("</tr>")
        for row in rows:
            out.append("<tr>")
            for cell in row:
                out.append(f"<td>{_html.escape(cell)}</td>")
            out.append("</tr>")
        out.append("</table><br>")
        return out

    lines: List[str] = []

    if not verbose:
        title_base, rows, _mc = tables[0]
        mixed_rows_disp: List[List[str]] = []
        for i, r in enumerate(rows):
            model = (mixed_models[i] if mixed_models and i < len(mixed_models) else "")
            mixed_rows_disp.append([r[0], r[1], r[2], r[3], model])
        title = f"{title_base} (as of {as_of_when.short})"
        lines.extend(_table_html(title, header_mixed, mixed_rows_disp))
        return lines

    # Verbose: include best-guess per model tables and details
    for t_index, (title_base, rows, model_code) in enumerate(tables):
        if t_index == 0:
            continue
        header = list(header_full)
        preview_rows: List[List[str]] = []
        for idx, (m, v, r90, prob) in enumerate(rows):
            mark = ""
            if model_code and selected_by_model:
                try:
                    if idx in selected_by_model.get(model_code, set()):
                        mark = "<--BEST"
                except Exception:
                    mark = ""
            preview_rows.append([m, v, r90, prob, mark])
        title = f"{title_base} (as of {as_of_when.short})"
        lines.extend(_table_html(title, header, preview_rows))

    detail_rows: List[str] = []
    detail_rows.append("<table class=\"general_table estimator_table\">")
    detail_rows.append("<h3>Details</h3>")
    if selection_info:
        detail_rows.append("<h4>Selection rationale</h4>")
        for info in selection_info:
            detail_rows.append(f"<li>{_html.escape(info)}")
    calib_msg = "Calibration JSON: used" if calib else "Calibration JSON: not used"
    detail_rows.append(
        f"<h4>Calibration</h4>{_html.escape(calib_msg)}"
    )
    if calib:
        try:
            cdate = calib.get("creation_date")
            ccomment = calib.get("comment")
            if cdate:
                detail_rows.append(
                    f"<li>Created: {_html.escape(str(cdate))}"
                )
            if ccomment:
                detail_rows.append(
                    f"<li>{_html.escape(str(ccomment))}"
                )
        except Exception:
            pass
    if calib_debug:
        for msg in calib_debug:
            detail_rows.append(
                f"<li>{_html.escape(msg)}"
            )
    detail_rows.append("<br>")
    lines.extend(detail_rows)
    return lines
