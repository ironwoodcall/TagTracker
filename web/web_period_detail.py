#!/usr/bin/env python3
"""TagTracker report showing detailed metrics for a single period."""

from __future__ import annotations

import html
import sqlite3

import web_common as cc
from web_daterange_selector import build_date_dow_filter_widget
from web_period_metrics import METRIC_ROWS, aggregate_period


def period_detail(
    ttdb: sqlite3.Connection,
    *,
    params: cc.ReportParameters,
) -> None:
    """Render the single-period detail report."""

    resolved_start = params.start_date
    resolved_end = params.end_date
    resolved_dow = params.dow
    resolved_pages_back = params.pages_back or 1

    params.what_report = cc.WHAT_DATERANGE_DETAIL
    params.start_date = resolved_start
    params.end_date = resolved_end
    params.dow = resolved_dow
    params.start_date2 = ""
    params.end_date2 = ""
    params.dow2 = ""
    params.pages_back = cc.increment_pages_back(resolved_pages_back)

    nav_pages_back = resolved_pages_back

    title = cc.titleize("Date range detail")
    print(title)
    print(f"{cc.main_and_back_buttons(nav_pages_back)}<br><br>")

    self_url = cc.CGIManager.selfref(
        params=params,
    )
    compare_url = cc.CGIManager.selfref(
        params=params,
        what_report=cc.WHAT_COMPARE_RANGES,
        start_date2=resolved_start,
        end_date2=resolved_end,
        dow2=resolved_dow,
        pages_back=1,
    )
    widget = build_date_dow_filter_widget(
        self_url,
        start_date=resolved_start,
        end_date=resolved_end,
        selected_dow=resolved_dow,
        include_day_filter=True,
        submit_label="Apply filters",
    )
    selection = widget.selection
    params.start_date = selection.start_date
    params.end_date = selection.end_date
    params.dow = selection.dow_value


    print(widget.html)
    # print("<br>")
    print(f"<p>You can also <a href='{compare_url}'>compare this to another date range</a></p>")

    description = selection.description(widget.options)

    metrics = aggregate_period(
        ttdb,
        selection.start_date,
        selection.end_date,
        selection.dow_value,
    )

    print("<table class='general_table'>")
    header_text = description or "All data"
    print(
        "<tr>"
        "<th colspan='3' style='text-align:center;font-size:1.5em;'>"
        f"{html.escape(header_text)}"
        "</th>"
        "</tr>"
    )
    print(
        "<tr>"
        "<th style='text-align:left;'>&nbsp;</th>"
        "<th style='text-align:left;'>Item</th>"
        "<th style='text-align:right;'>Value</th>"
        "</tr>"
    )

    for row in METRIC_ROWS:
        value = getattr(metrics, row["attr"])
        formatted_value = row["value_fmt"](value)
        row_class = row["row_class"] if "row_class" in row else ""
        row_span = row["row_span"] if "row_span" in row else ""
        row_span_color = row["row_span_color"] if "row_span_color" in row else "white"
        row_span_style = f"style=background-color:{row_span_color}"

        print(f"<tr {row_class}>")
        if row_span:
            print(
                f"<td rowspan={row_span} class='heavy-bottom' {row_span_style}>&nbsp;</td>"
            )
        print(
            f"<td style='text-align:left;'>{row['label']}</td>"
            f"<td style='text-align:right;'>{formatted_value}</td>"
            "</tr>"
        )

    print("</table>")

