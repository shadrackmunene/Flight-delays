"""Data quality metrics and report rendering.

All numbers in the report are computed from the data by this module; nothing is typed by hand.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .clean import DQ_RULES, NUMERIC_COLUMNS, _quote_path

MISSINGNESS_COLUMNS = [
    "fl_date", "op_carrier", "op_carrier_fl_num", "origin", "dest", "crs_dep_time", "dep_time",
    "dep_delay", "taxi_out", "wheels_off", "wheels_on", "taxi_in", "crs_arr_time", "arr_time",
    "arr_delay", "cancellation_code", "crs_elapsed_time", "actual_elapsed_time", "air_time",
    "distance", "carrier_delay", "weather_delay", "nas_delay", "security_delay",
    "late_aircraft_delay",
]
OUTCOME_ORDER = ["completed", "cancelled", "diverted", "inconsistent", "unknown"]


def collect_year_metrics(con, year: int, csv_path: Path, schema: dict) -> dict[str, pd.DataFrame]:
    """Compute quality metrics for the ``stage`` and ``cleaned`` tables of one year."""
    raw_rows = con.execute("SELECT count(*) FROM stage").fetchone()[0]

    outcomes = con.execute(
        "SELECT outcome, count(*) AS n_rows, sum(CAST(analysis_include AS INT)) AS n_included "
        "FROM cleaned GROUP BY outcome"
    ).df()
    outcomes.insert(0, "year", year)
    outcomes["raw_rows"] = raw_rows

    rule_sql = ", ".join(f"sum(CAST({r} AS INT)) AS {r}" for r in DQ_RULES)
    counts = con.execute(f"SELECT {rule_sql} FROM cleaned").df().iloc[0]
    rules = pd.DataFrame({
        "year": year,
        "rule": list(DQ_RULES),
        "severity": [DQ_RULES[r][0] for r in DQ_RULES],
        "description": [DQ_RULES[r][1] for r in DQ_RULES],
        "n_affected": [int(counts[r]) for r in DQ_RULES],
        "n_total": raw_rows,
    })

    miss_sql = ", ".join(f"sum(CAST({c} IS NULL AS INT)) AS {c}" for c in MISSINGNESS_COLUMNS)
    miss = con.execute(f"SELECT outcome, count(*) AS n_rows, {miss_sql} FROM cleaned GROUP BY outcome").df()
    miss = miss.melt(id_vars=["outcome", "n_rows"], var_name="column", value_name="n_null")
    miss.insert(0, "year", year)

    # Values present in the raw text but not castable to a number (parse failures).
    num_cols = NUMERIC_COLUMNS + ["cancelled", "diverted"]
    cast_sql = ", ".join(
        f"sum(CAST({c} IS NOT NULL AND try_cast({c} AS DOUBLE) IS NULL AS INT)) AS {c}" for c in num_cols
    )
    cast_sql += ", sum(CAST(fl_date IS NOT NULL AND try_cast(fl_date AS DATE) IS NULL AS INT)) AS fl_date"
    cast = con.execute(f"SELECT {cast_sql} FROM stage").df().iloc[0]
    cast_df = pd.DataFrame({"year": year, "column": cast.index, "n_cast_failures": cast.values.astype(int)})

    # Columns that are not part of the expected schema (e.g. the trailing 'Unnamed: 27').
    extras = []
    for col in schema["extra_columns"]:
        q = col.replace('"', '""')
        n = con.execute(
            f"SELECT count(*) FILTER (WHERE NULLIF(TRIM(\"{q}\"), '') IS NOT NULL) "
            f"FROM read_csv('{_quote_path(csv_path)}', all_varchar=true, header=true, null_padding=true)"
        ).fetchone()[0]
        extras.append({"year": year, "column": col, "n_nonempty": int(n)})
    extras_df = pd.DataFrame(extras, columns=["year", "column", "n_nonempty"])

    schema_df = pd.DataFrame([{
        "year": year,
        "n_header_columns": len(schema["header"]),
        "missing_expected": ", ".join(schema["missing_expected"]),
        "extra_columns": ", ".join(schema["extra_columns"]),
    }])

    ranges = con.execute("""
        SELECT min(dep_delay) AS dep_min, quantile_cont(dep_delay, 0.5) AS dep_p50,
               quantile_cont(dep_delay, 0.99) AS dep_p99, max(dep_delay) AS dep_max,
               min(arr_delay) AS arr_min, quantile_cont(arr_delay, 0.5) AS arr_p50,
               quantile_cont(arr_delay, 0.99) AS arr_p99, max(arr_delay) AS arr_max,
               sum(CAST(dep_delay < 0 AS INT)) AS n_negative_dep_delay,
               sum(CAST(arr_delay < 0 AS INT)) AS n_negative_arr_delay,
               min(fl_date) AS first_date, max(fl_date) AS last_date,
               count(DISTINCT op_carrier) AS n_carriers, count(DISTINCT origin) AS n_origins
        FROM cleaned
    """).df()
    ranges.insert(0, "year", year)

    return {"outcomes": outcomes, "rules": rules, "missingness": miss, "cast_failures": cast_df,
            "extras": extras_df, "schema": schema_df, "ranges": ranges}


def collect_coverage(con, flights_dir: Path) -> pd.DataFrame:
    """Rows per calendar month, computed from the cleaned Parquet files already on disk."""
    files = sorted(Path(flights_dir).glob("flights_*.parquet"))
    if not files:
        return pd.DataFrame(columns=["year", "month", "n_rows", "n_included", "n_exact_duplicate"])
    glob = _quote_path(Path(flights_dir) / "flights_*.parquet")
    return con.execute(f"""
        SELECT file_year AS year, month, count(*) AS n_rows,
               sum(CAST(analysis_include AS INT)) AS n_included,
               sum(CAST(dq_exact_duplicate AS INT)) AS n_exact_duplicate
        FROM read_parquet('{glob}') WHERE month IS NOT NULL
        GROUP BY 1, 2 ORDER BY 1, 2
    """).df()


def save_metrics(metrics: dict[str, pd.DataFrame], qdir: Path) -> None:
    """Persist metrics, replacing any previously stored rows for the same year(s)."""
    qdir.mkdir(parents=True, exist_ok=True)
    for name, df in metrics.items():
        path = qdir / f"{name}.csv"
        if path.exists() and not df.empty:
            old = pd.read_csv(path, keep_default_na=False)
            old = old[~old["year"].isin(df["year"].unique())]
            df = pd.concat([old, df], ignore_index=True).sort_values("year", kind="stable")
        df.to_csv(path, index=False)


def _pct(n: float, d: float) -> str:
    return f"{100 * n / d:.3f}%" if d else "n/a"


def render_report(qdir: Path, out_md: Path, sample_note: str = "") -> None:
    """Render docs/data_quality_report.md from the stored metric CSVs."""
    rd = lambda n: pd.read_csv(qdir / f"{n}.csv", keep_default_na=False)  # noqa: E731
    outcomes, rules, miss = rd("outcomes"), rd("rules"), rd("missingness")
    cast, extras, schema, ranges = rd("cast_failures"), rd("extras"), rd("schema"), rd("ranges")
    years = sorted(outcomes["year"].unique())
    L: list[str] = ["# Data Quality Report", ""]
    if sample_note:
        L += [f"> **{sample_note}**", ""]
    L += [
        "Generated by `python -m flightrel.pipeline`; every figure below is computed from the data.",
        "No record is deleted: each rule sets a flag column (`dq_*`) and the cleaned Parquet files",
        "keep all rows. `analysis_include` is FALSE only for the blocking rules listed in section 4.",
        "",
    ]

    # 1. Volumes
    L += ["## 1. Records and outcomes by year", "",
          "| Year | Raw rows | Completed | Cancelled | Diverted | Inconsistent/unknown | Included in analysis | Excluded |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    tot = {k: 0 for k in ("raw", "comp", "canc", "div", "oth", "inc")}
    for y in years:
        o = outcomes[outcomes["year"] == y].set_index("outcome")
        g = lambda k, c="n_rows": int(o[c].get(k, 0))  # noqa: E731
        raw = int(o["raw_rows"].iloc[0])
        oth = g("inconsistent") + g("unknown")
        inc = int(o["n_included"].sum())
        L.append(f"| {y} | {raw:,} | {g('completed'):,} ({_pct(g('completed'), raw)}) | {g('cancelled'):,} "
                 f"({_pct(g('cancelled'), raw)}) | {g('diverted'):,} ({_pct(g('diverted'), raw)}) | {oth:,} | "
                 f"{inc:,} | {raw - inc:,} ({_pct(raw - inc, raw)}) |")
        for k, v in zip(tot, (raw, g("completed"), g("cancelled"), g("diverted"), oth, inc)):
            tot[k] += v
    L.append(f"| **Total** | **{tot['raw']:,}** | {tot['comp']:,} | {tot['canc']:,} | {tot['div']:,} | "
             f"{tot['oth']:,} | {tot['inc']:,} | {tot['raw'] - tot['inc']:,} |")
    L.append("")

    # 2. Schema
    L += ["## 2. Schema consistency across years", "",
          "| Year | Header columns | Missing expected columns | Extra columns |", "|---|---:|---|---|"]
    for _, r in schema.iterrows():
        L.append(f"| {r['year']} | {r['n_header_columns']} | {r['missing_expected'] or 'none'} | "
                 f"{r['extra_columns'] or 'none'} |")
    L.append("")
    if len(extras):
        L += ["Non-empty values found in columns outside the expected schema:", "",
              "| Year | Column | Non-empty cells |", "|---|---|---:|"]
        for _, r in extras.iterrows():
            L.append(f"| {r['year']} | `{r['column']}` | {int(r['n_nonempty']):,} |")
        L.append("")

    # 3. Rules
    L += ["## 3. Rule-level results (all years combined)", "",
          "Severity: **error** = contradiction or blocking rule, **warn** = suspicious but retained, "
          "**info** = expected property reported for transparency.", "",
          "| Rule | Severity | Records affected | % of raw rows | Description |", "|---|---|---:|---:|---|"]
    agg = rules.groupby(["rule", "severity", "description"], sort=False)[["n_affected", "n_total"]].sum().reset_index()
    for _, r in agg.iterrows():
        L.append(f"| `{r['rule']}` | {r['severity']} | {int(r['n_affected']):,} | "
                 f"{_pct(r['n_affected'], r['n_total'])} | {r['description']} |")
    L.append("")
    L += ["### Rule counts by year (records affected; rules with at least one hit)", ""]
    hit = rules[rules["n_affected"] > 0].pivot_table(index="rule", columns="year", values="n_affected",
                                                     aggfunc="sum", fill_value=0)
    if hit.empty:
        L.append("No rule flagged any record.")
    else:
        L.append("| Rule | " + " | ".join(str(c) for c in hit.columns) + " |")
        L.append("|---|" + "---:|" * len(hit.columns))
        for rule, row in hit.iterrows():
            L.append(f"| `{rule}` | " + " | ".join(f"{int(v):,}" for v in row) + " |")
    L.append("")

    # 4. Handling policy
    from .clean import BLOCKING_RULES
    L += ["## 4. Handling policy", "",
          "| Situation | Treatment |", "|---|---|",
          "| Blocking rules: " + ", ".join(f"`{r}`" for r in BLOCKING_RULES) +
          " | Row kept in the cleaned file with `analysis_include = FALSE`; excluded from KPIs and models. |",
          "| Warning rules | Row kept and included; flag available for sensitivity analysis. |",
          "| Negative delays | Preserved (early departures/arrivals). Never clipped or flagged on their own. |",
          "| `2400` in an HHMM field | Interpreted as 00:00 (valid BTS spelling of midnight). |",
          "| Invalid HHMM (hour > 24, minute > 59, non-integer) | Set to NULL and flagged; the raw delay value is kept. |",
          "| Overnight flights | Dates are the scheduled departure date. `sched_dep_ts`/`actual_dep_ts` are built from "
          "date + minutes, so a departure delayed past midnight lands on the next calendar day. "
          "`sched_crosses_midnight` marks flights whose scheduled arrival falls on the next day. |",
          "| Cancelled / diverted flights | Own `outcome` value; kept in the table and excluded only from arrival-delay "
          "classification and arrival-delay KPIs. |",
          "| Missing values on cancelled flights | Expected (no departure/arrival occurred); see section 6. |",
          "| Empty trailing column | Dropped from the cleaned output only after the count in section 2 shows how many cells held data. |",
          ""]

    # 5. Cast failures
    L += ["## 5. Unparseable values (present in the CSV but not castable)", ""]
    cs = cast.groupby("column")["n_cast_failures"].sum()
    cs = cs[cs > 0]
    if cs.empty:
        L.append("No numeric or date field contained a non-numeric / non-date value.")
    else:
        L += ["| Column | Cells | % of raw rows |", "|---|---:|---:|"]
        for col, n in cs.items():
            L.append(f"| `{col}` | {int(n):,} | {_pct(n, tot['raw'])} |")
    L.append("")

    # 6. Missingness
    L += ["## 6. Missing values by outcome (all years combined)", "",
          "Missingness is expected for fields that cannot exist for a given outcome (for example "
          "arrival fields on cancelled flights). Unexpected gaps are those on *completed* flights.", ""]
    mg = miss.groupby(["outcome", "column"])[["n_rows", "n_null"]].sum().reset_index()
    n_by = mg.groupby("outcome")["n_rows"].first()
    cols = [c for c in MISSINGNESS_COLUMNS]
    present = [o for o in OUTCOME_ORDER if o in n_by.index]
    L.append("| Column | " + " | ".join(f"{o} (n={int(n_by[o]):,})" for o in present) + " |")
    L.append("|---|" + "---:|" * len(present))
    for c in cols:
        cells = []
        for o in present:
            row = mg[(mg.outcome == o) & (mg.column == c)]
            n = int(row["n_null"].iloc[0]) if len(row) else 0
            cells.append(_pct(n, n_by[o]))
        L.append(f"| `{c}` | " + " | ".join(cells) + " |")
    L.append("")

    # 7. Calendar coverage
    cov_path = qdir / "coverage.csv"
    L += ["## 7. Calendar coverage (flights per month after removing exact duplicates)", ""]
    if cov_path.exists():
        cov = pd.read_csv(cov_path)
        cov["n_unique"] = cov["n_rows"] - cov["n_exact_duplicate"]
        grid = cov.pivot_table(index="year", columns="month", values="n_unique", aggfunc="sum")
        grid = grid.reindex(columns=range(1, 13))
        gaps = [(int(y), int(m)) for y in grid.index for m in grid.columns if pd.isna(grid.loc[y, m])]
        L.append("| Year | " + " | ".join(f"{m:02d}" for m in grid.columns) + " |")
        L.append("|---|" + "---:|" * 12)
        for y, r in grid.iterrows():
            L.append(f"| {int(y)} | " + " | ".join("**MISSING**" if pd.isna(v) else f"{int(v):,}" for v in r) + " |")
        L.append("")
        if gaps:
            L.append("**Months with no records at all:** " + ", ".join(f"{y}-{m:02d}" for y, m in gaps) +
                     ". Annual KPIs for these years cover fewer than 12 months and are not comparable "
                     "with complete years without a seasonal adjustment or a matched-month comparison.")
        dm = cov[cov["n_exact_duplicate"] > 0]
        if len(dm):
            L.append("")
            L.append("**Months containing exact duplicates:** " + "; ".join(
                f"{int(r.year)}-{int(r.month):02d} ({int(r.n_exact_duplicate):,} of {int(r.n_rows):,} rows, "
                f"{100 * r.n_exact_duplicate / r.n_rows:.1f}%)" for r in dm.itertuples()) + ".")
    else:
        L.append("Coverage table not available.")
    L.append("")

    # 8. Ranges
    L += ["## 8. Delay ranges and date coverage by year", "",
          "| Year | First date | Last date | Dep delay min / p50 / p99 / max | Arr delay min / p50 / p99 / max | "
          "Carriers | Origins |", "|---|---|---|---|---|---:|---:|"]
    for _, r in ranges.iterrows():
        L.append(f"| {r['year']} | {str(r['first_date'])[:10]} | {str(r['last_date'])[:10]} | "
                 f"{r['dep_min']:.0f} / {r['dep_p50']:.0f} / {r['dep_p99']:.0f} / {r['dep_max']:.0f} | "
                 f"{r['arr_min']:.0f} / {r['arr_p50']:.0f} / {r['arr_p99']:.0f} / {r['arr_max']:.0f} | "
                 f"{int(r['n_carriers'])} | {int(r['n_origins'])} |")
    L.append("")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(L), encoding="utf-8")
