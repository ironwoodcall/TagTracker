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

import web.web_common as cc
import common.tt_util as ut
from web.web_predictor_model import PredictorModel, PredictorOutput
from common.tt_time import VTime
import web.web_base_config as wcfg


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
        '<div style="border:1px solid #aaa;padding:10px;border-radius:6px;max-width:26rem;">'
        '<div style="display:grid;grid-template-columns:1fr 1fr;column-gap:0.75rem;row-gap:0.5rem;align-items:center;">'
    )
    # Ensure routing stays on this report
    print(
        f"<input type='hidden' name='{cc.ReportParameters.cgi_name('what_report')}' value='{cc.WHAT_PREDICT_FUTURE}'>"
    )
    # Hidden schedule field that is set by the dropdown
    print(
        f"<input type='hidden' name='{cc.ReportParameters.cgi_name('schedule')}' value='{html.escape(sched_sel)}'>"
    )
    # Carry forward and increment pages_back across submissions so Back works
    try:
        _pb_base = params.pages_back if isinstance(params.pages_back, int) else 1
        next_pages_back = cc.increment_pages_back(_pb_base)
    except Exception:
        next_pages_back = 1
    print(
        f"<input type='hidden' name='{cc.ReportParameters.cgi_name('pages_back')}' value='{next_pages_back}'>"
    )

    # Top-left: Date
    print(
        f"<div style='display:flex;align-items:center;gap:0.25rem;'><label for='start_date'><b>Date:</b></label>"
        f"<input type='date' id='start_date' name='{cc.ReportParameters.cgi_name('start_date')}' value='{html.escape(date_val)}'></div>"
    )
    # Top-right: Max temp
    print(
        f"<div style='display:flex;align-items:center;gap:0.25rem;justify-content:flex-end;'><label for='temp'><b>Max temp:</b></label>"
        f"<input type='number' id='temp' step='any' size='4' style='width:5rem' name='{cc.ReportParameters.cgi_name('temperature')}' value='{html.escape(temp_val)}'></div>"
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
        print(
            f"<option value='{html.escape(val)}'{selected}>{html.escape(o)}–{html.escape(c)}</option>"
        )
    print("</select></div>")
    # Bottom-right: Precip
    print(
        f"<div style='display:flex;align-items:center;gap:0.25rem;justify-content:flex-end;'><label for='precip'><b>Precip (mm):</b></label>"
        f"<input type='number' id='precip' step='any' size='4' style='width:5rem' name='{cc.ReportParameters.cgi_name('precipitation')}' value='{html.escape(precip_val)}'></div>"
    )

    print("</div>")  # end grid
    print(
        "<div style='text-align:center;margin-top:10px;'><input type='submit' value='Predict'></div>"
    )
    # Informational note (kept within the same box, no width change)
    print(
        "<div style='margin-top:8px;font-size:0.85em;color:#555;line-height:1.3;'>"
        "This experimental model predicts bike traffic in the future based on past data. "
        "It remains experimental as the model is refined to try to let it make reliable predictions. "
        "It is heavily weighted to schedule and weather, but knows nothing about special events.<br><br>"
        "Treat predictions with a grain or two of salt."
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
    params.pages_back = params.pages_back or 1
    print(f"{cc.main_and_back_buttons(pages_back=params.pages_back)}<br><br>")

    # Flag to allow us to skip missing-parameter error message on first entry
    _initial_entry = not (params.start_date or params.schedule)

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

    # If temperature/precip not provided, try climate normals for selected month
    used_normals_temp = False
    used_normals_precip = False
    try:
        normals = getattr(wcfg, "CLIMATE_NORMALS", {}) or {}
        eff_date = params.start_date or ut.date_str("tomorrow")
        if normals and eff_date:
            dt = datetime.strptime(eff_date, "%Y-%m-%d")
            m = dt.month
            month_norm = normals.get(m) if isinstance(normals, dict) else None
            if isinstance(month_norm, dict):
                if (
                    params.temperature is None
                    and month_norm.get("temperature") is not None
                ):
                    try:
                        params.set_property(
                            "temperature", float(month_norm["temperature"])
                        )
                    except Exception:
                        params.temperature = float(month_norm["temperature"])
                    used_normals_temp = True
                if (
                    params.precipitation is None
                    and month_norm.get("precipitation") is not None
                ):
                    try:
                        params.set_property(
                            "precipitation", float(month_norm["precipitation"])
                        )
                    except Exception:
                        params.precipitation = float(month_norm["precipitation"])
                    used_normals_precip = True
    except Exception:
        pass

    # Render input form at top (will show defaults if applied)
    _render_form(database, params)

    # Informational note when climate normals were used as defaults
    if used_normals_temp or used_normals_precip:
        print(
            "<div style='color:red;margin-top:0.25rem;'>"
            "Temperature &/or precipitation have been set from Climate Normals. </br>"
            "Adjust these values for a better prediction.<br><br></div>"
        )

    # If temperature or precipitation still missing, show a bold notice and stop
    if params.precipitation is None or params.temperature is None:
        if not _initial_entry:
            print(
                "<div style='color:red;sfont-weight:bold;margin-top:0.25rem;'>Must give anticipated temperature and precipitation</div>"
            )
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

    # Compute predictions for both models if available
    out_sched = None
    out_analog = None
    pred_err = None
    try:
        # If schedule-driven payloads available, use them
        if getattr(model, "_payloads", None):
            out_sched = model.predict(
                precip=precip,
                temperature=temp,
                date=date,
                opening_time=otime,
                closing_time=ctime,
            )
        # If analog available, call it directly
        if getattr(model, "_analog", None) is not None:
            try:
                tot, tot_rng, pk, pk_rng = model._analog.predict(  # type: ignore[attr-defined]
                    date=date,
                    opening_time=otime,
                    closing_time=ctime,
                    max_temperature=float(temp),
                    precipitation=float(precip),
                )
                # Shape into a PredictorOutput instance for typing clarity
                out_analog = PredictorOutput(
                    activity_next_hour=None,
                    remainder=None if tot is None else int(round(max(0.0, float(tot)))),
                    peak=None if pk is None else int(round(max(0.0, float(pk)))),
                    peaktime=None,
                    activity_range=None,
                    remainder_range=(
                        None
                        if tot_rng is None
                        else (
                            max(0, int(round(tot_rng[0]))),
                            max(0, int(round(tot_rng[1]))),
                        )
                    ),
                    peak_range=(
                        None
                        if pk_rng is None
                        else (
                            max(0, int(round(pk_rng[0]))),
                            max(0, int(round(pk_rng[1]))),
                        )
                    ),
                    peaktime_range=None,
                )
            except Exception as e2:  # pylint:disable=broad-exception-caught
                pred_err = e2
        # If neither modern model available, fall back to whatever predict() provides
        if out_sched is None and out_analog is None:
            out_sched = model.predict(
                precip=precip,
                temperature=temp,
                date=date,
                opening_time=otime,
                closing_time=ctime,
            )
    except Exception as e:  # pylint:disable=broad-exception-caught
        pred_err = e

    if pred_err is not None and (out_sched is None and out_analog is None):
        print(
            "<div style='color:#a00'><b>Prediction error:</b> "
            + html.escape(f"{type(pred_err).__name__}: {pred_err}")
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
    print("<table class='general_table' style='max-width:64rem'>")
    # Title row
    try:
        pred_dt = datetime.strptime(date, "%Y-%m-%d").date()
        today = _date.today()
        days_delta = (pred_dt - today).days
        future_past = "future" if days_delta >= 0 else "past"
        n_abs = abs(days_delta)
        dow3 = ut.dow_str(date, 3)
        title = (
            f"Prediction for {dow3} {html.escape(date)} "
            f"({n_abs} {ut.plural(n_abs,'day')} in the {future_past})"
        )
    except Exception:
        title = f"Prediction for {html.escape(date)}"
    # Columns: Measure, [Actual], Schedule-driven (pred,range), Analog-day (pred,range)
    has_sched = out_sched is not None
    has_analog = out_analog is not None
    # Each model contributes 2 columns (pred, range)
    model_cols = (2 if has_sched else 0) + (2 if has_analog else 0)
    total_cols = (2 if has_actual else 1) + model_cols
    print(f"<tr><th colspan={total_cols} class='heavy-bottom'>{title}</th></tr>")

    # Header for predictions (now used for both inputs and model outputs)
    if has_actual:
        cells = ["<th>Measure</th>", "<th class='heavy-right'>Actual</th>"]
        if has_sched:
            cells.append("<th>Schedule-driven</th>")
            cells.append("<th class='heavy-right'>Range (approx)</th>")
        if has_analog:
            # If schedule-driven wasn't present, this becomes the first range column
            if not has_sched:
                cells.append("<th>Analog-day</th>")
                cells.append("<th class='heavy-right'>Range (approx)</th>")
            else:
                cells += ["<th>Analog-day</th>", "<th>Range (approx)</th>"]
        print("<tr>" + "".join(cells) + "</tr>")
        # Input rows shown in the table using Prediction/Actual columns
        # Schedule row with both model columns; empty ranges as nbsp
        row = ["<tr>", "<td>Schedule</td>"]
        actual_sched = (
            ""
            if (not actual_open or not actual_close)
            else html.escape(actual_open + "–" + actual_close)
        )
        row.append(f"<td class='heavy-right'>{actual_sched}</td>")
        first_range_done = False
        if has_sched:
            row.append(f"<td>{html.escape(otime)}–{html.escape(ctime)}</td>")
            row.append("<td class='heavy-right'>&nbsp;</td>")
            first_range_done = True
        if has_analog:
            row.append(f"<td>{html.escape(otime)}–{html.escape(ctime)}</td>")
            if first_range_done:
                row.append("<td>&nbsp;</td>")
            else:
                row.append("<td class='heavy-right'>&nbsp;</td>")
        row.append("</tr>")
        print("".join(row))
        # Max temp row
        row = ["<tr>", "<td>Max temp</td>"]
        row.append(
            f"<td class='heavy-right'>{'' if actual_temp is None else actual_temp}</td>"
        )
        first_range_done = False
        if has_sched:
            row.append(f"<td>{temp}</td>")
            row.append("<td class='heavy-right'>&nbsp;</td>")
            first_range_done = True
        if has_analog:
            row.append(f"<td>{temp}</td>")
            row.append(
                "<td class='heavy-right'>&nbsp;</td>"
                if not first_range_done
                else "<td>&nbsp;</td>"
            )
        row.append("</tr>")
        print("".join(row))
        # Precip row
        row = ["<tr class='heavy-bottom'>", "<td>Precipitation</td>"]
        row.append(
            f"<td class='heavy-right'>{'' if actual_precip is None else str(actual_precip) + ' mm'}</td>"
        )
        first_range_done = False
        if has_sched:
            row.append(f"<td>{precip} mm</td>")
            row.append("<td class='heavy-right'>&nbsp;</td>")
            first_range_done = True
        if has_analog:
            row.append(f"<td>{precip} mm</td>")
            row.append(
                "<td class='heavy-right'>&nbsp;</td>"
                if not first_range_done
                else "<td>&nbsp;</td>"
            )
        row.append("</tr>")
        print("".join(row))
    else:
        hdr = ["<th>Measure</th>"]
        if has_sched:
            hdr.append("<th>Schedule-driven</th>")
            hdr.append("<th class='heavy-right'>Range (approx)</th>")
        if has_analog:
            if not has_sched:
                hdr.append("<th>Analog-day</th>")
                hdr.append("<th class='heavy-right'>Range (approx)</th>")
            else:
                hdr += ["<th>Analog-day</th>", "<th>Range (approx)</th>"]
        print("<tr>" + "".join(hdr) + "</tr>")
        # Inputs rows without actuals
        row = ["<tr>", "<td>Schedule</td>"]
        if has_sched:
            row.append(f"<td>{html.escape(otime)}–{html.escape(ctime)}</td>")
            row.append("<td class='heavy-right'>&nbsp;</td>")
        if has_analog:
            row.append(f"<td>{html.escape(otime)}–{html.escape(ctime)}</td>")
            row.append("<td>&nbsp;</td>")
        row.append("</tr>")
        print("".join(row))
        row = ["<tr>", "<td>Max temp</td>"]
        if has_sched:
            row.append(f"<td>{temp}</td>")
            row.append("<td class='heavy-right'>&nbsp;</td>")
        if has_analog:
            row.append(f"<td>{temp}</td>")
            row.append("<td>&nbsp;</td>")
        row.append("</tr>")
        print("".join(row))
        row = ["<tr class='heavy-bottom'>", "<td>Precipitation</td>"]
        if has_sched:
            row.append(f"<td>{precip} mm</td>")
            row.append("<td class='heavy-right'>&nbsp;</td>")
        if has_analog:
            row.append(f"<td>{precip} mm</td>")
            row.append("<td>&nbsp;</td>")
        row.append("</tr>")
        print("".join(row))
    row_bits = ["<tr>", "<td>Total visits</td>"]
    if has_actual:
        row_bits.append(
            f"<td class='heavy-right'>{'' if actual_total is None else int(actual_total)}</td>"
        )
    if has_sched:
        row_bits.append(
            f"<td>{'' if out_sched.remainder is None else out_sched.remainder}</td>"
        )
        row_bits.append(
            f"<td class='heavy-right'>{(_fmt_rng(getattr(out_sched, 'remainder_range', None)) or '&nbsp;')}</td>"
        )
    if has_analog:
        row_bits.append(
            f"<td>{'' if out_analog.remainder is None else out_analog.remainder}</td>"
        )
        # Apply heavy border if schedule-driven absent
        if not has_sched:
            row_bits.append(
                f"<td class='heavy-right'>{(_fmt_rng(getattr(out_analog, 'remainder_range', None)) or '&nbsp;')}</td>"
            )
        else:
            row_bits.append(
                f"<td>{(_fmt_rng(getattr(out_analog, 'remainder_range', None)) or '&nbsp;')}</td>"
            )
    row_bits.append("</tr>")
    print("".join(row_bits))
    row_bits = ["<tr>", "<td>Max bikes</td>"]
    if has_actual:
        row_bits.append(
            f"<td class='heavy-right'>{'' if actual_max is None else int(actual_max)}</td>"
        )
    if has_sched:
        row_bits.append(f"<td>{'' if out_sched.peak is None else out_sched.peak}</td>")
        row_bits.append(
            f"<td class='heavy-right'>{(_fmt_rng(getattr(out_sched, 'peak_range', None)) or '&nbsp;')}</td>"
        )
    if has_analog:
        row_bits.append(
            f"<td>{'' if out_analog.peak is None else out_analog.peak}</td>"
        )
        # Apply heavy border if schedule-driven absent
        if not has_sched:
            row_bits.append(
                f"<td class='heavy-right'>{(_fmt_rng(getattr(out_analog, 'peak_range', None)) or '&nbsp;')}</td>"
            )
        else:
            row_bits.append(
                f"<td>{(_fmt_rng(getattr(out_analog, 'peak_range', None)) or '&nbsp;')}</td>"
            )
    row_bits.append("</tr>")
    print("".join(row_bits))
    print("</table>")
