"""Tests for KPI definitions (denominators, negative delays) and the statistics helpers."""
from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from flightrel import clean, kpi
from flightrel.stats import add_rate, wilson_interval
from conftest import row, write_csv


@pytest.fixture()
def con(tmp_path, cfg):
    """Eight hand-built 2015 flights covering every outcome and boundary delay."""
    rows = [
        row(OP_CARRIER_FL_NUM="1", DEP_DELAY="0.0", DEP_TIME="800.0", ARR_DELAY="14.0", ARR_TIME="1144.0"),   # on time (14)
        row(OP_CARRIER_FL_NUM="2", DEP_DELAY="0.0", DEP_TIME="800.0", ARR_DELAY="15.0", ARR_TIME="1145.0"),   # late (15 is late)
        row(OP_CARRIER_FL_NUM="3", DEP_DELAY="-10.0", DEP_TIME="750.0", ARR_DELAY="-40.0", ARR_TIME="1050.0"),  # early
        row(OP_CARRIER_FL_NUM="4", DEP_DELAY="20.0", DEP_TIME="820.0", ARR_DELAY="5.0", ARR_TIME="1135.0"),    # late dep, on-time arr
        row(OP_CARRIER_FL_NUM="5", DEP_DELAY="30.0", DEP_TIME="830.0", ARR_DELAY="45.0", ARR_TIME="1215.0"),   # late both
        row(OP_CARRIER_FL_NUM="6", CANCELLED="1.0", CANCELLATION_CODE="B", DEP_TIME="", DEP_DELAY="", TAXI_OUT="",
            WHEELS_OFF="", WHEELS_ON="", TAXI_IN="", ARR_TIME="", ARR_DELAY="", ACTUAL_ELAPSED_TIME="", AIR_TIME=""),
        row(OP_CARRIER_FL_NUM="7", DIVERTED="1.0", ARR_TIME="", ARR_DELAY=""),
        row(OP_CARRIER_FL_NUM="8", FL_DATE="2015-07-04", DEP_DELAY="0.0", DEP_TIME="800.0", ARR_DELAY="0.0", ARR_TIME="1130.0"),  # July
    ]
    c = clean.connect(cfg)
    out = tmp_path / "flights"
    csv_path = write_csv(tmp_path / "2015.csv", rows)
    clean.clean_year(c, csv_path, 2015, out / "flights_2015.parquet", cfg)
    kpi.connect_views(c, out, n_years=1)
    return c


def test_denominators_and_late_threshold(con):
    r = kpi.run(con, "kpi_by", scope="all", dims="year").iloc[0]
    assert r["scheduled_flights"] == 8
    assert r["cancelled_n"] == 1 and r["diverted_n"] == 1
    assert r["completed_n"] == 6                 # cancelled and diverted excluded from arrival KPIs
    assert r["arr_late_n"] == 2                  # 15 and 45; 14 is on time
    assert r["departed_n"] == 7                  # everything except the cancelled flight
    assert r["dep_late_n"] == 2                  # 20 and 30


def test_negative_delays_are_in_the_quantiles(con):
    r = kpi.run(con, "kpi_by", scope="all", dims="year").iloc[0]
    # completed arrival delays: 14, 15, -40, 5, 45, 0 -> sorted -40, 0, 5, 14, 15, 45 -> median 9.5
    assert r["arr_p50"] == pytest.approx(9.5)


def test_matched_month_scope_drops_july(con):
    r = kpi.run(con, "kpi_by", scope="matched_months", dims="year").iloc[0]
    assert r["scheduled_flights"] == 7


def test_departure_late_outcomes(con):
    r = kpi.run(con, "dep_late_outcomes", scope="all").iloc[0]
    assert r["dep_late_flights"] == 2 and r["arrived_on_time_n"] == 1


def test_wilson_interval_matches_known_value():
    lo, hi = wilson_interval(10, 100)
    assert (lo, hi) == (pytest.approx(0.0552, abs=1e-3), pytest.approx(0.1744, abs=1e-3))
    lo0, hi0 = wilson_interval(0, 50)
    assert lo0 == pytest.approx(0.0, abs=1e-12) and hi0 > 0


def test_add_rate_columns():
    import pandas as pd
    df = add_rate(pd.DataFrame({"k": [5, 50], "n": [10, 100]}), "k", "n", "r")
    assert df["r"].tolist() == [0.5, 0.5]
    assert df.loc[1, "r_hi"] - df.loc[1, "r_lo"] < df.loc[0, "r_hi"] - df.loc[0, "r_lo"]
