#!/usr/bin/python3
"""
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

import sqlite3
from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING

import common.tt_util as ut
import common.tt_dbutil as db
from common.tt_time import VTime
import web_common as cc
from web.web_base_config import (
    HIST_FIXED_Y_AXIS_ACTIVITY,
    HIST_FIXED_Y_AXIS_DURATION,
    HIST_FIXED_Y_AXIS_FULLNESS,
)

if TYPE_CHECKING:
    from web.datacolors import Dimension


@dataclass
class HistogramResult:
    """Structured histogram data plus operating hour metadata."""

    values: dict[str, float]
    day_count: int
    open_bucket: int | None = None
    close_bucket: int | None = None
    category_minutes: int = 30


@dataclass
class HistogramMatrixResult:
    """Structured two-dimensional histogram data for arrival vs duration buckets."""

    arrival_labels: list[str]
    duration_labels: list[str]
    normalized_values: dict[str, dict[str, float]]
    raw_values: dict[str, dict[str, float]]
    day_count: int
    arrival_bucket_minutes: int = 30
    duration_bucket_minutes: int = 30


def _build_day_filter_items(
    orgsite_filter: int,
    start_date: str | None,
    end_date: str | None,
    days_of_week: str | None,
) -> list[str]:
    """Return reusable WHERE-clause pieces that only reference the DAY table."""

    items: list[str] = []
    if orgsite_filter:
        items.append(f"D.orgsite_id = {orgsite_filter}")
    if start_date:
        items.append(f"D.DATE >= '{start_date}'")
    if end_date:
        items.append(f"D.DATE <= '{end_date}'")
    if days_of_week:
        cc.test_dow_parameter(days_of_week, list_ok=True)
        dow_bits = [int(s) for s in days_of_week.split(",")]
        zero_based_days_of_week = ["0" if i == 7 else str(i) for i in dow_bits]
        items.append(
            f"""strftime('%w',D.DATE) IN ('{"','".join(zero_based_days_of_week)}')"""
        )
    return items


def _bucket_label(bucket_minutes: int | None) -> str | None:
    """Return tidy label text for a bucket start in minutes."""

    if bucket_minutes is None:
        return None
    vt = VTime(bucket_minutes)
    if not vt:
        return None
    return vt.tidy if hasattr(vt, "tidy") else str(vt)


def _format_minutes(minutes: int) -> str:
    """Return zero-padded HH:MM string for a minutes value."""

    if minutes < 0:
        minutes = 0
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02}:{mins:02}"


def _duration_bucket_label(
    bucket_minutes: int | None, bucket_width: int = 30
) -> str | None:
    """Return label like '00:00' for the start of a duration bucket."""

    if bucket_minutes is None:
        return None
    return _format_minutes(bucket_minutes)


def _minutes_expr(column_name: str) -> str:
    """Return SQL expression that converts HH:MM text to minutes."""

    return (
        f"CASE WHEN {column_name} IS NULL OR {column_name} = '' THEN NULL "
        f"WHEN length({column_name}) < 5 THEN NULL "
        f"ELSE ((CAST(substr({column_name}, 1, 2) AS INTEGER) * 60) + "
        f"CAST(substr({column_name}, 4, 2) AS INTEGER)) END"
    )


def _duration_minutes_expr(column_name: str = "V.duration") -> str:
    """Return SQL expression that coerces duration text to integer minutes."""

    return (
        f"CASE WHEN {column_name} IS NULL OR {column_name} = '' THEN NULL "
        f"ELSE CAST({column_name} AS INTEGER) END"
    )


def html_histogram(
    data: dict,
    num_data_rows: int = 20,
    bar_color: str = "blue",
    title: str = "",
    subtitle: str = "",
    table_width: int = 40,
    border_color: str = "black",
    mini: bool = False,
    stack_data=None,
    stack_color: str = "",
    link_target: str = "",
    max_value: float | None = None,
    open_marker_label: str | None = None,
    close_marker_label: str | None = None,
    marker_color: str | None = None,
) -> str:
    """Create an html histogram from a dictionary.

    When ``stack_data`` is provided the histogram renders stacked columns, using
    ``bar_color`` for the base values and ``stack_color`` for the values stacked
    above them.

    Note about css style names.  The css stylesheet is inline and
    its names could conflict with other styles -- including other
    calls to this function on the same html page.  Workaround is
    to dynamically name the styles with random prefixes."""

    stack_data = stack_data or {}
    if not data and not stack_data:
        return "<p>No data available.</p>"

    bar_color = bar_color or "blue"
    stack_color = stack_color or "royalblue"

    # Input validation
    if (
        not all(
            isinstance(arg, type)
            for arg, type in zip(
                [data, num_data_rows, title, table_width], [dict, int, str, int]
            )
        )
        or num_data_rows < 1
        or table_width < 1
    ):
        return "Invalid input."

    all_keys = sorted(set(data.keys()) | set(stack_data.keys()))
    num_columns = len(all_keys)
    if num_columns == 0:
        return "<p>No data available.</p>"

    # Each style sheet must be unique wrt its classes in case mult on one page
    prefix = ut.random_string(4)

    marker_color = marker_color or "darkblue"
    marker_class_map: dict[str, list[str]] = {}

    if open_marker_label or close_marker_label:
        def resolve_marker(label: str | None) -> str | None:
            if not label:
                return None
            for key in all_keys:
                if key.startswith(label):
                    return key
            return None

        open_marker_key = resolve_marker(open_marker_label)
        close_marker_key = resolve_marker(close_marker_label)

        if open_marker_key:
            marker_class_map.setdefault(open_marker_key, []).append(
                f"{prefix}-marker-left"
            )
        if close_marker_key:
            marker_class_map.setdefault(close_marker_key, []).append(
                f"{prefix}-marker-right"
            )

    marker_css = ""
    if marker_class_map:
        marker_css = f"""
        .{prefix}-marker-left {{
            border-left: 1px dotted {marker_color};
        }}
        .{prefix}-marker-right {{
            border-right: 1px dotted {marker_color};
        }}
        """

    # Normalize data values to fit within the num of rows
    totals: dict[str, float] = {}
    base_values: dict[str, float] = {}
    stack_values: dict[str, float] = {}
    for key in all_keys:
        base_values[key] = float(data.get(key, 0) or 0)
        stack_values[key] = float(stack_data.get(key, 0) or 0)
        totals[key] = base_values[key] + stack_values[key]

    provided_max = None
    if max_value is not None:
        try:
            provided_max = float(max_value)
        except (TypeError, ValueError):
            provided_max = None
        if provided_max is not None and provided_max <= 0:
            provided_max = None

    reference_max = provided_max if provided_max is not None else max(totals.values(), default=0)

    normalized_primary: dict[str, int] = {}
    normalized_secondary: dict[str, int] = {}
    normalized_totals: dict[str, int] = {}

    for key in all_keys:
        combined_value = totals[key]
        if reference_max:
            clamped_total = min(combined_value, reference_max) if provided_max else combined_value
            total_height = int(round((clamped_total / reference_max) * num_data_rows))
        else:
            total_height = 0

        if stack_values[key] and combined_value and total_height:
            base_ratio = base_values[key] / combined_value if combined_value else 0
            base_ratio = min(max(base_ratio, 0), 1)
            primary_height = int(round(total_height * base_ratio))
            secondary_height = total_height - primary_height
        else:
            primary_height = total_height
            secondary_height = 0

        normalized_primary[key] = max(primary_height, 0)
        normalized_secondary[key] = max(secondary_height, 0)
        normalized_totals[key] = max(total_height, 0)

    # Calculate cell width
    if mini:
        cell_width = max(0.4, min(1.0, 6.0 / max(num_columns, 1)))
        cell_width_style = f"{cell_width}em"
        empty_width_style = cell_width_style
    else:
        cell_width = 100 / num_columns if num_columns else 0
        cell_width_style = f"{cell_width}%" if num_columns else "auto"
        empty_width_style = cell_width_style
    padding_value = max(
        0.2, max([len(k) for k in all_keys]) * 0.2
    )  # FIXME: may require adjustment

    has_stack = bool(stack_data)
    top_text_color = "#333333" if has_stack else "white"
    zero_text_color = "#333333" if has_stack else bar_color

    secondary_styles = ""
    if any(normalized_secondary.values()):
        secondary_styles = f"""
        .{prefix}-bar-cell-secondary {{
            background-color: {stack_color}; width: {cell_width}%;
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
        }}
        .{prefix}-bar-top-cell-secondary {{
            text-align: center; font-size: 0.8em;
            color: {top_text_color}; background-color: {stack_color};
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
        }}
        """

    # Build the HTML table with inline CSS styles
    html_table = f"""
    <style>
        .{prefix}-table {{ font-family: sans-serif;
                border-collapse: collapse; border: 1px solid {border_color};
                width: {table_width}%;}}
        .{prefix}-empty-cell {{ background-color: white; width: {empty_width_style}; min-width: {empty_width_style}; max-width: {empty_width_style}; }}
        .{prefix}-category-label {{
            transform: rotate(-90deg); padding: {padding_value}em 0;
            border: 1px solid {border_color};border-top: 2px solid {bar_color};
            font-size: 0.85em; text-align: center;
        }}
        .{prefix}-bar-cell {{
            background-color: {bar_color}; width: {cell_width_style};
            min-width: {cell_width_style}; max-width: {cell_width_style};
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
        }}
        .{prefix}-bar-top-cell {{
            text-align: center; font-size: 0.8em;
            color: {top_text_color}; background-color: {bar_color};
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
        }}
        .{prefix}-zero-bar-cell {{
            text-align: center; font-size: 0.8em;
            color: {zero_text_color}; background-color: white; width: {cell_width_style};
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
            border-bottom: 2px solid {bar_color}
        }}
        .{prefix}-emptiness-cell {{ background-color: white; width: {empty_width_style}; min-width: {empty_width_style}; max-width: {empty_width_style}; }}
        .{prefix}-titles {{ text-align: center; background-color: white; }}
        {secondary_styles}
        {marker_css}
    </style>
    """

    table_open = f"<table class='{prefix}-table'>"
    table_close = "</table>"
    if link_target:
        table_open = (
            f"<a href='{link_target}' style='text-decoration:none; color:inherit;'>"
            f"{table_open}"
        )
        table_close = f"{table_close}</a>"

    html_table += f"""
        {table_open}

        """
    # Add the title in otherwise blank row at top
    if title and not mini:
        html_table += f"""<tr><td colspan='{num_columns}' class='{prefix}-titles'
            >{title}</td></tr>"""

    if not mini:
        # Add an empty row at the top to create spacing above the bars
        html_table += "<tr>"
        for key in all_keys:
            cell_classes = [f"{prefix}-empty-cell"]
            cell_classes.extend(marker_class_map.get(key, []))
            html_table += (
                f"<td class='{' '.join(cell_classes)}'>&nbsp;</td>"
            )
        html_table += "</tr>"

    empty_text = "" if mini else "&nbsp;"
    for row_index in range(num_data_rows):
        html_table += "<tr>"
        for key in all_keys:
            total_height = normalized_totals[key]
            primary_height = normalized_primary[key]
            secondary_height = normalized_secondary[key]
            marker_classes = marker_class_map.get(key, [])

            if total_height == 0:
                if row_index == num_data_rows - 1:
                    val = "" if mini else int(round(totals[key]))
                    cell_classes = [f"{prefix}-zero-bar-cell"]
                    cell_classes.extend(marker_classes)
                    html_table += (
                        f"<td class='{' '.join(cell_classes)}'><b>{val}</b></td>"
                    )
                else:
                    cell_classes = [f"{prefix}-emptiness-cell"]
                    cell_classes.extend(marker_classes)
                    html_table += (
                        f"<td class='{' '.join(cell_classes)}'>{empty_text}</td>"
                    )
                continue

            row_from_bottom = num_data_rows - 1 - row_index
            if row_from_bottom >= total_height:
                cell_classes = [f"{prefix}-emptiness-cell"]
                cell_classes.extend(marker_classes)
                html_table += (
                    f"<td class='{' '.join(cell_classes)}'>{empty_text}</td>"
                )
                continue

            is_top_cell = row_from_bottom == total_height - 1
            in_primary = row_from_bottom < primary_height

            if in_primary:
                classes = [f"{prefix}-bar-cell"]
                if is_top_cell and secondary_height == 0:
                    classes.append(f"{prefix}-bar-top-cell")
            else:
                classes = [f"{prefix}-bar-cell-secondary"]
                if is_top_cell:
                    classes.append(f"{prefix}-bar-top-cell-secondary")

            if is_top_cell:
                display_val = "" if mini else int(round(totals[key]))
            else:
                display_val = empty_text

            classes.extend(marker_classes)
            html_table += f"<td class='{' '.join(classes)}'>{display_val}</td>"

        html_table += "</tr>\n"

    if not mini:
        html_table += "<tr>"
        for key in all_keys:
            cell_classes = [f"{prefix}-category-label"]
            cell_classes.extend(marker_class_map.get(key, []))
            html_table += (
                f"<td class='{' '.join(cell_classes)}'>{key}</td>"
            )
        html_table += "</tr>\n"

    # Add a caption below category labels
    if subtitle:
        html_table += f"""<tr><td colspan='{num_columns}' class='{prefix}-titles'
            style='font-size:0.85em'>{subtitle}</td></tr>"""

    html_table += table_close
    return html_table


def time_histogram_data(
    ttdb: sqlite3.Connection,
    orgsite_id: int,
    query_column: str,
    start_date: str = None,
    end_date: str = None,
    days_of_week: str = None,
    category_minutes: int = 30,
) -> HistogramResult:
    """Return averaged histogram data for the requested time column."""

    time_column_lower = query_column.lower()
    if time_column_lower not in {"time_in", "time_out", "duration"}:
        raise ValueError(f"Bad value for query column, '{query_column}' ")

    minutes_column_map = {
        "time_in": _minutes_expr("V.time_in"),
        "time_out": _minutes_expr("V.time_out"),
        "duration": "V.duration",
    }
    minutes_column = minutes_column_map[time_column_lower]

    orgsite_filter = orgsite_id if orgsite_id else 1  # FIXME: default fallback

    day_filter_items = _build_day_filter_items(
        orgsite_filter, start_date, end_date, days_of_week
    )

    filter_items: list[str] = [f"({minutes_column}) IS NOT NULL"] + day_filter_items
    if time_column_lower == "duration":
        filter_items.append("V.time_out IS NOT NULL")
        filter_items.append("V.time_out <> ''")
    filter_clause = " AND ".join(filter_items) if filter_items else "1 = 1"
    day_filter_clause = (
        " AND ".join(day_filter_items) if day_filter_items else "1 = 1"
    )

    if time_column_lower == "duration":
        start_time, end_time = ("00:00", "12:00")
    else:
        start_time, end_time = ("07:00", "22:00")

    base_cte = f"""
WITH filtered_visits AS (
    SELECT
        D.date AS visit_date,
        {minutes_column} AS minutes_value
    FROM
        DAY D
    JOIN
        VISIT V ON D.id = V.day_id
    WHERE {filter_clause}
)
    """

    day_count_query = (
        base_cte
        + "SELECT COUNT(DISTINCT visit_date) AS day_count FROM filtered_visits;"
    )
    day_rows = db.db_fetch(ttdb, day_count_query, ["day_count"])
    day_count = day_rows[0].day_count if day_rows else 0
    if day_count is None:
        day_count = 0
    elif not isinstance(day_count, int):
        day_count = int(day_count)

    bucket_query = (
        base_cte
        + "SELECT\n"
        f"    minutes_value - (minutes_value % {category_minutes}) AS bucket_start,\n"
        "    COUNT(*) AS bucket_count\n"
        "FROM filtered_visits\n"
        "WHERE minutes_value IS NOT NULL\n"
        "GROUP BY bucket_start\n"
        "ORDER BY bucket_start;\n"
    )
    bucket_rows = db.db_fetch(ttdb, bucket_query, ["bucket_start", "bucket_count"])
    bucket_counts: dict[int, int] = {}
    for row in bucket_rows:
        if row.bucket_start is None:
            continue
        bucket_counts[int(row.bucket_start)] = int(row.bucket_count)

    open_bucket = close_bucket = None
    hours_query = f"""
        SELECT
            MIN(NULLIF(D.time_open, '')) AS min_open,
            MAX(NULLIF(D.time_closed, '')) AS max_close
        FROM DAY D
        WHERE {day_filter_clause}
    """
    hours_rows = db.db_fetch(ttdb, hours_query, ["min_open", "max_close"])
    if hours_rows:
        open_val = getattr(hours_rows[0], "min_open", None)
        close_val = getattr(hours_rows[0], "max_close", None)
        open_minutes = VTime(open_val).num if open_val else None
        close_minutes = VTime(close_val).num if close_val else None
        if open_minutes is not None and category_minutes:
            open_bucket = (open_minutes // category_minutes) * category_minutes
        if close_minutes is not None and category_minutes:
            close_effective = max(close_minutes - 1, 0)
            close_bucket = (close_effective // category_minutes) * category_minutes

    if not bucket_counts:
        averaged_freq: dict[str, float] = {}
    else:
        start_minutes = VTime(start_time).num if start_time else min(bucket_counts.keys())
        end_minutes = VTime(end_time).num if end_time else max(bucket_counts.keys())
        start_bucket = (start_minutes // category_minutes) * category_minutes
        end_bucket = (end_minutes // category_minutes) * category_minutes
        categories_by_minute: dict[int, int] = {
            minute: 0
            for minute in range(start_bucket, end_bucket + category_minutes, category_minutes)
        }
        have_unders = have_overs = False
        for bucket_start, count in bucket_counts.items():
            if bucket_start in categories_by_minute:
                categories_by_minute[bucket_start] = count
            elif bucket_start < start_bucket:
                categories_by_minute[start_bucket] += count
                have_unders = True
            elif bucket_start > end_bucket:
                categories_by_minute[end_bucket] += count
                have_overs = True

        categories_str = {
            VTime(minute).tidy: value for minute, value in categories_by_minute.items()
        }
        if have_unders:
            start_label = VTime(start_bucket).tidy
            categories_str[f"{start_label}-"] = categories_str.pop(start_label, 0)
        if have_overs:
            end_label = VTime(end_bucket).tidy
            categories_str[f"{end_label}+"] = categories_str.pop(end_label, 0)
        averaged_freq = {
            key: (value / (day_count or 1)) for key, value in sorted(categories_str.items())
        }

    return HistogramResult(
        values=averaged_freq,
        day_count=day_count,
        open_bucket=open_bucket,
        close_bucket=close_bucket,
        category_minutes=category_minutes,
    )


def fullness_histogram_data(
    ttdb: sqlite3.Connection,
    orgsite_id: int,
    start_date: str = None,
    end_date: str = None,
    days_of_week: str = None,
    category_minutes: int = 30,
) -> HistogramResult:
    """Return averaged fullness data (bikes on hand) for each time block."""

    orgsite_filter = orgsite_id if orgsite_id else 1  # FIXME: default fallback

    day_filter_items = _build_day_filter_items(
        orgsite_filter, start_date, end_date, days_of_week
    )

    filter_items: list[str] = ["B.num_on_hand_combined IS NOT NULL"] + day_filter_items
    filter_clause = " AND ".join(filter_items) if filter_items else "1 = 1"
    day_filter_clause = (
        " AND ".join(day_filter_items) if day_filter_items else "1 = 1"
    )

    day_count_query = f"""
        SELECT COUNT(DISTINCT D.DATE) AS day_count
        FROM DAY D
        JOIN BLOCK B ON B.day_id = D.id
        WHERE {filter_clause}
    """
    day_rows = db.db_fetch(ttdb, day_count_query, ["day_count"])
    day_count = day_rows[0].day_count if day_rows else 0
    if day_count is None:
        day_count = 0
    elif not isinstance(day_count, int):
        day_count = int(day_count)

    bucket_query = f"""
        SELECT
            B.time_start AS bucket_start,
            AVG(B.num_on_hand_combined) AS avg_fullness,
            COUNT(*) AS sample_count
        FROM DAY D
        JOIN BLOCK B ON B.day_id = D.id
        WHERE {filter_clause}
        GROUP BY B.time_start
        ORDER BY B.time_start
    """
    bucket_rows = db.db_fetch(
        ttdb, bucket_query, ["bucket_start", "avg_fullness", "sample_count"]
    )

    bucket_totals: dict[int, float] = {}
    bucket_counts: dict[int, int] = {}
    for row in bucket_rows:
        bucket_time = VTime(row.bucket_start)
        if not bucket_time or getattr(bucket_time, "num", None) is None:
            continue
        minute_value = int(bucket_time.num)
        sample_count = int(row.sample_count or 0)
        if sample_count <= 0:
            continue
        avg_fullness = float(row.avg_fullness or 0.0)
        bucket_totals[minute_value] = bucket_totals.get(minute_value, 0.0) + (
            avg_fullness * sample_count
        )
        bucket_counts[minute_value] = bucket_counts.get(minute_value, 0) + sample_count

    open_bucket = close_bucket = None
    hours_query = f"""
        SELECT
            MIN(NULLIF(D.time_open, '')) AS min_open,
            MAX(NULLIF(D.time_closed, '')) AS max_close
        FROM DAY D
        WHERE {day_filter_clause}
    """
    hours_rows = db.db_fetch(ttdb, hours_query, ["min_open", "max_close"])
    if hours_rows:
        open_val = getattr(hours_rows[0], "min_open", None)
        close_val = getattr(hours_rows[0], "max_close", None)
        open_minutes = VTime(open_val).num if open_val else None
        close_minutes = VTime(close_val).num if close_val else None
        if open_minutes is not None and category_minutes:
            open_bucket = (open_minutes // category_minutes) * category_minutes
        if close_minutes is not None and category_minutes:
            close_effective = max(close_minutes - 1, 0)
            close_bucket = (close_effective // category_minutes) * category_minutes

    if not bucket_totals:
        return HistogramResult(
            values={},
            day_count=day_count,
            open_bucket=open_bucket,
            close_bucket=close_bucket,
            category_minutes=category_minutes,
        )

    start_minutes = VTime("07:00").num
    end_minutes = VTime("22:00").num
    if start_minutes is None or end_minutes is None:
        return HistogramResult(
            values={},
            day_count=day_count,
            open_bucket=open_bucket,
            close_bucket=close_bucket,
            category_minutes=category_minutes,
        )

    start_bucket = (start_minutes // category_minutes) * category_minutes
    end_bucket = (end_minutes // category_minutes) * category_minutes
    bucket_range = range(start_bucket, end_bucket + category_minutes, category_minutes)

    buckets_to_totals: dict[int, float] = {minute: 0.0 for minute in bucket_range}
    buckets_to_counts: dict[int, int] = {minute: 0 for minute in bucket_range}
    have_unders = have_overs = False

    for minute_value, total_fullness in bucket_totals.items():
        bucket_minute = (minute_value // category_minutes) * category_minutes
        count = bucket_counts.get(minute_value, 0)
        if count <= 0:
            continue
        if bucket_minute < start_bucket:
            buckets_to_totals[start_bucket] += total_fullness
            buckets_to_counts[start_bucket] += count
            have_unders = True
        elif bucket_minute > end_bucket:
            buckets_to_totals[end_bucket] += total_fullness
            buckets_to_counts[end_bucket] += count
            have_overs = True
        else:
            buckets_to_totals.setdefault(bucket_minute, 0.0)
            buckets_to_counts.setdefault(bucket_minute, 0)
            buckets_to_totals[bucket_minute] += total_fullness
            buckets_to_counts[bucket_minute] += count

    ordered_pairs: list[tuple[str, float]] = []
    for minute in bucket_range:
        vt = VTime(minute)
        if not vt:
            continue
        label = vt.tidy if hasattr(vt, "tidy") else str(vt)
        total = buckets_to_totals.get(minute, 0.0)
        count = buckets_to_counts.get(minute, 0)
        avg_value = total / count if count else 0.0
        ordered_pairs.append((label, avg_value))

    if ordered_pairs and have_unders:
        start_label, start_value = ordered_pairs[0]
        ordered_pairs[0] = (f"{start_label}-", start_value)

    if ordered_pairs and have_overs:
        end_idx = len(ordered_pairs) - 1
        end_label, end_value = ordered_pairs[end_idx]
        ordered_pairs[end_idx] = (f"{end_label}+", end_value)

    averaged_fullness = dict(ordered_pairs)

    return HistogramResult(
        values=averaged_fullness,
        day_count=day_count,
        open_bucket=open_bucket,
        close_bucket=close_bucket,
        category_minutes=category_minutes,
    )


def arrival_duration_matrix_data(
    ttdb: sqlite3.Connection,
    orgsite_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    days_of_week: str | None = None,
    arrival_bucket_minutes: int = 30,
    duration_bucket_minutes: int = 30,
    min_arrival_time: str = "06:00",
) -> HistogramMatrixResult:
    """Return normalized arrival vs duration data suitable for a heatmap table.

    Each arrival bucket holds a stack of duration buckets.  Values are normalized
    within each arrival bucket (max value => 1.0) so that a single Dimension
    can colourize the resulting HTML table.
    """

    if arrival_bucket_minutes < 1 or duration_bucket_minutes < 1:
        raise ValueError("Bucket widths must be positive integers.")

    time_in_minutes_expr = _minutes_expr("V.time_in")
    duration_minutes_expr = _duration_minutes_expr()

    threshold_minutes = VTime(min_arrival_time).num if min_arrival_time else None
    if threshold_minutes is None:
        threshold_minutes = 0

    orgsite_filter = orgsite_id if orgsite_id else 1  # FIXME: default fallback

    day_filter_items = _build_day_filter_items(
        orgsite_filter, start_date, end_date, days_of_week
    )
    filter_items: list[str] = list(day_filter_items)
    filter_items.extend(
        [
            "V.time_in IS NOT NULL",
            "V.time_in <> ''",
            "V.time_out IS NOT NULL",
            "V.time_out <> ''",
            f"({time_in_minutes_expr}) IS NOT NULL",
            f"({duration_minutes_expr}) IS NOT NULL",
            f"({duration_minutes_expr}) > 0",
        ]
    )
    if threshold_minutes:
        filter_items.append(f"({time_in_minutes_expr}) >= {threshold_minutes}")

    filter_clause = " AND ".join(filter_items) if filter_items else "1 = 1"
    base_cte = f"""
WITH filtered_visits AS (
    SELECT
        D.date AS visit_date,
        {time_in_minutes_expr} AS arrival_minutes,
        {duration_minutes_expr} AS duration_minutes
    FROM
        DAY D
    JOIN
        VISIT V ON D.id = V.day_id
    WHERE {filter_clause}
)
    """

    day_count_query = (
        base_cte
        + "SELECT COUNT(DISTINCT visit_date) AS day_count FROM filtered_visits;"
    )
    day_rows = db.db_fetch(ttdb, day_count_query, ["day_count"])
    day_count = day_rows[0].day_count if day_rows else 0
    if day_count is None:
        day_count = 0
    elif not isinstance(day_count, int):
        day_count = int(day_count)

    bucket_query = (
        base_cte
        + "SELECT\n"
        f"    arrival_minutes - (arrival_minutes % {arrival_bucket_minutes}) AS arrival_bucket,\n"
        f"    duration_minutes - (duration_minutes % {duration_bucket_minutes}) AS duration_bucket,\n"
        "    COUNT(*) AS bucket_count\n"
        "FROM filtered_visits\n"
        "WHERE arrival_minutes IS NOT NULL AND duration_minutes IS NOT NULL\n"
        "GROUP BY arrival_bucket, duration_bucket\n"
        "ORDER BY arrival_bucket, duration_bucket;\n"
    )
    bucket_rows = db.db_fetch(
        ttdb,
        bucket_query,
        ["arrival_bucket", "duration_bucket", "bucket_count"],
    )

    buckets: dict[int, dict[int, int]] = {}
    arrival_buckets: set[int] = set()
    duration_buckets: set[int] = set()
    for row in bucket_rows:
        if row.arrival_bucket is None or row.duration_bucket is None:
            continue
        arrival_minute = int(row.arrival_bucket)
        duration_minute = int(row.duration_bucket)
        count = int(row.bucket_count)
        arrival_buckets.add(arrival_minute)
        duration_buckets.add(duration_minute)
        buckets.setdefault(arrival_minute, {})
        buckets[arrival_minute][duration_minute] = count

    if not buckets:
        return HistogramMatrixResult(
            arrival_labels=[],
            duration_labels=[],
            normalized_values={},
            raw_values={},
            day_count=day_count,
            arrival_bucket_minutes=arrival_bucket_minutes,
            duration_bucket_minutes=duration_bucket_minutes,
        )

    arrival_range = sorted(arrival_buckets)
    if arrival_range:
        start_arrival = arrival_range[0]
        end_arrival = arrival_range[-1]
        arrival_range = list(
            range(start_arrival, end_arrival + arrival_bucket_minutes, arrival_bucket_minutes)
        )

    duration_range = sorted(duration_buckets)
    if duration_range:
        start_duration = 0
        end_duration = duration_range[-1]
        duration_range = list(
            range(start_duration, end_duration + duration_bucket_minutes, duration_bucket_minutes)
        )

    arrival_labels: list[str] = []
    for minute in arrival_range:
        label = _bucket_label(minute)
        if label is None:
            label = VTime(minute, allow_large=True).tidy if minute is not None else ""
        arrival_labels.append(label or _format_minutes(minute))

    duration_labels: list[str] = []
    for minute in duration_range:
        label = _duration_bucket_label(minute, duration_bucket_minutes)
        duration_labels.append(label or _format_minutes(minute))

    normalized_values: dict[str, dict[str, float]] = {}
    raw_values: dict[str, dict[str, float]] = {}

    for arrival_minute, arrival_label in zip(arrival_range, arrival_labels):
        raw_row: dict[str, float] = {}
        max_value = 0.0
        source = buckets.get(arrival_minute, {})
        for duration_minute, duration_label in zip(duration_range, duration_labels):
            val = float(source.get(duration_minute, 0))
            raw_row[duration_label] = val
            if val > max_value:
                max_value = val
        raw_values[arrival_label] = raw_row
        normalized_row: dict[str, float] = {}
        for duration_label in duration_labels:
            value = raw_row[duration_label]
            normalized_row[duration_label] = value / max_value if max_value else 0.0
        normalized_values[arrival_label] = normalized_row

    if day_count:
        for arrival_label, raw_row in raw_values.items():
            for duration_label, val in raw_row.items():
                raw_row[duration_label] = val / day_count

    return HistogramMatrixResult(
        arrival_labels=arrival_labels,
        duration_labels=duration_labels,
        normalized_values=normalized_values,
        raw_values=raw_values,
        day_count=day_count,
        arrival_bucket_minutes=arrival_bucket_minutes,
        duration_bucket_minutes=duration_bucket_minutes,
    )


def html_histogram_matrix(
    matrix: HistogramMatrixResult,
    dimension: "Dimension | None",
    *,
    title: str = "",
    subtitle: str = "",
    table_width: int = 60,
    border_color: str = "black",
    value_threshold: float = 0.2,
    show_counts: bool = True,
    use_contrasting_text: bool = False,
) -> str:
    """Render a 2D histogram matrix (arrival x duration) as HTML."""

    if not matrix.arrival_labels or not matrix.duration_labels:
        return "<p>No data available.</p>"

    try:
        threshold = float(value_threshold)
    except (TypeError, ValueError):
        threshold = 0.0
    threshold = max(0.0, min(1.0, threshold))

    if dimension is None:
        try:
            import datacolors as dc  # type: ignore
        except ModuleNotFoundError:  # pragma: no cover - fallback when run as package
            from web import datacolors as dc  # type: ignore

        dimension = dc.Dimension()
        dimension.add_config(0.0, "white")
        dimension.add_config(1.0, "RoyalBlue")

    table_width = table_width or 0
    table_width = max(table_width, 10)
    width_style = f"{table_width}%" if table_width else "auto"
    prefix = ut.random_string(4)

    data_columns = len(matrix.arrival_labels)
    colspan = data_columns + 2

    color_func_name = "css_bg_fg" if use_contrasting_text and hasattr(dimension, "css_bg_fg") else "css_bg"
    color_func = getattr(dimension, color_func_name)

    data_cell_width_em = 1.2
    row_unit_em = 0.18
    cell_height_em = row_unit_em * 2

    style_block = f"""
    <style>
        .{prefix}-table {{
            border-collapse: collapse;
            width: {width_style};
            font-family: sans-serif;
            margin: 0 auto;
            border: 1px solid {border_color};
            background: white;
            table-layout: fixed;
        }}
        .{prefix}-title-cell {{
            text-align: center;
            font-weight: bold;
            padding: 0.4em 0.6em;
            background: #f8f8f8;
            border-bottom: 1px solid {border_color};
        }}
        .{prefix}-subtitle-cell {{
            text-align: center;
            font-size: 0.85em;
            padding: 0.35em 0.6em;
            background: #fafafa;
            border-top: 1px solid {border_color};
        }}
        .{prefix}-arrival-cell {{
            text-align: center;
            font-weight: normal;
            padding: 0.1em 0.15em;
            background: white;
            white-space: nowrap;
            height: 3.5em;
            vertical-align: top;
            border-left: 1px solid {border_color};
            border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
            border-bottom: 1px solid {border_color};
        }}
        .{prefix}-axis-title {{
            text-align: center;
            vertical-align: middle;
            background: white;
            border-left: 1px solid {border_color};
            border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
            border-bottom: 1px solid {border_color};
            width: 2.4em;
            padding: 0;
        }}
        .{prefix}-axis-title-text {{
            display: inline-block;
            transform: rotate(90deg);
            transform-origin: center;
            white-space: nowrap;
            font-weight: bold;
            font-size: 0.85em;
            letter-spacing: 0.05em;
        }}
        .{prefix}-arrival-text {{
            display: inline-block;
            transform: rotate(-90deg);
            transform-origin: center;
            white-space: nowrap;
            font-weight: normal;
            font-size: 0.8em;
        }}
        .{prefix}-label-cell {{
            text-align: right;
            font-weight: normal;
            padding: 0.15em 0.25em;
            background: white;
            white-space: nowrap;
            border-left: 1px solid {border_color};
            border-right: 1px solid {border_color};
            border-bottom: 1px solid {border_color};
            font-size: 0.85em;
            min-width: 4.5em;
            width: 4.5em;
        }}
        .{prefix}-data-cell {{
            text-align: center;
            padding: 0.03em 0.04em;
            width: {data_cell_width_em:.2f}em;
            min-width: {data_cell_width_em:.2f}em;
            height: {cell_height_em:.3f}em;
        }}
        .{prefix}-corner-cell {{
            background: white;
            border-left: 1px solid {border_color};
            border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
            border-bottom: 1px solid {border_color};
        }}
        .{prefix}-axis-corner {{
            background: white;
            border-left: 1px solid {border_color};
            border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
            border-bottom: 1px solid {border_color};
            width: 2.4em;
        }}
        .{prefix}-data-row {{
            height: {row_unit_em:.3f}em;
        }}
        .{prefix}-data-row-blank {{
            height: 0;
        }}
    </style>
    """

    parts: list[str] = [style_block, f"<table class='{prefix}-table'>"]

    if title:
        parts.append(
            f"<tr><td colspan='{colspan}' class='{prefix}-title-cell'>{title}</td></tr>"
        )

    duration_labels_desc = list(reversed(matrix.duration_labels))
    column_top_indices: dict[str, int | None] = {}
    for arrival_label in matrix.arrival_labels:
        top_index = None
        normalized_row = matrix.normalized_values.get(arrival_label, {})
        for idx, duration_label in enumerate(duration_labels_desc):
            if normalized_row.get(duration_label, 0.0) >= threshold:
                top_index = idx
                break
        column_top_indices[arrival_label] = top_index

    axis_rowspan = len(duration_labels_desc) * 2 if duration_labels_desc else 0

    for row_index, duration_label in enumerate(duration_labels_desc):
        parts.append(f"<tr class='{prefix}-data-row'>")
        if row_index == 0 and axis_rowspan:
            parts.append(
                f"<th class='{prefix}-axis-title' rowspan='{axis_rowspan}'><span class='{prefix}-axis-title-text'>Duration of visit</span></th>"
            )
        display_duration = duration_label or "&nbsp;"
        parts.append(
            f"<th class='{prefix}-label-cell' rowspan='2'>{display_duration}</th>"
        )
        for arrival_label in matrix.arrival_labels:
            normalized_row = matrix.normalized_values.get(arrival_label, {})
            raw_row = matrix.raw_values.get(arrival_label, {})
            normalized_value = normalized_row.get(duration_label, 0.0)
            raw_value = raw_row.get(duration_label, 0.0)
            effective_value = normalized_value if normalized_value >= threshold else 0.0
            cell_text = "&nbsp;"
            if show_counts:
                if normalized_value >= threshold:
                    if raw_value.is_integer():
                        cell_text = str(int(raw_value))
                    else:
                        cell_text = f"{raw_value:.2f}"
                else:
                    cell_text = "0"
            classes = [f"{prefix}-data-cell"]
            style_value = color_func(effective_value)
            style_components = [style_value, f"height: {cell_height_em:.3f}em;", f"min-height: {cell_height_em:.3f}em;"]
            top_index = column_top_indices.get(arrival_label)
            if top_index is not None and row_index >= top_index:
                style_components.append(f"border-left: 1px solid {border_color};")
                style_components.append(f"border-right: 1px solid {border_color};")
                if row_index == top_index:
                    style_components.append(f"border-top: 1px solid {border_color};")
            mean_visits = float(raw_value)
            if mean_visits.is_integer():
                visit_text = f"{int(mean_visits)} visit{'s' if mean_visits != 1 else ''}/day"
            else:
                visit_text = f"{mean_visits:.2f} visits/day"
            tooltip = (
                f"{visit_text}\n"
                f"starting {arrival_label}\n"
                f"lasting {duration_label}"
            )
            title_text = escape(tooltip, quote=True).replace("\n", "&#10;")
            style_attr = " ".join(style_components)
            parts.append(
                f"<td class='{' '.join(classes)}' rowspan='2' style='{style_attr}' "
                f"title='{title_text}'>{cell_text}</td>"
            )
        parts.append("</tr>")
        parts.append(f"<tr class='{prefix}-data-row-blank'></tr>")

    parts.append("<tr>")
    parts.append(f"<th class='{prefix}-axis-corner'>&nbsp;</th>")
    parts.append(f"<th class='{prefix}-corner-cell'>&nbsp;</th>")
    for idx, arrival_label in enumerate(matrix.arrival_labels):
        display_arrival = arrival_label if arrival_label else "&nbsp;"
        parts.append(
            f"<th class='{prefix}-arrival-cell'><span class='{prefix}-arrival-text'>{display_arrival}</span></th>"
        )
    parts.append("</tr>")

    if subtitle:
        parts.append(
            f"<tr><td colspan='{colspan}' class='{prefix}-subtitle-cell'>{subtitle}</td></tr>"
        )

    parts.append("</table>")
    return "\n".join(parts)


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
    min_arrival_time: str = "06:00",
    title: str = "",
    subtitle: str = "",
    table_width: int = 60,
    border_color: str = "black",
    value_threshold: float = 0.2,
    show_counts: bool = True,
    use_contrasting_text: bool = False,
) -> str:
    """Convenience helper to fetch data and render the arrival-duration matrix."""

    matrix = arrival_duration_matrix_data(
        ttdb=ttdb,
        orgsite_id=orgsite_id,
        start_date=start_date,
        end_date=end_date,
        days_of_week=days_of_week,
        arrival_bucket_minutes=arrival_bucket_minutes,
        duration_bucket_minutes=duration_bucket_minutes,
        min_arrival_time=min_arrival_time,
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
        value_threshold=value_threshold,
        show_counts=show_counts,
        use_contrasting_text=use_contrasting_text,
    )


def times_hist_table(
    ttdb: sqlite3.Connection,
    orgsite_id:int,
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
        open_marker_label = _bucket_label(result.open_bucket)
        close_marker_label = _bucket_label(result.close_bucket)

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
            median_val = expanded_values[n // 2] if n % 2 == 1 else (
                expanded_values[n // 2 - 1] + expanded_values[n // 2]
            ) / 2
            variance = sum((val - mean_val) ** 2 for val in expanded_values) / n
            std_dev = variance ** 0.5
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
        open_marker_label = _bucket_label(result.open_bucket)
        close_marker_label = _bucket_label(result.close_bucket)

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
        open_bucket_candidates = [arrivals_result.open_bucket, departures_result.open_bucket]
        close_bucket_candidates = [arrivals_result.close_bucket, departures_result.close_bucket]
        open_bucket_candidates = [v for v in open_bucket_candidates if v is not None]
        close_bucket_candidates = [v for v in close_bucket_candidates if v is not None]
        if open_bucket_candidates:
            open_marker_label = _bucket_label(min(open_bucket_candidates))
        if close_bucket_candidates:
            close_marker_label = _bucket_label(max(close_bucket_candidates))

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
    # return chartjs_histogram(times_freq,400,400,bar_color=color,title=top_text,subtitle=bottom_text,)


if __name__ == "__main__":
    # Example usage
    data_example = {
        "00:00": 2003,
        "00:30": 3482,
        "01:00": 3996,
        "01:30": 3791,
        "02:00": 2910,
        "02:30": 2246,
        "03:00": 1707,
        "03:30": 1365,
        "04:00": 1027,
        "04:30": 846,
        "05:00": 738,
        "05:30": 730,
        "06:00": 584,
        "06:30": 654,
        "07:00": 771,
        "07:30": 1093,
        "08:00": 2042,
        "08:30": 2135,
        "09:00": 777,
        "09:30": 334,
        "10:00": 177,
        "10:30": 101,
        "11:00": 62,
        "11:30": 41,
        "12:00+": 55,
    }
    print("Content-type: text/html\n\n")
    result = html_histogram(
        data_example,
        num_data_rows=6,
        subtitle="Frequency distribution of visit lengths",
        table_width=20,
        mini=True,
        bar_color="royalblue",
        border_color="white",
    )

    print(
        """<div style="display: flex;">
        <!-- Left Column -->
        <div XXstyle="flex: 0; margin-right: 20px;">"""
    )
    print(result)

    print(
        """ </div>
        <!-- Right Column -->
        <div XXstyle="flex: 0;">"""
    )
    print("<br><br>")
    result = html_histogram(
        data_example,
        20,
        "orange",
        "<b>Lengths of visit 2023</b>",
        "Category start (30 minute categories)",
        10,
        mini=False,
    )
    print(result)
    print("</div></div>")
