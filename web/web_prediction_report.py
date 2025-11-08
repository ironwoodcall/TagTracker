#!/usr/bin/env python3
"""Prediction report page using the schedule-driven predictor.

Accepts CGI parameters via ReportParameters (date, schedule, precipitation,
temperature) and renders a simple HTML table of predicted metrics:
total visits (as 'remainder') and max bikes. Activity and time-of-max are
left blank for this model.
"""

from __future__ import annotations

import html
from typing import Optional, Iterable, Tuple

import web_common as cc
import common.tt_util as ut
from web.web_predictor_model import PredictorModel
from common.tt_time import VTime


def _fmt_rng(r: Optional[tuple[int, int]], is_time: bool = False) -> str:
    if not r:
        return ""
    a, b = r
    if is_time:
        return f"{VTime(a).short} to {VTime(b).short}"
    return f"{a} to {b}"


def _open_close_pairs(database) -> list[tuple[str, str]]:
    """Return distinct (time_open, time_closed) pairs observed in DB.

    Ordered by open then close. Returns HH:MM strings.
    """
    try:
        rows = database.execute(
            """
            SELECT DISTINCT time_open, time_closed
              FROM DAY
             WHERE time_open IS NOT NULL AND time_open != ''
               AND time_closed IS NOT NULL AND time_closed != ''
             ORDER BY time_open, time_closed
            ;
            """
        ).fetchall()
    except Exception:
        return []
    out: list[tuple[str, str]] = []
    for r in rows:
        o, c = (str(r[0] or ""), str(r[1] or ""))
        if o and c:
            out.append((o, c))
    return out


def _render_form(database, params) -> None:
    pairs = _open_close_pairs(database)
    date_val = params.start_date or ut.date_str("today")
    sched_sel = str(getattr(params, "schedule", "") or "")
    precip_val = "" if params.precipitation is None else str(params.precipitation)
    temp_val = "" if params.temperature is None else str(params.temperature)

    # Begin form
    print("<form method='GET' style='margin-bottom:1rem'>")
    # Ensure routing stays on this report
    print(f"<input type='hidden' name='{cc.ReportParameters.cgi_name('what_report')}' value='{cc.WHAT_PREDICT_FUTURE}'>")

    # Date picker
    print(
        f"<label for='start_date'><b>Date:</b></label> "
        f"<input type='date' id='start_date' name='{cc.ReportParameters.cgi_name('start_date')}' value='{html.escape(date_val)}'> "
    )

    # Open/Close dropdown
    print(
        f"<label for='schedule_select'><b>Open–Close:</b></label> "
        f"<select id='schedule_select' onchange=\"var el=document.getElementsByName('{cc.ReportParameters.cgi_name('schedule')}')[0]; if(this.value && this.value!='-') el.value=this.value;\">"
    )
    print("<option value='-'>-- select --</option>")
    for o, c in pairs:
        val = f"{o}-{c}"
        selected = " selected" if (sched_sel == val) else ""
        print(f"<option value='{html.escape(val)}'{selected}>{html.escape(o)}–{html.escape(c)}</option>")
    print("</select> ")

    # Single schedule field (manual entry or set by dropdown)
    print(
        f"<input type='text' size='11' name='{cc.ReportParameters.cgi_name('schedule')}' placeholder='HH:MM-HH:MM' value='{html.escape(sched_sel)}'> "
    )

    # Weather fields
    print(
        f"<label for='precip'><b>Precip (mm):</b></label> "
        f"<input type='number' id='precip' step='0.1' name='{cc.ReportParameters.cgi_name('precipitation')}' value='{html.escape(precip_val)}'> "
        f"<label for='temp'><b>Max temp:</b></label> "
        f"<input type='number' id='temp' step='0.1' name='{cc.ReportParameters.cgi_name('temperature')}' value='{html.escape(temp_val)}'> "
    )

    print("<input type='submit' value='Predict'>")
    print("</form>")


def prediction_report(database, params) -> None:
    """Render the prediction page.

    database: sqlite3.Connection (unused here; included for consistency)
    params: ReportParameters with resolved fields
    """

    print(cc.titleize("Future day prediction"))
    print(f"{cc.main_and_back_buttons(pages_back=getattr(params, 'pages_back', 1) or 1)}<br><br>")

    # Render input form at top
    _render_form(database, params)

    # Validate required parameters; if missing, just show form and stop
    if not (params.start_date and getattr(params, 'schedule', None) and params.precipitation is not None and params.temperature is not None):
        return

    # Load predictor
    model = PredictorModel()
    model.load()
    if not model.ready:
        print(
            "<div style='color:#a00'><b>Predictor model is not available.</b> "
            "Run helpers/train_predictor_model.py and ensure TRAINED_MODEL_FOLDER is set."
            "</div>"
        )
        return

    # Prepare inputs
    date = params.start_date  # resolved Y-m-d
    sched_val = str(getattr(params, "schedule", ""))
    try:
        otime, ctime = [s.strip() for s in sched_val.split("-", 1)]
    except Exception:
        print("<div style='color:#a00'><b>Bad schedule value.</b></div>")
        return
    precip = float(params.precipitation)
    temp = float(params.temperature)

    try:
        out = model.predict(
            precip=precip,
            temperature=temp,
            date=date,
            opening_time=otime,
            closing_time=ctime,
        )
    except Exception as e:  # pylint:disable=broad-exception-caught
        print(
            "<div style='color:#a00'><b>Prediction error:</b> "
            + html.escape(f"{type(e).__name__}: {e}")
            + "</div>"
        )
        return

    # Render table
    print("<table class='general_table' style='max-width:38rem'>")
    print(
        "<tr><th>Measure</th><th>Value</th><th>Range (approx)</th><th>Notes</th></tr>"
    )
    print(
        "<tr>"
        f"<td>Activity, first hour (from {html.escape(otime)})</td>"
        f"<td>{'' if out.activity_next_hour is None else out.activity_next_hour}</td>"
        f"<td>{_fmt_rng(out.activity_range)}</td>"
        f"<td></td>"
        "</tr>"
    )
    print(
        "<tr>"
        "<td>Total visits</td>"
        f"<td>{'' if out.remainder is None else out.remainder}</td>"
        f"<td>{_fmt_rng(out.remainder_range)}</td>"
        f"<td></td>"
        "</tr>"
    )
    print(
        "<tr>"
        "<td>Max bikes</td>"
        f"<td>{'' if out.peak is None else out.peak}</td>"
        f"<td>{_fmt_rng(out.peak_range)}</td>"
        f"<td></td>"
        "</tr>"
    )
    print(
        "<tr>"
        "<td>Time of max</td>"
        f"<td>{'' if out.peaktime is None else VTime(out.peaktime).short}</td>"
        f"<td>{_fmt_rng(out.peaktime_range, True)}</td>"
        f"<td></td>"
        "</tr>"
    )
    print("</table>")
