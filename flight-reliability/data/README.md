# Data

The raw files are **not** stored in this repository (about 7 GB in total).

**Data source:** Mu, Yuanyuwendy, *Airline Delay and Cancellation Data, 2009–2018*, Kaggle.
https://www.kaggle.com/datasets/yuanyuwendymu/airline-delay-and-cancellation-data-2009-2018

## Download

Option 1 — browser: download the archive from the Kaggle page above and extract
`2009.csv` … `2018.csv` into `data/raw/` (or any folder you point the pipeline at).

Option 2 — Kaggle CLI (requires your own Kaggle API token in `%USERPROFILE%\.kaggle\kaggle.json`; never commit it):

```powershell
kaggle datasets download -d yuanyuwendymu/airline-delay-and-cancellation-data-2009-2018 -p data/raw --unzip
```

## Run the pipeline

```powershell
python -m flightrel.pipeline --raw-dir data/raw          # all years
python -m flightrel.pipeline --raw-dir data/raw --years 2018 --limit-rows 300000 --sample   # smoke test
```

Outputs (all git-ignored): `data/processed/flights/flights_<year>.parquet` and
`data/processed/quality/*.csv`. The human-readable report is written to `docs/data_quality_report.md`.
