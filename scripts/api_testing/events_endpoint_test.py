"""
Events Endpoint Verification — does the `media_id` filter actually work?

The pipeline's ADR-002 treats /modern/stats/events as the primary data source,
filtered per project media ID. This was never tested. This script confirms:
  1. Does ?media_id=<id> filter the response to only that media?
  2. How many events exist per project media (pagination depth / volume)?

Usage:
    python scripts/api_testing/events_endpoint_test.py
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get("WISTIA_API_TOKEN")
if not TOKEN:
    print("WISTIA_API_TOKEN not found in .env")
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
EVENTS_URL = "https://api.wistia.com/modern/stats/events"
PROJECT_MEDIA = ["gskhw4w4lm", "v08dlrgr7v"]
MAX_PAGES_PROBE = 60  # safety cap so we don't paginate forever


def get_page(media_id: str, page: int) -> list:
    resp = requests.get(
        EVENTS_URL,
        headers=HEADERS,
        params={"media_id": media_id, "page": page},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def test_media(media_id: str) -> None:
    print(f"\n{'=' * 64}")
    print(f"  media_id = {media_id}")
    print(f"{'=' * 64}")

    page1 = get_page(media_id, 1)
    print(f"  Page 1: {len(page1)} events")

    if not page1:
        print("  >> Filter returned ZERO events for this media on page 1.")
        return

    # Does the filter actually constrain results to this media?
    returned_ids = {e.get("media_id") for e in page1}
    if returned_ids == {media_id}:
        print(f"  >> FILTER WORKS — all page-1 events are media_id={media_id}")
    else:
        print(f"  >> FILTER DOES NOT WORK — page 1 contains: {returned_ids}")
        return

    # Probe pagination depth to estimate total volume.
    total = len(page1)
    last_nonempty = 1
    for page in range(2, MAX_PAGES_PROBE + 1):
        rows = get_page(media_id, page)
        if not rows:
            print(f"  Pagination ends at page {page} (empty array).")
            break
        total += len(rows)
        last_nonempty = page
    else:
        print(f"  Probe cap hit at page {MAX_PAGES_PROBE} — more pages exist.")

    print(f"  Events counted: {total} across {last_nonempty} page(s)")
    sample = page1[0]
    print(f"  Sample event keys: {sorted(sample.keys())}")
    print(f"  Sample received_at: {sample.get('received_at')}")
    print(f"  Sample percent_viewed: {sample.get('percent_viewed')}")


def main() -> None:
    print("Events endpoint — media_id filter verification")
    print(f"Token: {TOKEN[:6]}...{TOKEN[-4:]}")
    for media_id in PROJECT_MEDIA:
        try:
            test_media(media_id)
        except requests.HTTPError as exc:
            print(f"  HTTP error for {media_id}: {exc}")
        except requests.RequestException as exc:
            print(f"  Request failed for {media_id}: {exc}")


if __name__ == "__main__":
    main()
