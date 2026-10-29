# Data Dictionary

Source: Mu, Yuanyuwendy, *Airline Delay and Cancellation Data, 2009–2018*, Kaggle.
Each yearly CSV has 28 columns: the 19 fields named in the project brief, eight further operational
fields (marked *extra*), and an empty trailing column (`Unnamed: 27`, dropped; its non-empty cell count
is reported in the data quality report). Cleaned output is `data/processed/flights/flights_<year>.parquet`.

**Availability** tells you when the value is known: *pre* = known before departure (usable by Model A),
*dep* = known once the aircraft leaves the gate / takes off (usable by Model B), *post* = known only after
arrival (**never** used as a predictor; target or leakage).

## 1. Supplied fields (as cleaned)

| Cleaned column | Raw field | Type | Unit / values | Availability | Notes |
|---|---|---|---|---|---|
| `fl_date` | FL_DATE | DATE | | pre | Scheduled departure date. |
| `op_carrier` | OP_CARRIER | VARCHAR | 2-char carrier code | pre | |
| `op_carrier_fl_num` | OP_CARRIER_FL_NUM | VARCHAR | | pre | Kept as text. |
| `origin`, `dest` | ORIGIN, DEST | VARCHAR | IATA airport code | pre | |
| `crs_dep_time` | CRS_DEP_TIME | INTEGER | HHMM, local time | pre | 2400 → 0; invalid → NULL. |
| `dep_time` | DEP_TIME | INTEGER | HHMM, local time | dep | NULL if cancelled or invalid. |
| `dep_delay` | DEP_DELAY | DOUBLE | minutes, **negative = early** | dep | |
| `taxi_out` | TAXI_OUT | DOUBLE | minutes | dep | Gate to wheels-off. |
| `wheels_off` | WHEELS_OFF | INTEGER | HHMM | dep | |
| `wheels_on` | WHEELS_ON | INTEGER | HHMM | post | |
| `taxi_in` | TAXI_IN | DOUBLE | minutes | post | |
| `crs_arr_time` | CRS_ARR_TIME | INTEGER | HHMM, local time at destination | pre | |
| `arr_time` | ARR_TIME | INTEGER | HHMM | post | |
| `arr_delay` | ARR_DELAY | DOUBLE | minutes, **negative = early** | post | **Prediction target source.** |
| `cancelled` | CANCELLED | TINYINT | 0/1 | post | |
| `cancellation_code` | CANCELLATION_CODE | VARCHAR | A carrier, B weather, C national air system, D security | post | Only for cancelled flights. |
| `diverted` | DIVERTED | TINYINT | 0/1 | post | |
| `crs_elapsed_time` | CRS_ELAPSED_TIME | DOUBLE | minutes | pre | Scheduled gate-to-gate duration. |

## 2. Extra fields in the files

| Cleaned column | Type | Availability | Notes |
|---|---|---|---|
| `distance` | DOUBLE (miles) | pre | Fixed per route; allowed in Model A. |
| `actual_elapsed_time` | DOUBLE (min) | post | **Leakage**: equals arrival minus departure. |
| `air_time` | DOUBLE (min) | post | **Leakage**. |
| `carrier_delay`, `weather_delay`, `nas_delay`, `security_delay`, `late_aircraft_delay` | DOUBLE (min) | post | **Leakage**: cause attribution of an arrival delay. BTS reports them only for arrivals ≥ 15 min late, so they are also mostly missing. |

## 3. Engineered fields (added by `flightrel.clean`)

| Column | Type | Definition |
|---|---|---|
| `row_id` | BIGINT | `file_year × 10⁸ + row position in the CSV`. Stable, unique key. |
| `file_year` | INTEGER | Year of the source file. |
| `year`, `month`, `day_of_week` | INTEGER | From `fl_date`; `day_of_week` is ISO (1 = Monday … 7 = Sunday). |
| `route` | VARCHAR | `origin-dest` (directional). |
| `outcome` | VARCHAR | `completed`, `cancelled`, `diverted`, `inconsistent` (both flags set) or `unknown` (flag missing/invalid). |
| `crs_dep_min`, `crs_arr_min` | INTEGER | Minutes since midnight of the scheduled times. |
| `sched_dep_hour` | INTEGER | `crs_dep_min // 60` (0–23). |
| `sched_dep_ts` | TIMESTAMP | `fl_date` + scheduled departure (local clock). |
| `actual_dep_ts` | TIMESTAMP | `sched_dep_ts + dep_delay`. Rolls to the next/previous day when the delay crosses midnight. |
| `sched_crosses_midnight` | BOOLEAN | `crs_dep_min + crs_elapsed_time ≥ 1440`. Uses elapsed time because arrival clocks are in the destination time zone. |
| `dq_*` | BOOLEAN | One flag per quality rule; see `data_quality_report.md` for definitions and counts. |
| `analysis_include` | BOOLEAN | FALSE if any blocking rule fires. Rows are retained regardless. |

## 4. KPI definitions (used from Stage 3 onward)

| KPI | Definition | Denominator |
|---|---|---|
| Cancellation rate | `outcome='cancelled'` / all `analysis_include` flights | scheduled flights |
| Diversion rate | `outcome='diverted'` / all `analysis_include` flights | scheduled flights |
| Arrival delay rate (D15) | `arr_delay ≥ 15` | completed flights with non-missing `arr_delay` |
| On-time performance (OTP) | `arr_delay < 15` (early and negative delays count as on time) | same as above |
| Departure delay rate | `dep_delay ≥ 15` | flights that departed with non-missing `dep_delay` |
| Median / P90 / P95 delay | Quantiles of `arr_delay` or `dep_delay`, negatives included | same as above |
| Disruption rate | cancelled or diverted or `arr_delay ≥ 15`, over all flights | scheduled flights |

The 15-minute threshold follows the US DOT definition of a delayed flight; sensitivity to 0/30/60 minutes is
analysed in Stage 4.
