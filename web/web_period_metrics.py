#!/usr/bin/env python3
"""Shared helpers for assembling TagTracker period metrics."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from statistics import mean, median
from typing import Any, Sequence, Tuple

import web_common as cc
from common.tt_daysummary import DayTotals
from common.tt_time import VTime

try:
    from common.commuter_hump import CommuterHumpAnalyzer
except ImportError:  # pragma: no cover - optional dependency
    CommuterHumpAnalyzer = None


__all__ = [
    "PeriodMetrics",
    "MetricRow",
    "aggregate_period",
    "format_float",
    "format_float_delta",
    "format_int",
    "format_int_delta",
    "format_minutes",
    "format_minutes_delta",
    "format_percent",
    "METRIC_ROWS",
]


@dataclass
class PeriodMetrics:
    """Aggregated values for a date range."""

    days_open: int = 0
    open_minutes: int = 0
    total_bikes_parked: int = 0
    regular_bikes: int = 0
    oversize_bikes: int = 0
    most_bikes: int = 0
    bikes_registered: int = 0
    max_bikes_parked: int = 0
    bikes_left: int = 0
    total_precipitation: float | None = 0.0
    max_high_temperature: float | None = None
    longest_visit_minutes: int | None = None
    mean_visit_minutes: int | None = None
    median_visit_minutes: int | None = None
    mean_bikes_per_day_combined: float | None = 0.0
    median_bikes_per_day_combined: float | None = 0.0
    mean_bikes_per_day_regular: float | None = 0.0
    median_bikes_per_day_regular: float | None = 0.0
    mean_bikes_per_day_oversize: float | None = 0.0
    median_bikes_per_day_oversize: float | None = 0.0
    mean_bikes_registered_per_day: float | None = None
    median_bikes_registered_per_day: float | None = None
    mean_bikes_left_per_day: float | None = None
    commuters: int | None = None
    commuters_per_day: float | None = None
    median_commuters_per_day: float | None = None
    mean_most_bikes_per_day: float | None = None
    median_most_bikes_per_day: float | None = None


def _parse_dow_tokens(dow_value: str) -> set[int]:
    """Return the permitted ISO days_of_week for the normalized selector value."""
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


def _fetch_commuter_metrics(
    ttdb: sqlite3.Connection,
    start_iso: str,
    end_iso: str,
    days_of_week: Sequence[int],
) -> tuple[int | None, float | None]:
    """Run the commuter hump analysis and return commuter count and mean per day."""
    if CommuterHumpAnalyzer is None:
        return None, None
    if not start_iso or not end_iso:
        return None, None
    ordered_start, ordered_end = sorted((start_iso, end_iso))
    normalized_weekdays = tuple(sorted(set(days_of_week))) or tuple(range(1, 8))
    try:
        analyzer = CommuterHumpAnalyzer(
            db_path=ttdb,
            start_date=ordered_start,
            end_date=ordered_end,
            days_of_week=normalized_weekdays,
        ).run()
    except Exception:
        return None, None
    if analyzer is None or getattr(analyzer, "error", None):
        return None, None
    commuter_count = getattr(analyzer, "commuter_count", None)
    if commuter_count is not None:
        try:
            commuter_count = int(commuter_count)
        except (TypeError, ValueError):
            commuter_count = None
    mean_value = getattr(analyzer, "mean_commuter_per_day", None)
    if mean_value is None:
        return commuter_count, None
    try:
        mean_value = float(mean_value)
    except (TypeError, ValueError):
        return commuter_count, None
    if math.isnan(mean_value):
        return commuter_count, None
    return commuter_count, mean_value


def aggregate_period(
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
    if days:
        metrics.mean_bikes_left_per_day = metrics.bikes_left / len(days)
    else:
        metrics.mean_bikes_left_per_day = None

    bike_type_attr_map = [
        ("combined", "num_parked_combined"),
        ("regular", "num_parked_regular"),
        ("oversize", "num_parked_oversize"),
    ]
    for label, attr in bike_type_attr_map:
        totals = [(getattr(day, attr, 0) or 0) for day in days]
        if totals:
            setattr(metrics, f"mean_bikes_per_day_{label}", mean(totals))
            setattr(metrics, f"median_bikes_per_day_{label}", median(totals))
        else:
            setattr(metrics, f"mean_bikes_per_day_{label}", None)
            setattr(metrics, f"median_bikes_per_day_{label}", None)

    registered_counts = [(getattr(day, "bikes_registered", 0) or 0) for day in days]
    if registered_counts:
        metrics.mean_bikes_registered_per_day = mean(registered_counts)
        metrics.median_bikes_registered_per_day = median(registered_counts)
    else:
        metrics.mean_bikes_registered_per_day = None
        metrics.median_bikes_registered_per_day = None
    metrics.commuters = None
    metrics.commuters_per_day = None
    if days:
        day_dates = [
            getattr(day, "date", None)
            for day in days
            if getattr(day, "date", None)
        ]
        if day_dates:
            commuter_count, commuters_per_day = _fetch_commuter_metrics(
                ttdb,
                min(day_dates),
                max(day_dates),
                allowed or range(1, 8),
            )
            metrics.commuters = commuter_count
            metrics.commuters_per_day = commuters_per_day
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

    daily_maximums = [
        (getattr(day, "num_fullest_combined", 0) or 0) for day in days
    ]
    if daily_maximums:
        metrics.mean_most_bikes_per_day = mean(daily_maximums)
        metrics.median_most_bikes_per_day = median(daily_maximums)
    else:
        metrics.mean_most_bikes_per_day = None
        metrics.median_most_bikes_per_day = None

    day_where_clauses = ["orgsite_id = ?"]
    params: list[Any] = [1]
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
        metrics.longest_visit_minutes = max(durations_minutes)
        metrics.mean_visit_minutes = int(round(mean(durations_minutes)))
        metrics.median_visit_minutes = int(round(median(durations_minutes)))
    else:
        metrics.longest_visit_minutes = None
        metrics.mean_visit_minutes = None
        metrics.median_visit_minutes = None

    daily_commuter_counts: list[float] = []
    if days and CommuterHumpAnalyzer is not None:
        commuter_weekdays = tuple(sorted(allowed)) if allowed else tuple(range(1, 8))
        for day in days:
            commuter_count, _ = _fetch_commuter_metrics(
                ttdb,
                getattr(day, "date", ""),
                getattr(day, "date", ""),
                commuter_weekdays,
            )
            if commuter_count is None:
                continue
            daily_commuter_counts.append(float(commuter_count))
    if daily_commuter_counts:
        metrics.median_commuters_per_day = median(daily_commuter_counts)
        if metrics.commuters_per_day is None:
            metrics.commuters_per_day = mean(daily_commuter_counts)

    return metrics


def format_minutes(value: int | VTime) -> str:
    """Return a display string for a minute count."""
    if value is None:
        return "-"
    if isinstance(value, VTime):
        return value.tidy
    if not value:
        return "0:00"
    return VTime(value, allow_large=True).tidy


def format_minutes_delta(delta: int) -> str:
    """Return a signed duration for the minutes delta."""
    if delta is None:
        return "-"
    if not delta:
        return "0:00"
    sign = "+" if delta > 0 else "-"
    return f"{sign}{format_minutes(abs(delta))}"


def format_int(value: int) -> str:
    """Return an integer formatted with thousands separators."""
    if value is None:
        return "-"
    return f"{value:,}"


def format_int_delta(delta: int) -> str:
    """Return a signed integer string with thousands separators."""
    if delta is None:
        return "-"
    if not delta:
        return "0"
    return f"{delta:+,}"


def format_percent(base_value: int, delta_value: int) -> str:
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


def format_float(value: float, decimals: int = 1) -> str:
    """Return a floating-point value with a fixed number of decimals."""
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"


def format_float_delta(delta: float, decimals: int = 1) -> str:
    """Return a signed floating-point delta."""
    if delta is None:
        return "-"
    if delta == 0:
        return f"{0:.{decimals}f}"
    formatted = f"{abs(delta):.{decimals}f}"
    sign = "+" if delta > 0 else "-"
    return f"{sign}{formatted}"


MetricRow = dict[str, Any]


METRIC_ROWS: Tuple[MetricRow, ...] = (
    {
        "label": "Days open (total):",
        "row_span": 2,
        "row_span_color": "#d6d8ce",
        "attr": "days_open",
        "value_fmt": format_int,
        "delta_fmt": format_int_delta,
    },
    {
        "label": "Hours open (total):",
        "row_class": "class='heavy-bottom'",
        "attr": "open_minutes",
        "value_fmt": format_minutes,
        "delta_fmt": format_minutes_delta,
    },
    {
        "label": "Visits (all bike types):",
        "row_span": 8,
        "row_span_color": "#c1b8aa",
        "attr": "total_bikes_parked",
        "value_fmt": format_int,
        "delta_fmt": format_int_delta,
    },
    {
        "label": "&nbsp;&nbsp;&nbsp;Regular bike visits:",
        "attr": "regular_bikes",
        "value_fmt": format_int,
        "delta_fmt": format_int_delta,
    },
    {
        "label": "&nbsp;&nbsp;&nbsp;Oversize bike visits:",
        "attr": "oversize_bikes",
        "value_fmt": format_int,
        "delta_fmt": format_int_delta,
    },
    {
        "label": "&nbsp;&nbsp;&nbsp;Commuter portion:",
        "attr": "commuters",
        "value_fmt": format_int,
        "delta_fmt": format_int_delta,
    },
    {
        "label": "Max visits in one day:",
        "attr": "max_bikes_parked",
        "value_fmt": format_int,
        "delta_fmt": format_int_delta,
    },
    {
        "label": "Max bikes on-site:",
        "attr": "most_bikes",
        "value_fmt": format_int,
        "delta_fmt": format_int_delta,
    },
    {
        "label": "Bikes left on-site:",
        "attr": "bikes_left",
        "value_fmt": format_int,
        "delta_fmt": format_int_delta,
    },
    {
        "label": "Registrations:",
        "row_class": "class=heavy-bottom",
        "attr": "bikes_registered",
        "value_fmt": format_int,
        "delta_fmt": format_int_delta,
    },
    {
        "label": "Mean visits <b>per day</b> (all bike types):",
        "row_span": 13,
        "row_span_color": "#d6d8ce",
        "attr": "mean_bikes_per_day_combined",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "&nbsp;&nbsp;&nbsp;Regular bike visits:",
        "attr": "mean_bikes_per_day_regular",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "&nbsp;&nbsp;&nbsp;Oversize bike visits:",
        "attr": "mean_bikes_per_day_oversize",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "&nbsp;&nbsp;&nbsp;Commuter portion:",
        "attr": "commuters_per_day",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "Median visits <b>per day</b> (all bike types):",
        "attr": "median_bikes_per_day_combined",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "&nbsp;&nbsp;&nbsp;Regular bike visits:",
        "attr": "median_bikes_per_day_regular",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "&nbsp;&nbsp;&nbsp;Oversize bike visits:",
        "attr": "median_bikes_per_day_oversize",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "&nbsp;&nbsp;&nbsp;Commuter portion:",
        "attr": "median_commuters_per_day",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "Max bikes on-site <b>per day</b> (mean):",
        "attr": "mean_most_bikes_per_day",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "Max bikes on-site <b>per day</b> (median):",
        "attr": "median_most_bikes_per_day",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "Bikes <i>left</i> on-site <b>per day</b>:",
        "attr": "mean_bikes_left_per_day",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "Registrations <b>per day</b> (mean):",
        "attr": "mean_bikes_registered_per_day",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "Registrations <b>per day</b> (median):",
        "row_class": "class='heavy-bottom'",
        "attr": "median_bikes_registered_per_day",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "Visit duration (max):",
        "row_span": 3,
        "row_span_color": "#c1b8aa",
        "attr": "longest_visit_minutes",
        "value_fmt": format_minutes,
        "delta_fmt": format_minutes_delta,
    },
    {
        "label": "Visit duration (mean):",
        "attr": "mean_visit_minutes",
        "value_fmt": format_minutes,
        "delta_fmt": format_minutes_delta,
    },
    {
        "label": "Visit duration (median)",
        "row_class": "class='heavy-bottom'",
        "attr": "median_visit_minutes",
        "value_fmt": format_minutes,
        "delta_fmt": format_minutes_delta,
    },
    {
        "label": "Total precipitation:",
        "row_span": 2,
        "row_span_color": "#d6d8ce",
        "attr": "total_precipitation",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
    {
        "label": "Max temperature:",
        "row_class": "class='heavy-bottom'",
        "attr": "max_high_temperature",
        "value_fmt": lambda value: format_float(value, decimals=1),
        "delta_fmt": lambda delta: format_float_delta(delta, decimals=1),
    },
)
