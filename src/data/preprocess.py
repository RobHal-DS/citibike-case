"""
Preprocess raw data into analysis-ready parquet files.

Produces:
  - data/processed/nypd_2025.parquet          (all 2025 crashes, coord-filtered)
  - data/processed/nypd_bike_2025.parquet      (bicycle-involved subset)
  - data/processed/stations.parquet            (deduplicated CitiBike stations)

Usage:
    python src/data/preprocess.py
    # or
    make preprocess
"""

import zipfile
from pathlib import Path

import polars as pl

RAW_DIR = Path(__file__).parents[2] / "data" / "raw"
PROC_DIR = Path(__file__).parents[2] / "data" / "processed"
PROC_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# NYPD Motor Vehicle Collisions
# ---------------------------------------------------------------------------

def preprocess_nypd() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Load, join vehicles table, filter to 2025, return (all, bike) frames."""
    CRASH_COLS = [
        "CRASH DATE", "CRASH TIME", "BOROUGH",
        "LATITUDE", "LONGITUDE",
        "NUMBER OF PERSONS INJURED", "NUMBER OF PERSONS KILLED",
        "NUMBER OF CYCLIST INJURED", "NUMBER OF CYCLIST KILLED",
        "VEHICLE TYPE CODE 1", "VEHICLE TYPE CODE 2",
        "CONTRIBUTING FACTOR VEHICLE 1",
        "COLLISION_ID",
    ]
    nypd = pl.read_csv(
        RAW_DIR / "nypd_motor_vehicle_collisions.csv",
        columns=CRASH_COLS,
        infer_schema_length=10_000,
    )
    print(f"Total NYPD crash records: {len(nypd):,}")

    # Vehicles table — flag collisions involving a bicycle/ebike
    vehicles = pl.read_csv(
        RAW_DIR / "nypd_motor_vehicle_collisions_vehicles.csv",
        columns=["COLLISION_ID", "VEHICLE_TYPE"],
        infer_schema_length=10_000,
    )
    bike_vehicle_ids = (
        vehicles
        .filter(
            pl.col("VEHICLE_TYPE").fill_null("")
            .str.to_lowercase().str.contains("bicycle|bike")
        )
        .select("COLLISION_ID")
        .unique()
        .with_columns(pl.lit(True).alias("has_bike_vehicle"))
    )
    nypd = nypd.join(bike_vehicle_ids, on="COLLISION_ID", how="left")
    nypd = nypd.with_columns(pl.col("has_bike_vehicle").fill_null(False))

    # Combine CRASH DATE + CRASH TIME into a full datetime.
    # Pad CRASH TIME to HH:MM — raw data uses unpadded hours ("0:34", "8:01")
    # which %H cannot parse, silently producing nulls for hours 0–9.
    nypd = nypd.with_columns(
        (pl.col("CRASH DATE") + " " + pl.col("CRASH TIME").fill_null("00:00").str.pad_start(5, "0"))
        .str.to_datetime("%m/%d/%Y %H:%M", strict=False)
        .alias("crash_dt")
    )
    nypd_2025 = nypd.filter(pl.col("crash_dt").dt.year() == 2025)

    # Drop rows without usable coordinates
    nypd_2025 = nypd_2025.drop_nulls(subset=["LATITUDE", "LONGITUDE"])
    nypd_2025 = nypd_2025.filter(
        pl.col("LATITUDE").is_between(40.4, 40.95)
        & pl.col("LONGITUDE").is_between(-74.3, -73.6)
    )
    print(f"2025 records after coord filter: {len(nypd_2025):,}")

    # Bicycle-involved subset
    bike_mask = (
        pl.col("has_bike_vehicle")
        | pl.col("VEHICLE TYPE CODE 1").fill_null("").str.to_uppercase().str.contains("BIKE|BICYCLE|CYCLIST|E-BIK")
        | pl.col("VEHICLE TYPE CODE 2").fill_null("").str.to_uppercase().str.contains("BIKE|BICYCLE|CYCLIST|E-BIK")
        | (pl.col("NUMBER OF CYCLIST INJURED").fill_null(0) > 0)
        | (pl.col("NUMBER OF CYCLIST KILLED").fill_null(0) > 0)
    )
    nypd_bike = nypd_2025.filter(bike_mask)
    print(f"Bicycle-involved crashes (2025): {len(nypd_bike):,}")

    return nypd_2025, nypd_bike


# ---------------------------------------------------------------------------
# CitiBike Stations (deduplicated)
# ---------------------------------------------------------------------------

def preprocess_stations() -> pl.DataFrame:
    """Build a deduplicated station table from monthly trip ZIPs."""
    COLS = ["start_station_id", "start_station_name", "start_lat", "start_lng"]
    SCHEMA = {"start_station_id": pl.String}

    files = sorted(RAW_DIR.glob("2025??-citibike-tripdata.zip"))
    if not files:
        raise FileNotFoundError("No CitiBike ZIPs found. Run `make data` first.")

    dfs = []
    for f in files:
        with zipfile.ZipFile(f) as zf:
            with zf.open(zf.namelist()[0]) as csv_file:
                dfs.append(pl.read_csv(csv_file, columns=COLS, schema_overrides=SCHEMA))

    raw = pl.concat(dfs)

    # First pass: one row per station_id (median coords, first name)
    by_id = (
        raw
        .drop_nulls(subset=["start_station_id", "start_lat", "start_lng"])
        .group_by("start_station_id")
        .agg([
            pl.col("start_station_name").first().alias("name"),
            pl.col("start_lat").median().alias("latitude"),
            pl.col("start_lng").median().alias("longitude"),
        ])
    )

    # Second pass: deduplicate by name (multiple IDs can map to same
    # physical station, e.g. dock expansions or re-registrations)
    stations = (
        by_id
        .group_by("name")
        .agg([
            pl.col("start_station_id").first().alias("station_id"),
            pl.col("latitude").median(),
            pl.col("longitude").median(),
        ])
    )
    print(f"Unique stations (deduplicated by name): {len(stations):,}")
    return stations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Preprocessing NYPD data ===")
    nypd_2025, nypd_bike = preprocess_nypd()
    nypd_2025.write_parquet(PROC_DIR / "nypd_2025.parquet")
    nypd_bike.write_parquet(PROC_DIR / "nypd_bike_2025.parquet")
    print(f"Saved {len(nypd_2025):,} total + {len(nypd_bike):,} bike crashes\n")

    print("=== Preprocessing CitiBike stations ===")
    stations = preprocess_stations()
    stations.write_parquet(PROC_DIR / "stations.parquet")
    print(f"Saved {len(stations):,} stations\n")

    print("All preprocessing complete.")


if __name__ == "__main__":
    main()
