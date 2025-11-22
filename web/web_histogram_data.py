"""
Data preparation utilities for the histogram views.
"""

from dataclasses import dataclass
import sqlite3

import common.tt_dbutil as db
import web.web_common as cc
from common.tt_time import VTime


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


def _build_day_filter_items(
    orgsite_filter: int = 1,
    start_date: str | None = None,
    end_date: str | None = None,
    days_of_week: str | None = None,
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
        # SQLite's strftime uses 0=Sunday, TagTracker uses 7=Sunday; convert.
        zero_based_days_of_week = ["0" if i == 7 else str(i) for i in dow_bits]
        items.append(
            f"""strftime('%w',D.DATE) IN ('{"','".join(zero_based_days_of_week)}')"""
        )
    return items


@dataclass
class HistogramResult:
    """Structured histogram data plus operating hour metadata.

    The rendering layer expects ``values`` to already be averaged per day and the
    optional ``open/close`` buckets to align with ``category_minutes``.
    """

    values: dict[str, float]
    day_count: int
    open_bucket: int | None = None
    close_bucket: int | None = None
    category_minutes: int = 30


class ArrivalDepartureMatrix:
    """Structured two-dimensional histogram data for arrival vs duration buckets."""

    NORMALIZATION_GLOBAL = "global"
    NORMALIZATION_COLUMN = "column"
    NORMALIZATION_BLEND = "blend"
    # Any visits per day below this threshold will be truncated to 0
    VISIT_MIN_THRESHOLD = 0.01

    def __init__(
        self,
        arrival_bucket_minutes: int = 30,
        duration_bucket_minutes: int = 30,
    ):
        self.arrival_bucket_minutes = arrival_bucket_minutes
        self.duration_bucket_minutes = duration_bucket_minutes
        self.raw_values = {}
        self.day_count = None
        self.arrival_labels = []
        self.duration_labels = []
        self.normalized_values = {}

    def fetch_raw_data(
        self,
        ttdb: sqlite3.Connection,
        start_date: str | None = None,
        end_date: str | None = None,
        days_of_week: str | None = None,
        arrival_bucket_minutes: int = 30,
        duration_bucket_minutes: int = 30,
        min_arrival_threshold: str = "06:00",
        max_duration_threshold: str | None = None,
    ):
        """Load data from the database:
        raw_values
        day_count
        arrival_labels  (these will be .tidy - e.g. " 9:30" not "09:30" )
        duration_labels (ditto)
        """

        arrival_minutes_expr = _minutes_expr("V.time_in")
        duration_minutes_expr = _duration_minutes_expr()

        day_filter_clause = self._build_day_filter_clause(
            start_date=start_date, end_date=end_date, days_of_week=days_of_week
        )
        threshold_clause = self._build_threshold_clause(
            min_arrival_threshold=min_arrival_threshold,
            max_duration_threshold=max_duration_threshold,
        )
        base_cte = self._build_filtered_visits_cte(
            day_filter_clause=day_filter_clause,
            threshold_clause=threshold_clause,
            arrival_minutes_expr=arrival_minutes_expr,
            duration_minutes_expr=duration_minutes_expr,
        )

        day_count = self._fetch_distinct_day_count(ttdb, base_cte)
        bucket_rows = self._fetch_bucket_rows(
            ttdb,
            base_cte,
            arrival_bucket_minutes=arrival_bucket_minutes,
            duration_bucket_minutes=duration_bucket_minutes,
        )

        buckets, arrival_range, duration_range = self._organize_bucket_rows(
            bucket_rows,
            arrival_bucket_minutes=arrival_bucket_minutes,
            duration_bucket_minutes=duration_bucket_minutes,
        )

        if not buckets:
            self.raw_values = {}
            self.day_count = 0
            return

        self.arrival_labels = self._build_arrival_labels(arrival_range)
        self.duration_labels = self._build_duration_labels(duration_range)

        raw_values = self._build_raw_matrix(
            arrival_range=arrival_range,
            duration_range=duration_range,
            arrival_labels=self.arrival_labels,
            duration_labels=self.duration_labels,
            buckets=buckets,
        )
        self.raw_values = self._average_by_day(raw_values, day_count)
        self.raw_values = self._truncate_low_values(self.raw_values, day_count)
        self.day_count = day_count

    def _build_day_filter_clause(
        self,
        start_date: str | None,
        end_date: str | None,
        days_of_week: str | None,
    ) -> str:
        day_filter_items = _build_day_filter_items(
            start_date=start_date, end_date=end_date, days_of_week=days_of_week
        )
        return " AND ".join(day_filter_items) if day_filter_items else "1 = 1"

    def _build_threshold_clause(
        self,
        min_arrival_threshold: str | None,
        max_duration_threshold: str | None,
    ) -> str:
        arrival_threshold_minutes = (
            VTime(min_arrival_threshold).num if min_arrival_threshold else None
        )
        max_duration_minutes = (
            VTime(max_duration_threshold, allow_large=True).num
            if max_duration_threshold
            else None
        )

        threshold_filters: list[str] = []
        if arrival_threshold_minutes is not None:
            threshold_filters.append(
                f"(arrival_minutes >= {int(arrival_threshold_minutes)})"
            )
        if max_duration_minutes is not None:
            threshold_filters.append(
                f"(duration_minutes <= {int(max_duration_minutes)})"
            )
        return " AND ".join(threshold_filters) if threshold_filters else "1 = 1"

    def _build_filtered_visits_cte(
        self,
        day_filter_clause: str,
        threshold_clause: str,
        arrival_minutes_expr: str,
        duration_minutes_expr: str,
    ) -> str:
        return f"""
        WITH filtered_visits AS (
        SELECT
            D.date AS visit_date,
            {arrival_minutes_expr} AS arrival_minutes,
            {duration_minutes_expr} AS duration_minutes
        FROM
            DAY D
        JOIN
            VISIT V ON D.id = V.day_id
        WHERE {day_filter_clause}
            AND V.time_out IS NOT NULL
            AND V.time_out != ''
            AND {arrival_minutes_expr} IS NOT NULL
            AND {duration_minutes_expr} IS NOT NULL
            AND {threshold_clause}
    )
        """

    def _fetch_distinct_day_count(self, ttdb: sqlite3.Connection, base_cte: str) -> int:
        day_count_query = (
            base_cte
            + "SELECT COUNT(DISTINCT visit_date) AS day_count FROM filtered_visits;"
        )
        day_rows = db.db_fetch(ttdb, day_count_query, ["day_count"])
        day_count = day_rows[0].day_count if day_rows else 0
        if day_count is None:
            return 0
        if not isinstance(day_count, int):
            return int(day_count)
        return day_count

    def _fetch_bucket_rows(
        self,
        ttdb: sqlite3.Connection,
        base_cte: str,
        arrival_bucket_minutes: int,
        duration_bucket_minutes: int,
    ):
        bucket_query = (
            base_cte + "SELECT\n"
            f"    arrival_minutes - (arrival_minutes % {arrival_bucket_minutes}) AS arrival_bucket,\n"
            f"    duration_minutes - (duration_minutes % {duration_bucket_minutes}) AS duration_bucket,\n"
            "    COUNT(*) AS bucket_count\n"
            "FROM filtered_visits\n"
            "WHERE arrival_minutes IS NOT NULL AND duration_minutes IS NOT NULL\n"
            "GROUP BY arrival_bucket, duration_bucket\n"
            "ORDER BY arrival_bucket, duration_bucket;\n"
        )
        return db.db_fetch(
            ttdb,
            bucket_query,
            ["arrival_bucket", "duration_bucket", "bucket_count"],
        )

    def _organize_bucket_rows(
        self,
        bucket_rows,
        arrival_bucket_minutes: int,
        duration_bucket_minutes: int,
    ) -> tuple[dict[int, dict[int, int]], list[int], list[int]]:
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

        arrival_range = self._expand_arrival_range(
            arrival_buckets=arrival_buckets,
            bucket_minutes=arrival_bucket_minutes,
        )
        duration_range = self._expand_duration_range(
            duration_buckets=duration_buckets,
            bucket_minutes=duration_bucket_minutes,
        )

        return buckets, arrival_range, duration_range

    def _expand_arrival_range(
        self, arrival_buckets: set[int], bucket_minutes: int
    ) -> list[int]:
        arrival_range = sorted(arrival_buckets)
        if not arrival_range:
            return arrival_range
        start_arrival = arrival_range[0]
        end_arrival = arrival_range[-1]
        return list(
            range(start_arrival, end_arrival + bucket_minutes, bucket_minutes)
        )

    def _expand_duration_range(
        self, duration_buckets: set[int], bucket_minutes: int
    ) -> list[int]:
        duration_range = sorted(duration_buckets)
        if not duration_range:
            return duration_range
        end_duration = duration_range[-1]
        return list(range(0, end_duration + bucket_minutes, bucket_minutes))

    def _build_arrival_labels(self, arrival_range: list[int]) -> list[str]:
        labels: list[str] = []
        for minute in arrival_range:
            label = bucket_label(minute)
            if label is None:
                label = (
                    VTime(minute, allow_large=True).tidy if minute is not None else ""
                )
            labels.append(label or VTime(minute).tidy)
        return labels

    def _build_duration_labels(self, duration_range: list[int]) -> list[str]:
        labels: list[str] = []
        for minute in duration_range:
            label = duration_bucket_label(minute)
            labels.append(label or VTime(minute).tidy)
        return labels

    def _build_raw_matrix(
        self,
        arrival_range: list[int],
        duration_range: list[int],
        arrival_labels: list[str],
        duration_labels: list[str],
        buckets: dict[int, dict[int, int]],
    ) -> dict[str, dict[str, float]]:
        raw_values: dict[str, dict[str, float]] = {}

        for arrival_minute, arrival_label in zip(arrival_range, arrival_labels):
            source = buckets.get(arrival_minute, {})
            raw_row: dict[str, float] = {}
            for duration_minute, duration_label in zip(duration_range, duration_labels):
                raw_row[duration_label] = float(source.get(duration_minute, 0))
            raw_values[arrival_label] = raw_row

        return raw_values

    def _average_by_day(
        self, raw_values: dict[str, dict[str, float]], day_count: int
    ) -> dict[str, dict[str, float]]:
        if not day_count:
            return raw_values
        for raw_row in raw_values.values():
            for duration_label, value in raw_row.items():
                raw_row[duration_label] = value / day_count
        return raw_values

    def _truncate_low_values(
        self, raw_values: dict[str, dict[str, float]], day_count: int
    ) -> dict[str, dict[str, float]]:
        """Truncate any row values (visits/day) to 0 that
        are below a minimum threshold.
        """
        if not day_count:
            return raw_values
        for raw_row in raw_values.values():
            for duration_label, value in raw_row.items():
                if raw_row[duration_label] < self.VISIT_MIN_THRESHOLD:
                    raw_row[duration_label] = 0
        return raw_values

    def _normalize_column(self) -> dict[str, dict[str, float]]:
        """Returns normalized from raw using 'column' method,
        i.e., normalizes the data from each column independently.
        """

        normalized = {}

        for col, inner in self.raw_values.items():
            # find max for this column
            col_max = max(inner.values(), default=0.0)

            if col_max == 0:
                # if all zero, make entire column zeros
                normalized[col] = {row: 0.0 for row in inner}
            else:
                # divide each value by column max
                normalized[col] = {row: val / col_max for row, val in inner.items()}
        return normalized

    def _normalize_global(self) -> dict[str, dict[str, float]] | None:
        """Returns normalized from raw using 'global' method"""

        # 1. find the global max value across all nested dicts
        max_val = max(v for inner in self.raw_values.values() for v in inner.values())
        if not max_val:
            return None

        # 2. divide each value by the global max
        normalized = {
            outer_k: {inner_k: v / max_val for inner_k, v in inner.items()}
            for outer_k, inner in self.raw_values.items()
        }
        return normalized

    def _normalize_blend(self) -> dict[str, dict[str, float]]:
        """Return normalized data using the 'blend' method,
        i.e. the average of global and column normalizations.
        """

        global_matrix = self._normalize_global()
        column_matrix = self._normalize_column()

        blended_matrix = {}
        for arrival_label in self.arrival_labels:
            column_row = column_matrix.get(arrival_label, {})
            global_row = global_matrix.get(arrival_label, {})
            blended_row: dict[str, float] = {}
            for duration_label in self.duration_labels:
                column_val = column_row.get(duration_label, 0.0)
                global_val = global_row.get(duration_label, 0.0)
                blended_row[duration_label] = (column_val + global_val) / 2.0
            blended_matrix[arrival_label] = blended_row

        return blended_matrix

    def normalize(self, normalization_mode: str):
        """Sets .normalized_values in matrix according to normalization_mode.

        normalization_mode is 'column', 'global', or 'blend'.
        """

        # duration_labels = list(self.duration_labels)[::-1]
        # per_column_lookup = self.normalized_values

        # Choose the normalization table based on the requested mode.
        if normalization_mode == self.NORMALIZATION_COLUMN:
            self.normalized_values = self._normalize_column()
        elif normalization_mode == self.NORMALIZATION_GLOBAL:
            self.normalized_values = self._normalize_global()
        elif normalization_mode == self.NORMALIZATION_BLEND:
            self.normalized_values = self._normalize_blend()
        else:
            cc.error_out(f"Unrecognized normalization mode '{normalization_mode}'")


def bucket_label(bucket_minutes: int | None) -> str | None:
    """Return tidy label text for a bucket start in minutes.

    ``VTime`` instances expose several string helpers; prefer ``tidy`` when
    available so labels match the rest of the web UI, otherwise fall back to the
    default ``str`` representation.
    """
    return VTime(bucket_minutes).tidy


def duration_bucket_label(
    bucket_minutes: int | None
) -> str | None:
    """Return label like '00:00' for the start of a duration bucket."""

    # if bucket_minutes is None:
    #     return None
    return VTime(bucket_minutes).tidy


def time_histogram_data(
    ttdb: sqlite3.Connection,
    query_column: str,
    start_date: str = None,
    end_date: str = None,
    days_of_week: str = None,
    category_minutes: int = 30,
) -> HistogramResult:
    """Return averaged histogram data for the requested time column."""

    # Accept only known columns so SQL fragments remain safe.
    time_column_lower = query_column.lower()
    if time_column_lower not in {"time_in", "time_out", "duration"}:
        raise ValueError(f"Bad value for query column, '{query_column}' ")

    minutes_column_map = {
        "time_in": _minutes_expr("V.time_in"),
        "time_out": _minutes_expr("V.time_out"),
        "duration": "V.duration",
    }
    minutes_column = minutes_column_map[time_column_lower]

    orgsite_filter =  1  # FIXME: default fallback

    day_filter_items = _build_day_filter_items(
        orgsite_filter, start_date, end_date, days_of_week
    )

    # Filter rows where minutes are present; durations also require a time_out.
    filter_items: list[str] = [f"({minutes_column}) IS NOT NULL"] + day_filter_items
    if time_column_lower == "duration":
        filter_items.append("V.time_out IS NOT NULL")
        filter_items.append("V.time_out <> ''")
    filter_clause = " AND ".join(filter_items) if filter_items else "1 = 1"
    day_filter_clause = " AND ".join(day_filter_items) if day_filter_items else "1 = 1"

    if time_column_lower == "duration":
        start_time, end_time = ("00:00", "12:00")
    else:
        start_time, end_time = ("07:00", "22:00")

    # Common table expression keeps the expensive filtering reusable.
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
    # Average counts per day, so capture the number of distinct days in scope.
    day_rows = db.db_fetch(ttdb, day_count_query, ["day_count"])
    day_count = day_rows[0].day_count if day_rows else 0
    if day_count is None:
        day_count = 0
    elif not isinstance(day_count, int):
        day_count = int(day_count)

    bucket_query = (
        base_cte + "SELECT\n"
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
        # Base label range defaults to operating hours when possible.
        start_minutes = (
            VTime(start_time).num if start_time else min(bucket_counts.keys())
        )
        end_minutes = VTime(end_time).num if end_time else max(bucket_counts.keys())
        start_bucket = (start_minutes // category_minutes) * category_minutes
        end_bucket = (end_minutes // category_minutes) * category_minutes
        categories_by_minute: dict[int, int] = {
            minute: 0
            for minute in range(
                start_bucket, end_bucket + category_minutes, category_minutes
            )
        }
        have_unders = have_overs = False
        for bucket_start, count in bucket_counts.items():
            # Buckets outside the target window are rolled into the first/last bin
            # so the chart still reflects their impact.
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
            # Divide by day_count (defaulting to 1) to get per-day averages.
            key: (value / (day_count or 1))
            for key, value in sorted(categories_str.items())
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
    day_filter_clause = " AND ".join(day_filter_items) if day_filter_items else "1 = 1"

    day_count_query = f"""
        SELECT COUNT(DISTINCT D.DATE) AS day_count
        FROM DAY D
        JOIN BLOCK B ON B.day_id = D.id
        WHERE {filter_clause}
    """
    # Day count is needed later to normalize averages when data is sparse.
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

    # Fullness reports always focus on business hours (07:00-22:00 local time).
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
        # Add out-of-range samples to the nearest visible bucket so totals stay balanced.
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
        # Prefix '-' or '+' markers so downstream renderers know values were
        # aggregated from buckets outside the visible window.
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


__all__ = [
    "HistogramResult",
    "ArrivalDepartureMatrix",
    "bucket_label",
    "duration_bucket_label",
    "fullness_histogram_data",
    "time_histogram_data",
]
