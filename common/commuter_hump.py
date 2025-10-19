#!/usr/bin/env python3
"""
commuter_hump.py
----------------

Estimate the proportion of "commuter" visits—those forming a secondary bump
around full workday durations—based on visit durations stored in minutes
in a SQLite database.

Methodology:
- Most visits follow a short-stay pattern that declines smoothly as durations grow.
- A smaller secondary "hump" around 7–9 hours represents all-day commuters.
- We fit a smooth baseline model (log-normal) to short visits (<6 h),
  then measure how many observed visits exceed that baseline in the 6–10 h range.

Design:
- `load_data()` loads and filters visit durations from VISIT × DAY tables.
- `fit()` performs the statistical analysis, populating all computed results
  as instance properties and returning `self` (for chaining).
- `run()` is a convenience method that executes both.

Outputs include:
  - total and commuter visit counts
  - commuter fraction of all visits
  - per-day means
  - per-duration-bin breakdown

Dependencies: numpy, scipy, sqlite3 (standard library)
"""

import sys
import sqlite3
import numpy as np
from scipy import stats


class CommuterHumpAnalyzer:
    """
    Analyze visit durations to estimate the commuter “hump” proportion.

    Attributes populated after calling `fit()` or `run()`:
        Required at start of analysis
            db_path: SQLite database path queried for visits.
            start_date, end_date: Inclusive ISO dates bounding the analysis window.
            weekdays: Iterable of weekday numbers (1=Mon … 7=Sun) included in the sample.
        Results of analysis:
            durations: NumPy array of visit durations (hours) extracted from the DB.
            day_count: Number of distinct calendar days represented in the sample.
            total_visits: Total visit observations analyzed.
            commuter_count: Estimated commuter (hump) visit count.
            commuter_fraction: Commuter visits as a fraction of total (0–1).
            mean_total_per_day: Average total visits per day across the window.
            mean_commuter_per_day: Average commuter visits per day.
            mean_baseline_per_day: Average non-commuter visits per day.
        Uncertainty diagnostics:
            commuter_fraction_se: Standard error of the commuter fraction.
            commuter_count_se: Standard error of the commuter count.
            mean_commuter_per_day_se: Standard error of commuter visits per day.
            commuter_fraction_ci: 95% Wilson confidence interval (tuple) for the commuter fraction.
            commuter_count_ci: Wilson interval mapped to absolute commuter counts.
            mean_commuter_per_day_ci: Wilson interval mapped to per-day commuter means.
        Reporting helpers:
            bucket_table: List of per-duration-bin summaries used for reporting.
        Status:
            error: Optional message describing a loading or fitting problem (None on success).
    """

    def __init__(self, db_path, start_date, end_date, weekdays):
        self.db_path = db_path
        self.start_date = start_date
        self.end_date = end_date
        self.weekdays = weekdays

        # --- Data inputs
        self.durations = None  # array of durations (hours)
        self.day_count = 0  # distinct days analyzed
        self.error = None  # message populated when load/fit fails

        # --- Results (populated after .fit())
        self.total_visits = None
        self.commuter_count = None
        self.commuter_fraction = None
        self.mean_total_per_day = None
        self.mean_commuter_per_day = None
        self.mean_baseline_per_day = None
        self.commuter_fraction_ci = None
        self.commuter_count_ci = None
        self.mean_commuter_per_day_ci = None
        self.commuter_fraction_se = None
        self.commuter_count_se = None
        self.mean_commuter_per_day_se = None
        self.bucket_table = None

    # ------------------------------------------------------------------
    def load_data(self):
        """Load visit durations (in hours) for the selected date range and weekdays."""
        self.error = None
        query = f"""
            SELECT v.duration, d.date
            FROM VISIT v
            JOIN DAY d ON v.day_id = d.id
            WHERE d.date BETWEEN ? AND ?
              AND d.weekday IN ({",".join("?" * len(self.weekdays))})
              AND v.duration IS NOT NULL
              AND v.duration > 0
        """
        params = [self.start_date, self.end_date, *self.weekdays]

        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(query, params)
                rows = cur.fetchall()
        except sqlite3.Error as exc:
            self.error = f"Database error while loading visit data: {exc}"
            self.durations = None
            self.day_count = 0
            return False

        if not rows:
            self.error = "No visit data found for the given date range and weekdays."
            self.durations = None
            self.day_count = 0
            return False

        durations_min = [r[0] for r in rows]
        self.durations = np.array(durations_min, dtype=float) / 60.0  # → hours
        self.day_count = len(set(r[1] for r in rows))

        if self.day_count == 0:
            self.error = "No distinct days found for the selected visit data."
            self.durations = None
            return False

        return True

    # ------------------------------------------------------------------
    def fit(self, fit_max=6.0, hump_min=6.0, hump_max=10.0, bin_width=0.5):
        """
        Fit a baseline log-normal distribution to short-stay durations,
        estimate the commuter 'hump' excess, and populate result properties.

        Returns
        -------
        self : CommuterHumpAnalyzer
            The analyzer instance, with computed attributes:
                total_visits
                commuter_count
                commuter_fraction
                mean_total_per_day
                mean_commuter_per_day
                mean_baseline_per_day
                bucket_table
        """
        # Reset outputs to avoid stale values when re-running fit.
        self.total_visits = None
        self.commuter_count = None
        self.commuter_fraction = None
        self.mean_total_per_day = None
        self.mean_commuter_per_day = None
        self.mean_baseline_per_day = None
        self.commuter_fraction_se = None
        self.commuter_count_se = None
        self.mean_commuter_per_day_se = None
        self.commuter_fraction_ci = None
        self.commuter_count_ci = None
        self.mean_commuter_per_day_ci = None
        self.bucket_table = None
        self.error = None

        if self.durations is None:
            if not self.load_data():
                return self

        if self.error:
            return self

        durations = self.durations
        total = len(durations)
        if total == 0 or self.day_count == 0:
            if not self.error:
                self.error = "No visit durations available for analysis."
            return self

        # --- Histogram
        bins = np.arange(0, 13 + bin_width, bin_width)
        counts, edges = np.histogram(durations, bins=bins)
        centers = (edges[:-1] + edges[1:]) / 2

        # --- Fit log-normal baseline
        fit_mask = (durations > 0.25) & (durations < fit_max)
        fit_data = durations[fit_mask]
        if fit_data.size == 0:
            self.error = (
                "Insufficient short-stay data to fit the baseline distribution."
            )
            return self
        try:
            params = stats.lognorm.fit(fit_data, floc=0)
        except ValueError as exc:
            self.error = f"Failed to fit baseline distribution: {exc}"
            return self
        expected_pdf = stats.lognorm.pdf(centers, *params)
        pdf_sum = expected_pdf.sum()
        if pdf_sum == 0:
            self.error = "Baseline model produced zero total density."
            return self
        expected_counts = expected_pdf / pdf_sum * total

        # --- Commuter excess
        excess = np.clip(counts - expected_counts, 0, None)
        commuter_mask = (centers >= hump_min) & (centers <= hump_max)
        commuter_counts = np.where(commuter_mask, excess, 0)
        baseline_counts = counts - commuter_counts

        # --- Summary metrics
        self.total_visits = total
        self.commuter_count = commuter_counts.sum()
        self.commuter_fraction = self.commuter_count / total
        self.mean_total_per_day = total / self.day_count
        self.mean_commuter_per_day = self.commuter_count / self.day_count
        self.mean_baseline_per_day = (
            self.mean_total_per_day - self.mean_commuter_per_day
        )

        # --- Standard errors (commuter metrics)
        if total > 0:
            p = self.commuter_fraction
            fraction_se = np.sqrt(p * (1 - p) / total)
            self.commuter_fraction_se = fraction_se
            self.commuter_count_se = fraction_se * total
            if self.day_count > 0:
                self.mean_commuter_per_day_se = fraction_se * total / self.day_count
            else:
                self.mean_commuter_per_day_se = np.nan
        else:
            self.commuter_fraction_se = np.nan
            self.commuter_count_se = np.nan
            self.mean_commuter_per_day_se = np.nan

        # --- Confidence intervals (95%)
        if total > 0:
            alpha = 0.05
            z = stats.norm.ppf(1 - alpha / 2)
            p = self.commuter_fraction
            denom = 1 + (z**2 / total)
            center = (p + (z**2 / (2 * total))) / denom
            margin = (
                z * np.sqrt((p * (1 - p) / total) + (z**2 / (4 * total**2))) / denom
            )
            frac_low = max(0.0, center - margin)
            frac_high = min(1.0, center + margin)
            self.commuter_fraction_ci = (frac_low, frac_high)
            self.commuter_count_ci = (frac_low * total, frac_high * total)
            if self.day_count > 0:
                self.mean_commuter_per_day_ci = (
                    self.commuter_count_ci[0] / self.day_count,
                    self.commuter_count_ci[1] / self.day_count,
                )
            else:
                self.mean_commuter_per_day_ci = (np.nan, np.nan)
        else:
            self.commuter_fraction_ci = (np.nan, np.nan)
            self.commuter_count_ci = (np.nan, np.nan)
            self.mean_commuter_per_day_ci = (np.nan, np.nan)

        # --- Per-bin breakdown
        self.bucket_table = [
            {
                "range": f"{low:.1f}–{high:.1f}",
                "commuter_mean": c / self.day_count,
                "baseline_mean": nc / self.day_count,
                "total_mean": tot / self.day_count,
            }
            for c, nc, tot, low, high in zip(
                commuter_counts, baseline_counts, counts, edges[:-1], edges[1:]
            )
        ]

        return self

    # ------------------------------------------------------------------
    def run(self):
        """Convenience: load data and fit model; returns self."""
        if not self.load_data():
            return self
        return self.fit()

    # ------------------------------------------------------------------
    def confidence_text(self, long_text=False, thresholds=None, method="blended"):
        """
        Collapse the commuter fraction uncertainty into a qualitative level.

        Parameters
        ----------
        long_text : bool, optional
            When True, return ``("very low", "low", "medium", "high", "very high")``.
            When False (default), return the abbreviations ``("VL", "L", "M", "H", "VH")``.
        thresholds : sequence of float, optional
            Policy-specific cut points (see ``method``). Defaults depend on ``method``.
        method : {"absolute", "relative", "blended"}, optional
            How to translate uncertainty into qualitative levels:

            - "absolute" compares the absolute standard error of the commuter fraction
              against the thresholds (default cut points: ``(0.08, 0.05, 0.03, 0.015)``).
            - "relative" gauges the Wilson half-width relative to the commuter fraction.
              The thresholds apply to the ratio of half-width to fraction
              (default cut points: ``(1.0, 0.6, 0.35, 0.2)``).
            - "blended" requires both a small absolute standard error and
              the commuter count meeting minimums for higher tiers.
              Thresholds are tuples of ``(fraction_se, min_commuter_count)`` for each level.
              Defaults: ``((0.08, 0), (0.05, 10), (0.03, 25), (0.02, 50))``.

        Returns
        -------
        str
            One of ``{"VL","L","M","H","VH"}`` or the full-text equivalents.
        """
        if method not in {"absolute", "relative", "blended"}:
            raise ValueError("method must be 'absolute', 'relative', or 'blended'.")

        se = self.commuter_fraction_se
        p = self.commuter_fraction
        if (
            se is None
            or np.isnan(se)
            or p is None
            or np.isnan(p)
            or self.total_visits in (None, 0)
        ):
            return "none" if long_text else "N"

        metric = None
        threshold_values = None

        if method == "absolute":
            if thresholds is None:
                thresholds = (0.08, 0.05, 0.03, 0.015)
            else:
                thresholds = tuple(thresholds)
                if len(thresholds) != 4:
                    raise ValueError(
                        "thresholds must contain four standard-error cut points."
                    )
                if any(thresholds[i] < thresholds[i + 1] for i in range(3)):
                    raise ValueError("thresholds must be in non-increasing order.")
            metric = se
            threshold_values = thresholds

        elif method == "relative":
            if thresholds is None:
                thresholds = (1.0, 0.6, 0.35, 0.2)
            else:
                thresholds = tuple(thresholds)
                if len(thresholds) != 4:
                    raise ValueError("thresholds must contain four ratio cut points.")
                if any(thresholds[i] < thresholds[i + 1] for i in range(3)):
                    raise ValueError("thresholds must be in non-increasing order.")
            # use Wilson interval half-width (if available) to keep bounds within [0,1]
            if self.commuter_fraction_ci:
                lower, upper = self.commuter_fraction_ci
                half_width = (upper - lower) / 2
            else:
                half_width = 1.96 * se  # fallback to normal approximation
            frac = max(p, 1e-6)
            metric = half_width / frac
            threshold_values = thresholds

        else:  # blended
            if thresholds is None:
                thresholds = ((0.08, 0), (0.05, 10), (0.03, 25), (0.02, 50))
            else:
                thresholds = tuple(thresholds)
                if len(thresholds) != 4:
                    raise ValueError("thresholds must contain four (se, count) tuples.")
                for t in thresholds:
                    if len(t) != 2:
                        raise ValueError(
                            "each blended threshold must be a (se, count) tuple."
                        )
            threshold_values = thresholds

        full_levels = ("very low", "low", "medium", "high", "very high")
        short_levels = ("VL", "L", "M", "H", "VH")

        if method == "blended":
            commuter_count = self.commuter_count or 0
            se_thresholds = [t[0] for t in threshold_values]
            count_thresholds = [t[1] for t in threshold_values]
            if se >= se_thresholds[0] or commuter_count < count_thresholds[0]:
                idx = 0
            elif se >= se_thresholds[1] or commuter_count < count_thresholds[1]:
                idx = 1
            elif se >= se_thresholds[2] or commuter_count < count_thresholds[2]:
                idx = 2
            elif se >= se_thresholds[3] or commuter_count < count_thresholds[3]:
                idx = 3
            else:
                idx = 4
        else:
            if metric is None or threshold_values is None:
                raise RuntimeError("confidence_text internal metric not set.")
            metric_value = metric
            tv = threshold_values
            if metric_value >= tv[0]:
                idx = 0
            elif metric_value >= tv[1]:
                idx = 1
            elif metric_value >= tv[2]:
                idx = 2
            elif metric_value >= tv[3]:
                idx = 3
            else:
                idx = 4

        return full_levels[idx] if long_text else short_levels[idx]

    def commuter_confidence_level(self, long_text=False, thresholds=None):
        """Backward-compatible wrapper for :meth:`confidence_text`."""
        return self.confidence_text(long_text=long_text, thresholds=thresholds)


# ----------------------------------------------------------------------
# Utility functions for displaying results
# ----------------------------------------------------------------------


def describe_days(weekdays):
    names = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
    return ",".join(names.get(d, str(d)) for d in sorted(weekdays))


def print_summary(analyzer, weekdays):
    """Display overall summary table."""
    print()
    descr = (
        f"Visit Summary ({analyzer.day_count} days analyzed: {describe_days(weekdays)})"
    )
    print(descr)
    print("=" * len(descr))
    header = f"{'Metric':<30} {'Count':>12} {'Per Day':>12} {'Proportion':>15}"
    print(header)
    print("-" * len(header))
    print(
        f"{'Baseline visits':<30} "
        f"{(analyzer.total_visits - analyzer.commuter_count):>12,.0f} "
        f"{analyzer.mean_baseline_per_day:>12.2f} "
        f"{100-analyzer.commuter_fraction*100:>14.2f}%"
    )
    print(
        f"{'Commuter visits':<30} "
        f"{analyzer.commuter_count:>12,.0f} "
        f"{analyzer.mean_commuter_per_day:>12.2f} "
        f"{analyzer.commuter_fraction*100:>14.2f}%"
    )
    print(
        f"{'Total visits':<30} "
        f"{analyzer.total_visits:>12,.0f} "
        f"{analyzer.mean_total_per_day:>12.2f} "
        f"{100:14.2f}%"
    )
    print("-" * len(header))
    fraction_se = analyzer.commuter_fraction_se
    if fraction_se is not None and not np.isnan(fraction_se):
        count_se = analyzer.commuter_count_se
        per_day_se = analyzer.mean_commuter_per_day_se
        print(
            f"{'Commuter Standard Error':<30} "
            f"{count_se:>12.2f} "
            f"{per_day_se:>12.3f} "
            f"{fraction_se*100:>14.2f}%"
        )
    for method in ["absolute", "relative", "blended"]:
        print(
            f"Confidence level ({method}): "
            f"{analyzer.confidence_text(long_text=True,method=method)}"
        )


def print_bucket_table(analyzer):
    """Display per-duration half-hour bucket means."""
    print()
    print("Mean Visits per Day by Duration Bucket (hours)")
    print("==============================================")
    header = f"{'Duration Range':<15} {'Baseline':>12} {'Commuter':>12} {'Total':>12}"
    print(header)
    print("-" * len(header))
    for row in analyzer.bucket_table:
        print(
            f"{row['range']:<15} "
            f"{row['baseline_mean']:>12.2f} "
            f"{row['commuter_mean']:>12.2f} "
            f"{row['total_mean']:>12.2f}"
        )
    print("-" * len(header))
    print("")


# ----------------------------------------------------------------------
def main():
    if len(sys.argv) < 5:
        print(
            "Usage: python commuter_hump.py <database> <start_date> <end_date> <weekday ...>\n"
            "Example: python commuter_hump.py data.db 2024-01-01 2024-12-31 1 2 3 4 5"
        )
        sys.exit(1)

    db_path, start_date, end_date = sys.argv[1:4]
    weekdays = [int(x) for x in sys.argv[4:]]

    analyzer = CommuterHumpAnalyzer(db_path, start_date, end_date, weekdays).run()
    if analyzer.error:
        print(f"Analysis error: {analyzer.error}", file=sys.stderr)
        return
    print_summary(analyzer, weekdays)
    # print_bucket_table(analyzer) # do not change


if __name__ == "__main__":
    main()
