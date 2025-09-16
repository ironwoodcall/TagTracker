#!/usr/bin/env python3
"""Core modeling helpers for web_estimator.

Contains minimal computation-only versions of SimpleModel and LRModel used by
the Estimator. Presentation (result_msg) is intentionally omitted.
"""
from __future__ import annotations

import math
import statistics
from typing import List, Optional, Tuple


# Model state constants (kept consistent with web_estimator)
INCOMPLETE = "incomplete"
READY = "ready"
OK = "ok"
ERROR = "error"


class SimpleModel:
    """Match similar days and compute trimmed summary statistics."""

    def __init__(self) -> None:
        self.raw_befores: Optional[List[int]] = None
        self.raw_afters: Optional[List[int]] = None
        self.raw_dates: List[str] = []
        self.match_tolerance: Optional[float] = None
        self.trim_tolerance: Optional[float] = None

        self.matched_afters: List[int] = []
        self.trimmed_afters: List[int] = []
        self.num_points: Optional[int] = None
        self.num_discarded: Optional[int] = None

        self.min: Optional[int] = None
        self.max: Optional[int] = None
        self.mean: Optional[int] = None
        self.median: Optional[int] = None

        self.error: str = ""
        self.state: str = INCOMPLETE

    def _discard_outliers(self) -> None:
        if len(self.matched_afters) <= 2:
            self.trimmed_afters = self.matched_afters
            self.num_discarded = (self.num_points or 0) - len(self.trimmed_afters)
            return
        mean = statistics.mean(self.matched_afters)
        std_dev = statistics.stdev(self.matched_afters)
        if std_dev == 0:
            self.trimmed_afters = self.matched_afters
            self.num_discarded = (self.num_points or 0) - len(self.trimmed_afters)
            return
        z = float(self.trim_tolerance or 0)
        self.trimmed_afters = [
            v for v in self.matched_afters if abs((v - mean) / std_dev) <= z
        ]
        self.num_discarded = (self.num_points or 0) - len(self.trimmed_afters)

    def create_model(
        self,
        dates: List[str],
        befores: List[int],
        afters: List[int],
        tolerance: float,
        z_threshold: float,
    ) -> None:
        if self.state == ERROR:
            return
        self.raw_dates = dates
        self.raw_befores = befores
        self.raw_afters = afters
        self.match_tolerance = tolerance
        self.trim_tolerance = z_threshold
        self.state = READY

    def guess(self, bikes_so_far: int) -> None:
        if self.state == ERROR:
            return
        if self.state not in [READY, OK]:
            self.state = ERROR
            self.error = "can not guess, model not in ready state."
            return
        self.matched_afters = []
        for i, before in enumerate(self.raw_befores or []):
            if abs(bikes_so_far - before) <= (self.match_tolerance or 0):
                self.matched_afters.append((self.raw_afters or [])[i])
        self.num_points = len(self.matched_afters)

        if not self.matched_afters:
            self.error = "no similar dates"
            self.state = ERROR
            return

        self._discard_outliers()
        if not self.trimmed_afters:
            self.trimmed_afters = self.matched_afters

        self.min = min(self.trimmed_afters)
        self.max = max(self.trimmed_afters)
        self.mean = int(statistics.mean(self.trimmed_afters))
        self.median = int(statistics.median(self.trimmed_afters))
        self.state = OK


class LRModel:
    """Least-squares linear regression y = a*x + b with basic stats."""

    def __init__(self) -> None:
        self.state: str = INCOMPLETE
        self.error: Optional[str] = None
        self.xy_data: Optional[List[Tuple[float, float]]] = None
        self.num_points: Optional[int] = None
        self.slope: Optional[float] = None
        self.intercept: Optional[float] = None
        self.correlation_coefficient: Optional[float] = None
        self.r_squared: Optional[float] = None
        self.further_bikes: Optional[int] = None

    def calculate_model(self, xy_data: List[Tuple[float, float]]) -> None:
        if self.state == ERROR:
            return
        self.xy_data = xy_data
        self.num_points = len(xy_data)
        if (self.num_points or 0) < 2:
            self.error = "not enough data points"
            self.state = ERROR
            return
        xs = [x for x, _ in xy_data]
        if all(x == 0 for x in xs):
            self.error = "all x values are 0"
            self.state = ERROR
            return
        sum_x = sum(xs)
        sum_y = sum(y for _, y in xy_data)
        sum_xy = sum(x * y for x, y in xy_data)
        sum_x2 = sum(x * x for x in xs)
        n = float(self.num_points)
        try:
            self.slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        except ZeroDivisionError:
            self.error = "DIV/0 in slope calculation."
            self.state = ERROR
            return
        mean_x = sum_x / n
        mean_y = sum_y / n
        self.intercept = mean_y - (self.slope or 0) * mean_x

        # Correlation coefficient (r) and R^2
        xdiff2 = sum((x - mean_x) ** 2 for x in xs)
        ydiff2 = sum((y - mean_y) ** 2 for _x, y in xy_data)
        diffprod = sum((x - mean_x) * (y - mean_y) for x, y in xy_data)
        try:
            r = diffprod / (math.sqrt(xdiff2) * math.sqrt(ydiff2))
            self.correlation_coefficient = r
            self.r_squared = r * r
        except ZeroDivisionError:
            self.correlation_coefficient = None
            self.r_squared = None

        self.state = READY

    def guess(self, x: float) -> None:
        if self.state == ERROR:
            return
        if self.state not in [READY, OK]:
            self.state = ERROR
            self.error = "model not ready, can not guess"
            return
        self.further_bikes = int(round((self.slope or 0) * x + (self.intercept or 0)))
        self.state = OK

