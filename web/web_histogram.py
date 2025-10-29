#!/usr/bin/python3
"""
Legacy histogram facade.

The historical ``web_histogram`` module grew to include data access, rendering,
and orchestration helpers.  Its contents are now split across dedicated modules
to improve maintainability:

* ``web_histogram_data``: data-layer helpers and DTOs
* ``web_histogram_render``: HTML renderers
* ``web_histogram_tables``: high-level helpers combining the above

This wrapper keeps the original import surface available while delegating the
work to the new modules.
"""

from web_histogram_data import (
    ArrivalDepartureMatrix,
    HistogramResult,
    # arrival_duration_matrix_data,
    bucket_label,
    duration_bucket_label,
    # format_minutes,
    fullness_histogram_data,
    time_histogram_data,
)
from web_histogram_render import html_histogram, html_histogram_matrix
from web_histogram_tables import (
    activity_hist_table,
    arrival_duration_hist_table,
    fullness_hist_table,
    times_hist_table,
)

# Backward compatible aliases for legacy private helpers.
_bucket_label = bucket_label
# _format_minutes = format_minutes
_duration_bucket_label = duration_bucket_label


__all__ = [
    "ArrivalDepartureMatrix",
    "HistogramResult",
    "activity_hist_table",
    "arrival_duration_hist_table",
    # "arrival_duration_matrix_data",
    "bucket_label",
    "fullness_hist_table",
    "fullness_histogram_data",
    "html_histogram",
    "html_histogram_matrix",
    "time_histogram_data",
    "times_hist_table",
    "duration_bucket_label",
    # "format_minutes",
    "_bucket_label",
    # "_format_minutes",
    "_duration_bucket_label",
]
