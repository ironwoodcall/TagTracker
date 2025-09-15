#!/usr/bin/env python3
"""Historical wrapper for the web estimator.

This module preserves imports of the current Estimator and Estimator_old for
legacy references. It is not a literal code snapshot, but provides a stable
import path in case external tooling refers to 'web_estimator_old'.
"""

from web_estimator import Estimator, Estimator_old  # re-export

__all__ = ["Estimator", "Estimator_old"]

