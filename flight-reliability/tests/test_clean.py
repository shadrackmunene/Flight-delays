"""Tests for the cleaning transformations and logical constraints."""
from __future__ import annotations

import pandas as pd
import pytest

from flightrel import clean
from flightrel.clean import BLOCKING_RULES, DQ_RULES
from conftest import HEADER, row


def test_no_rows_are_dropped(run_clean):
    rows = [row(), row(OP_CARRIER_FL_NUM="101"), row(FL_DATE="garbage", OP_CARRIER_FL_NUM="102"),
            row(CANCELLED="7", OP_CARRIER_FL_NUM="103")]
    df = run_clean(rows)
    assert len(df) == len(rows)
    assert df["row_id"].is_unique


def test_valid_flight_has_no_error_flags(run_clean):
    df = run_clean([row()])
    r = df.iloc[0]
    assert r["outcome"] == "completed"
    assert bool(r["analysis_include"])
    flagged = [c for c in DQ_RULES if r[c]]
    assert flagged == []


def test_negative_delays_preserved(run_clean):
    r = run_clean([row(DEP_DELAY="-12.0", DEP_TIME="748.0", ARR_DELAY="-30.0", ARR_TIME="1100.0")]).iloc[0]
    assert r["dep_delay"] == -12.0
    assert r["arr_delay"] == -30.0
    assert not r["dq_extreme_dep_delay"]


def test_midnight_2400_is_zero_and_flagged_as_info(run_clean):
    r = run_clean([row(CRS_DEP_TIME="2400", DEP_TIME="0.0", DEP_DELAY="0.0")]).iloc[0]
    assert r["crs_dep_min"] == 0
    assert r["crs_dep_time"] == 0  # 2400 normalised to 0000
    assert r["sched_dep_hour"] == 0
    assert r["dq_has_time_2400"]
    assert not r["dq_invalid_crs_dep_time"]
    assert not r["dq_dep_time_inconsistent"]


@pytest.mark.parametrize("bad", ["2575", "1260", "2501", "-100", "abc", "1234.5"])
def test_invalid_hhmm_becomes_null_and_flagged(run_clean, bad):
    r = run_clean([row(DEP_TIME=bad)]).iloc[0]
    assert pd.isna(r["dep_time"])
    assert r["dq_invalid_dep_time"]
    assert bool(r["analysis_include"])  # a bad actual time does not block the record


def test_invalid_scheduled_departure_blocks_analysis(run_clean):
    r = run_clean([row(CRS_DEP_TIME="2575")]).iloc[0]
    assert r["dq_invalid_crs_dep_time"]
    assert not r["analysis_include"]


def test_overnight_flight_dates_and_timestamps(run_clean):
    # Scheduled 23:30, 120 minute flight, departs 90 minutes late at 01:00 the next day.
    r = run_clean([row(CRS_DEP_TIME="2330", DEP_TIME="100.0", DEP_DELAY="90.0", CRS_ELAPSED_TIME="120.0",
                       CRS_ARR_TIME="130", ARR_TIME="300.0", ARR_DELAY="90.0")]).iloc[0]
    assert r["sched_crosses_midnight"]
    assert r["sched_dep_ts"] == pd.Timestamp("2015-03-10 23:30")
    assert r["actual_dep_ts"] == pd.Timestamp("2015-03-11 01:00")
    assert not r["dq_dep_time_inconsistent"]
    assert not r["dq_arr_time_inconsistent"]


def test_early_departure_before_midnight_wraps_consistently(run_clean):
    # Scheduled 00:10, left 20 minutes early (23:50 the previous clock day).
    r = run_clean([row(CRS_DEP_TIME="10", DEP_TIME="2350.0", DEP_DELAY="-20.0")]).iloc[0]
    assert not r["dq_dep_time_inconsistent"]
    assert r["actual_dep_ts"] == pd.Timestamp("2015-03-09 23:50")


def test_dep_time_inconsistent_with_delay_is_flagged(run_clean):
    r = run_clean([row(DEP_TIME="900.0", DEP_DELAY="5.0")]).iloc[0]
    assert r["dq_dep_time_inconsistent"]


def test_cancelled_flight_outcome_and_expected_missingness(run_clean):
    r = run_clean([row(CANCELLED="1.0", CANCELLATION_CODE="B", DEP_TIME="", DEP_DELAY="", TAXI_OUT="",
                       WHEELS_OFF="", WHEELS_ON="", TAXI_IN="", ARR_TIME="", ARR_DELAY="",
                       ACTUAL_ELAPSED_TIME="", AIR_TIME="")]).iloc[0]
    assert r["outcome"] == "cancelled"
    assert r["cancelled"] == 1 and r["diverted"] == 0
    assert not r["dq_completed_missing_arr_delay"]  # not applicable to cancelled flights
    assert not r["dq_cancelled_no_code"]
    assert bool(r["analysis_include"])


def test_cancelled_with_arrival_and_without_code_flagged(run_clean):
    r = run_clean([row(CANCELLED="1.0")]).iloc[0]  # keeps ARR_DELAY from BASE, no code
    assert r["dq_cancelled_has_arrival"]
    assert r["dq_cancelled_no_code"]


def test_cancelled_and_diverted_is_inconsistent_and_excluded(run_clean):
    r = run_clean([row(CANCELLED="1.0", DIVERTED="1.0", CANCELLATION_CODE="A")]).iloc[0]
    assert r["outcome"] == "inconsistent"
    assert r["dq_cancelled_and_diverted"]
    assert not r["analysis_include"]


def test_diverted_flight_is_separate_outcome(run_clean):
    r = run_clean([row(DIVERTED="1.0", ARR_TIME="", ARR_DELAY="")]).iloc[0]
    assert r["outcome"] == "diverted"
    assert not r["dq_completed_missing_arr_delay"]


def test_completed_flight_missing_arr_delay_flagged_but_kept(run_clean):
    r = run_clean([row(ARR_DELAY="", ARR_TIME="")]).iloc[0]
    assert r["dq_completed_missing_arr_delay"]
    assert bool(r["analysis_include"])


@pytest.mark.parametrize("flag", ["2", "", "x", "-1"])
def test_invalid_cancel_flag_is_unknown_and_excluded(run_clean, flag):
    r = run_clean([row(CANCELLED=flag)]).iloc[0]
    assert r["outcome"] == "unknown"
    assert r["dq_invalid_cancel_flag"]
    assert not r["analysis_include"]


def test_code_on_noncancelled_and_invalid_code(run_clean):
    r = run_clean([row(CANCELLATION_CODE="Z")]).iloc[0]
    assert r["dq_code_on_noncancelled"]
    assert r["dq_invalid_cancel_code"]


def test_exact_duplicate_second_copy_flagged_first_kept(run_clean):
    df = run_clean([row(), row(), row(OP_CARRIER_FL_NUM="999")])
    assert df["dq_exact_duplicate"].tolist() == [False, True, False]
    assert df["analysis_include"].tolist() == [True, False, True]


def test_key_conflict_is_flagged_not_exact_duplicate(run_clean):
    df = run_clean([row(), row(DEP_DELAY="50.0", DEP_TIME="850.0")])
    assert df["dq_exact_duplicate"].tolist() == [False, False]
    assert df["dq_key_conflict"].tolist() == [False, True]
    assert df["analysis_include"].all()


def test_date_outside_file_year_or_unparseable_is_bad_date(run_clean):
    df = run_clean([row(FL_DATE="2014-12-31"), row(FL_DATE="2015-02-30", OP_CARRIER_FL_NUM="2"),
                    row(FL_DATE="", OP_CARRIER_FL_NUM="3"), row(OP_CARRIER_FL_NUM="4")])
    assert df["dq_bad_date"].tolist() == [True, True, True, False]
    assert df["analysis_include"].tolist() == [False, False, False, True]


def test_extreme_delays_flagged_but_retained(run_clean):
    r = run_clean([row(DEP_DELAY="1800.0", ARR_DELAY="1780.0", DEP_TIME="1305.0", ARR_TIME="1105.0")]).iloc[0]
    assert r["dq_extreme_dep_delay"] and r["dq_extreme_arr_delay"]
    assert r["dep_delay"] == 1800.0
    assert bool(r["analysis_include"])


def test_implausible_taxi_and_airport_codes(run_clean):
    r = run_clean([row(TAXI_OUT="-3.0", ORIGIN="JFKX")]).iloc[0]
    assert r["dq_implausible_taxi"]
    assert r["dq_bad_airport_code"]


def test_missing_key_field_blocks(run_clean):
    r = run_clean([row(OP_CARRIER="")]).iloc[0]
    assert r["dq_missing_key_field"]
    assert not r["analysis_include"]


def test_derived_calendar_and_route_fields(run_clean):
    r = run_clean([row(FL_DATE="2015-03-10")]).iloc[0]  # a Tuesday
    assert (r["year"], r["month"], r["day_of_week"]) == (2015, 3, 2)
    assert r["route"] == "JFK-LAX"
    assert r["sched_dep_hour"] == 8


def test_schema_drift_missing_and_extra_columns(tmp_path, cfg):
    header = [c for c in HEADER if c not in ("TAXI_IN", "Unnamed: 27")] + ["SURPRISE"]
    base = row()
    base["SURPRISE"] = "1"
    from conftest import write_csv
    con = clean.connect(cfg)
    p = write_csv(tmp_path / "2015.csv", [base], header)
    schema = clean.clean_year(con, p, 2015, tmp_path / "o.parquet", cfg)
    assert schema["missing_expected"] == ["TAXI_IN"]
    assert schema["extra_columns"] == ["SURPRISE"]
    r = con.execute("SELECT * FROM cleaned").df().iloc[0]
    assert pd.isna(r["taxi_in"])


def test_blocking_rules_are_known_rules():
    assert set(BLOCKING_RULES) <= set(DQ_RULES)
