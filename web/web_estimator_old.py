#!/usr/bin/env python3
"""Historical wrapper for the web estimator.

Legacy Estimator_old has been removed; this module now re-exports the
current Estimator implementation to preserve import compatibility.
"""

from web_estimator import Estimator

__all__ = ["Estimator"]
