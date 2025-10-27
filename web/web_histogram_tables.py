"""
High-level helpers that combine histogram data queries with HTML rendering.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from common.tt_time import VTime

from web_histogram_data import (
    bucket_label,
    fullness_histogram_data,
    time_histogram_data,
    HistogramMatrixResult,
)
from web_histogram_render import html_histogram, html_histogram_matrix
from web_base_config import (
    HIST_FIXED_Y_AXIS_ACTIVITY,
    HIST_FIXED_Y_AXIS_FULLNESS,
)

if TYPE_CHECKING:
    from web.datacolors import Dimension


def arrival_duration_hist_table(
    ttdb: sqlite3.Connection,
    orgsite_id: int,
    dimension: "Dimension | None" = None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    days_of_week: str | None = None,
    arrival_bucket_minutes: int = 30,
    duration_bucket_minutes: int = 30,
    min_arrival_threshold: str = "06:00",
    max_duration_threshold: str | None = None,
    title: str = "",
    subtitle: str = "",
    table_width: int = 60,
    border_color: str = "black",
    visit_threshold: float = 0.05,
    show_counts: bool = True,
    use_contrasting_text: bool = False,
    normalization_mode: str = HistogramMatrixResult.NORMALIZATION_BLEND,
) -> str:
    """Convenience helper to fetch data and render the arrival-duration matrix.

    Args:
        normalization_mode: Pass ``"column"``, ``"global"``, or ``"blend"`` to choose
            how the heatmap values are scaled.
    """

    matrix = HistogramMatrixResult(
        arrival_bucket_minutes=arrival_bucket_minutes,
        duration_bucket_minutes=duration_bucket_minutes,
    )
    # Fetch the raw data & set the day count
    matrix.fetch_raw_data(
        ttdb=ttdb,
        start_date=start_date,
        end_date=end_date,
        days_of_week=days_of_week,
        arrival_bucket_minutes=arrival_bucket_minutes,
        duration_bucket_minutes=duration_bucket_minutes,
        min_arrival_threshold=min_arrival_threshold,
        max_duration_threshold=max_duration_threshold,
    )

    if not matrix.arrival_labels or not matrix.duration_labels:
        return "<p>No data available.</p>"

    subtitle_text = subtitle
    if not subtitle_text and matrix.day_count:
        plural = "day" if matrix.day_count == 1 else "days"
        subtitle_text = f"Averaged across {matrix.day_count} {plural}"

    return html_histogram_matrix(
        matrix,
        dimension,
        title=title,
        subtitle=subtitle_text,
        table_width=table_width,
        border_color=border_color,
        visit_threshold=visit_threshold,
        show_counts=show_counts,
        use_contrasting_text=use_contrasting_text,
        normalization_mode=normalization_mode,
    )


def times_hist_table(
    ttdb: sqlite3.Connection,
    orgsite_id: int,
    query_column: str,
    start_date: str = None,
    end_date: str = None,
    days_of_week: str = None,
    title: str = "",
    subtitle: str = "",
    color: str = None,
    mini: bool = False,
    max_value: float | None = None,
) -> str:
    """Create one html histogram table on lengths of visit."""

    result = time_histogram_data(
        ttdb,
        orgsite_id=orgsite_id,
        query_column=query_column,
        start_date=start_date,
        end_date=end_date,
        days_of_week=days_of_week,
    )
    averaged_freq = result.values
    day_count = result.day_count
    should_mark_hours = query_column.lower() in {"time_in", "time_out"}
    open_marker_label = None
    close_marker_label = None
    if should_mark_hours and day_count == 1:
        open_marker_label = bucket_label(result.open_bucket)
        close_marker_label = bucket_label(result.close_bucket)

    stats_summary = ""
    if query_column.lower() == "duration" and averaged_freq:
        expanded_values: list[float] = []
        for label, freq in averaged_freq.items():
            if freq is None:
                continue
            minutes = VTime(label).num
            if minutes is None:
                continue
            expanded_values.extend([minutes] * int(round(freq)))
        if expanded_values:
            expanded_values.sort()
            n = len(expanded_values)
            mean_val = sum(expanded_values) / n
            median_val = (
                expanded_values[n // 2]
                if n % 2 == 1
                else (expanded_values[n // 2 - 1] + expanded_values[n // 2]) / 2
            )
            variance = sum((val - mean_val) ** 2 for val in expanded_values) / n
            std_dev = variance**0.5
            median_vt = VTime(median_val, allow_large=True)
            mean_vt = VTime(mean_val, allow_large=True)
            std_vt = VTime(std_dev, allow_large=True)
            day_phrase = ""
            if day_count:
                plural = "day" if day_count == 1 else "days"
                day_phrase = f", averaged across {day_count} {plural}"
            stats_summary = (
                "Lengths of visits "
                f"(median {median_vt.tidy.strip()}, mean {mean_vt.tidy.strip()}, "
                f"SD {std_vt.tidy.strip()}{day_phrase})"
            )

    if mini:
        top_text = ""
        bottom_text = stats_summary if stats_summary else title
        row_count = 20
    else:
        top_text = title
        bottom_text = stats_summary if stats_summary else subtitle
        row_count = 20
    return html_histogram(
        averaged_freq,
        row_count,
        color,
        mini=mini,
        title=top_text,
        subtitle=bottom_text,
        max_value=max_value,
        open_marker_label=open_marker_label,
        close_marker_label=close_marker_label,
    )


def fullness_hist_table(
    ttdb: sqlite3.Connection,
    orgsite_id: int,
    start_date: str = None,
    end_date: str = None,
    days_of_week: str = None,
    title: str = "",
    subtitle: str = "",
    bar_color: str = "darkcyan",
    mini: bool = False,
    link_target: str = "",
) -> str:
    """Render a histogram of bikes on hand (fullness) by time block."""

    result = fullness_histogram_data(
        ttdb,
        orgsite_id=orgsite_id,
        start_date=start_date,
        end_date=end_date,
        days_of_week=days_of_week,
    )
    averaged_fullness = result.values
    day_count = result.day_count
    open_marker_label = None
    close_marker_label = None
    if day_count == 1:
        open_marker_label = bucket_label(result.open_bucket)
        close_marker_label = bucket_label(result.close_bucket)

    if not averaged_fullness:
        return "<p>No data available.</p>"

    if mini:
        top_text = ""
        bottom_text = title
        row_count = 20
    else:
        top_text = title
        extra = ""
        if day_count:
            plural = "day" if day_count == 1 else "days"
            extra = f" (averaged across {day_count} {plural})"
        bottom_text = f"{subtitle}{extra}" if subtitle else extra.strip()
        row_count = 20

    return html_histogram(
        averaged_fullness,
        row_count,
        bar_color,
        mini=mini,
        title=top_text,
        subtitle=bottom_text,
        link_target=link_target,
        max_value=HIST_FIXED_Y_AXIS_FULLNESS,
        open_marker_label=open_marker_label,
        close_marker_label=close_marker_label,
    )


def activity_hist_table(
    ttdb: sqlite3.Connection,
    orgsite_id: int,
    start_date: str = None,
    end_date: str = None,
    days_of_week: str = None,
    title: str = "",
    subtitle: str = "",
    inbound_color: str = "lightcoral",
    outbound_color: str = "lightskyblue",
    mini: bool = False,
    link_target: str = "",
) -> str:
    """Render a stacked histogram for arrivals (bottom) and departures (top)."""

    arrivals_result = time_histogram_data(
        ttdb,
        orgsite_id=orgsite_id,
        query_column="time_in",
        start_date=start_date,
        end_date=end_date,
        days_of_week=days_of_week,
    )
    departures_result = time_histogram_data(
        ttdb,
        orgsite_id=orgsite_id,
        query_column="time_out",
        start_date=start_date,
        end_date=end_date,
        days_of_week=days_of_week,
    )

    arrivals = arrivals_result.values
    departures = departures_result.values

    day_count = max(arrivals_result.day_count, departures_result.day_count)

    open_marker_label = None
    close_marker_label = None
    if arrivals_result.day_count == 1 and departures_result.day_count == 1:
        open_bucket_candidates = [
            arrivals_result.open_bucket,
            departures_result.open_bucket,
        ]
        close_bucket_candidates = [
            arrivals_result.close_bucket,
            departures_result.close_bucket,
        ]
        open_bucket_candidates = [v for v in open_bucket_candidates if v is not None]
        close_bucket_candidates = [v for v in close_bucket_candidates if v is not None]
        if open_bucket_candidates:
            open_marker_label = bucket_label(min(open_bucket_candidates))
        if close_bucket_candidates:
            close_marker_label = bucket_label(max(close_bucket_candidates))

    if subtitle and "{" in subtitle:
        plural = "day" if day_count == 1 else "days"
        day_label = f"{day_count} {plural}"
        if "{days}" in subtitle:
            subtitle = subtitle.replace("{days}", day_label)
        if "{day_count}" in subtitle:
            subtitle = subtitle.replace("{day_count}", str(day_count))
        if "{day_label}" in subtitle:
            subtitle = subtitle.replace("{day_label}", day_label)

    if mini:
        top_text = ""
        bottom_text = title
        row_count = 20
    else:
        top_text = title
        bottom_text = subtitle
        row_count = 20

    return html_histogram(
        arrivals,
        row_count,
        inbound_color,
        mini=mini,
        title=top_text,
        subtitle=bottom_text,
        stack_data=departures,
        stack_color=outbound_color,
        link_target=link_target,
        max_value=HIST_FIXED_Y_AXIS_ACTIVITY,
        open_marker_label=open_marker_label,
        close_marker_label=close_marker_label,
    )


__all__ = [
    "activity_hist_table",
    "arrival_duration_hist_table",
    "fullness_hist_table",
    "times_hist_table",
]
