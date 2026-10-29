"""Ingestion and cleaning of the yearly flight CSVs with DuckDB.

Design principles
-----------------
* Every raw column is read as text and cast with TRY_CAST, so malformed values are
  counted rather than crashing the load or being silently coerced.
* No record is deleted. Each rule adds a boolean ``dq_*`` column; ``analysis_include``
  combines the documented blocking rules. Counts per rule are reported by quality.py.
* Negative delays (early departures/arrivals) are preserved as-is.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

# Columns expected in every yearly file (upper-case header names).
EXPECTED_COLUMNS = [
    "FL_DATE", "OP_CARRIER", "OP_CARRIER_FL_NUM", "ORIGIN", "DEST",
    "CRS_DEP_TIME", "DEP_TIME", "DEP_DELAY", "TAXI_OUT", "WHEELS_OFF", "WHEELS_ON",
    "TAXI_IN", "CRS_ARR_TIME", "ARR_TIME", "ARR_DELAY", "CANCELLED",
    "CANCELLATION_CODE", "DIVERTED", "CRS_ELAPSED_TIME", "ACTUAL_ELAPSED_TIME",
    "AIR_TIME", "DISTANCE", "CARRIER_DELAY", "WEATHER_DELAY", "NAS_DELAY",
    "SECURITY_DELAY", "LATE_AIRCRAFT_DELAY",
]
HHMM_COLUMNS = ["crs_dep_time", "dep_time", "wheels_off", "wheels_on", "crs_arr_time", "arr_time"]
NUMERIC_COLUMNS = [
    "dep_delay", "taxi_out", "taxi_in", "arr_delay", "crs_elapsed_time",
    "actual_elapsed_time", "air_time", "distance", "carrier_delay", "weather_delay",
    "nas_delay", "security_delay", "late_aircraft_delay",
]

# severity: "error" = blocks analysis_include or is a contradiction; "warn" = suspicious,
# retained; "info" = expected property of the data, reported for transparency.
DQ_RULES: dict[str, tuple[str, str]] = {
    "dq_bad_date": ("error", "FL_DATE missing/unparseable, or calendar year differs from the file year"),
    "dq_missing_key_field": ("error", "OP_CARRIER, ORIGIN or DEST is missing"),
    "dq_bad_airport_code": ("warn", "ORIGIN or DEST is not a 3-character alphanumeric code"),
    "dq_origin_equals_dest": ("warn", "ORIGIN equals DEST"),
    "dq_invalid_crs_dep_time": ("error", "CRS_DEP_TIME present but not a valid HHMM time (or missing)"),
    "dq_invalid_dep_time": ("warn", "DEP_TIME present but not a valid HHMM time"),
    "dq_invalid_wheels_off": ("warn", "WHEELS_OFF present but not a valid HHMM time"),
    "dq_invalid_wheels_on": ("warn", "WHEELS_ON present but not a valid HHMM time"),
    "dq_invalid_crs_arr_time": ("warn", "CRS_ARR_TIME present but not a valid HHMM time"),
    "dq_invalid_arr_time": ("warn", "ARR_TIME present but not a valid HHMM time"),
    "dq_has_time_2400": ("info", "At least one HHMM field equals 2400 (treated as 00:00)"),
    "dq_dep_time_inconsistent": ("warn", "DEP_TIME differs from CRS_DEP_TIME + DEP_DELAY (mod 24h)"),
    "dq_arr_time_inconsistent": ("warn", "ARR_TIME differs from CRS_ARR_TIME + ARR_DELAY (mod 24h), completed flights"),
    "dq_invalid_cancel_flag": ("error", "CANCELLED is missing or not 0/1"),
    "dq_invalid_diverted_flag": ("error", "DIVERTED is missing or not 0/1"),
    "dq_cancelled_and_diverted": ("error", "CANCELLED = 1 and DIVERTED = 1 on the same record"),
    "dq_cancelled_has_arrival": ("warn", "Cancelled flight has ARR_TIME or ARR_DELAY"),
    "dq_cancelled_no_code": ("warn", "Cancelled flight without CANCELLATION_CODE"),
    "dq_code_on_noncancelled": ("warn", "CANCELLATION_CODE present on a non-cancelled flight"),
    "dq_invalid_cancel_code": ("warn", "CANCELLATION_CODE not in {A,B,C,D}"),
    "dq_completed_missing_arr_delay": ("warn", "Completed flight with missing ARR_DELAY"),
    "dq_completed_missing_dep_delay": ("warn", "Completed flight with missing DEP_DELAY"),
    "dq_completed_missing_taxi_out": ("warn", "Completed flight with missing TAXI_OUT"),
    "dq_missing_crs_elapsed": ("warn", "CRS_ELAPSED_TIME missing or non-positive"),
    "dq_extreme_dep_delay": ("warn", "DEP_DELAY outside the plausible range set in config"),
    "dq_extreme_arr_delay": ("warn", "ARR_DELAY outside the plausible range set in config"),
    "dq_implausible_taxi": ("warn", "TAXI_OUT or TAXI_IN negative or above the config maximum"),
    "dq_exact_duplicate": ("error", "Repeat of an earlier record identical in every raw column"),
    "dq_key_conflict": ("warn", "Shares date/carrier/flight/route/scheduled-time key with an earlier, different record"),
}
# Rules that set analysis_include = FALSE (records are kept, but excluded from KPIs/models).
BLOCKING_RULES = [
    "dq_bad_date", "dq_missing_key_field", "dq_invalid_crs_dep_time",
    "dq_invalid_cancel_flag", "dq_invalid_diverted_flag", "dq_cancelled_and_diverted",
    "dq_exact_duplicate",
]

_MACROS = """
CREATE OR REPLACE MACRO hhmm_int(r) AS (
    CASE WHEN isfinite(try_cast(r AS DOUBLE))
              AND try_cast(r AS DOUBLE) = round(try_cast(r AS DOUBLE))
         THEN CAST(try_cast(r AS DOUBLE) AS INTEGER) END
);
-- Minutes since midnight; 2400 is a valid BTS spelling of midnight and maps to 0.
CREATE OR REPLACE MACRO hhmm_min(x) AS (
    CASE WHEN x = 2400 THEN 0
         WHEN x BETWEEN 0 AND 2359 AND x % 100 < 60 THEN (x // 100) * 60 + x % 100 END
);
-- Output HHMM: invalid -> NULL, 2400 -> 0, otherwise unchanged.
CREATE OR REPLACE MACRO hhmm_norm(x) AS (
    CASE WHEN x = 2400 THEN 0 WHEN hhmm_min(x) IS NOT NULL THEN x END
);
CREATE OR REPLACE MACRO wrap_day(m) AS (((CAST(round(m) AS BIGINT) % 1440) + 1440) % 1440);
"""


def _quote_path(p: Path | str) -> str:
    return str(p).replace("\\", "/").replace("'", "''")


def connect(cfg: dict | None = None, temp_dir: Path | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    if cfg:
        con.execute(f"SET memory_limit='{cfg['duckdb']['memory_limit']}'")
        con.execute(f"SET threads={int(cfg['duckdb']['threads'])}")
    if temp_dir:
        Path(temp_dir).mkdir(parents=True, exist_ok=True)
        con.execute(f"SET temp_directory='{_quote_path(temp_dir)}'")
    con.execute(_MACROS)
    return con


def inspect_schema(con: duckdb.DuckDBPyConnection, csv_path: Path) -> dict:
    """Return header names (normalised) and deviations from the expected schema."""
    cur = con.execute(
        f"SELECT * FROM read_csv('{_quote_path(csv_path)}', all_varchar=true, header=true) LIMIT 0"
    )
    header = [d[0].strip() for d in cur.description]
    upper = [h.upper() for h in header]
    return {
        "header": header,
        "missing_expected": [c for c in EXPECTED_COLUMNS if c not in upper],
        "extra_columns": [h for h, u in zip(header, upper) if u not in EXPECTED_COLUMNS],
    }


def create_stage(con, csv_path: Path, schema: dict, limit_rows: int | None = None) -> None:
    """Create TEMP table ``stage``: all-text, lower-case names, blanks as NULL, with file_row."""
    by_upper = {h.upper(): h for h in schema["header"]}
    select = []
    for col in EXPECTED_COLUMNS:
        if col in by_upper:
            src = by_upper[col].replace('"', '""')
            select.append(f"NULLIF(TRIM(\"{src}\"), '') AS {col.lower()}")
        else:
            select.append(f"CAST(NULL AS VARCHAR) AS {col.lower()}")
    lim = f"LIMIT {int(limit_rows)}" if limit_rows else ""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE stage AS
        SELECT row_number() OVER () AS file_row, {', '.join(select)}
        FROM read_csv('{_quote_path(csv_path)}', all_varchar=true, header=true, null_padding=true)
        {lim}
    """)


def build_cleaned_sql(year: int, cfg: dict) -> str:
    q = cfg["quality"]
    raw_cols = [c.lower() for c in EXPECTED_COLUMNS]
    exact_key = " || '|' || ".join(f"coalesce(s.{c}, '')" for c in raw_cols)
    blocking = " OR ".join(f"{r}" for r in BLOCKING_RULES)
    flag_select = ",\n        ".join(f"{r}" for r in DQ_RULES)

    return f"""
    CREATE OR REPLACE TEMP TABLE cleaned AS
    WITH t AS (  -- typed values
        SELECT
            file_row,
            {year} AS file_year,
            try_cast(s.fl_date AS DATE) AS fl_date,
            s.op_carrier AS op_carrier, s.op_carrier_fl_num AS op_carrier_fl_num,
            s.origin AS origin, s.dest AS dest,
            hhmm_int(s.crs_dep_time) AS crs_dep_time, hhmm_int(s.dep_time) AS dep_time,
            hhmm_int(s.wheels_off) AS wheels_off, hhmm_int(s.wheels_on) AS wheels_on,
            hhmm_int(s.crs_arr_time) AS crs_arr_time, hhmm_int(s.arr_time) AS arr_time,
            s.dep_time IS NOT NULL AS has_dep_time, s.wheels_off IS NOT NULL AS has_wheels_off,
            s.wheels_on IS NOT NULL AS has_wheels_on, s.crs_arr_time IS NOT NULL AS has_crs_arr_time,
            s.arr_time IS NOT NULL AS has_arr_time,
            try_cast(s.dep_delay AS DOUBLE) AS dep_delay, try_cast(s.arr_delay AS DOUBLE) AS arr_delay,
            try_cast(s.taxi_out AS DOUBLE) AS taxi_out, try_cast(s.taxi_in AS DOUBLE) AS taxi_in,
            try_cast(s.cancelled AS DOUBLE) AS cancelled_v, try_cast(s.diverted AS DOUBLE) AS diverted_v,
            upper(s.cancellation_code) AS cancellation_code,
            try_cast(s.crs_elapsed_time AS DOUBLE) AS crs_elapsed_time,
            try_cast(s.actual_elapsed_time AS DOUBLE) AS actual_elapsed_time,
            try_cast(s.air_time AS DOUBLE) AS air_time, try_cast(s.distance AS DOUBLE) AS distance,
            try_cast(s.carrier_delay AS DOUBLE) AS carrier_delay,
            try_cast(s.weather_delay AS DOUBLE) AS weather_delay,
            try_cast(s.nas_delay AS DOUBLE) AS nas_delay,
            try_cast(s.security_delay AS DOUBLE) AS security_delay,
            try_cast(s.late_aircraft_delay AS DOUBLE) AS late_aircraft_delay,
            {exact_key} AS exact_key,
            coalesce(s.fl_date,'') || '|' || coalesce(s.op_carrier,'') || '|' || coalesce(s.op_carrier_fl_num,'')
              || '|' || coalesce(s.origin,'') || '|' || coalesce(s.dest,'') || '|'
              || coalesce(s.crs_dep_time,'') AS flight_key
        FROM stage s
    ), m AS (  -- minutes, outcome, duplicate ranks
        SELECT t.*,
            hhmm_min(crs_dep_time) AS crs_dep_min, hhmm_min(dep_time) AS dep_time_min,
            hhmm_min(crs_arr_time) AS crs_arr_min, hhmm_min(arr_time) AS arr_time_min,
            coalesce(cancelled_v IN (0, 1), false) AS cancel_ok,
            coalesce(diverted_v IN (0, 1), false) AS div_ok,
            row_number() OVER (PARTITION BY exact_key ORDER BY file_row) AS exact_rank,
            row_number() OVER (PARTITION BY flight_key ORDER BY file_row) AS key_rank
        FROM t
    ), o AS (
        SELECT m.*,
            CASE WHEN NOT (cancel_ok AND div_ok) THEN 'unknown'
                 WHEN cancelled_v = 1 AND diverted_v = 1 THEN 'inconsistent'
                 WHEN cancelled_v = 1 THEN 'cancelled'
                 WHEN diverted_v = 1 THEN 'diverted'
                 ELSE 'completed' END AS outcome
        FROM m
    ), f AS (
        SELECT o.*,
            coalesce(fl_date IS NULL OR year(fl_date) <> file_year, true) AS dq_bad_date,
            (op_carrier IS NULL OR origin IS NULL OR dest IS NULL) AS dq_missing_key_field,
            coalesce(NOT regexp_full_match(origin, '[A-Z0-9]{{3}}')
                     OR NOT regexp_full_match(dest, '[A-Z0-9]{{3}}'), false) AS dq_bad_airport_code,
            coalesce(origin = dest, false) AS dq_origin_equals_dest,
            (crs_dep_min IS NULL) AS dq_invalid_crs_dep_time,
            (has_dep_time AND dep_time_min IS NULL) AS dq_invalid_dep_time,
            (has_wheels_off AND hhmm_min(wheels_off) IS NULL) AS dq_invalid_wheels_off,
            (has_wheels_on AND hhmm_min(wheels_on) IS NULL) AS dq_invalid_wheels_on,
            (has_crs_arr_time AND crs_arr_min IS NULL) AS dq_invalid_crs_arr_time,
            (has_arr_time AND arr_time_min IS NULL) AS dq_invalid_arr_time,
            coalesce(crs_dep_time = 2400 OR dep_time = 2400 OR wheels_off = 2400 OR wheels_on = 2400
                     OR crs_arr_time = 2400 OR arr_time = 2400, false) AS dq_has_time_2400,
            coalesce(dep_time_min <> wrap_day(crs_dep_min + dep_delay), false) AS dq_dep_time_inconsistent,
            coalesce(outcome = 'completed' AND arr_time_min <> wrap_day(crs_arr_min + arr_delay), false)
                AS dq_arr_time_inconsistent,
            NOT cancel_ok AS dq_invalid_cancel_flag,
            NOT div_ok AS dq_invalid_diverted_flag,
            coalesce(cancelled_v = 1 AND diverted_v = 1, false) AS dq_cancelled_and_diverted,
            coalesce(cancelled_v = 1 AND (has_arr_time OR arr_delay IS NOT NULL), false)
                AS dq_cancelled_has_arrival,
            coalesce(cancelled_v = 1 AND cancellation_code IS NULL, false) AS dq_cancelled_no_code,
            coalesce(cancelled_v = 0 AND cancellation_code IS NOT NULL, false) AS dq_code_on_noncancelled,
            coalesce(cancellation_code NOT IN ('A','B','C','D'), false) AS dq_invalid_cancel_code,
            (outcome = 'completed' AND arr_delay IS NULL) AS dq_completed_missing_arr_delay,
            (outcome = 'completed' AND dep_delay IS NULL) AS dq_completed_missing_dep_delay,
            (outcome = 'completed' AND taxi_out IS NULL) AS dq_completed_missing_taxi_out,
            coalesce(crs_elapsed_time <= 0, true) AS dq_missing_crs_elapsed,
            coalesce(dep_delay > {q['delay_extreme_max_min']} OR dep_delay < {q['early_extreme_min_min']}, false)
                AS dq_extreme_dep_delay,
            coalesce(arr_delay > {q['delay_extreme_max_min']} OR arr_delay < {q['early_extreme_min_min']}, false)
                AS dq_extreme_arr_delay,
            coalesce(taxi_out < 0 OR taxi_out > {q['taxi_max_min']}
                     OR taxi_in < 0 OR taxi_in > {q['taxi_max_min']}, false) AS dq_implausible_taxi,
            (exact_rank > 1) AS dq_exact_duplicate,
            (key_rank > 1 AND exact_rank = 1) AS dq_key_conflict
        FROM o
    )
    SELECT
        CAST(file_year AS BIGINT) * 100000000 + file_row AS row_id,
        file_year,
        fl_date,
        year(fl_date) AS year,
        month(fl_date) AS month,
        isodow(fl_date) AS day_of_week,            -- 1 = Monday ... 7 = Sunday
        op_carrier, op_carrier_fl_num, origin, dest,
        origin || '-' || dest AS route,
        outcome,
        CAST(cancelled_v AS TINYINT) AS cancelled,
        CAST(diverted_v AS TINYINT) AS diverted,
        cancellation_code,
        hhmm_norm(crs_dep_time) AS crs_dep_time, crs_dep_min, crs_dep_min // 60 AS sched_dep_hour,
        hhmm_norm(crs_arr_time) AS crs_arr_time, crs_arr_min,
        hhmm_norm(dep_time) AS dep_time, hhmm_norm(wheels_off) AS wheels_off,
        hhmm_norm(wheels_on) AS wheels_on, hhmm_norm(arr_time) AS arr_time,
        dep_delay, arr_delay, taxi_out, taxi_in,
        crs_elapsed_time, actual_elapsed_time, air_time, distance,
        carrier_delay, weather_delay, nas_delay, security_delay, late_aircraft_delay,
        CAST(fl_date AS TIMESTAMP) + crs_dep_min * INTERVAL 1 MINUTE AS sched_dep_ts,
        CAST(fl_date AS TIMESTAMP) + (crs_dep_min + dep_delay) * INTERVAL 1 MINUTE AS actual_dep_ts,
        coalesce(crs_dep_min + crs_elapsed_time >= 1440, false) AS sched_crosses_midnight,
        {flag_select},
        NOT ({blocking}) AS analysis_include
    FROM f
    """


def clean_year(
    con: duckdb.DuckDBPyConnection,
    csv_path: Path,
    year: int,
    out_path: Path,
    cfg: dict,
    limit_rows: int | None = None,
) -> dict:
    """Clean one yearly CSV into Parquet. Returns schema info; tables stay in ``con``."""
    schema = inspect_schema(con, csv_path)
    create_stage(con, csv_path, schema, limit_rows)
    con.execute(build_cleaned_sql(year, cfg))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY cleaned TO '{_quote_path(out_path)}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    return schema
