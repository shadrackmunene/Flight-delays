"""Shared fixtures: build tiny yearly CSVs with the real 28-column layout."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from flightrel import clean
from flightrel.config import load_config

HEADER = [
    "FL_DATE", "OP_CARRIER", "OP_CARRIER_FL_NUM", "ORIGIN", "DEST", "CRS_DEP_TIME", "DEP_TIME",
    "DEP_DELAY", "TAXI_OUT", "WHEELS_OFF", "WHEELS_ON", "TAXI_IN", "CRS_ARR_TIME", "ARR_TIME",
    "ARR_DELAY", "CANCELLED", "CANCELLATION_CODE", "DIVERTED", "CRS_ELAPSED_TIME",
    "ACTUAL_ELAPSED_TIME", "AIR_TIME", "DISTANCE", "CARRIER_DELAY", "WEATHER_DELAY", "NAS_DELAY",
    "SECURITY_DELAY", "LATE_AIRCRAFT_DELAY", "Unnamed: 27",
]

# A fully valid, completed flight (internally consistent times and delays).
BASE = {
    "FL_DATE": "2015-03-10", "OP_CARRIER": "AA", "OP_CARRIER_FL_NUM": "100", "ORIGIN": "JFK",
    "DEST": "LAX", "CRS_DEP_TIME": "800", "DEP_TIME": "805.0", "DEP_DELAY": "5.0",
    "TAXI_OUT": "15.0", "WHEELS_OFF": "820.0", "WHEELS_ON": "1100.0", "TAXI_IN": "5.0",
    "CRS_ARR_TIME": "1130", "ARR_TIME": "1105.0", "ARR_DELAY": "-25.0", "CANCELLED": "0.0",
    "CANCELLATION_CODE": "", "DIVERTED": "0.0", "CRS_ELAPSED_TIME": "390.0",
    "ACTUAL_ELAPSED_TIME": "360.0", "AIR_TIME": "340.0", "DISTANCE": "2475.0",
    "CARRIER_DELAY": "", "WEATHER_DELAY": "", "NAS_DELAY": "", "SECURITY_DELAY": "",
    "LATE_AIRCRAFT_DELAY": "", "Unnamed: 27": "",
}


def row(**overrides) -> dict:
    r = dict(BASE)
    r.update({k.upper() if k.upper() in BASE else k: v for k, v in overrides.items()})
    return r


def write_csv(path: Path, rows: list[dict], header: list[str] = HEADER) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture()
def run_clean(tmp_path, cfg):
    """Return a function: rows -> pandas DataFrame of the cleaned output (one row per input row)."""

    def _run(rows: list[dict], year: int = 2015, header: list[str] = HEADER):
        con = clean.connect(cfg)
        csv_path = write_csv(tmp_path / f"{year}.csv", rows, header)
        clean.clean_year(con, csv_path, year, tmp_path / "out" / f"flights_{year}.parquet", cfg)
        return con.execute("SELECT * FROM cleaned ORDER BY row_id").df()

    return _run
