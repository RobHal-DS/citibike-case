"""
Shared feature engineering utilities used across notebooks 03 and 04.
"""

import numpy as np
import polars as pl
import geopandas as gpd


def haversine_km(lat1, lon1, lat2, lon2):
    """Vectorized haversine distance in kilometers."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def stations_to_geodataframe(stations_df: pl.DataFrame) -> gpd.GeoDataFrame:
    """Convert a Polars DataFrame with lat/lon columns to a GeoDataFrame (WGS84)."""
    pdf = stations_df.to_pandas()
    geometry = gpd.points_from_xy(pdf["longitude"], pdf["latitude"])
    return gpd.GeoDataFrame(pdf, geometry=geometry, crs="EPSG:4326")


def accidents_to_geodataframe(accidents_df: pl.DataFrame) -> gpd.GeoDataFrame:
    """Convert NYPD collisions Polars DataFrame to GeoDataFrame, dropping rows without coords."""
    pdf = (
        accidents_df
        .filter(
            pl.col("LATITUDE").is_not_null()
            & pl.col("LONGITUDE").is_not_null()
            & (pl.col("LATITUDE") != 0)
            & (pl.col("LONGITUDE") != 0)
        )
        .to_pandas()
    )
    geometry = gpd.points_from_xy(pdf["LONGITUDE"], pdf["LATITUDE"])
    return gpd.GeoDataFrame(pdf, geometry=geometry, crs="EPSG:4326")


def compute_station_risk_scores(
    stations_gdf: gpd.GeoDataFrame,
    accidents_gdf: gpd.GeoDataFrame,
    buffer_m: float = 250.0,
) -> gpd.GeoDataFrame:
    """
    For each station, count NYPD accidents within `buffer_m` meters.
    The risk score is bike-focused: cyclist injuries and bike accident counts
    dominate the composite, since we're pricing a per-ride bike insurance.

    Returns stations_gdf with added columns:
      - accident_count: total collisions within buffer
      - bike_accident_count: collisions involving a bicycle
      - cyclist_injuries: sum of cyclist injured + killed within buffer
      - total_injuries: sum of all persons injured within buffer
      - bike_severity: cyclist injuries per bike accident (0 if none)
      - severity_score: all injuries per accident (kept for reference)
      - bike_accident_rate: bike accidents / total accidents
      - risk_score: normalised composite score [0, 1]
    """
    # Reproject to a meter-based CRS for accurate buffering
    stations_m = stations_gdf.to_crs("EPSG:3857")
    accidents_m = accidents_gdf.to_crs("EPSG:3857")

    stations_buffered = stations_m.copy()
    stations_buffered["geometry"] = stations_m.geometry.buffer(buffer_m)

    joined = gpd.sjoin(accidents_m, stations_buffered, how="inner", predicate="within")

    # Bike flag: use Vehicles table flag (has_bike_vehicle) if available,
    # fall back to free-text VEHICLE TYPE CODE 1 from Crashes table
    if "has_bike_vehicle" in joined.columns:
        is_bike = joined["has_bike_vehicle"].fillna(False) | (
            joined["VEHICLE TYPE CODE 1"]
            .str.upper()
            .str.contains("BIKE|BICYCLE|CYCLIST", na=False)
        )
    else:
        is_bike = (
            joined["VEHICLE TYPE CODE 1"]
            .str.upper()
            .str.contains("BIKE|BICYCLE|CYCLIST", na=False)
        )
    joined = joined.assign(_is_bike=is_bike)

    # Compute cyclist injuries per crash (injured + killed)
    joined = joined.assign(
        _cyclist_injuries=(
            joined["NUMBER OF CYCLIST INJURED"].fillna(0)
            + joined["NUMBER OF CYCLIST KILLED"].fillna(0)
        )
    )

    agg = (
        joined.groupby("index_right")
        .agg(
            accident_count=("COLLISION_ID", "count"),
            bike_accident_count=("_is_bike", "sum"),
            cyclist_injuries=("_cyclist_injuries", "sum"),
            total_injuries=("NUMBER OF PERSONS INJURED", "sum"),
        )
        .reset_index()
        .rename(columns={"index_right": "station_idx"})
    )

    result = stations_gdf.copy().reset_index(drop=True)
    result = result.merge(agg, left_index=True, right_on="station_idx", how="left")
    result[["accident_count", "bike_accident_count", "cyclist_injuries", "total_injuries"]] = (
        result[["accident_count", "bike_accident_count", "cyclist_injuries", "total_injuries"]].fillna(0)
    )

    # Bike-specific severity: cyclist injuries per bike accident
    result["bike_severity"] = np.where(
        result["bike_accident_count"] > 0,
        result["cyclist_injuries"] / result["bike_accident_count"],
        0,
    )
    # General severity kept for reference
    result["severity_score"] = np.where(
        result["accident_count"] > 0,
        result["total_injuries"] / result["accident_count"],
        0,
    )
    result["bike_accident_rate"] = np.where(
        result["accident_count"] > 0,
        result["bike_accident_count"] / result["accident_count"],
        0,
    )

    # Composite risk: bike-focused weighted sum, min-max normalized to [0, 1]
    # Weights reflect that for a per-ride bike insurance, cyclist-specific
    # metrics matter most, with general accident density as context signal.
    raw = (
        0.4 * result["bike_accident_count"]
        + 0.4 * result["cyclist_injuries"]
        + 0.2 * result["accident_count"]
    )
    rmin, rmax = raw.min(), raw.max()
    result["risk_score"] = (raw - rmin) / (rmax - rmin) if rmax > rmin else 0.0

    return result


def add_trip_features(trips_df: pl.DataFrame) -> pl.DataFrame:
    """Add time features known at ride start to a trips Polars DataFrame."""
    df = trips_df
    if df["started_at"].dtype == pl.String:
        df = df.with_columns(pl.col("started_at").str.to_datetime(strict=False))

    df = df.with_columns([
        pl.col("started_at").dt.hour().alias("hour_of_day"),
        pl.col("started_at").dt.weekday().alias("day_of_week"),
        pl.col("started_at").dt.month().alias("month"),
        (
            pl.col("started_at").dt.hour().is_between(7, 9)
            | pl.col("started_at").dt.hour().is_between(17, 19)
        ).cast(pl.Int8).alias("is_rush_hour"),
        (pl.col("member_casual") == "casual").cast(pl.Int8).alias("user_type_encoded"),
    ])
    return df


def compute_temporal_multiplier(nypd_bike_df: pl.DataFrame) -> pl.DataFrame:
    """Compute hour x day-of-week accident risk multiplier from NYPD bike crash data.

    Each (hour, dow) cell gets a multiplier relative to the mean crash count.
    A multiplier of 2.0 means twice the average accident frequency.

    Args:
        nypd_bike_df: NYPD bike crash DataFrame with 'crash_dt' (datetime) column
            and optionally a pre-computed 'hour' column (from CRASH TIME).
            If 'hour' exists, it is used as-is; otherwise hour is extracted
            from crash_dt (which may lack time info if parsed from CRASH DATE only).

    Returns:
        Polars DataFrame with columns: hour, dow, accident_count, temporal_multiplier.
    """
    # crash_dt is often date-only (midnight) — use pre-computed 'hour' from CRASH TIME if available
    if "hour" not in nypd_bike_df.columns:
        nypd_bike_df = nypd_bike_df.with_columns(
            pl.col("crash_dt").dt.hour().alias("hour")
        )
    nypd_bike_df = nypd_bike_df.with_columns(
        pl.col("crash_dt").dt.weekday().alias("dow"),
    )
    nypd_bike_df = nypd_bike_df.drop_nulls(subset=["hour", "dow"])
    temporal_counts = (
        nypd_bike_df.group_by(["hour", "dow"]).len()
        .rename({"len": "accident_count"})
    )

    # Ensure all 168 hour×dow bins exist (0-23 × 1-7).
    # Hours with zero recorded crashes (e.g. 0-9 AM) would otherwise be missing,
    # causing a fill_null(1.0) downstream that incorrectly treats "no data" as
    # "average risk" instead of "low risk".
    full_grid = pl.DataFrame({
        "hour": [h for h in range(24) for _ in range(1, 8)],
        "dow":  [d for _ in range(24) for d in range(1, 8)],
    }).cast({"hour": temporal_counts["hour"].dtype, "dow": temporal_counts["dow"].dtype})

    temporal_counts = (
        full_grid
        .join(temporal_counts, on=["hour", "dow"], how="left")
        .with_columns(pl.col("accident_count").fill_null(0))
    )

    mean_count = temporal_counts["accident_count"].mean()
    temporal_counts = temporal_counts.with_columns(
        (pl.col("accident_count") / mean_count).alias("temporal_multiplier")
    )
    return temporal_counts


def compute_rider_multiplier(trips_df: pl.DataFrame) -> dict[str, float]:
    """Compute rider type multiplier from median trip duration ratio.

    Casual riders take longer trips than members, implying higher exposure.
    The multiplier is the ratio of each type's median duration to the overall median.

    Args:
        trips_df: Trips DataFrame with 'started_at', 'ended_at', and 'member_casual' columns.

    Returns:
        Dict mapping rider type to multiplier, e.g. {'casual': 1.32, 'member': 0.87}.
    """
    trips_with_dur = trips_df.with_columns(
        ((pl.col("ended_at") - pl.col("started_at")).dt.total_seconds() / 60.0).alias("dur_min")
    )
    overall_median = trips_with_dur["dur_min"].median()
    duration_by_type = (
        trips_with_dur
        .group_by("member_casual")
        .agg(pl.col("dur_min").median().alias("median_dur"))
    )
    durations = dict(zip(
        duration_by_type["member_casual"].to_list(),
        duration_by_type["median_dur"].to_list(),
    ))
    return {k: v / overall_median for k, v in durations.items()}
