"""Run the named SQL KPI queries in sql/kpis.sql against the cleaned Parquet files."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .clean import _quote_path
from .config import PROJECT_ROOT

SQL_FILE = PROJECT_ROOT / "sql" / "kpis.sql"
LATE_MIN = 15
MIN_STABLE_FLIGHTS = 10_000  # per year, for a carrier to count as continuously reporting

SCOPES = {
    "all": "TRUE",
    "matched_months": "matched_month",
    "stable_matched": "matched_month AND stable",
}


def load_queries(path: Path = SQL_FILE) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^-- name: (\w+)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def connect_views(con, flights_dir: Path, n_years: int = 10) -> None:
    glob = _quote_path(Path(flights_dir) / "flights_*.parquet")
    con.execute(f"""
        CREATE OR REPLACE VIEW stable_carriers AS
        SELECT op_carrier FROM (
            SELECT op_carrier, year, count(*) AS n FROM read_parquet('{glob}') WHERE analysis_include
            GROUP BY 1, 2 HAVING count(*) >= {MIN_STABLE_FLIGHTS})
        GROUP BY op_carrier HAVING count(*) = {n_years}
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW f AS
        SELECT p.*,
               CASE WHEN outcome = 'completed' AND arr_delay IS NOT NULL THEN arr_delay >= {LATE_MIN} END AS arr_late,
               CASE WHEN outcome <> 'cancelled' AND dep_delay IS NOT NULL THEN dep_delay >= {LATE_MIN} END AS dep_late,
               month NOT IN (7, 10) AS matched_month,
               op_carrier IN (SELECT op_carrier FROM stable_carriers) AS stable
        FROM read_parquet('{glob}') p WHERE analysis_include
    """)


def run(con, name: str, scope: str = "all", dims: str = "year", having: str = "", **params) -> pd.DataFrame:
    sql = load_queries()[name]
    where = SCOPES.get(scope, scope)
    sql = sql.replace("{where}", where).replace("{dims}", dims).replace("{having}", having)
    for k, v in params.items():
        sql = sql.replace("{" + k + "}", str(v))
    return con.execute(sql).df()
