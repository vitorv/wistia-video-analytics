"""
Wistia Stats API Exploration Script

Run this script to test API authentication and inspect actual response shapes.
Saves all responses to scripts/api_testing/api_responses/ for reference.

Usage:
    1. Create a .env file in the project root with: WISTIA_API_TOKEN=your_token_here
    2. pip install requests python-dotenv
    3. python scripts/api_testing/api_exploration.py
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

# Load token from .env file (never hardcode!)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  python-dotenv not installed. Set WISTIA_API_TOKEN as environment variable.")

API_TOKEN = os.environ.get("WISTIA_API_TOKEN")
if not API_TOKEN:
    print("❌ WISTIA_API_TOKEN not found. Create a .env file with: WISTIA_API_TOKEN=your_token")
    sys.exit(1)

MEDIA_IDS = ["gskhw4w4lm", "v08dlrgr7v"]
BASE_URL_MODERN = "https://api.wistia.com/modern"
BASE_URL_LEGACY = "https://api.wistia.com/v1"

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Accept": "application/json",
}

OUTPUT_DIR = Path(__file__).parent / "api_responses"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── Helper ──────────────────────────────────────────────────────────────────

def fetch_and_save(label: str, url: str, params: dict | None = None) -> dict | list | None:
    """Make a GET request, print summary, save full response to file."""
    print(f"\n{'='*60}")
    print(f"📡 {label}")
    print(f"   GET {url}")
    if params:
        print(f"   Params: {params}")

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        print(f"   Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            # Save to file
            filename = label.lower().replace(" ", "_").replace("/", "_") + ".json"
            filepath = OUTPUT_DIR / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"   ✅ Saved to {filepath}")

            # Print summary
            if isinstance(data, list):
                print(f"   Records: {len(data)}")
                if data:
                    print(f"   First record keys: {list(data[0].keys())}")
            elif isinstance(data, dict):
                print(f"   Keys: {list(data.keys())}")
            return data
        else:
            print(f"   ❌ Error: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return None


# ─── API Calls ───────────────────────────────────────────────────────────────

def main():
    print("🔍 Wistia Stats API Exploration")
    token_display = (
        f"{API_TOKEN[:8]}...{API_TOKEN[-4:]}" if API_TOKEN else "N/A"
    )
    print(f"   Token: {token_display}")
    print(f"   Media IDs: {MEDIA_IDS}")
    print(f"   Timestamp: {datetime.now().isoformat()}")

    # ── 1. Test Legacy Endpoint (from assignment PDF) ──
    for media_id in MEDIA_IDS:
        fetch_and_save(
            f"legacy_media_stats_{media_id}",
            f"{BASE_URL_LEGACY}/stats/medias/{media_id}.json"
        )

    # ── 2. Modern: Media Stats (Aggregate) ──
    for media_id in MEDIA_IDS:
        fetch_and_save(
            f"modern_media_stats_{media_id}",
            f"{BASE_URL_MODERN}/stats/medias/{media_id}"
        )

    # ── 3. Modern: Media Stats by Date ──
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    for media_id in MEDIA_IDS:
        fetch_and_save(
            f"modern_media_by_date_{media_id}",
            f"{BASE_URL_MODERN}/stats/medias/{media_id}/by_date",
            params={"start_date": "2020-01-01", "end_date": today}
        )

    # ── 4. Modern: Media Engagement ──
    for media_id in MEDIA_IDS:
        fetch_and_save(
            f"modern_media_engagement_{media_id}",
            f"{BASE_URL_MODERN}/stats/medias/{media_id}/engagement"
        )

    # ── 5. Modern: List Visitors (Page 1) ──
    visitors = fetch_and_save(
        "modern_visitors_page1",
        f"{BASE_URL_MODERN}/stats/visitors",
        params={"page": 1}
    )

    # ── 6. Check how many pages of visitors exist ──
    if visitors and len(visitors) > 0:
        print(f"\n   Page 1 has {len(visitors)} visitors. Checking page 2...")
        page2 = fetch_and_save(
            "modern_visitors_page2",
            f"{BASE_URL_MODERN}/stats/visitors",
            params={"page": 2}
        )
        if page2 and len(page2) > 0:
            print(f"   Page 2 has {len(page2)} visitors. More pages may exist.")
        else:
            print(f"   Page 2 is empty. Only 1 page of visitors.")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"✅ All responses saved to: {OUTPUT_DIR.resolve()}")
    print(f"   Inspect the JSON files to understand field names and data shapes.")
    print(f"\n📋 Next steps:")
    print(f"   1. Review the JSON responses")
    print(f"   2. Compare field names against the data model in architecture.md")
    print(f"   3. Note any missing fields or unexpected shapes")
    print(f"   4. Update context_vault/reference/api_notes.md with findings")


if __name__ == "__main__":
    main()
