"""
Generate derived summary CSVs that are safe to publish.

Raw Google Places JSONs cannot be redistributed (Google Maps Platform TOS),
but aggregated and analytical outputs are your own derivative work.

Output:
    results/mosques_per_state.csv
    results/top10_loneliest.csv
"""

import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seed_mosques_google import haversine_m


def load_mosques():
    mosques = []
    for f in sorted(glob.glob("data/mosques_google_*.json")):
        region = os.path.basename(f).replace("mosques_google_", "").replace(".json", "")
        if region == "chicagoland":
            continue
        with open(f, encoding="utf-8") as fp:
            mosques.extend(json.load(fp))
    return mosques


def write_state_counts(mosques, path):
    from collections import Counter
    counts = Counter(m.get("state") for m in mosques if m.get("state"))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["state", "mosque_count"])
        for state, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            w.writerow([state, n])
    print(f"Wrote {path} ({len(counts)} rows)")


def write_loneliest(mosques, path, top_n=10):
    for m in mosques:
        best = float("inf")
        best_other = None
        for other in mosques:
            if other is m:
                continue
            d = haversine_m(m["lat"], m["lon"], other["lat"], other["lon"])
            if d < best:
                best = d
                best_other = other
        m["_nearest_km"] = best / 1000
        m["_nearest"] = best_other
    mosques.sort(key=lambda x: -x["_nearest_km"])

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "name", "city", "state", "nearest_mosque", "nearest_city", "distance_mi"])
        for i, m in enumerate(mosques[:top_n], 1):
            n = m["_nearest"]
            city = m.get("city") or ""
            n_city = n.get("city") or ""
            w.writerow([
                i,
                m.get("name"),
                city,
                m.get("state"),
                n.get("name"),
                n_city,
                f"{m['_nearest_km'] * 0.621371:.1f}",
            ])
    print(f"Wrote {path}")


def main():
    mosques = load_mosques()
    print(f"Loaded {len(mosques)} mosques")
    os.makedirs("results", exist_ok=True)
    write_state_counts(mosques, "results/mosques_per_state.csv")
    write_loneliest(mosques, "results/top10_loneliest.csv")


if __name__ == "__main__":
    main()
