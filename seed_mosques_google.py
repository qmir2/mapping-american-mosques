"""
Mosque Seeder — Google Places API (New)

Uses searchNearby with includedType=mosque across a grid of tiles, then
filters out non-operational and low-signal listings, and enriches with
prayer times from Aladhan.

Usage:
    export GOOGLE_PLACES_API_KEY=your_key
    .venv/bin/python seed_mosques_google.py

Output:
    mosques_google_chicagoland.json
"""

import os
import re
import sys
import math
import json
import time
from collections import Counter
from datetime import date
import requests

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")
if not API_KEY and os.path.exists(".env"):
    for line in open(".env"):
        if line.startswith("GOOGLE_PLACES_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip()
            break
if not API_KEY:
    raise SystemExit("GOOGLE_PLACES_API_KEY not set (env var or .env file)")

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
SEARCHTEXT_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.addressComponents",
    "places.location",
    "places.types",
    "places.primaryType",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.businessStatus",
    "places.regularOpeningHours",
    "places.userRatingCount",
])

REGIONS = {
    "chicagoland": {
        "bbox": (41.4, -88.4, 42.2, -87.2),
        "label": "Chicagoland",
        "step_deg": 0.08,
        "tile_radius_m": 10000,
    },
    "illinois": {
        "bbox": (36.97, -91.51, 42.51, -87.02),
        "label": "Illinois",
        "step_deg": 0.15,
        "tile_radius_m": 15000,
        "state_filter": "IL",
    },
    # Sparse states — use one searchText call per state rectangle.
    "vermont":        {"bbox": (42.73,  -73.44, 45.02,  -71.47), "label": "Vermont",        "strategy": "text", "state_filter": "VT"},
    "wyoming":        {"bbox": (40.99, -111.06, 45.01, -104.05), "label": "Wyoming",        "strategy": "text", "state_filter": "WY"},
    "south_dakota":   {"bbox": (42.48, -104.06, 45.94,  -96.44), "label": "South Dakota",   "strategy": "text", "state_filter": "SD"},
    "montana":        {"bbox": (44.36, -116.05, 49.00, -104.04), "label": "Montana",        "strategy": "text", "state_filter": "MT"},
    "alaska":         {"bbox": (51.20, -179.90, 71.50, -129.90), "label": "Alaska",         "strategy": "text", "state_filter": "AK"},
    "west_virginia":  {"bbox": (37.20,  -82.65, 40.64,  -77.72), "label": "West Virginia",  "strategy": "text", "state_filter": "WV"},
    "new_hampshire":  {"bbox": (42.70,  -72.56, 45.31,  -70.70), "label": "New Hampshire",  "strategy": "text", "state_filter": "NH"},
    "north_dakota":   {"bbox": (45.94, -104.05, 49.00,  -96.55), "label": "North Dakota",   "strategy": "text", "state_filter": "ND"},
    "maine":          {"bbox": (43.06,  -71.08, 47.46,  -66.95), "label": "Maine",          "strategy": "text", "state_filter": "ME"},
    "idaho":          {"bbox": (42.00, -117.24, 49.00, -111.04), "label": "Idaho",          "strategy": "text", "state_filter": "ID"},
    "rhode_island":   {"bbox": (41.14,  -71.91, 42.02,  -71.12), "label": "Rhode Island",   "strategy": "text", "state_filter": "RI"},
    "hawaii":         {"bbox": (18.91, -160.24, 22.23, -154.81), "label": "Hawaii",         "strategy": "text", "state_filter": "HI"},
    "delaware":       {"bbox": (38.45,  -75.79, 39.84,  -75.05), "label": "Delaware",       "strategy": "text", "state_filter": "DE"},
    "nevada":         {"bbox": (35.00, -120.00, 42.00, -114.04), "label": "Nevada",         "strategy": "text", "state_filter": "NV"},
    "new_mexico":     {"bbox": (31.33, -109.05, 37.00, -103.00), "label": "New Mexico",     "strategy": "text", "state_filter": "NM"},
    "dc":             {"bbox": (38.79,  -77.12, 38.99,  -76.91), "label": "DC",             "strategy": "text", "state_filter": "DC"},
    "nebraska":       {"bbox": (40.00, -104.05, 43.00,  -95.31), "label": "Nebraska",       "strategy": "text", "state_filter": "NE"},
    "utah":           {"bbox": (37.00, -114.05, 42.00, -109.04), "label": "Utah",           "strategy": "text", "state_filter": "UT"},
    "oklahoma":       {"bbox": (33.62, -103.00, 37.00,  -94.43), "label": "Oklahoma",       "strategy": "text", "state_filter": "OK"},
    "arkansas":       {"bbox": (33.00,  -94.62, 36.50,  -89.64), "label": "Arkansas",       "strategy": "text", "state_filter": "AR"},
    "mississippi":    {"bbox": (30.17,  -91.66, 35.01,  -88.10), "label": "Mississippi",    "strategy": "text", "state_filter": "MS"},
    "kansas":         {"bbox": (37.00, -102.05, 40.00,  -94.59), "label": "Kansas",         "strategy": "text", "state_filter": "KS"},
    "oregon":         {"bbox": (42.00, -124.70, 46.30, -116.46), "label": "Oregon",         "strategy": "text", "state_filter": "OR"},
    "iowa":           {"bbox": (40.38,  -96.64, 43.50,  -90.14), "label": "Iowa",           "strategy": "text", "state_filter": "IA"},
    # Medium-density states — start with text; switch to grid if they hit 60-cap.
    "arizona":        {"bbox": (31.33, -114.82, 37.00, -109.04), "label": "Arizona",        "strategy": "text", "state_filter": "AZ"},
    "colorado":       {"bbox": (36.99, -109.06, 41.00, -102.04), "label": "Colorado",       "strategy": "text", "state_filter": "CO"},
    "connecticut":    {"bbox": (40.95,  -73.73, 42.05,  -71.78), "label": "Connecticut",    "strategy": "text", "state_filter": "CT"},
    "indiana":        {"bbox": (37.77,  -88.10, 41.76,  -84.78), "label": "Indiana",        "strategy": "text", "state_filter": "IN"},
    "kentucky":       {"bbox": (36.50,  -89.57, 39.15,  -81.97), "label": "Kentucky",       "strategy": "text", "state_filter": "KY"},
    "louisiana":      {"bbox": (28.93,  -94.04, 33.02,  -88.82), "label": "Louisiana",      "strategy": "text", "state_filter": "LA"},
    "minnesota":      {"bbox": (43.50,  -97.24, 49.38,  -89.49), "label": "Minnesota",      "strategy": "text", "state_filter": "MN"},
    "missouri":       {"bbox": (35.99,  -95.77, 40.61,  -89.10), "label": "Missouri",       "strategy": "text", "state_filter": "MO"},
    "alabama":        {"bbox": (30.14,  -88.47, 35.01,  -84.89), "label": "Alabama",        "strategy": "text", "state_filter": "AL"},
    "tennessee":      {"bbox": (34.98,  -90.31, 36.68,  -81.65), "label": "Tennessee",      "strategy": "text", "state_filter": "TN"},
    "south_carolina": {"bbox": (32.03,  -83.35, 35.22,  -78.54), "label": "South Carolina", "strategy": "text", "state_filter": "SC"},
    "wisconsin":      {"bbox": (42.49,  -92.89, 47.08,  -86.77), "label": "Wisconsin",      "strategy": "text", "state_filter": "WI"},
    "washington":     {"bbox": (45.54, -124.77, 49.00, -116.92), "label": "Washington",     "strategy": "text", "state_filter": "WA"},
    "north_carolina": {"bbox": (33.84,  -84.32, 36.59,  -75.46), "label": "North Carolina", "strategy": "text", "state_filter": "NC"},
    "ohio":           {"bbox": (38.40,  -84.82, 41.98,  -80.52), "label": "Ohio",           "strategy": "text", "state_filter": "OH"},
    "georgia":        {"bbox": (30.36,  -85.61, 35.00,  -80.84), "label": "Georgia",        "strategy": "text", "state_filter": "GA"},
    "massachusetts":  {"bbox": (41.24,  -73.51, 42.89,  -69.86), "label": "Massachusetts",  "strategy": "text", "state_filter": "MA"},
    # High-density states — auto-split recurses as needed.
    "california":     {"bbox": (32.53, -124.48, 42.01, -114.13), "label": "California",     "strategy": "text", "state_filter": "CA"},
    "texas":          {"bbox": (25.84, -106.65, 36.50,  -93.51), "label": "Texas",          "strategy": "text", "state_filter": "TX"},
    "new_york":       {"bbox": (40.50,  -79.76, 45.02,  -71.86), "label": "New York",       "strategy": "text", "state_filter": "NY"},
    "new_jersey":     {"bbox": (38.93,  -75.56, 41.36,  -73.88), "label": "New Jersey",     "strategy": "text", "state_filter": "NJ"},
    "michigan":       {"bbox": (41.70,  -90.42, 48.31,  -82.12), "label": "Michigan",       "strategy": "text", "state_filter": "MI"},
    "pennsylvania":   {"bbox": (39.72,  -80.52, 42.27,  -74.69), "label": "Pennsylvania",   "strategy": "text", "state_filter": "PA"},
    "florida":        {"bbox": (24.40,  -87.63, 31.00,  -79.97), "label": "Florida",        "strategy": "text", "state_filter": "FL"},
    "virginia":       {"bbox": (36.54,  -83.68, 39.47,  -75.24), "label": "Virginia",       "strategy": "text", "state_filter": "VA"},
    "maryland":       {"bbox": (37.89,  -79.49, 39.72,  -75.05), "label": "Maryland",       "strategy": "text", "state_filter": "MD"},
}

TILE_RADIUS_M = 10000
TILE_STEP_DEG = 0.08
DEDUPE_DISTANCE_M = 100

MIN_USER_RATING_COUNT = 3

# Drop entries whose name indicates they're a non-prayer sub-facility
# even if Google types them as primaryType=mosque.
NAME_EXCLUDE_RE = re.compile(r"\bfood\s+(pantry|bank)\b", re.I)

# Ahmadiyya is classified as non-Muslim by mainstream Sunni and Shia authorities
# and is excluded from this directory.
AHMADIYYA_RE = re.compile(r"ahmadiyya|ahmadi\b", re.I)

FETCH_PRAYER_TIMES = False


def grid_tiles(bbox, step):
    south, west, north, east = bbox
    tiles = []
    lat = south
    while lat <= north + 1e-9:
        lon = west
        while lon <= east + 1e-9:
            tiles.append((round(lat, 4), round(lon, 4)))
            lon += step
        lat += step
    return tiles


def _post_with_retry(url, headers, body, attempts=4):
    for i in range(attempts):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if i == attempts - 1:
                raise
            wait = 2 ** i
            print(f"    retry in {wait}s: {e}")
            time.sleep(wait)


def search_text(bbox, textQuery="mosque", included_type="mosque", max_pages=3):
    south, west, north, east = bbox
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK + ",nextPageToken",
    }
    base_body = {
        "textQuery": textQuery,
        "includedType": included_type,
        "pageSize": 20,
        "locationRestriction": {
            "rectangle": {
                "low": {"latitude": south, "longitude": west},
                "high": {"latitude": north, "longitude": east},
            }
        },
    }
    results = []
    page_token = None
    for _ in range(max_pages):
        body = dict(base_body)
        if page_token:
            body["pageToken"] = page_token
        resp = _post_with_retry(SEARCHTEXT_URL, headers, body)
        data = resp.json()
        results.extend(data.get("places") or [])
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2)  # Google recommends a short delay before using nextPageToken
    return results


def search_nearby(lat, lon, radius):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {
        "includedTypes": ["mosque"],
        "maxResultCount": 20,
        "rankPreference": "DISTANCE",
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": radius,
            }
        },
    }
    resp = requests.post(PLACES_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json().get("places", [])


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def dedupe(mosques, threshold_m=DEDUPE_DISTANCE_M):
    """Drop duplicates. Two entries are duplicates if ANY of:
      - same formatted address
      - within 50m of each other (Google sometimes lists one building twice)
      - (same website OR same phone) AND within threshold_m

    Keep the one with more reviews."""
    def loser(a, b):
        return a if (a.get("user_rating_count") or 0) < (b.get("user_rating_count") or 0) else b

    to_drop = set()

    by_address = {}
    for m in mosques:
        addr = m.get("address")
        if addr:
            by_address.setdefault(addr.strip(), []).append(m)
    for addr, group in by_address.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["place_id"] in to_drop or b["place_id"] in to_drop:
                    continue
                drop = loser(a, b)
                to_drop.add(drop["place_id"])
                print(f"  dedupe: dropped '{drop['name']}' (same address as '{(a if drop is b else b)['name']}')")

    groups = {}
    for m in mosques:
        if m["place_id"] in to_drop:
            continue
        for key in (m.get("website"), m.get("phone")):
            if key:
                groups.setdefault(key, []).append(m)
    for group in groups.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["place_id"] in to_drop or b["place_id"] in to_drop:
                    continue
                if not (a.get("lat") and b.get("lat")):
                    continue
                d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
                if d < threshold_m:
                    drop = loser(a, b)
                    to_drop.add(drop["place_id"])
                    print(f"  dedupe: dropped '{drop['name']}' (shared contact, {d:.0f}m from '{(a if drop is b else b)['name']}')")

    return [m for m in mosques if m["place_id"] not in to_drop]


def parse_place(p, region_key):
    loc = p.get("location") or {}
    addr_comps = {}
    for c in p.get("addressComponents", []) or []:
        types = c.get("types") or []
        if types:
            addr_comps[types[0]] = c.get("shortText") or c.get("longText")

    return {
        "place_id": p.get("id"),
        "name": (p.get("displayName") or {}).get("text"),
        "lat": loc.get("latitude"),
        "lon": loc.get("longitude"),
        "address": p.get("formattedAddress"),
        "city": addr_comps.get("locality") or addr_comps.get("postal_town"),
        "state": addr_comps.get("administrative_area_level_1"),
        "postcode": addr_comps.get("postal_code"),
        "phone": p.get("nationalPhoneNumber"),
        "website": p.get("websiteUri"),
        "primary_type": p.get("primaryType"),
        "types": p.get("types") or [],
        "business_status": p.get("businessStatus"),
        "user_rating_count": p.get("userRatingCount", 0),
        "opening_hours": (p.get("regularOpeningHours") or {}).get("weekdayDescriptions"),
        "region": region_key,
    }


def in_bbox(m, bbox):
    south, west, north, east = bbox
    return south <= m["lat"] <= north and west <= m["lon"] <= east


# ── Aladhan (prayer start times, not iqamah) ─────────────────
ALADHAN_URL = "https://api.aladhan.com/v1/timings"
PRAYER_METHOD = 2  # ISNA


def get_prayer_times(lat, lon, target_date=None):
    if target_date is None:
        target_date = date.today()
    params = {
        "latitude": lat,
        "longitude": lon,
        "method": PRAYER_METHOD,
        "date": target_date.strftime("%d-%m-%Y"),
    }
    try:
        resp = requests.get(ALADHAN_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            return None
        t = data["data"]["timings"]
        return {
            "fajr": t.get("Fajr"),
            "sunrise": t.get("Sunrise"),
            "dhuhr": t.get("Dhuhr"),
            "asr": t.get("Asr"),
            "maghrib": t.get("Maghrib"),
            "isha": t.get("Isha"),
            "date": target_date.isoformat(),
            "method": "ISNA",
        }
    except Exception as e:
        print(f"    Aladhan error for ({lat}, {lon}): {e}")
        return None


def search_text_auto_split(bbox, depth=0, max_depth=8, indent="  "):
    """searchText with automatic quadrant split on 60-result saturation.
    Recurses until no sub-quad saturates, or max_depth reached."""
    places = search_text(bbox)
    saturated = len(places) >= 60
    print(f"{indent}searchText at depth={depth} returned {len(places)} places" + (" (SATURATED)" if saturated else ""))
    if not saturated:
        return places
    if depth >= max_depth:
        print(f"{indent}!! hit max_depth={max_depth} while still saturated; data may be incomplete here")
        return places
    south, west, north, east = bbox
    mid_lat = (south + north) / 2
    mid_lon = (west + east) / 2
    quads = [
        (south, west, mid_lat, mid_lon),
        (south, mid_lon, mid_lat, east),
        (mid_lat, west, north, mid_lon),
        (mid_lat, mid_lon, north, east),
    ]
    by_id = {p.get("id"): p for p in places if p.get("id")}
    for q in quads:
        sub = search_text_auto_split(q, depth + 1, max_depth, indent + "  ")
        for p in sub:
            pid = p.get("id")
            if pid:
                by_id[pid] = p
    return list(by_id.values())


def seed_region_text(region_key, region_config):
    print(f"\n{'='*60}")
    print(f"Seeding {region_config['label']} via searchText (rectangle)")
    print(f"{'='*60}")

    places = search_text_auto_split(region_config["bbox"])
    print(f"  Total unique after auto-split: {len(places)}")

    by_id = {p.get("id"): p for p in places if p.get("id")}
    return postprocess_places(by_id, region_key, region_config)


def seed_region(region_key, region_config):
    if region_config.get("strategy") == "text":
        return seed_region_text(region_key, region_config)

    print(f"\n{'='*60}")
    print(f"Seeding {region_config['label']} via Google Places")
    print(f"{'='*60}")

    step = region_config.get("step_deg", TILE_STEP_DEG)
    radius = region_config.get("tile_radius_m", TILE_RADIUS_M)
    tiles = grid_tiles(region_config["bbox"], step)
    print(f"  {len(tiles)} grid tiles (step={step}°, radius={radius}m)")

    by_id = {}
    saturated_centers = []
    for i, (lat, lon) in enumerate(tiles, 1):
        try:
            places = search_nearby(lat, lon, radius)
        except requests.HTTPError as e:
            print(f"    tile {i}/{len(tiles)} ({lat},{lon}) failed: {e}")
            continue
        if len(places) == 20:
            cities = []
            for p in places:
                for c in p.get("addressComponents") or []:
                    if "locality" in (c.get("types") or []):
                        cities.append(c.get("shortText") or c.get("longText"))
                        break
            top_city = Counter(cities).most_common(1)[0][0] if cities else "?"
            saturated_centers.append((lat, lon, top_city))
        for p in places:
            pid = p.get("id")
            if pid and pid not in by_id:
                by_id[pid] = p
        if i % 10 == 0:
            print(f"    tile {i}/{len(tiles)} — {len(by_id)} unique so far")

    print(f"  Raw unique after main pass: {len(by_id)}")

    if saturated_centers:
        print(f"  Saturated tile areas (by most common city in results):")
        for lat, lon, city in saturated_centers:
            print(f"    ({lat:.4f}, {lon:.4f}) — {city}")
        print(f"  Subdividing {len(saturated_centers)} saturated tiles at half radius...")
        before = len(by_id)
        offset = step / 2
        sub_radius = radius // 2
        for lat, lon, _city in saturated_centers:
            for dlat, dlon in [(offset, offset), (offset, -offset), (-offset, offset), (-offset, -offset)]:
                slat, slon = lat + dlat, lon + dlon
                try:
                    sub_places = search_nearby(slat, slon, sub_radius)
                except requests.HTTPError as e:
                    print(f"    sub-tile ({slat:.3f},{slon:.3f}) failed: {e}")
                    continue
                for p in sub_places:
                    pid = p.get("id")
                    if pid and pid not in by_id:
                        by_id[pid] = p
        print(f"  Subdivision added {len(by_id) - before} new unique places")

    return postprocess_places(by_id, region_key, region_config)


def postprocess_places(by_id, region_key, region_config):
    parsed = [parse_place(p, region_key) for p in by_id.values()]

    in_region = [m for m in parsed if m["lat"] and m["lon"] and in_bbox(m, region_config["bbox"])]
    print(f"  After bbox clip: {len(in_region)}")

    state_filter = region_config.get("state_filter")
    if state_filter:
        before = len(in_region)
        in_region = [m for m in in_region if m.get("state") == state_filter]
        print(f"  After state_filter={state_filter}: {len(in_region)} (dropped {before - len(in_region)})")

    operational = [m for m in in_region if m["business_status"] == "OPERATIONAL"]
    print(f"  After operational filter: {len(operational)}")

    def is_excluded(m):
        name = m.get("name") or ""
        website = m.get("website") or ""
        return (
            NAME_EXCLUDE_RE.search(name)
            or AHMADIYYA_RE.search(name)
            or AHMADIYYA_RE.search(website)
        )

    name_ok = [m for m in operational if not is_excluded(m)]
    excluded = [m for m in operational if is_excluded(m)]
    if excluded:
        print(f"  After exclude filter (food-pantry, ahmadiyya): {len(name_ok)} (dropped: {[m['name'] for m in excluded]})")

    # Keep if at least MIN_USER_RATING_COUNT reviews AND
    # (primaryType == "mosque" OR has website OR has phone).
    # The review threshold drops ghost/speculative listings; the type/contact
    # clause drops places Google didn't type as mosque AND have no way to verify.
    def keep(m):
        if (m.get("user_rating_count") or 0) < MIN_USER_RATING_COUNT:
            return False
        if m.get("primary_type") == "mosque":
            return True
        return bool(m.get("website") or m.get("phone"))

    kept = [m for m in name_ok if keep(m)]
    dropped = [m for m in name_ok if not keep(m)]
    if dropped:
        print(f"  After quality filter (reviews>={MIN_USER_RATING_COUNT} AND primary=mosque OR contact): {len(kept)} (dropped {len(dropped)})")
        for d in dropped:
            print(f"    - {d['name']} — {d.get('city')}, {d.get('state')} — reviews={d.get('user_rating_count') or 0}, primary={d.get('primary_type')}, site={'y' if d.get('website') else 'n'}, phone={'y' if d.get('phone') else 'n'}")

    before = len(kept)
    kept = dedupe(kept)
    print(f"  After dedupe (same address / contact within {DEDUPE_DISTANCE_M}m): {len(kept)} (dropped {before - len(kept)})")

    if FETCH_PRAYER_TIMES:
        print(f"  Fetching prayer times from Aladhan...")
        for i, m in enumerate(kept, 1):
            m["prayer_times"] = get_prayer_times(m["lat"], m["lon"])
            if i % 10 == 0:
                print(f"    {i}/{len(kept)}")
            time.sleep(0.15)

    return kept


def save_json(mosques, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(mosques, f, indent=2, ensure_ascii=False)
    print(f"  Saved {filename} ({len(mosques)} mosques)")


def main():
    args = sys.argv[1:]
    if not args:
        to_run = REGIONS
    else:
        keys = []
        for a in args:
            if a == "sparse":
                keys.extend(k for k, v in REGIONS.items() if v.get("strategy") == "text")
            elif a in REGIONS:
                keys.append(a)
            else:
                raise SystemExit(f"Unknown region '{a}'. Valid: {list(REGIONS)} or 'sparse'")
        to_run = {k: REGIONS[k] for k in keys}

    for region_key, region_config in to_run.items():
        mosques = seed_region(region_key, region_config)
        save_json(mosques, f"data/mosques_google_{region_key}.json")


if __name__ == "__main__":
    main()
