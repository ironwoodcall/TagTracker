#!/usr/bin/env python3
"""TagTracker report to compare two date/day-of-week ranges."""

from __future__ import annotations

import html
import sqlite3
from typing import Any, Mapping, Sequence

import web_common as cc
from web_daterange_selector import (
    DATE_PATTERN,
    DEFAULT_DOW_OPTIONS,
    DateDowSelection,
    find_dow_option,
    _render_hidden_fields,
)
from web_period_metrics import (
    METRIC_ROWS,
    aggregate_period,
    format_percent,
)


def _coerce_param_value(value: Any) -> str:
    """Normalize query parameter values to strings, skipping blanks."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _normalize_query_params(params: Mapping[str, Any]) -> dict[str, str]:
    """Normalize and filter query parameters for use in hidden fields."""
    normalized: dict[str, str] = {}
    for key, value in (params or {}).items():
        coerced = _coerce_param_value(value)
        if coerced == "":
            continue
        normalized[str(key)] = coerced
    return normalized

def _percent_to_color(percent_value: float | None) -> str:
    """
    Return a hex colour representing the given percent change.

    -100% maps to a vivid orange (#f6a26f), +100% to a bright teal (#6fddd1),
    and 0% to white. Values beyond +/-100% are clamped. A sub-linear exponent
    ensures even small deltas receive a hint of colour.
    """
    if percent_value is None:
        return "#ffffff"

    neg_color = (246, 162, 111)  # richer orange
    pos_color = (111, 221, 209)  # brighter teal
    neutral_color = (255, 255, 255)  # white

    interpolation_exponent = 0.7

    clamped = max(min(percent_value, 100.0), -100.0)
    if clamped < 0:
        weight = abs(clamped) / 100.0
        weight = weight**interpolation_exponent
        r = int(neutral_color[0] * (1 - weight) + neg_color[0] * weight)
        g = int(neutral_color[1] * (1 - weight) + neg_color[1] * weight)
        b = int(neutral_color[2] * (1 - weight) + neg_color[2] * weight)
    else:
        weight = clamped / 100.0
        weight = weight**interpolation_exponent
        r = int(neutral_color[0] * (1 - weight) + pos_color[0] * weight)
        g = int(neutral_color[1] * (1 - weight) + pos_color[1] * weight)
        b = int(neutral_color[2] * (1 - weight) + pos_color[2] * weight)

    return f"#{r:02x}{g:02x}{b:02x}"


def _render_compare_filter_form(
    form_action: str,
    selection_a: DateDowSelection,
    selection_b: DateDowSelection,
    *,
    field_names: tuple[dict[str, str], dict[str, str]],
    submit_label: str = "Apply filters",
    options: Sequence = DEFAULT_DOW_OPTIONS,
    hidden_fields: str = "",
) -> str:
    """Render the combined Period A / Period B filter form."""

    field_names_tuple = tuple(field_names)
    options_tuple = tuple(options)

    form_style = "border: 1px solid black; padding: 12px 18px; display: inline-block;"

    html_bits = [
        f'<form action="{html.escape(form_action)}" method="get" style="{form_style}">',
        "<div style='display:flex; gap:2rem; justify-content:center; align-items:flex-start;'>",
    ]

    for heading, selection, names in (
        ("Period A", selection_a, field_names_tuple[0]),
        ("Period B", selection_b, field_names_tuple[1]),
    ):
        start_field = names["start"]
        end_field = names["end"]
        dow_field = names["dow"]
        escaped_start_field = html.escape(start_field)
        escaped_end_field = html.escape(end_field)
        escaped_dow_field = html.escape(dow_field)

        start_value = html.escape(selection.start_date)
        end_value = html.escape(selection.end_date)

        column_bits = [
            "<div>",
            f"<h3 style='margin:0 0 0.75rem 0; text-align:center;'>{heading}</h3>",
            "<div style='display:grid; grid-template-columns:auto auto;"
            " column-gap:0.5rem; row-gap:0.5rem; align-items:center;'>",
            f'<label for="{escaped_start_field}">Start date:</label>',
            f'<input type="date" id="{escaped_start_field}" name="{escaped_start_field}" '
            f'value="{start_value}" required pattern="{DATE_PATTERN}">',
            f'<label for="{escaped_end_field}">End date:</label>',
            f'<input type="date" id="{escaped_end_field}" name="{escaped_end_field}" '
            f'value="{end_value}" required pattern="{DATE_PATTERN}">',
        ]

        options_html: list[str] = []
        for option in options_tuple:
            value = html.escape(option.value)
            label = html.escape(option.label)
            selected_attr = " selected" if option.value == selection.dow_value else ""
            options_html.append(
                f'<option value="{value}"{selected_attr}>{label}</option>'
            )
        select_markup = "\n                ".join(options_html)
        column_bits.extend(
            [
                f'<label for="{escaped_dow_field}">Day of week:</label>',
                f'<select id="{escaped_dow_field}" name="{escaped_dow_field}">'
                f"\n                {select_markup}\n            </select>",
                "</div>",
                "</div>",
            ]
        )

        html_bits.extend(column_bits)

    html_bits.append("</div>")
    html_bits.append(
        "<div style='text-align:center; margin-top:0.75rem;'>"
        f'<input type="submit" value="{html.escape(submit_label)}">'
        "</div>"
    )

    if hidden_fields:
        html_bits.append(hidden_fields)

    html_bits.append("</form>")

    return "\n        ".join(html_bits)


def _print_instructions() -> None:
    """Text at the top of the page to explain what to do."""
    print(
        """
        <style>
            .intro-text {
            max-width: 70ch;
            text-align: left;
            }
        </style>

        <div class="intro-text">
            <p>
                This page compares bike parking data from two
                different customizable time periods.
            </p>
            <p>
                Use the date filter to set
                the parameters for Period A and for Period B.  By default, this
                page starts by comparing the most recent complete month to the
                corresponding month the preceding year.
            </p>
            <p>
                If looking at differences between periods,
                be aware that different selections may have different numbers of days,
                so the counts <i>per day</i> may often be more helpful than raw counts.
            </p>
        </div>
    """
    )


def compare_ranges(
    ttdb: sqlite3.Connection,
    *,
    params: cc.ReportParameters,
    pages_back: int = 1,
    start_date_a: str = "",
    end_date_a: str = "",
    dow_a: str = "",
    start_date_b: str = "",
    end_date_b: str = "",
    dow_b: str = "",
) -> None:
    """Render the comparison report between two date ranges."""

    resolved_start_a = start_date_a or ""
    resolved_end_a = end_date_a or ""
    resolved_start_b = start_date_b or ""
    resolved_end_b = end_date_b or ""
    resolved_dow_a = dow_a or ""
    resolved_dow_b = dow_b or ""

    resolved_pages_back: int = pages_back
    if not isinstance(resolved_pages_back, int):
        resolved_pages_back = 1

    field_names_a = {
        "start": cc.CGIManager.param_name("start_date"),
        "end": cc.CGIManager.param_name("end_date"),
        "dow": cc.CGIManager.param_name("dow"),
    }
    field_names_b = {
        "start": cc.CGIManager.param_name("start_date2"),
        "end": cc.CGIManager.param_name("end_date2"),
        "dow": cc.CGIManager.param_name("dow2"),
    }

    params.what_report = cc.WHAT_COMPARE_RANGES
    params.start_date = resolved_start_a
    params.end_date = resolved_end_a
    params.start_date2 = resolved_start_b
    params.end_date2 = resolved_end_b
    params.dow = resolved_dow_a
    params.dow2 = resolved_dow_b
    params.pages_back = cc.increment_pages_back(resolved_pages_back)

    query_params = cc.CGIManager.params_to_query_mapping(params)
    # query_params["back"] = resolved_pages_back
    normalized_updates = _normalize_query_params(query_params)

    nav_pages_back = resolved_pages_back

    title = cc.titleize("Date range comparison")
    print(title)
    print(f"{cc.main_and_back_buttons(nav_pages_back)}<br><br>")

    _print_instructions()

    options_tuple = tuple(DEFAULT_DOW_OPTIONS)
    selection_a = DateDowSelection(
        start_date=resolved_start_a,
        end_date=resolved_end_a,
        dow_value=find_dow_option(resolved_dow_a, options_tuple).value,
    )
    selection_b = DateDowSelection(
        start_date=resolved_start_b,
        end_date=resolved_end_b,
        dow_value=find_dow_option(resolved_dow_b, options_tuple).value,
    )


    self_url = cc.selfref(
        what=cc.WHAT_COMPARE_RANGES,
        start_date=resolved_start_a,
        end_date=resolved_end_a,
        start_date2=resolved_start_b,
        end_date2=resolved_end_b,
        qdow=resolved_dow_a,
        dow2=resolved_dow_b,
        pages_back=cc.increment_pages_back(resolved_pages_back),
    )


    form_action = self_url.split("?", 1)[0]

    excluded = {
        field_names_a["start"].lower(),
        field_names_a["end"].lower(),
        field_names_a["dow"].lower(),
        field_names_b["start"].lower(),
        field_names_b["end"].lower(),
        field_names_b["dow"].lower(),
    }
    hidden_params = {
        key: [value]
        for key, value in normalized_updates.items()
        if key.lower() not in excluded
    }
    hidden_fields = _render_hidden_fields(hidden_params)

    print(
        _render_compare_filter_form(
            form_action,
            selection_a,
            selection_b,
            field_names=(field_names_a, field_names_b),
            submit_label="Apply filters",
            options=options_tuple,
            hidden_fields=hidden_fields,
        )
    )

    description_a = selection_a.description(options_tuple)
    description_b = selection_b.description(options_tuple)
    print("<br>")

    metrics_a = aggregate_period(
        ttdb,
        selection_a.start_date,
        selection_a.end_date,
        selection_a.dow_value,
    )
    metrics_b = aggregate_period(
        ttdb,
        selection_b.start_date,
        selection_b.end_date,
        selection_b.dow_value,
    )

    metric_rows = METRIC_ROWS

    print("<table class='general_table'>")
    description_row = (
        f"Period A: {html.escape(description_a or 'All data')}<br>"
        f"Period B: {html.escape(description_b or 'All data')}"
    )
    print(
        "<tr>"
        "<th colspan='6' style='text-align:center;font-size:1.5em;'>"
        f"{description_row}"
        "</th>"
        "</tr>"
    )
    print(
        "<tr>"
        "<th colspan=2 style='text-align:left;'>Item</th>"
        "<th style='text-align:right;'>Period A</th>"
        "<th style='text-align:right;'>Period B</th>"
        "<th style='text-align:right;'>Δ</th>"
        "<th style='text-align:right;'>%Δ</th>"
        "</tr>"
    )

    for row in metric_rows:
        value_a = getattr(metrics_a, row["attr"])
        value_b = getattr(metrics_b, row["attr"])
        delta = None
        if value_a is not None and value_b is not None:
            delta = value_b - value_a
        formatted_a = row["value_fmt"](value_a)
        formatted_b = row["value_fmt"](value_b)
        formatted_delta = row["delta_fmt"](delta)
        percent = format_percent(value_a, delta)
        percent_value = None
        if delta is not None:
            numeric_delta = float(delta)
            if isinstance(value_a, (int, float)):
                if abs(value_a) > 1e-9:
                    percent_value = (numeric_delta / float(value_a)) * 100.0
                elif numeric_delta == 0:
                    percent_value = 0.0
            elif numeric_delta == 0:
                percent_value = 0.0
        percent_cell_style = (
            f"text-align:right;background-color:{_percent_to_color(percent_value)};"
        )
        row_class = row["row_class"] if "row_class" in row else ""
        row_span = row["row_span"] if "row_span" in row else ""
        row_span_color = row["row_span_color"] if "row_span_color" in row else "white"
        row_span_style = f"style=background-color:{row_span_color}"

        print(f"<tr {row_class}>")
        if row_span:
            print(f"<td rowspan={row_span} class='heavy-bottom' {row_span_style}>&nbsp;</td>")
        print(
            f"<td style='text-align:left;'>{row['label']}</td>"
            f"<td style='text-align:right;'>{formatted_a}</td>"
            f"<td style='text-align:right;'>{formatted_b}</td>"
            f"<td style='text-align:right;'>{formatted_delta}</td>"
            f'<td style="{percent_cell_style}">{percent}</td>'
            "</tr>"
        )

    print("</table>")
