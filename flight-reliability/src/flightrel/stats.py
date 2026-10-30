"""Small statistical helpers shared by the descriptive and inferential stages."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def wilson_interval(k, n, conf: float = 0.95):
    """Wilson score interval for a binomial proportion; vectorised, returns (low, high)."""
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    z = stats.norm.ppf(0.5 + conf / 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = k / n
        denom = 1 + z**2 / n
        centre = (p + z**2 / (2 * n)) / denom
        half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return centre - half, centre + half


def add_rate(df: pd.DataFrame, k: str, n: str, name: str, conf: float = 0.95) -> pd.DataFrame:
    """Add ``name``, ``name_lo`` and ``name_hi`` columns (rate and Wilson interval) for k out of n."""
    out = df.copy()
    out[name] = out[k] / out[n]
    out[f"{name}_lo"], out[f"{name}_hi"] = wilson_interval(out[k], out[n], conf)
    return out
