"""
Render 'The Loneliest Places in America to be a Muslim' map.

Uses a Voronoi diagram over all US mosque locations. The vertices of the
Voronoi diagram are the local maxima of "distance to nearest mosque." The
point on land with the largest such distance is the loneliest place.

Output: results/loneliest_points_map.png
"""

import glob
import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import requests
from matplotlib import patheffects
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.patches import Polygon as MplPolygon
from scipy.spatial import Voronoi, cKDTree
from shapely.geometry import MultiPolygon, Point, shape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seed_mosques_google import haversine_m


MOSQUE_DOT_COLOR = "#0891b2"
LONELY_COLOR = "#dc2626"
STATE_FILL = "#fafafa"
STATE_EDGE = "#2f2f2f"
VORONOI_EDGE = "#cccccc"

CONTIGUOUS_BBOX = (-125, -66.5, 24, 50)
KM_TO_MI = 0.621371


def load_mosques():
    mosques = []
    for f in sorted(glob.glob("data/mosques_google_*.json")):
        region = os.path.basename(f).replace("mosques_google_", "").replace(".json", "")
        if region == "chicagoland":
            continue
        with open(f, encoding="utf-8") as fp:
            mosques.extend(json.load(fp))
    return mosques


def load_us_states_geojson():
    url = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def build_us_union(gj):
    polys = []
    for feature in gj["features"]:
        geom = shape(feature["geometry"])
        if geom.geom_type == "Polygon":
            polys.append(geom)
        elif geom.geom_type == "MultiPolygon":
            polys.extend(geom.geoms)
    return MultiPolygon(polys)


def plot_states(ax, gj, bbox):
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
            patches.append(MplPolygon(ring, closed=True))
    pc = PatchCollection(patches, facecolor=STATE_FILL, edgecolor=STATE_EDGE, linewidths=0.8, zorder=1)
    ax.add_collection(pc)


def plot_voronoi_edges(ax, vor, bbox):
    """Draw finite Voronoi ridges as thin lines."""
    segments = []
    center = vor.points.mean(axis=0)
    ptp_bound = np.ptp(vor.points, axis=0) * 10
    for pointidx, simplex in zip(vor.ridge_points, vor.ridge_vertices):
        simplex = np.asarray(simplex)
        if np.all(simplex >= 0):
            segments.append(vor.vertices[simplex])
        else:
            i = simplex[simplex >= 0][0]
            t = vor.points[pointidx[1]] - vor.points[pointidx[0]]
            t /= np.linalg.norm(t)
            n = np.array([-t[1], t[0]])
            midpoint = vor.points[pointidx].mean(axis=0)
            direction = np.sign(np.dot(midpoint - center, n)) * n
            far = vor.vertices[i] + direction * ptp_bound.max()
            segments.append([vor.vertices[i], far])
    lc = LineCollection(segments, colors=VORONOI_EDGE, linewidths=0.4, zorder=2)
    ax.add_collection(lc)


def main():
    print("Loading mosques...")
    mosques = load_mosques()
    contig = [m for m in mosques
              if CONTIGUOUS_BBOX[0] <= m["lon"] <= CONTIGUOUS_BBOX[1]
              and CONTIGUOUS_BBOX[2] <= m["lat"] <= CONTIGUOUS_BBOX[3]]
    print(f"  {len(contig)} mosques in contiguous US")

    print("Computing Voronoi diagram...")
    pts = np.array([[m["lon"], m["lat"]] for m in contig])
    vor = Voronoi(pts)

    print("Loading US states polygon...")
    gj = load_us_states_geojson()
    us_union = build_us_union(gj)

    print("Finding loneliest points (Voronoi vertices inside US)...")
    tree = cKDTree(pts)
    candidates = []
    for vx, vy in vor.vertices:
        if not (CONTIGUOUS_BBOX[0] <= vx <= CONTIGUOUS_BBOX[1]
                and CONTIGUOUS_BBOX[2] <= vy <= CONTIGUOUS_BBOX[3]):
            continue
        if not us_union.contains(Point(vx, vy)):
            continue
        _, idx = tree.query([vx, vy])
        nearest = pts[idx]
        d_km = haversine_m(vy, vx, nearest[1], nearest[0]) / 1000
        candidates.append((d_km, vx, vy, contig[idx]))
    candidates.sort(key=lambda x: -x[0])
    top = candidates[:5]
    print(f"  #1: ({top[0][2]:.3f}, {top[0][1]:.3f}) — {top[0][0] * KM_TO_MI:.0f} mi to nearest mosque")

    print("Rendering map...")
    fig = plt.figure(figsize=(18, 11), facecolor="white")
    ax = fig.add_axes([0.02, 0.10, 0.96, 0.82])

    plot_states(ax, gj, CONTIGUOUS_BBOX)

    lons = [m["lon"] for m in contig]
    lats = [m["lat"] for m in contig]
    ax.scatter(lons, lats, s=10, color=MOSQUE_DOT_COLOR, alpha=0.5, zorder=3, linewidths=0,
               label=f"All {len(contig):,} US mosques (contiguous)")

    top_lons = [c[1] for c in top]
    top_lats = [c[2] for c in top]
    ax.scatter(top_lons, top_lats, s=220, color=LONELY_COLOR, marker="*",
               edgecolors="white", linewidths=1.5, zorder=5, label="5 loneliest points")

    stroke = [patheffects.withStroke(linewidth=3.5, foreground="white")]
    label_offsets = [(14, 14), (14, 10), (14, -24), (-180, 14), (-180, -24)]
    for i, ((d_km, vx, vy, nearest_m), offset) in enumerate(zip(top, label_offsets)):
        mi = d_km * KM_TO_MI
        text = f"#{i + 1}  {mi:.0f} mi\nto {nearest_m.get('city') or '?'}, {nearest_m.get('state') or '?'}"
        ax.annotate(text, (vx, vy), textcoords="offset points", xytext=offset,
                    fontsize=11, fontweight="bold", color="#111", zorder=6,
                    path_effects=stroke)

    ax.set_xlim(CONTIGUOUS_BBOX[0], CONTIGUOUS_BBOX[1])
    ax.set_ylim(CONTIGUOUS_BBOX[2], CONTIGUOUS_BBOX[3])
    ax.set_aspect("equal")
    ax.set_axis_off()

    fig.text(0.5, 0.91, "The Loneliest Places in America to be a Muslim",
             ha="center", fontsize=22, fontweight="bold", color="#111")

    from matplotlib.lines import Line2D
    legend_elems = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=MOSQUE_DOT_COLOR, markersize=7, alpha=0.6,
               label=f"All {len(contig):,} US mosques"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor=LONELY_COLOR, markeredgecolor="white",
               markersize=16, label="5 loneliest points"),
    ]
    ax.legend(handles=legend_elems, loc="lower right", frameon=True, fontsize=11,
              facecolor="white", edgecolor="#ddd")

    fig.text(0.5, 0.04, "Data: Google Places API  ·  github.com/qmir2",
             ha="center", fontsize=10, color="#666")

    os.makedirs("results", exist_ok=True)
    out = "results/loneliest_points_map.png"
    plt.savefig(out, dpi=200, bbox_inches="tight", pad_inches=0.4, facecolor="white")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
