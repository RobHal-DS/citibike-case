# CitiBike × AXA: Usage-Based Micro-Insurance

Dynamic per-ride accident insurance for CitiBike, priced by station risk, time of day, and rider type. See **[RESULTS.md](RESULTS.md)** for approach, model, and business case.

## Repo Structure

```
├── notebooks/
│   ├── 01_eda_citibike.ipynb       # Trip patterns, rider segments
│   ├── 02_eda_nypd.ipynb           # Accident hotspots, bicycle incidents
│   ├── 03_spatial_analysis.ipynb   # Station risk scoring + interactive map ← start here
│   └── 04_risk_model.ipynb         # Formula-based risk model, premium calc, business case
├── src/
│   ├── data/download.py            # Download raw data
│   ├── features/risk_features.py   # Spatial join, feature engineering
│   └── visualization/maps.py       # Folium map helpers
├── data/                           # gitignored — see below
├── outputs/figures/                # Saved charts and maps
├── RESULTS.md                      # Approach, model, and business case ← start here
└── pyproject.toml
```

## How to Run

```bash
# 1. Install dependencies (requires uv — https://docs.astral.sh/uv/)
make install        # or: uv sync

# 2. Download raw data (~9 GB total, may take a while)
make data           # CitiBike 2025 trip ZIPs + NYPD collision CSVs

# 3. Preprocess into analysis-ready parquets
make preprocess     # → data/processed/*.parquet (stations, NYPD crashes)

# 4. Run notebooks in order
uv run jupyter lab
# Open notebooks/ and run 01 → 02 → 03 → 04
```

| Make target | What it does |
|---|---|
| `make install` | Install Python dependencies via uv |
| `make data` | Download raw CitiBike + NYPD data |
| `make preprocess` | Build station table + filter/geocode NYPD crashes |
| `make notebooks` | Execute all notebooks non-interactively |
| `make clean` | Remove all generated data, figures, and caches |

> **Data note:** Raw and processed data are gitignored. `make data` downloads CitiBike 2025 monthly trip files from the public S3 bucket, plus NYPD collision data (Crashes + Vehicles tables) from NYC Open Data.

## Dependencies

Python 3.12+. Key packages: `polars`, `geopandas`, `folium`, `plotly`, `seaborn`. See [`pyproject.toml`](pyproject.toml) for full list.

## Author

Robert — AXA Deutschland Data Science Team Lead interview case study, April 2026.
