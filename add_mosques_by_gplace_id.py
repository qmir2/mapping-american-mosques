"""
Add specific mosques to our dataset by Google Place ID.

Use when your seeder missed a place — usually because Google types it as
something other than "mosque" (e.g., "community_center", "religious_institution").
You've already verified the place is a real operating mosque.

Usage:
    .venv/bin/python add_mosques_by_gplace_id.py

Edit TO_ADD below with the gplace_ids you want to add.
"""

import json
import os
import requests

from seed_mosques_google import parse_place, in_bbox, REGIONS, API_KEY, FIELD_MASK

PLACE_URL = "https://places.googleapis.com/v1/places"

TO_ADD = [
    "ChIJAYnE7sA5DogRG9HAjXH5pmQ",  # Mosque Harlem Center, Bridgeview
    "ChIJX14LfiXTD4gRbB5kXau_kIs",  # Masjid Tabaq, Chicago
    "ChIJXaewYnU5DogRP8MLmog2yJo",  # Al-Nahda Center (NFP), Worth
    "ChIJt6nGw8LPD4gRfauA1JcY8Es",  # Ahlul Bait Center, Evanston
    "ChIJXeBkntOsD4gRlScDRg1YU7A",  # Islamic Education Center, Glendale Heights
    "ChIJVaS7YSrdDYgRU54CEw0oyDI",  # Kankakee Islamic Center, Kankakee
]


def fetch_place(place_id):
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK.replace("places.", ""),
    }
    r = requests.get(f"{PLACE_URL}/{place_id}", headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def merge_into(path, region_key, region_config, records):
    with open(path, encoding="utf-8") as f:
        mosques = json.load(f)
    existing_ids = {m["place_id"] for m in mosques}

    added = 0
    for rec in records:
        if rec["place_id"] in existing_ids:
            print(f"  skip (already present): {rec['name']}")
            continue
        if region_config.get("state_filter") and rec.get("state") != region_config["state_filter"]:
            print(f"  skip (state != {region_config['state_filter']}): {rec['name']} in {rec.get('state')}")
            continue
        if not in_bbox(rec, region_config["bbox"]):
            print(f"  skip (outside bbox): {rec['name']}")
            continue
        mosques.append(rec)
        added += 1
        print(f"  added: {rec['name']} — {rec.get('city')}, {rec.get('state')}")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(mosques, f, indent=2, ensure_ascii=False)
    print(f"  {path}: +{added} (now {len(mosques)})")


def main():
    print(f"Fetching {len(TO_ADD)} places...")
    records = []
    for pid in TO_ADD:
        try:
            data = fetch_place(pid)
        except requests.HTTPError as e:
            print(f"  {pid}: FAILED {e}")
            continue
        # parse_place expects Google's "places" shape (id, displayName, etc.)
        rec = parse_place(data, region_key="")
        records.append(rec)
        print(f"  {rec['name']} — {rec.get('city')}, {rec.get('state')}")

    for region_key, region_config in REGIONS.items():
        print(f"\nMerging into {region_key}:")
        for r in records:
            r["region"] = region_key
        merge_into(f"data/mosques_google_{region_key}.json", region_key, region_config, records)


if __name__ == "__main__":
    main()
