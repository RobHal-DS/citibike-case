"""Folium map helpers for risk visualization."""

import folium
from folium.plugins import HeatMap
import geopandas as gpd


def risk_color(score: float, low_threshold: float = 0.33, high_threshold: float = 0.66) -> str:
    """Map a normalized risk score [0, 1] to a hex color (green → yellow → red)."""
    if score < low_threshold:
        return "#2ecc71"
    if score < high_threshold:
        return "#f39c12"
    return "#e74c3c"


def make_risk_map(
    stations_gdf: gpd.GeoDataFrame,
    accidents_gdf: gpd.GeoDataFrame | None = None,
    center: tuple[float, float] = (40.7128, -74.0060),
    zoom: int = 12,
    low_threshold: float = 0.33,
    high_threshold: float = 0.66,
) -> folium.Map:
    """
    Build a Folium map with:
      - Circle markers per station, coloured by risk_score
      - Optional NYPD accident heatmap layer
    """
    m = folium.Map(location=center, zoom_start=zoom, tiles="CartoDB positron")

    if accidents_gdf is not None:
        heat_data = [
            [row.geometry.y, row.geometry.x]
            for _, row in accidents_gdf.iterrows()
            if row.geometry is not None
        ]
        HeatMap(heat_data, name="NYPD Accident Density", radius=10, blur=15).add_to(m)

    risk_groups = {
        "Low Risk": folium.FeatureGroup(name="🟢 Low Risk", show=True),
        "Medium Risk": folium.FeatureGroup(name="🟠 Medium Risk", show=True),
        "High Risk": folium.FeatureGroup(name="🔴 High Risk", show=True),
    }

    for _, row in stations_gdf.iterrows():
        if row.geometry is None:
            continue
        score = row.get("risk_score", 0)
        color = risk_color(score, low_threshold, high_threshold)
        if score < low_threshold:
            group = risk_groups["Low Risk"]
        elif score < high_threshold:
            group = risk_groups["Medium Risk"]
        else:
            group = risk_groups["High Risk"]
        tooltip = (
            f"<b>{row.get('name', 'Station')}</b><br>"
            f"Risk Score: {score:.2f}<br>"
            f"Accidents (250m): {int(row.get('accident_count', 0))}<br>"
            f"Bike Accident Rate: {row.get('bike_accident_rate', 0):.1%}"
        )
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=6 + score * 10,
            color=color,
            fill=True,
            fill_opacity=0.75,
            tooltip=tooltip,
        ).add_to(group)

    for group in risk_groups.values():
        group.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m
