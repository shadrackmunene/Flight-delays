"""Tests for the persistence logic used to identify repeatedly unreliable airports and routes."""
from __future__ import annotations

import pandas as pd
import pytest
from scipy import stats

from flightrel import descriptive


def _cells(rates_by_entity: dict[str, list[float]], n: int = 1000) -> pd.DataFrame:
    rows = []
    for ent, rates in rates_by_entity.items():
        for i, r in enumerate(rates):
            rows.append({"entity": ent, "year": 2009 + i, "completed_n": n, "arr_late_n": round(r * n)})
    return pd.DataFrame(rows)


def test_persistent_entity_is_ranked_first_and_counted():
    years = 10
    # Ten entities: 'BAD' is always the worst; the rest have flat, distinct rates.
    data = {f"E{i}": [0.10 + 0.01 * i] * years for i in range(9)}
    data["BAD"] = [0.60] * years
    g = descriptive.persistence(_cells(data), quantile=0.90).set_index("entity")
    assert g.loc["BAD", "years_poor"] == years
    assert g.loc["E0", "years_poor"] == 0
    assert g.index[0] == "BAD"


def test_p_by_chance_matches_binomial_tail():
    data = {f"E{i}": [0.10 + 0.01 * i] * 10 for i in range(9)}
    data["BAD"] = [0.60] * 10
    g = descriptive.persistence(_cells(data), quantile=0.90).set_index("entity")
    assert g.loc["BAD", "p_by_chance"] == pytest.approx(stats.binom.sf(9, 10, 0.10))


def test_entities_with_too_few_observed_years_are_dropped():
    data = {"SHORT": [0.9] * (descriptive.MIN_YEARS_OBSERVED - 1)}
    data.update({f"E{i}": [0.1 + 0.01 * i] * 10 for i in range(5)})
    g = descriptive.persistence(_cells(data), quantile=0.90)
    assert "SHORT" not in set(g["entity"])
