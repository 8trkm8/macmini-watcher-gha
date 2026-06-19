"""
Apple Japan refurbished store watcher: Mac mini M4 / M4 Pro.

Reads schema.org JSON-LD Product blocks embedded in Apple's refurbished pages
(stable structured data — no fragile HTML scraping), filters for Mac mini M4
family, and POSTs an ntfy.sh push notification when a new matching product
appears. Designed to run on GitHub Actions every 15 minutes.
"""

import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

STATE_FILE = Path("state.json")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_URL = "https://ntfy.sh/"

if not NTFY_TOPIC:
    print("[fatal] NTFY_TOPIC env var is required", file=sys.stderr)
    sys.exit(2)

PAGES = [
    "https://www.apple.com/jp/shop/refurbished/mac/mac-mini",
    "https://www.apple.com/jp/shop/refurbished/mac",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def extract_products_from_jsonld(html):
    """Yield Product dicts from all <script type='application/ld+json'> blocks."""
    soup = BeautifulSoup(html, "html.parser")
    for block in soup.find_all("script", type="application/ld+json"):
        raw = block.string or block.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "Product":
                yield item
            graph = item.get("@graph")
            if isinstance(graph, list):
                for sub in graph:
                    if isinstance(sub, dict) and sub.get("@type") == "Product":
                        yield sub


def normalize(product):
    """Reduce a JSON-LD Product to {name, price, url}."""
    name = (product.get("name") or "").strip()
    url = (product.get("url") or product.get("mainEntityOfPage") or "").strip()

    offers = product.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    price_value = None
    for offer in offers:
        if isinstance(offer, dict) and offer.get("price") is not None:
            price_value = offer["price"]
            break
    price_str = ""
    if price_value is not None:
        try:
            price_str = f"¥{int(price_value):,}"
        except (TypeError, ValueError):
            price_str = str(price_value)

    return {"name": name, "price": price_str, "url": url}


def fetch_products():
    by_url = {}
    for page_url in PAGES:
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=30, allow_redirects=True)
            r.raise_for_status()
        except Exception as e:
            print(f"[warn] fetch failed for {page_url}: {e}", file=sys.stderr)
            continue

        for raw in extract_products_from_jsonld(r.text):
            p = normalize(raw)
            if not p["name"] or not p["url"]:
                continue
            # Dedup by URL across pages.
            if p["url"] not in by_url:
                by_url[p["url"]] = p

    return list(by_url.values())


def is_target(product):
    """Mac mini with an M4-family chip (matches M4, M4 Pro, M4 Max)."""
    name = product["name"]
    if "Mac mini" not in name:
        return False
    if not re.search(r"\bM4\b", name):
        return False
    return True


def load_state():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as e:
            print(f"[warn] state.json read error: {e}", file=sys.stderr)
    return []


def save_state(urls):
    STATE_FILE.write_text(
        json.dumps(urls, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def send_ntfy(new_items):
    lines = []
    for p in new_items:
        line = p["name"]
        if p["price"]:
            line = f"{p['name']}  {p['price']}"
        lines.append(line)
    message = "\n".join(lines)

    click_url = new_items[0]["url"]
    payload = {
        "topic": NTFY_TOPIC,
        "title": "Mac mini M4 入荷!",
        "message": message,
        "priority": 5,
        "tags": ["rotating_light", "computer"],
        "click": click_url,
        "actions": [
            {
                "action": "view",
                "label": "Apple整備済を開く",
                "url": click_url,
                "clear": True,
            }
        ],
    }
    r = requests.post(NTFY_URL, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    products = fetch_products()
    print(f"[info] scraped {len(products)} unique products from JSON-LD")

    targets = [p for p in products if is_target(p)]
    print(f"[info] {len(targets)} Mac mini M4 product(s) currently in stock:")
    for t in targets:
        print(f"  - {t['name']}  {t['price']}  {t['url']}")

    seen = set(load_state())
    new_items = [t for t in targets if t["url"] not in seen]

    if new_items:
        print(f"[info] {len(new_items)} new item(s) -> sending ntfy")
        try:
            result = send_ntfy(new_items)
            print(f"[info] ntfy ok: id={result.get('id')}")
        except Exception as e:
            print(f"[error] ntfy send failed: {e}", file=sys.stderr)
            # Don't update state — retry next run so we don't drop a notification.
            sys.exit(1)
    else:
        print("[info] no new items — skipping notification")

    save_state([t["url"] for t in targets])
    print("[info] state.json updated")


if __name__ == "__main__":
    main()
