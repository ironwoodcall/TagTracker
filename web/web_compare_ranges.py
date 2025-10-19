#!/usr/bin/env python3
"""TagTracker report to compare two date/day-of-week ranges."""

from __future__ import annotations

import html
import sqlite3
import urllib.parse
from dataclasses import dataclass
from statistics import mean, median
from typing import Sequence

import web_common as cc
from web_daterange_selector import (
    DATE_PATTERN,
    DEFAULT_DOW_OPTIONS,
    DateDowSelection,
    find_dow_option,
    _render_hidden_fields,
)
from common.tt_daysummary import DayTotals
from common.tt_time import VTime


@dataclass
class PeriodMetrics:
    """Aggregated values for a date range."""

    days_open: int = 0
    open_minutes: int = 0
    total_bikes_parked: int = 0
    most_bikes: int = 0
    bikes_registered: int = 0
    max_bikes_parked: int = 0
    bikes_left: int = 0
    total_precipitation: float | None = 0.0
    max_high_temperature: float | None = None
    regular_bikes: int = 0
    oversize_bikes: int = 0
    shortest_visit_minutes: int | None = None
    longest_visit_minutes: int | None = None
    mean_visit_minutes: int | None = None
    median_visit_minutes: int | None = None
    mean_bikes_per_day: float | None = None
    median_bikes_per_day: float | None = None
    mean_bikes_registered_per_day: float | None = None


def _parse_dow_tokens(dow_value: str) -> set[int]:
    """Return the permitted ISO weekdays for the normalized selector value."""
    allowed: set[int] = set()
    if not dow_value:
        return allowed
    for token in dow_value.split(","):
        token = token.strip()
        if not token.isdigit():
            continue
        candidate = int(token)
        if 1 <= candidate <= 7:
            allowed.add(candidate)
    return allowed


def _open_minutes_for_day(day: DayTotals) -> int:
    """Return the number of minutes the site was open for a single day."""
    open_minutes = getattr(getattr(day, "time_open", None), "as_minutes", None)
    close_minutes = getattr(getattr(day, "time_closed", None), "as_minutes", None)
    if open_minutes is None or close_minutes is None:
        return 0
    duration = close_minutes - open_minutes
    if duration < 0:
        return 0
    return duration


def _aggregate_period(
    ttdb: sqlite3.Connection,
    start_date: str,
    end_date: str,
    dow_value: str,
) -> PeriodMetrics:
    """Collect daily summaries and roll them into PeriodMetrics."""
    days = cc.get_days_data(ttdb, min_date=start_date, max_date=end_date)
    allowed = _parse_dow_tokens(dow_value)
    if allowed:
        days = [day for day in days if getattr(day, "weekday", None) in allowed]

    metrics = PeriodMetrics()
    metrics.days_open = len(days)
    metrics.open_minutes = sum(_open_minutes_for_day(day) for day in days)
    metrics.total_bikes_parked = sum(
        (getattr(day, "num_parked_combined", 0) or 0) for day in days
    )
    metrics.most_bikes = (
        max((getattr(day, "num_fullest_combined", 0) or 0) for day in days)
        if days
        else 0
    )
    metrics.bikes_registered = sum(
        (getattr(day, "bikes_registered", 0) or 0) for day in days
    )
    metrics.max_bikes_parked = (
        max((getattr(day, "num_parked_combined", 0) or 0) for day in days)
        if days
        else 0
    )
    metrics.bikes_left = sum(
        (getattr(day, "num_remaining_combined", 0) or 0) for day in days
    )
    bike_totals = [(getattr(day, "num_parked_combined", 0) or 0) for day in days]
    if bike_totals:
        metrics.mean_bikes_per_day = mean(bike_totals)
        metrics.median_bikes_per_day = median(bike_totals)
    else:
        metrics.mean_bikes_per_day = None
        metrics.median_bikes_per_day = None
    registered_counts = [(getattr(day, "bikes_registered", 0) or 0) for day in days]
    if registered_counts:
        metrics.mean_bikes_registered_per_day = mean(registered_counts)
    else:
        metrics.mean_bikes_registered_per_day = None
    precip_values = [
        getattr(day, "precipitation", None)
        for day in days
        if getattr(day, "precipitation", None) is not None
    ]
    metrics.total_precipitation = sum(precip_values) if precip_values else 0.0
    temperature_values = [
        getattr(day, "max_temperature", None)
        for day in days
        if getattr(day, "max_temperature", None) is not None
    ]
    metrics.max_high_temperature = (
        max(temperature_values) if temperature_values else None
    )
    metrics.regular_bikes = sum(
        (getattr(day, "num_parked_regular", 0) or 0) for day in days
    )
    metrics.oversize_bikes = sum(
        (getattr(day, "num_parked_oversize", 0) or 0) for day in days
    )

    day_where_clauses = ["orgsite_id = ?"]
    params: list = [1]
    if start_date:
        day_where_clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        day_where_clauses.append("date <= ?")
        params.append(end_date)
    if allowed:
        placeholders = ",".join("?" for _ in allowed)
        day_where_clauses.append(f"weekday IN ({placeholders})")
        params.extend(sorted(allowed))
    day_clause = " AND ".join(day_where_clauses)
    visit_query = (
        "SELECT duration FROM VISIT WHERE day_id IN ("
        f"SELECT id FROM DAY WHERE {day_clause}"
        ")"
    )
    cursor = ttdb.cursor()
    cursor.execute(visit_query, params)
    visit_durations = [row[0] for row in cursor.fetchall() if row[0] is not None]
    cursor.close()
    if visit_durations:
        durations_minutes = [int(round(duration)) for duration in visit_durations]
        metrics.shortest_visit_minutes = min(durations_minutes)
        metrics.longest_visit_minutes = max(durations_minutes)
        metrics.mean_visit_minutes = int(round(mean(durations_minutes)))
        metrics.median_visit_minutes = int(round(median(durations_minutes)))
    else:
        metrics.shortest_visit_minutes = None
        metrics.longest_visit_minutes = None
        metrics.mean_visit_minutes = None
        metrics.median_visit_minutes = None

    return metrics


def _format_minutes(value: int | VTime) -> str:
    """Return a display string for a minute count."""
    if value is None:
        return "-"
    if isinstance(value, VTime):
        return value.tidy
    if not value:
        return "0:00"
    return VTime(value, allow_large=True).tidy


def _format_minutes_delta(delta: int) -> str:
    """Return a signed duration for the minutes delta."""
    if delta is None:
        return "-"
    if not delta:
        return "0:00"
    sign = "+" if delta > 0 else "-"
    return f"{sign}{_format_minutes(abs(delta))}"


def _format_int(value: int) -> str:
    """Return an integer formatted with thousands separators."""
    if value is None:
        return "-"
    return f"{value:,}"


def _format_int_delta(delta: int) -> str:
    """Return a signed integer string with thousands separators."""
    if delta is None:
        return "-"
    if not delta:
        return "0"
    return f"{delta:+,}"


def _format_percent(base_value: int, delta_value: int) -> str:
    """Return percentage change with a single decimal place."""
    if delta_value is None:
        return "-"
    if base_value in (None, 0):
        return "0.0%" if delta_value == 0 else "-"
    change = (delta_value / base_value) * 100
    change = round(change, 1)
    if change == 0:
        return "0.0%"
    return f"{change:+.1f}%"


def _format_float(value: float, decimals: int = 1) -> str:
    """Return a floating-point value with a fixed number of decimals."""
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"


def _format_float_delta(delta: float, decimals: int = 1) -> str:
    """Return a signed floating-point delta."""
    if delta is None:
        return "-"
    if delta == 0:
        return f"{0:.{decimals}f}"
    formatted = f"{abs(delta):.{decimals}f}"
    sign = "+" if delta > 0 else "-"
    return f"{sign}{formatted}"


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
    base_url: str,
    selection_a: DateDowSelection,
    selection_b: DateDowSelection,
    *,
    submit_label: str = "Apply filters",
    options: Sequence = DEFAULT_DOW_OPTIONS,
) -> str:
    """Render the combined Period A / Period B filter form."""

    options_tuple = tuple(options)

    parsed_url = urllib.parse.urlparse(base_url)
    base_portion = base_url.split("?", 1)[0]
    query_params = urllib.parse.parse_qs(parsed_url.query)
    excluded = {"start_date", "end_date", "dow", "start_date2", "end_date2", "dow2"}
    filtered_params = {
        k: v for k, v in query_params.items() if k.lower() not in excluded
    }
    hidden_fields = _render_hidden_fields(filtered_params)

    form_style = "border: 1px solid black; padding: 12px 18px; display: inline-block;"

    html_bits = [
        f'<form action="{html.escape(base_portion)}" method="get" style="{form_style}">',
        "<div style='display:flex; gap:2rem; justify-content:center; align-items:flex-start;'>",
    ]

    for heading, selection, suffix in (
        ("Period A", selection_a, ""),
        ("Period B", selection_b, "2"),
    ):
        start_field = f"start_date{suffix}"
        end_field = f"end_date{suffix}"
        dow_field = f"dow{suffix}"

        start_value = html.escape(selection.start_date)
        end_value = html.escape(selection.end_date)

        column_bits = [
            "<div>",
            f"<h3 style='margin:0 0 0.75rem 0; text-align:center;'>{heading}</h3>",
            "<div style='display:grid; grid-template-columns:auto auto;"
            " column-gap:0.5rem; row-gap:0.5rem; align-items:center;'>",
            f'<label for="{start_field}">Start date:</label>',
            f'<input type="date" id="{start_field}" name="{start_field}" '
            f'value="{start_value}" required pattern="{DATE_PATTERN}">',
            f'<label for="{end_field}">End date:</label>',
            f'<input type="date" id="{end_field}" name="{end_field}" '
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
                f'<label for="{dow_field}">Day of week:</label>',
                f'<select id="{dow_field}" name="{dow_field}">'
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
    pages_back: int = 1,
    start_date_a: str = "",
    end_date_a: str = "",
    dow_a: str = "",
    start_date_b: str = "",
    end_date_b: str = "",
    dow_b: str = "",
) -> None:
    """Render the comparison report between two date ranges."""

    title = cc.titleize("Compare date ranges")
    print(title)
    print(f"{cc.main_and_back_buttons(pages_back)}<br><br>")

    _print_instructions()

    self_url = cc.selfref(
        what=cc.WHAT_COMPARE_RANGES,
        pages_back=cc.increment_pages_back(pages_back),
    )

    options_tuple = tuple(DEFAULT_DOW_OPTIONS)
    selection_a = DateDowSelection(
        start_date=start_date_a or "",
        end_date=end_date_a or "",
        dow_value=find_dow_option(dow_a, options_tuple).value,
    )
    selection_b = DateDowSelection(
        start_date=start_date_b or "",
        end_date=end_date_b or "",
        dow_value=find_dow_option(dow_b, options_tuple).value,
    )

    print(
        _render_compare_filter_form(
            self_url,
            selection_a,
            selection_b,
            submit_label="Apply filters",
            options=options_tuple,
        )
    )

    description_a = selection_a.description(options_tuple)
    description_b = selection_b.description(options_tuple)
    # print(
    #     "<div style='display:flex; flex-wrap:wrap; gap:1.5rem; margin-top:0.75rem;'>"
    # )
    # print(
    #     f"<p style='margin:0;font-style:italic;'><strong>Period A:</strong> "
    #     f"{html.escape(description_a or 'All data')}</p>"
    # )
    # print(
    #     f"<p style='margin:0;font-style:italic;'><strong>Period B:</strong> "
    #     f"{html.escape(description_b or 'All data')}</p>"
    # )
    # print("</div>")
    print("<br>")

    metrics_a = _aggregate_period(
        ttdb,
        selection_a.start_date,
        selection_a.end_date,
        selection_a.dow_value,
    )
    metrics_b = _aggregate_period(
        ttdb,
        selection_b.start_date,
        selection_b.end_date,
        selection_b.dow_value,
    )

    metric_rows = [
        {
            "label": "Days open:",
            "attr": "days_open",
            "value_fmt": _format_int,
            "delta_fmt": _format_int_delta,
        },
        {
            "label": "Hours open:",
            "attr": "open_minutes",
            "value_fmt": _format_minutes,
            "delta_fmt": _format_minutes_delta,
        },
        {
            "label": "Total bikes parked:",
            "attr": "total_bikes_parked",
            "value_fmt": _format_int,
            "delta_fmt": _format_int_delta,
        },
        {
            "label": "Regular bikes parked:",
            "attr": "regular_bikes",
            "value_fmt": _format_int,
            "delta_fmt": _format_int_delta,
        },
        {
            "label": "Oversize bikes parked:",
            "attr": "oversize_bikes",
            "value_fmt": _format_int,
            "delta_fmt": _format_int_delta,
        },
        {
            "label": "Max bikes parked in one day:",
            "attr": "max_bikes_parked",
            "value_fmt": _format_int,
            "delta_fmt": _format_int_delta,
        },
        {
            "label": "Mean bikes per day:",
            "attr": "mean_bikes_per_day",
            "value_fmt": lambda value: _format_float(value, decimals=1),
            "delta_fmt": lambda delta: _format_float_delta(delta, decimals=1),
        },
        {
            "label": "Median bikes per day:",
            "attr": "median_bikes_per_day",
            "value_fmt": lambda value: _format_float(value, decimals=1),
            "delta_fmt": lambda delta: _format_float_delta(delta, decimals=1),
        },
        {
            "label": "Most bikes at once:",
            "attr": "most_bikes",
            "value_fmt": _format_int,
            "delta_fmt": _format_int_delta,
        },
        {
            "label": "Bikes left at end of day:",
            "attr": "bikes_left",
            "value_fmt": _format_int,
            "delta_fmt": _format_int_delta,
        },
        {
            "label": "Bikes registered:",
            "attr": "bikes_registered",
            "value_fmt": _format_int,
            "delta_fmt": _format_int_delta,
        },
        {
            "label": "Mean bikes registered per day:",
            "attr": "mean_bikes_registered_per_day",
            "value_fmt": lambda value: _format_float(value, decimals=1),
            "delta_fmt": lambda delta: _format_float_delta(delta, decimals=1),
        },
        {
            "label": "Shortest visit:",
            "attr": "shortest_visit_minutes",
            "value_fmt": _format_minutes,
            "delta_fmt": _format_minutes_delta,
        },
        {
            "label": "Longest visit:",
            "attr": "longest_visit_minutes",
            "value_fmt": _format_minutes,
            "delta_fmt": _format_minutes_delta,
        },
        {
            "label": "Mean visit length:",
            "attr": "mean_visit_minutes",
            "value_fmt": _format_minutes,
            "delta_fmt": _format_minutes_delta,
        },
        {
            "label": "Median visit length:",
            "attr": "median_visit_minutes",
            "value_fmt": _format_minutes,
            "delta_fmt": _format_minutes_delta,
        },
        {
            "label": "Total precipitation:",
            "attr": "total_precipitation",
            "value_fmt": lambda value: _format_float(value, decimals=1),
            "delta_fmt": lambda delta: _format_float_delta(delta, decimals=1),
        },
        {
            "label": "Max daily high temperature:",
            "attr": "max_high_temperature",
            "value_fmt": lambda value: _format_float(value, decimals=1),
            "delta_fmt": lambda delta: _format_float_delta(delta, decimals=1),
        },
    ]

    print("<table class='general_table'>")
    description_row = (
        f"Period A: {html.escape(description_a or 'All data')}<br>"
        f"Period B: {html.escape(description_b or 'All data')}"
    )
    print(
        "<tr>"
        "<th colspan='5' style='text-align:center;font-size:1.5em;'>"
        f"{description_row}"
        "</th>"
        "</tr>"
    )
    print(
        "<tr>"
        "<th style='text-align:left;'>Item</th>"
        "<th style='text-align:right;'>Period A</th>"
        "<th style='text-align:right;'>Period B</th>"
        "<th style='text-align:right;'>Delta</th>"
        "<th style='text-align:right;'>%Delta</th>"
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
        percent = _format_percent(value_a, delta)
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
        print(
            "<tr>"
            f"<td style='text-align:left;'>{html.escape(row['label'])}</td>"
            f"<td style='text-align:right;'>{formatted_a}</td>"
            f"<td style='text-align:right;'>{formatted_b}</td>"
            f"<td style='text-align:right;'>{formatted_delta}</td>"
            f'<td style="{percent_cell_style}">{percent}</td>'
            "</tr>"
        )

    print("</table>")
