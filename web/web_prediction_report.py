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
from datetime import datetime, date as _date

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
    """Return (time_open, time_closed) pairs with at least 3 uses in last 14 months.

    Uses the DB's own latest DAY date as reference. Returns HH:MM strings sorted.
    """
    try:
        rows = database.execute(
            """
            SELECT time_open, time_closed, COUNT(*) AS cnt
              FROM DAY
             WHERE orgsite_id = 1
               AND time_open IS NOT NULL AND time_open != ''
               AND time_closed IS NOT NULL AND time_closed != ''
               AND date >= DATE((SELECT MAX(DATE(date)) FROM DAY WHERE orgsite_id = 1), '-14 months')
             GROUP BY time_open, time_closed
            HAVING cnt >= 3
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
    # Extra guard: ensure sorted order (HH:MM then HH:MM)
    pairs = sorted(pairs, key=lambda t: (t[0], t[1]))
    # Default the date shown in the form to tomorrow if not provided
    date_val = params.start_date or ut.date_str("tomorrow")
    sched_sel = str(getattr(params, "schedule", "") or "")
    precip_val = "" if params.precipitation is None else str(params.precipitation)
    temp_val = "" if params.temperature is None else str(params.temperature)

    # Begin form
    print(
        "<form method='GET' style=\"margin-bottom:1rem\">"
        "<div style=\"border:1px solid #aaa;padding:10px;border-radius:6px;max-width:26rem;\">"
        "<div style=\"display:grid;grid-template-columns:1fr 1fr;column-gap:0.75rem;row-gap:0.5rem;align-items:center;\">"
    )
    # Ensure routing stays on this report
    print(f"<input type='hidden' name='{cc.ReportParameters.cgi_name('what_report')}' value='{cc.WHAT_PREDICT_FUTURE}'>")
    # Hidden schedule field that is set by the dropdown
    print(f"<input type='hidden' name='{cc.ReportParameters.cgi_name('schedule')}' value='{html.escape(sched_sel)}'>")

    # Top-left: Date
    print(
        f"<div style='display:flex;align-items:center;gap:0.25rem;'><label for='start_date'><b>Date:</b></label>"
        f"<input type='date' id='start_date' name='{cc.ReportParameters.cgi_name('start_date')}' value='{html.escape(date_val)}'></div>"
    )
    # Top-right: Max temp
    print(
        f"<div style='display:flex;align-items:center;gap:0.25rem;justify-content:flex-end;'><label for='temp'><b>Max temp:</b></label>"
        f"<input type='number' id='temp' step='0.1' size='4' style='width:5rem' name='{cc.ReportParameters.cgi_name('temperature')}' value='{html.escape(temp_val)}'></div>"
    )
    # Bottom-left: Schedule dropdown
    print(
        f"<div style='display:flex;align-items:center;gap:0.25rem;'><label for='schedule_select'><b>Open–Close:</b></label>"
        f"<select id='schedule_select' style='width:auto' onchange=\"var el=document.getElementsByName('{cc.ReportParameters.cgi_name('schedule')}')[0]; if(this.value && this.value!='-') el.value=this.value;\">"
    )
    print("<option value='-'>-- select --</option>")
    for o, c in pairs:
        val = f"{o}-{c}"
        selected = " selected" if (sched_sel == val) else ""
        print(f"<option value='{html.escape(val)}'{selected}>{html.escape(o)}–{html.escape(c)}</option>")
    print("</select></div>")
    # Bottom-right: Precip
    print(
        f"<div style='display:flex;align-items:center;gap:0.25rem;justify-content:flex-end;'><label for='precip'><b>Precip (mm):</b></label>"
        f"<input type='number' id='precip' step='0.1' size='4' style='width:5rem' name='{cc.ReportParameters.cgi_name('precipitation')}' value='{html.escape(precip_val)}'></div>"
    )

    print("</div>")  # end grid
    print("<div style='text-align:center;margin-top:10px;'><input type='submit' value='Predict'></div>")
    # Informational note (kept within the same box, no width change)
    print(
        "<div style='margin-top:8px;font-size:0.85em;color:#555;line-height:1.3;'>"
        "This experimental model predicts bike traffic in the future based on past data. "
        "It remains experimental as the model is refined to try to let it make reliable predictions. "
        "It is heavily weighted to schedule and weather, but knows nothing about special events."
        "</div>"
    )
    print("</div>")  # end bordered box

    print("</form>")


def _default_schedule_for_date(database, target_date: str) -> str | None:
    """Return a canonical 'HH:MM-HH:MM' schedule for the most recent
    date in the DB that has the same weekday as ``target_date``.

    Returns None if no match is found.
    """
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        return None

    # SQLite strftime('%w', date) is 0..6 with Sunday=0
    iso = dt.isoweekday()  # 1..7 (Mon..Sun)
    sqlite_w = 0 if iso == 7 else iso

    try:
        row = database.execute(
            """
            SELECT time_open, time_closed
              FROM DAY
             WHERE orgsite_id = 1
               AND time_open IS NOT NULL AND time_open != ''
               AND time_closed IS NOT NULL AND time_closed != ''
               AND strftime('%w', date) = ?
             ORDER BY date DESC
             LIMIT 1
            ;
            """,
            (str(sqlite_w),),
        ).fetchone()
    except Exception:
        row = None

    if not row:
        return None

    try:
        o = VTime(str(row[0]))
        c = VTime(str(row[1]))
        if not o or not c:
            return None
        return f"{str(o)}-{str(c)}"
    except Exception:
        return None


def prediction_report(database, params) -> None:
    """Render the prediction page.

    database: sqlite3.Connection (unused here; included for consistency)
    params: ReportParameters with resolved fields
    """

    print(cc.titleize("Future day prediction"))
    print(f"{cc.main_and_back_buttons(pages_back=cc.increment_pages_back(params.pages_back))}<br><br>")

    # Apply defaults before rendering the form so selections reflect them
    if not (params.start_date and str(params.start_date).strip()):
        # Use tomorrow as the default start date, stored as YYYY-MM-DD
        default_date = ut.date_str("tomorrow")
        if default_date:
            try:
                params.set_property("start_date", default_date)
            except Exception:
                # If normalization fails for some reason, fall back to assign
                params.start_date = default_date

    # If no schedule given, use most recent schedule for same weekday
    if not getattr(params, "schedule", None):
        effective_date = params.start_date or ut.date_str("tomorrow")
        sched = _default_schedule_for_date(database, effective_date)
        if sched:
            try:
                params.set_property("schedule", sched)
            except Exception:
                params.schedule = sched

    # Render input form at top (will show defaults if applied)
    _render_form(database, params)

    # If temperature or precipitation missing, show a bold notice below the box and stop
    if params.precipitation is None or params.temperature is None:
        print("<div style='font-weight:bold;margin-top:0.25rem;'>Must give anticipated temperature and precipitation</div>")
        return

    # Validate required parameters; if missing anything else, just stop
    if not (params.start_date and getattr(params, "schedule", None)):
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

    # Fetch actuals (if present in DB for this date)
    has_actual = False
    actual_total = None
    actual_max = None
    actual_open = None
    actual_close = None
    actual_temp = None
    actual_precip = None
    try:
        cur = database.cursor()
        row = cur.execute(
            (
                "SELECT time_open, time_closed, max_temperature, precipitation, "
                "num_parked_combined, num_fullest_combined "
                "FROM DAY WHERE date = ? AND orgsite_id = 1"
            ),
            (date,),
        ).fetchone()
        if row is not None:
            has_actual = True
            actual_open = str(row[0])[:5] if row[0] else None
            actual_close = str(row[1])[:5] if row[1] else None
            actual_temp = row[2]
            actual_precip = row[3]
            actual_total = row[4]
            actual_max = row[5]
    except Exception:
        has_actual = False
        actual_open = actual_close = None
        actual_temp = actual_precip = None
        actual_total = actual_max = None

    # Render table
    print("<table class='general_table' style='max-width:42rem'>")
    # Title row
    try:
        pred_dt = datetime.strptime(date, "%Y-%m-%d").date()
        today = _date.today()
        days_delta = (pred_dt - today).days
        future_past = "future" if days_delta >= 0 else "past"
        n_abs = abs(days_delta)
        dow3 = ut.dow_str(date, 3)
        title = f"Prediction for {dow3} {html.escape(date)} ({n_abs} days in the {future_past})"
    except Exception:
        title = f"Prediction for {html.escape(date)}"
    total_cols = 5 if has_actual else 4
    print(f"<tr><th colspan={total_cols} class='heavy-bottom'>{title}</th></tr>")

    # Header for predictions (now used for both inputs and model outputs)
    if has_actual:
        print("<tr><th>Measure</th><th>Actual</th><th>Prediction</th><th>Range (approx)</th><th>Notes</th></tr>")
        # Input rows shown in the table using Prediction/Actual columns
        print(
            "<tr>"
            "<td>Schedule</td>"
            f"<td>{'' if (not actual_open or not actual_close) else html.escape(actual_open + '–' + actual_close)}</td>"
            f"<td>{html.escape(otime)}–{html.escape(ctime)}</td>"
            "<td></td><td></td>"
            "</tr>"
        )
        print(
            "<tr>"
            "<td>Max temp</td>"
            f"<td>{'' if actual_temp is None else actual_temp}</td>"
            f"<td>{temp}</td>"
            "<td></td><td></td>"
            "</tr>"
        )
        print(
            "<tr class='heavy-bottom'>"
            "<td>Precipitation</td>"
            f"<td>{'' if actual_precip is None else str(actual_precip) + ' mm'}</td>"
            f"<td>{precip} mm</td>"
            "<td></td><td></td>"
            "</tr>"
        )
    else:
        print("<tr><th>Measure</th><th>Prediction</th><th>Range (approx)</th><th>Notes</th></tr>")
        print(
            "<tr>"
            "<td>Schedule</td>"
            f"<td>{html.escape(otime)}–{html.escape(ctime)}</td>"
            "<td></td><td></td>"
            "</tr>"
        )
        print(
            "<tr>"
            "<td>Max temp</td>"
            f"<td>{temp}</td>"
            "<td></td><td></td>"
            "</tr>"
        )
        print(
            "<tr class='heavy-bottom'>"
            "<td>Precipitation</td>"
            f"<td>{precip} mm</td>"
            "<td></td><td></td>"
            "</tr>"
        )
    if has_actual:
        print(
            "<tr>"
            "<td>Total visits</td>"
            f"<td>{'' if actual_total is None else int(actual_total)}</td>"
            f"<td>{'' if out.remainder is None else out.remainder}</td>"
            f"<td>{_fmt_rng(out.remainder_range)}</td>"
            f"<td></td>"
            "</tr>"
        )
    else:
        print(
            "<tr>"
            "<td>Total visits</td>"
            f"<td>{'' if out.remainder is None else out.remainder}</td>"
            f"<td>{_fmt_rng(out.remainder_range)}</td>"
            f"<td></td>"
            "</tr>"
        )
    if has_actual:
        print(
            "<tr>"
            "<td>Max bikes</td>"
            f"<td>{'' if actual_max is None else int(actual_max)}</td>"
            f"<td>{'' if out.peak is None else out.peak}</td>"
            f"<td>{_fmt_rng(out.peak_range)}</td>"
            f"<td></td>"
            "</tr>"
        )
    else:
        print(
            "<tr>"
            "<td>Max bikes</td>"
            f"<td>{'' if out.peak is None else out.peak}</td>"
            f"<td>{_fmt_rng(out.peak_range)}</td>"
            f"<td></td>"
            "</tr>"
        )
    print("</table>")
