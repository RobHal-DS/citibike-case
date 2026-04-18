"""
Download CitiBike 2025 trip data and NYPD Motor Vehicle Collision data.

Downloads:
  - 12 monthly CitiBike trip ZIPs from S3 (~8 GB total)
  - NYPD Motor Vehicle Collisions — Crashes table (h9gi-nx95)
  - NYPD Motor Vehicle Collisions — Vehicles table (bm4k-52h4)

Usage:
    python src/data/download.py
    # or
    make data
"""

from pathlib import Path

import requests
from tqdm import tqdm

RAW_DIR = Path(__file__).parents[2] / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# CitiBike monthly ZIPs on S3 (no annual archive for 2025)
CITIBIKE_YEAR = 2025
CITIBIKE_BASE_URL = "https://s3.amazonaws.com/tripdata"

# NYC Open Data Socrata exports — Motor Vehicle Collisions
NYPD_CRASHES_URL = (
    "https://data.cityofnewyork.us/api/views/h9gi-nx95/rows.csv"
    "?accessType=DOWNLOAD"
)
NYPD_VEHICLES_URL = (
    "https://data.cityofnewyork.us/api/views/bm4k-52h4/rows.csv"
    "?accessType=DOWNLOAD"
)


def download_file(url: str, dest: Path, desc: str) -> None:
    if dest.exists():
        print(f"  [skip] {dest.name} already exists")
        return
    print(f"  Downloading {desc} → {dest.name}")
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    with open(dest, "wb") as f, tqdm(
        total=total, unit="B", unit_scale=True, desc=dest.name, leave=False
    ) as bar:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
            bar.update(len(chunk))
    size_mb = dest.stat().st_size / 1e6
    print(f"  ✓ {dest.name}  ({size_mb:.1f} MB)")


def download_citibike() -> None:
    print(f"\n=== CitiBike {CITIBIKE_YEAR} Trip Data (12 monthly files) ===")
    for month in range(1, 13):
        filename = f"{CITIBIKE_YEAR}{month:02d}-citibike-tripdata.zip"
        url = f"{CITIBIKE_BASE_URL}/{filename}"
        dest = RAW_DIR / filename
        download_file(url, dest, f"CitiBike {CITIBIKE_YEAR}-{month:02d}")


def download_nypd() -> None:
    print("\n=== NYPD Motor Vehicle Collisions — Crashes ===")
    dest_crashes = RAW_DIR / "nypd_motor_vehicle_collisions.csv"
    download_file(NYPD_CRASHES_URL, dest_crashes, "NYPD crashes (full history)")

    print("\n=== NYPD Motor Vehicle Collisions — Vehicles ===")
    dest_vehicles = RAW_DIR / "nypd_motor_vehicle_collisions_vehicles.csv"
    download_file(NYPD_VEHICLES_URL, dest_vehicles, "NYPD vehicles (full history)")


def main() -> None:
    print(f"Saving raw data to: {RAW_DIR.resolve()}")
    download_citibike()
    download_nypd()
    print("\nAll downloads complete.")
    print("Next: run notebooks in order, starting with 01_eda_citibike.ipynb")


if __name__ == "__main__":
    main()
