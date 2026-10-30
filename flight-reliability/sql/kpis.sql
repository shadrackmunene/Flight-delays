-- Operational KPI queries (DuckDB dialect). Run through flightrel.kpi, which substitutes {placeholders}.
--
-- Base views (created by flightrel.kpi.connect_views):
--   f  : every record with analysis_include = TRUE, plus
--          arr_late  = (arr_delay >= 15) for completed flights with a known arrival delay, else NULL
--          dep_late  = (dep_delay >= 15) for non-cancelled flights with a known departure delay, else NULL
--          matched_month = month is present in all ten years (excludes Jul and Oct; see data quality report)
--          stable    = carrier reports >= 10,000 flights in every year 2009-2018
--   Because the late flags are NULL outside their denominators, count(arr_late) is the completed-flight
--   denominator and sum(arr_late) the number of late arrivals. Negative delays are kept in all quantiles.

-- name: kpi_by
-- Generic KPI block. {dims} = grouping columns, {where} = row filter, {having} = group filter.
SELECT {dims},
       count(*)                                  AS scheduled_flights,
       count(*) FILTER (WHERE outcome = 'cancelled') AS cancelled_n,
       count(*) FILTER (WHERE outcome = 'diverted')  AS diverted_n,
       count(arr_late)                           AS completed_n,        -- denominator for arrival KPIs
       sum(arr_late::INT)                        AS arr_late_n,         -- arr_delay >= 15
       count(dep_late)                           AS departed_n,         -- denominator for departure KPIs
       sum(dep_late::INT)                        AS dep_late_n,         -- dep_delay >= 15
       avg(arr_delay)                            AS arr_mean,
       quantile_cont(arr_delay, 0.5)             AS arr_p50,
       quantile_cont(arr_delay, 0.9)             AS arr_p90,
       quantile_cont(arr_delay, 0.95)            AS arr_p95,
       quantile_cont(dep_delay, 0.5)             AS dep_p50,
       quantile_cont(dep_delay, 0.9)             AS dep_p90
FROM f
WHERE {where}
GROUP BY {dims}
{having}
ORDER BY {dims};

-- name: dep_to_arr
-- How a departure delay carries into arrival. Completed flights with both delays known.
SELECT CASE WHEN dep_delay < -5  THEN '1: early (< -5)'
            WHEN dep_delay < 0   THEN '2: slightly early (-5 to -1)'
            WHEN dep_delay < 15  THEN '3: on time (0 to 14)'
            WHEN dep_delay < 30  THEN '4: 15-29'
            WHEN dep_delay < 60  THEN '5: 30-59'
            WHEN dep_delay < 120 THEN '6: 60-119'
            ELSE '7: 120+' END                      AS dep_delay_bin,
       count(*)                                     AS n,
       sum(arr_late::INT)                           AS arr_late_n,
       quantile_cont(arr_delay, 0.5)                AS arr_p50,
       avg(arr_delay - dep_delay)                   AS mean_change_in_delay,     -- arrival minus departure delay
       quantile_cont(arr_delay - dep_delay, 0.5)    AS median_change_in_delay
FROM f
WHERE arr_late IS NOT NULL AND dep_delay IS NOT NULL AND {where}
GROUP BY 1 ORDER BY 1;

-- name: dep_late_outcomes
-- Of flights that left >= 15 minutes late, how many still arrived on time (< 15 min late)?
SELECT count(*)                                           AS dep_late_flights,
       sum((arr_delay < 15)::INT)                         AS arrived_on_time_n,
       sum((arr_delay < 0)::INT)                          AS arrived_early_n,
       corr(dep_delay, arr_delay)                         AS corr_dep_arr_late_departures  -- only flights with dep_delay >= 15
FROM f
WHERE arr_late IS NOT NULL AND dep_delay IS NOT NULL AND dep_delay >= 15 AND {where};

-- name: dep_arr_corr
SELECT corr(dep_delay, arr_delay) AS pearson_r, count(*) AS n
FROM f WHERE arr_late IS NOT NULL AND dep_delay IS NOT NULL AND {where};

-- name: taxi_out_bins
-- Late-arrival rate by taxi-out time, split by whether the flight left on time. Taxi-out is observed at wheels-off.
SELECT CASE WHEN dep_delay < 15 THEN 'departed on time (<15)' ELSE 'departed late (>=15)' END AS departure_status,
       CASE WHEN taxi_out < 10 THEN '1: <10' WHEN taxi_out < 15 THEN '2: 10-14' WHEN taxi_out < 20 THEN '3: 15-19'
            WHEN taxi_out < 30 THEN '4: 20-29' WHEN taxi_out < 45 THEN '5: 30-44' ELSE '6: 45+' END AS taxi_out_bin,
       count(*) AS n, sum(arr_late::INT) AS arr_late_n, quantile_cont(arr_delay, 0.5) AS arr_p50
FROM f
WHERE arr_late IS NOT NULL AND dep_delay IS NOT NULL AND taxi_out IS NOT NULL AND taxi_out BETWEEN 0 AND 300 AND {where}
GROUP BY 1, 2 ORDER BY 1, 2;

-- name: taxi_in_bins
-- Taxi-in is only known after landing, so this is an association, never a predictor.
SELECT CASE WHEN taxi_in < 5 THEN '1: <5' WHEN taxi_in < 8 THEN '2: 5-7' WHEN taxi_in < 12 THEN '3: 8-11'
            WHEN taxi_in < 20 THEN '4: 12-19' ELSE '5: 20+' END AS taxi_in_bin,
       count(*) AS n, sum(arr_late::INT) AS arr_late_n, quantile_cont(arr_delay, 0.5) AS arr_p50
FROM f
WHERE arr_late IS NOT NULL AND taxi_in IS NOT NULL AND taxi_in BETWEEN 0 AND 300 AND {where}
GROUP BY 1 ORDER BY 1;

-- name: taxi_out_by_airport
-- Median and P90 taxi-out per origin airport.
SELECT origin, count(taxi_out) AS n, quantile_cont(taxi_out, 0.5) AS taxi_out_p50,
       quantile_cont(taxi_out, 0.9) AS taxi_out_p90, avg(arr_late::INT) AS arr_late_rate
FROM f WHERE taxi_out BETWEEN 0 AND 300 AND {where}
GROUP BY origin HAVING count(taxi_out) >= {min_flights} ORDER BY taxi_out_p50 DESC;

-- name: cancel_codes
-- Cancellation counts by reason (A carrier, B weather, C national air system, D security).
SELECT {dims}, cancellation_code, count(*) AS cancelled_n
FROM f WHERE outcome = 'cancelled' AND {where}
GROUP BY {dims}, cancellation_code ORDER BY {dims}, cancellation_code;

-- name: route_year
-- Route x year KPI cells, used to find routes that are poor repeatedly (not just once).
SELECT route, year, count(arr_late) AS completed_n, sum(arr_late::INT) AS arr_late_n,
       count(*) AS scheduled_flights, count(*) FILTER (WHERE outcome = 'cancelled') AS cancelled_n
FROM f WHERE {where}
GROUP BY route, year HAVING count(arr_late) >= {min_flights};

-- name: entity_year
-- Airport (origin or dest) x year KPI cells for the persistence analysis.
SELECT {entity} AS entity, year, count(arr_late) AS completed_n, sum(arr_late::INT) AS arr_late_n,
       quantile_cont(arr_delay, 0.5) AS arr_p50
FROM f WHERE {where}
GROUP BY {entity}, year HAVING count(arr_late) >= {min_flights};
