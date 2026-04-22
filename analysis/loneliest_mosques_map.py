"""
Render 'The Loneliest Mosques in America' map.

Input:  data/mosques_google_*.json
Output: results/loneliest_mosques_map.png
"""

import glob
import json
import os
import sys

import matplotlib.pyplot as plt
import requests
from matplotlib import patheffects
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon as MplPolygon
from pyproj import Transformer

KM_TO_MI = 0.621371

# EPSG:5070 — NAD83 / Conus Albers. Equal-area projection optimized for CONUS.
# EPSG:3338 — NAD83 / Alaska Albers.
# Hawaii inset stays in equirectangular because at Hawaii's small spatial extent
# the distortion is negligible and a single projection across insets would be
# awkward.
PROJ_CONUS = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
PROJ_ALASKA = Transformer.from_crs("EPSG:4326", "EPSG:3338", always_xy=True)


def project(transformer, lon, lat):
    x, y = transformer.transform(lon, lat)
    return x, y

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seed_mosques_google import haversine_m


MOSQUE_DOT_COLOR = "#0891b2"
LONELY_COLOR = "#dc2626"
STATE_FILL = "#fafafa"
STATE_EDGE = "#2f2f2f"

CONTIGUOUS_BBOX = (-125, -66.5, 24, 50)
ALASKA_BBOX = (-170, -130, 54, 72)
HAWAII_BBOX = (-160.5, -154, 18.5, 22.5)


def load_mosques():
    mosques = []
    for f in sorted(glob.glob("data/mosques_google_*.json")):
        region = os.path.basename(f).replace("mosques_google_", "").replace(".json", "")
        if region == "chicagoland":
            continue
        with open(f, encoding="utf-8") as fp:
            mosques.extend(json.load(fp))
    return mosques


def compute_nearest_neighbors(mosques):
    for m in mosques:
        best_d = float("inf")
        best_other = None
        for other in mosques:
            if other is m:
                continue
            d = haversine_m(m["lat"], m["lon"], other["lat"], other["lon"])
            if d < best_d:
                best_d, best_other = d, other
        m["_nearest_km"] = best_d / 1000
        m["_nearest"] = best_other


def city_from_mosque(m):
    if m.get("city"):
        return m["city"]
    addr = m.get("address", "")
    parts = [p.strip() for p in addr.split(",")]
    return parts[-3] if len(parts) >= 3 else "?"


def load_us_states_geojson():
    url = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def plot_states(ax, gj, bbox, transformer=None):
    west, east, south, north = bbox
    patches = []
    for feature in gj["features"]:
        geom = feature["geometry"]
        if geom["type"] == "Polygon":
            polys = [geom["coordinates"]]
        elif geom["type"] == "MultiPolygon":
            polys = geom["coordinates"]
        else:
            continue
        for poly in polys:
            ring = poly[0]
            lons = [p[0] for p in ring]
            lats = [p[1] for p in ring]
            if max(lons) < west or min(lons) > east or max(lats) < south or min(lats) > north:
                continue
            if transformer is not None:
                ring = [project(transformer, lon, lat) for lon, lat in ring]
            patches.append(MplPolygon(ring, closed=True))
    pc = PatchCollection(patches, facecolor=STATE_FILL, edgecolor=STATE_EDGE, linewidths=0.8, zorder=1)
    ax.add_collection(pc)


def plot_mosques(ax, mosques, loneliest, top_n_labeled, bbox, dot_size=14, star_size=170, label=True, transformer=None):
    west, east, south, north = bbox

    def in_view(lat, lon):
        return south <= lat <= north and west <= lon <= east

    def to_xy(lon, lat):
        return project(transformer, lon, lat) if transformer is not None else (lon, lat)

    xs, ys = [], []
    for m in mosques:
        if in_view(m["lat"], m["lon"]):
            x, y = to_xy(m["lon"], m["lat"])
            xs.append(x)
            ys.append(y)
    ax.scatter(xs, ys, s=dot_size, color=MOSQUE_DOT_COLOR, alpha=0.4, zorder=2, linewidths=0)

    for m in loneliest[:5]:
        if not (in_view(m["lat"], m["lon"]) or in_view(m["_nearest"]["lat"], m["_nearest"]["lon"])):
            continue
        n = m["_nearest"]
        x1, y1 = to_xy(m["lon"], m["lat"])
        x2, y2 = to_xy(n["lon"], n["lat"])
        ax.plot(
            [x1, x2], [y1, y2],
            color=LONELY_COLOR,
            linewidth=1.6,
            linestyle=(0, (4, 3)),
            alpha=0.85,
            zorder=3,
            dash_capstyle="round",
        )

    lone_xy = [to_xy(m["lon"], m["lat"]) for m in loneliest if in_view(m["lat"], m["lon"])]
    if lone_xy:
        ax.scatter(
            [p[0] for p in lone_xy],
            [p[1] for p in lone_xy],
            s=star_size,
            color=LONELY_COLOR,
            marker="*",
            zorder=4,
            edgecolors="white",
            linewidths=1.5,
        )

    if label:
        stroke = [patheffects.withStroke(linewidth=3.5, foreground="white")]
        for m in loneliest[:top_n_labeled]:
            if not in_view(m["lat"], m["lon"]):
                continue
            city = city_from_mosque(m)
            state = m.get("state") or ""
            loc = f"{city}, {state}" if state else city
            miles = m["_nearest_km"] * KM_TO_MI
            text = f"{loc}\n{miles:.0f} mi"
            x, y = to_xy(m["lon"], m["lat"])
            ax.annotate(
                text, (x, y),
                textcoords="offset points",
                xytext=(12, 10),
                fontsize=11,
                fontweight="bold",
                color="#111",
                zorder=5,
                path_effects=stroke,
            )

    if transformer is not None:
        # Sample points along the bbox boundary in lat/lon and project each —
        # the projected bbox is curved, so corner-only projection clips real
        # US territory (Florida Keys, southern Texas, northern Maine).
        import numpy as _np
        samples = []
        for lon in _np.linspace(west, east, 40):
            samples.append((lon, south))
            samples.append((lon, north))
        for lat in _np.linspace(south, north, 40):
            samples.append((west, lat))
            samples.append((east, lat))
        xs_b = [project(transformer, lon, lat)[0] for lon, lat in samples]
        ys_b = [project(transformer, lon, lat)[1] for lon, lat in samples]
        ax.set_xlim(min(xs_b), max(xs_b))
        ax.set_ylim(min(ys_b), max(ys_b))
    else:
        ax.set_xlim(west, east)
        ax.set_ylim(south, north)
    ax.set_aspect("equal")
    ax.set_axis_off()


def main():
    print("Loading mosques...")
    mosques = load_mosques()
    print(f"  {len(mosques)} mosques")

    print("Computing nearest-neighbor distances...")
    compute_nearest_neighbors(mosques)
    mosques.sort(key=lambda m: -m["_nearest_km"])
    loneliest = mosques[:10]

    print("Loading US states GeoJSON...")
    gj = load_us_states_geojson()

    print("Rendering map...")
    fig = plt.figure(figsize=(18, 11), facecolor="white")

    main_ax = fig.add_axes([0.02, 0.10, 0.96, 0.82])
    plot_states(main_ax, gj, CONTIGUOUS_BBOX, transformer=PROJ_CONUS)
    plot_mosques(main_ax, mosques, loneliest, top_n_labeled=5, bbox=CONTIGUOUS_BBOX, transformer=PROJ_CONUS)

    ak_ax = fig.add_axes([0.04, 0.10, 0.18, 0.18])
    plot_states(ak_ax, gj, ALASKA_BBOX, transformer=PROJ_ALASKA)
    plot_mosques(ak_ax, mosques, loneliest, top_n_labeled=0, bbox=ALASKA_BBOX, dot_size=60, star_size=140, label=False, transformer=PROJ_ALASKA)
    ak_ax.text(0.02, 0.93, "Alaska", transform=ak_ax.transAxes, fontsize=10, fontweight="bold", color="#222")

    hi_ax = fig.add_axes([0.22, 0.10, 0.12, 0.12])
    plot_states(hi_ax, gj, HAWAII_BBOX)
    plot_mosques(hi_ax, mosques, loneliest, top_n_labeled=0, bbox=HAWAII_BBOX, dot_size=60, star_size=140, label=False)
    hi_ax.text(0.02, 0.90, "Hawaii", transform=hi_ax.transAxes, fontsize=10, fontweight="bold", color="#222")

    fig.text(
        0.5,
        0.91,
        "The Loneliest Mosques in America",
        ha="center",
        fontsize=22,
        fontweight="bold",
        color="#111",
    )

    from matplotlib.lines import Line2D
    legend_elems = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=MOSQUE_DOT_COLOR, markersize=7, alpha=0.6, label=f"All {len(mosques):,} US mosques"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor=LONELY_COLOR, markeredgecolor="white", markersize=14, label="10 loneliest"),
        Line2D([0], [0], color=LONELY_COLOR, linewidth=1.6, linestyle=(0, (4, 3)), label="Distance to nearest mosque (top 5)"),
    ]
    main_ax.legend(handles=legend_elems, loc="lower right", frameon=True, fontsize=11, facecolor="white", edgecolor="#ddd")

    fig.text(0.5, 0.04, "Data: Google Places API  ·  github.com/qmir2", ha="center", fontsize=10, color="#666")

    os.makedirs("results", exist_ok=True)
    out = "results/loneliest_mosques_map.png"
    plt.savefig(out, dpi=200, bbox_inches="tight", pad_inches=0.4, facecolor="white")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
