"""Command-line entry point: raw CSVs -> cleaned Parquet + data quality report.

    python -m flightrel.pipeline --raw-dir <folder with 2009.csv ... 2018.csv>
    python -m flightrel.pipeline --raw-dir <folder> --years 2009 --limit-rows 200000 --sample
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from . import clean, quality
from .config import PROJECT_ROOT, load_config


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir", type=Path, help="Folder containing the yearly CSV files")
    ap.add_argument("--years", type=int, nargs="*", help="Subset of years (default: all in config)")
    ap.add_argument("--limit-rows", type=int, help="Read only the first N rows of each file (smoke test)")
    ap.add_argument("--report-only", action="store_true",
                    help="Rebuild coverage and the report from existing outputs without re-cleaning")
    ap.add_argument("--sample", action="store_true",
                    help="Write to data/processed_sample and docs/data_quality_report_sample.md")
    args = ap.parse_args(argv)

    cfg = load_config()
    raw_dir = args.raw_dir or cfg["paths"]["raw_dir"]
    years = args.years or cfg["years"]
    proc = cfg["paths"]["processed_dir"]
    report = PROJECT_ROOT / "docs" / "data_quality_report.md"
    if args.sample:
        proc = proc.parent / "processed_sample"
        report = PROJECT_ROOT / "docs" / "data_quality_report_sample.md"

    missing = [y for y in years if not (Path(raw_dir) / f"{y}.csv").exists()]
    if args.report_only:
        years, missing = [], []
    if missing:
        print(f"Missing input files for {missing} in {raw_dir}.\n"
              "See data/README.md for download instructions.")
        return 1

    con = clean.connect(cfg, cfg["paths"]["interim_dir"])
    for y in years:
        t0 = time.time()
        csv_path = Path(raw_dir) / f"{y}.csv"
        out = proc / "flights" / f"flights_{y}.parquet"
        schema = clean.clean_year(con, csv_path, y, out, cfg, args.limit_rows)
        metrics = quality.collect_year_metrics(con, y, csv_path, schema)
        quality.save_metrics(metrics, proc / "quality")
        n = metrics["outcomes"]["raw_rows"].iloc[0]
        print(f"{y}: {n:,} rows -> {out.name} ({time.time() - t0:.0f}s)", flush=True)

    cov = quality.collect_coverage(con, proc / "flights")
    cov.to_csv(proc / "quality" / "coverage.csv", index=False)

    note = ""
    if args.limit_rows:
        note = f"SAMPLE RUN: only the first {args.limit_rows:,} rows of each file were processed. Not final."
    quality.render_report(proc / "quality", report, note)
    print(f"Report written: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
