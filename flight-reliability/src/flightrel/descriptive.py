"""Stage 3 descriptive analysis: runs the KPI queries and writes tables to reports/tables/.

    python -m flightrel.descriptive
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import clean, kpi
from .config import PROJECT_ROOT, load_config
from .stats import add_rate

TABLES = PROJECT_ROOT / "reports" / "tables"

MIN_AIRPORT_YEAR = 5_000   # completed flights per airport-year to be observed
MIN_ROUTE_YEAR = 300       # completed flights per route-year to be observed
MIN_YEARS_OBSERVED = 8     # of 10, to assess persistence
POOR_QUANTILE_AIRPORT = 0.75
POOR_QUANTILE_ROUTE = 0.90


def with_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Add rates and Wilson intervals to a ``kpi_by`` result."""
    df = add_rate(df, "arr_late_n", "completed_n", "arr_late_rate")
    df = add_rate(df, "dep_late_n", "departed_n", "dep_late_rate")
    df = add_rate(df, "cancelled_n", "scheduled_flights", "cancel_rate")
    df["divert_rate"] = df["diverted_n"] / df["scheduled_flights"]
    df["otp"] = 1 - df["arr_late_rate"]
    return df


def persistence(cells: pd.DataFrame, quantile: float) -> pd.DataFrame:
    """Count in how many observed years an entity is in the worst tail of its own year.

    ``cells`` has entity, year, completed_n, arr_late_n. Under pure chance, an entity is in the worst tail of
    a year with probability (1 - quantile), so a binomial tail gives a reference for repeated poor performance.
    """
    c = cells.copy()
    c["rate"] = c["arr_late_n"] / c["completed_n"]
    c["cutoff"] = c.groupby("year")["rate"].transform(lambda s: s.quantile(quantile))
    c["poor"] = c["rate"] >= c["cutoff"]
    g = c.groupby("entity").agg(years_observed=("year", "nunique"), years_poor=("poor", "sum"),
                                completed_n=("completed_n", "sum"), arr_late_n=("arr_late_n", "sum"),
                                worst_year_rate=("rate", "max"), best_year_rate=("rate", "min")).reset_index()
    g = g[g["years_observed"] >= MIN_YEARS_OBSERVED].copy()
    g["arr_late_rate"] = g["arr_late_n"] / g["completed_n"]
    p0 = 1 - quantile
    g["p_by_chance"] = [stats.binom.sf(k - 1, n, p0) for k, n in zip(g["years_poor"], g["years_observed"])]
    return g.sort_values(["years_poor", "arr_late_rate"], ascending=False)


def build_all(con) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}

    # A. Annual trends under three scopes
    out["annual"] = pd.concat(
        [with_rates(kpi.run(con, "kpi_by", scope=s, dims="year")).assign(scope=s) for s in kpi.SCOPES],
        ignore_index=True)

    # B. Calendar patterns (matched months avoid the 2009/2011 gaps skewing month comparisons)
    out["month"] = with_rates(kpi.run(con, "kpi_by", scope="all", dims="month"))
    out["month_year"] = with_rates(kpi.run(con, "kpi_by", scope="all", dims="year, month"))
    out["weekday"] = with_rates(kpi.run(con, "kpi_by", scope="matched_months", dims="day_of_week"))
    out["hour"] = with_rates(kpi.run(con, "kpi_by", scope="matched_months", dims="sched_dep_hour"))
    out["hour_weekday"] = with_rates(kpi.run(con, "kpi_by", scope="matched_months", dims="day_of_week, sched_dep_hour"))

    # C. Carriers
    out["carrier"] = with_rates(kpi.run(con, "kpi_by", scope="matched_months", dims="op_carrier"))
    out["carrier_year"] = with_rates(kpi.run(con, "kpi_by", scope="matched_months", dims="op_carrier, year"))

    # D. Airports and routes
    for col in ("origin", "dest"):
        out[f"airport_{col}"] = with_rates(kpi.run(con, "kpi_by", scope="matched_months", dims=col,
                                                   having="HAVING count(arr_late) >= 50000"))
    out["persist_origin"] = persistence(kpi.run(con, "entity_year", scope="matched_months", entity="origin",
                                                min_flights=MIN_AIRPORT_YEAR), POOR_QUANTILE_AIRPORT)
    out["persist_dest"] = persistence(kpi.run(con, "entity_year", scope="matched_months", entity="dest",
                                              min_flights=MIN_AIRPORT_YEAR), POOR_QUANTILE_AIRPORT)
    out["persist_route"] = persistence(kpi.run(con, "route_year", scope="matched_months",
                                               min_flights=MIN_ROUTE_YEAR).rename(columns={"route": "entity"}),
                                       POOR_QUANTILE_ROUTE)

    # E. Departure -> arrival
    out["dep_to_arr"] = add_rate(kpi.run(con, "dep_to_arr", scope="matched_months"), "arr_late_n", "n", "arr_late_rate")
    out["dep_late_outcomes"] = kpi.run(con, "dep_late_outcomes", scope="matched_months")
    out["dep_arr_corr"] = kpi.run(con, "dep_arr_corr", scope="matched_months")

    # F. Taxi
    out["taxi_out_bins"] = add_rate(kpi.run(con, "taxi_out_bins", scope="matched_months"), "arr_late_n", "n", "arr_late_rate")
    out["taxi_in_bins"] = add_rate(kpi.run(con, "taxi_in_bins", scope="matched_months"), "arr_late_n", "n", "arr_late_rate")
    out["taxi_out_airport"] = kpi.run(con, "taxi_out_by_airport", scope="matched_months", min_flights=100000)

    # G. Cancellations
    out["cancel_year"] = with_rates(kpi.run(con, "kpi_by", scope="all", dims="year"))
    out["cancel_codes_year"] = kpi.run(con, "cancel_codes", scope="all", dims="year")
    out["cancel_codes_month"] = kpi.run(con, "cancel_codes", scope="all", dims="month")
    out["cancel_codes_carrier"] = kpi.run(con, "cancel_codes", scope="matched_months", dims="op_carrier")
    out["cancel_codes_origin"] = kpi.run(con, "cancel_codes", scope="matched_months", dims="origin")
    return out


def main() -> None:
    cfg = load_config()
    con = clean.connect(cfg, cfg["paths"]["interim_dir"])
    kpi.connect_views(con, cfg["paths"]["processed_dir"] / "flights", len(cfg["years"]))
    TABLES.mkdir(parents=True, exist_ok=True)
    stable = con.execute("SELECT op_carrier FROM stable_carriers ORDER BY 1").df()["op_carrier"].tolist()
    print("Stable carriers:", stable)
    pd.Series(stable, name="op_carrier").to_csv(TABLES / "stable_carriers.csv", index=False)
    for name, df in build_all(con).items():
        df.to_csv(TABLES / f"{name}.csv", index=False)
        print(f"{name}: {len(df)} rows")


if __name__ == "__main__":
    main()
