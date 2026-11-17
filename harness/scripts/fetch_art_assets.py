#!/usr/bin/env python3
"""Fetch decorative artworks for the Luminest landing page from Wikimedia Commons.

Only works whose Commons metadata explicitly says Public domain or CC0 are
accepted. Anything else is REFUSED and never written to disk — the same
fail-close posture as the harness licence gate.

    env -u PYTHONPATH python3 harness/scripts/fetch_art_assets.py

Writes outputs/art-sources/*.jpg plus outputs/art-sources/art.json, which
records title, artist, date, licence, licence URL, source page, retrieval time
and the measured sha256 of every file.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import time

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ART_DIR = os.path.join(WORKSPACE, "outputs", "art-sources")
API = "https://commons.wikimedia.org/w/api.php"

# slug, exact Commons file title, short decorative role
TITLES = [
    ("reader", "Fragonard, The Reader.jpg", "reading figure"),
    ("lesson", "A reading lesson (1866), by Leon Basile Perrault.jpg", "two learners"),
    ("astronomer", "Johannes Vermeer - The Astronomer - 1668.jpg", "scholar with globe"),
    ("geographer", "Johannes Vermeer - The Geographer - WGA24687.jpg", "maps and measurement"),
    ("map", "1650 Jansson Map of the Ancient World - Geographicus - OrbisTerrarum-jansson-1650.jpg", "antique map"),
    ("principia", "Newton-Principia-Mathematica 1-500x700.jpg", "old mathematical folio"),
    ("lamp", "Patent Drawing for T. A. Edison's Incandescent Electric Lamp - NARA - 6277646.jpg", "patent drawing"),
    ("botany", "The American Flora. Vol. 1, 1855 - pl. 23 Tropaeolum majus (6021776775).jpg", "botanical plate"),
]

ALLOWED = ("public domain", "cc0", "pd-old", "pd-art", "pd-us")


def curl_json(params: dict) -> dict:
    cmd = ["curl", "-sS", "--max-time", "45", "-G", API]
    for key, value in params.items():
        cmd += ["--data-urlencode", "%s=%s" % (key, value)]
    return json.loads(subprocess.check_output(cmd))


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(value or ""))).strip()


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    os.makedirs(ART_DIR, exist_ok=True)
    titles = "|".join("File:" + t for _, t, _ in TITLES)
    data = curl_json({
        "action": "query", "format": "json", "titles": titles,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata",
        "iiurlwidth": "1000",
    })
    pages = {p["title"]: p for p in data.get("query", {}).get("pages", {}).values()}

    rows = []
    for slug, title, role in TITLES:
        key = "File:" + title
        page = pages.get(key)
        if not page or "imageinfo" not in page:
            print("REFUSE %-12s no Commons imageinfo for %s" % (slug, key))
            continue
        ii = page["imageinfo"][0]
        em = ii.get("extmetadata", {})
        licence = clean(em.get("LicenseShortName", {}).get("value"))
        usage = clean(em.get("UsageTerms", {}).get("value"))
        copyrighted = clean(em.get("Copyrighted", {}).get("value"))
        evidence = (licence + " " + usage).lower()
        if not any(token in evidence for token in ALLOWED):
            print("REFUSE %-12s licence not verifiably free: %r / %r" % (slug, licence, usage))
            continue
        if copyrighted.lower() in ("true", "yes"):
            print("REFUSE %-12s Commons marks it copyrighted" % slug)
            continue

        url = ii.get("thumburl") or ii.get("url")
        if not url:
            print("REFUSE %-12s no downloadable URL" % slug)
            continue
        dest = os.path.join(ART_DIR, slug + ".jpg")
        subprocess.check_call(["curl", "-sS", "--max-time", "120", "-L", "-o", dest, url])
        size = os.path.getsize(dest)
        if size < 15_000:
            os.remove(dest)
            print("REFUSE %-12s download looks empty (%d bytes)" % (slug, size))
            continue

        rows.append({
            "slug": slug,
            "file": slug + ".jpg",
            "role": role,
            "commons_title": key,
            "artist": clean(em.get("Artist", {}).get("value"))[:180],
            "date": clean(em.get("DateTimeOriginal", {}).get("value"))[:80],
            "licence": licence,
            "usage_terms": usage,
            "copyrighted_flag": copyrighted,
            "licence_url": clean(em.get("LicenseUrl", {}).get("value")),
            "source_page": ii.get("descriptionurl", ""),
            "credit": clean(em.get("Credit", {}).get("value"))[:180],
            "source_width": ii.get("width"),
            "source_height": ii.get("height"),
            "bytes": size,
            "sha256": sha256(dest),
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
        print("OK     %-12s %-16s %7d bytes  %s" % (slug, licence[:16], size, key[:56]))

    manifest = {
        "source": "Wikimedia Commons API (commons.wikimedia.org/w/api.php)",
        "policy": "fail-close: only Public domain / CC0 / PD-* metadata accepted; others refused and never shipped",
        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(rows),
        "works": rows,
    }
    with open(os.path.join(ART_DIR, "art.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print("Wrote %d licensed works -> %s" % (len(rows), ART_DIR))
    return 0 if len(rows) == len(TITLES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
