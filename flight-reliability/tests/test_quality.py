"""Tests for quality metrics, coverage detection and report rendering."""
from __future__ import annotations

from flightrel import clean, quality
from conftest import row, write_csv


def _run(tmp_path, cfg, rows, year=2015):
    con = clean.connect(cfg)
    csv_path = write_csv(tmp_path / f"{year}.csv", rows)
    schema = clean.clean_year(con, csv_path, year, tmp_path / "flights" / f"flights_{year}.parquet", cfg)
    return con, csv_path, schema


def test_coverage_detects_missing_month_and_duplicated_month(tmp_path, cfg):
    jan, feb, mar = (row(FL_DATE=f"2015-0{m}-10", OP_CARRIER_FL_NUM=str(m)) for m in (1, 2, 3))
    # February is written twice (exact duplicate); April..December are absent.
    con, _, _ = _run(tmp_path, cfg, [jan, feb, feb, mar])
    cov = quality.collect_coverage(con, tmp_path / "flights")
    by_month = cov.set_index("month")
    assert sorted(by_month.index) == [1, 2, 3]
    assert by_month.loc[2, "n_rows"] == 2 and by_month.loc[2, "n_exact_duplicate"] == 1
    assert by_month.loc[1, "n_exact_duplicate"] == 0


def test_metrics_count_every_rule_and_outcome(tmp_path, cfg):
    rows = [row(), row(OP_CARRIER_FL_NUM="2", CANCELLED="1.0", CANCELLATION_CODE="A", ARR_DELAY="", ARR_TIME=""),
            row(OP_CARRIER_FL_NUM="3", DIVERTED="1.0", ARR_DELAY="", ARR_TIME="")]
    con, csv_path, schema = _run(tmp_path, cfg, rows)
    m = quality.collect_year_metrics(con, 2015, csv_path, schema)
    out = m["outcomes"].set_index("outcome")["n_rows"].to_dict()
    assert out == {"completed": 1, "cancelled": 1, "diverted": 1}
    assert (m["rules"]["n_total"] == 3).all()
    assert set(m["rules"]["rule"]) == set(clean.DQ_RULES)
    assert m["extras"]["n_nonempty"].tolist() == [0]  # the trailing 'Unnamed: 27' column is empty


def test_report_renders_from_saved_metrics(tmp_path, cfg):
    con, csv_path, schema = _run(tmp_path, cfg, [row(), row(OP_CARRIER_FL_NUM="2")])
    qdir = tmp_path / "quality"
    quality.save_metrics(quality.collect_year_metrics(con, 2015, csv_path, schema), qdir)
    quality.collect_coverage(con, tmp_path / "flights").to_csv(qdir / "coverage.csv", index=False)
    out = tmp_path / "report.md"
    quality.render_report(qdir, out)
    text = out.read_text(encoding="utf-8")
    assert "Calendar coverage" in text and "**MISSING**" in text  # only March present
    assert "| 2015 | 2 |" in text
