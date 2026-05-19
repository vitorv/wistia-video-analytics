"""Quick audit: check every data model column against what the API actually returns."""
import os, json, requests
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "api_responses"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TOKEN = os.environ["WISTIA_API_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
MEDIA_IDS = ["gskhw4w4lm", "v08dlrgr7v"]
NOT_FOUND = "NOT FOUND"

print("=" * 60)
print("1. MEDIA METADATA (Data API) - for dim_media")
print("=" * 60)
for mid in MEDIA_IDS:
    r = requests.get(f"https://api.wistia.com/modern/medias/{mid}", headers=HEADERS)
    print(f"\nModern /modern/medias/{mid}: Status {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print(f"  All keys: {list(d.keys())}")
        for k in ["name", "hashed_id", "url", "created", "type", "duration", "description", "section"]:
            val = d.get(k, NOT_FOUND)
            print(f"  {k}: {val}")
        with open(OUTPUT_DIR / f"modern_media_metadata_{mid}.json", "w") as f:
            json.dump(d, f, indent=2)
    else:
        print(f"  Error: {r.text[:200]}")

    r2 = requests.get(f"https://api.wistia.com/v1/medias/{mid}.json", headers=HEADERS)
    print(f"Legacy /v1/medias/{mid}.json: Status {r2.status_code}")
    if r2.status_code == 200:
        d2 = r2.json()
        print(f"  All keys: {list(d2.keys())}")
        for k in ["name", "hashed_id", "url", "created", "type", "duration", "description", "section"]:
            val = d2.get(k, NOT_FOUND)
            print(f"  {k}: {val}")

print("\n" + "=" * 60)
print("2. VISITOR DETAIL - checking for media-level linkage")
print("=" * 60)
r3 = requests.get("https://api.wistia.com/modern/stats/visitors", headers=HEADERS, params={"page": 1})
if r3.status_code == 200:
    visitors = r3.json()
    if visitors:
        vkey = visitors[0]["visitor_key"]
        r4 = requests.get(f"https://api.wistia.com/modern/stats/visitors/{vkey}", headers=HEADERS)
        print(f"\nVisitor detail: Status {r4.status_code}")
        if r4.status_code == 200:
            vd = r4.json()
            print(f"  Keys: {list(vd.keys())}")
            for k in ["events", "medias", "media_events", "sessions"]:
                if k in vd:
                    items = vd[k]
                    print(f"  {k}: {type(items).__name__} with {len(items)} items")
                else:
                    print(f"  {k}: {NOT_FOUND}")
            with open(OUTPUT_DIR / "modern_visitor_detail.json", "w") as f:
                json.dump(vd, f, indent=2)

print("\n" + "=" * 60)
print("3. BY_DATE - checking available fields per day")
print("=" * 60)
r5 = requests.get(
    "https://api.wistia.com/modern/stats/medias/gskhw4w4lm/by_date",
    headers=HEADERS,
    params={"start_date": "2026-05-17", "end_date": "2026-05-18"},
)
if r5.status_code == 200:
    daily = r5.json()
    print(f"\nRecords: {len(daily)}")
    if daily:
        print(f"Sample record: {json.dumps(daily[0], indent=2)}")
        print(f"Keys: {list(daily[0].keys())}")
        for k in ["play_rate", "visitor_id", "visitors", "engagement", "watched_percent", "media_id"]:
            found = k in daily[0]
            label = "FOUND" if found else "NOT IN by_date"
            print(f"  {k}: {label}")
