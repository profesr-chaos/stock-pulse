"""Fill in missing article images from Open Graph tags.

Costs one request per article, so it is strictly best-effort and capped: only
the newest few image-less articles per refresh, only for articles whose real
publisher URL we know, and always after the articles themselves are safely
stored. The previous version fetched (sometimes twice) for *every* RSS entry
before deciding whether to keep it, which is where most of the scrape time went.
"""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

import db
import settings

from ..http_client import scraper

_META_CANDIDATES = (
    ("property", "og:image"),
    ("property", "og:image:secure_url"),
    ("name", "twitter:image"),
    ("name", "twitter:image:src"),
    ("itemprop", "image"),
)


def extract_image(html: str, base_url: str) -> str | None:
    """Split out for testing: pull the best social image from a page."""
    soup = BeautifulSoup(html, "html.parser")

    for attribute, value in _META_CANDIDATES:
        tag = soup.find("meta", attrs={attribute: value})
        content = tag.get("content") if tag else None
        if content and not content.strip().endswith(".svg"):
            return urljoin(base_url, content.strip())

    # Fall back to the first sizeable inline image.
    for img in soup.find_all("img", limit=25):
        src = img.get("src") or img.get("data-src")
        if not src or src.strip().endswith(".svg") or src.startswith("data:"):
            continue
        if _too_small(img):
            continue
        return urljoin(base_url, src.strip())

    return None


def _too_small(img) -> bool:
    """Skip tracking pixels, icons and spacers."""
    for attribute in ("width", "height"):
        raw = img.get(attribute)
        if raw and str(raw).strip().rstrip("px").isdigit() and int(str(raw).strip().rstrip("px")) < 200:
            return True
    return False


def backfill_images(short_names: list[str], limit: int | None = None) -> int:
    """Fetch og:image for the newest image-less articles. Returns rows updated."""
    if not settings.FETCH_ARTICLE_IMAGES or not short_names:
        return 0

    limit = limit if limit is not None else settings.IMAGE_FETCH_LIMIT
    targets = db.news.get_missing_images(short_names, limit=limit)
    if not targets:
        return 0

    responses = scraper.get_many([{"url": t["url"]} for t in targets])

    found = {}
    for target, response in zip(targets, responses):
        if not response or not response.ok or "html" not in response.headers.get("content-type", "html"):
            continue
        image = extract_image(response.text, response.url)
        if image:
            found[target["id"]] = image

    updated = db.news.set_images(found)
    if updated:
        print(f"[images] added {updated} images")
    return updated
