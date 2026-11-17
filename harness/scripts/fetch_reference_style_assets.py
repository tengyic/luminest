#!/usr/bin/env python3
"""Fetch open-licensed assets matching the paper/figure style of the reference page.

Fail-close rule: only Wikimedia Commons works whose metadata explicitly reports
Public domain / CC0 / PD-* AND whose `Copyrighted` flag is not True are shipped.
Every shipped file is optimized locally and recorded with its measured sha256.

    env -u PYTHONPATH python3 harness/scripts/fetch_reference_style_assets.py
    env -u PYTHONPATH python3 harness/scripts/fetch_reference_style_assets.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import time

from PIL import Image, ImageDraw, ImageOps

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(WORKSPACE, "outputs", "reference-style-assets")
WEB_DIR = os.path.join(OUT_DIR, "web")
MANIFEST = os.path.join(OUT_DIR, "assets.json")
API = "https://commons.wikimedia.org/w/api.php"

# slug, exact Commons file title, visual role in the Luminest variant
TITLES = [
    ("child-title", "A Child's Own Book of Verse - title.png", "old book title ornament"),
    ("children-tree", "Children reading beneath a tree - Story-Friends (1927) - Mabel Betsy Hill.jpg", "students reading"),
    ("children-outdoors", "Two children reading outdoors - C. A. Northam - Our Little Ones and the Nursery (1888).jpg", "two learners"),
    ("woman-girl", "Woman and girl reading - My Very First Little French Book (1909).png", "adult and child reading"),
    ("reading-group", "Woman reading to a group of children - Little Sunshine's Holiday (1900) - Etheldred B. Barry.jpg", "teacher with group"),
    ("school-1904", "North Creek Public School 1904 illustration.jpg", "classroom / teacher scene"),
    ("books-plate", "Oliver Ellsworth, full-length portrait, standing, facing right, left hand on stack of books LCCN96511656.jpg", "scholar with books"),
    ("books-bookplate", "Soldier with stack of books from 1918 Bookplate of War Service Library LCCN2016646251 (cropped).jpg", "book stack ornament"),
    ("idea-patent", "BubbleLightPatent.png", "idea / light bulb patent drawing"),
    ("edison-bulb", "Drawing of the Incandescent Light Bulb by Thomas Edison, 01-27-1880 (Page 1 of 2) (5286032634).jpg", "light bulb patent sheet"),
]

ALLOWED = ("public domain", "cc0", "pd-old", "pd-art", "pd-us")
MAX_SIDE = 900
JPEG_QUALITY = 72
CREAM = (247, 241, 225)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(value or ""))).strip()


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def curl_json(params: dict) -> dict:
    cmd = ["curl", "-sS", "--max-time", "60", "-G", API]
    for key, value in params.items():
        cmd += ["--data-urlencode", "%s=%s" % (key, value)]
    return json.loads(subprocess.check_output(cmd))


def fetch() -> int:
    os.makedirs(WEB_DIR, exist_ok=True)
    titles = "|".join("File:" + title for _, title, _ in TITLES)
    data = curl_json({
        "action": "query", "format": "json", "titles": titles,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata",
        "iiurlwidth": str(MAX_SIDE),
    })
    pages = {p["title"]: p for p in data.get("query", {}).get("pages", {}).values()}

    rows = []
    for slug, title, role in TITLES:
        key = "File:" + title
        page = pages.get(key)
        if not page or "imageinfo" not in page:
            print("REFUSE %-18s no Commons imageinfo for %s" % (slug, key))
            continue
        ii = page["imageinfo"][0]
        em = ii.get("extmetadata", {})
        licence = clean(em.get("LicenseShortName", {}).get("value"))
        usage = clean(em.get("UsageTerms", {}).get("value"))
        copyrighted = clean(em.get("Copyrighted", {}).get("value"))
        evidence = (licence + " " + usage).lower()
        if not any(token in evidence for token in ALLOWED):
            print("REFUSE %-18s licence not verifiably free: %r / %r" % (slug, licence, usage))
            continue
        if copyrighted.lower() in ("true", "yes"):
            print("REFUSE %-18s Commons marks it copyrighted" % slug)
            continue
        url = ii.get("thumburl") or ii.get("url")
        if not url:
            print("REFUSE %-18s no downloadable URL" % slug)
            continue

        raw = os.path.join(OUT_DIR, slug + ".source")
        download = subprocess.run([
            "curl", "-sS", "--max-time", "75", "--retry", "2", "--retry-delay", "1",
            "-L", "-o", raw, url,
        ])
        if download.returncode != 0 or not os.path.isfile(raw) or os.path.getsize(raw) < 5_000:
            print("REFUSE %-18s download failed after retries (%s)" % (slug, download.returncode))
            if os.path.exists(raw):
                os.remove(raw)
            continue
        try:
            with Image.open(raw) as src:
                im = ImageOps.exif_transpose(src)
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    im = im.convert("RGBA")
                    bg = Image.new("RGBA", im.size, CREAM + (255,))
                    im = Image.alpha_composite(bg, im).convert("RGB")
                else:
                    im = im.convert("RGB")
                im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
                dest = os.path.join(WEB_DIR, slug + ".jpg")
                im.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        except Exception as exc:
            print("REFUSE %-18s image decode failed: %s" % (slug, exc))
            if os.path.exists(raw):
                os.remove(raw)
            continue
        finally:
            if os.path.exists(raw):
                os.remove(raw)

        size = os.path.getsize(dest)
        if size < 5_000:
            os.remove(dest)
            print("REFUSE %-18s optimized file looks blank (%d bytes)" % (slug, size))
            continue

        rows.append({
            "slug": slug,
            "role": role,
            "file": "web/" + slug + ".jpg",
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
            "shipped_bytes": size,
            "shipped_sha256": sha256(dest),
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
        print("OK     %-18s %-16s %7d bytes  %s" % (slug, licence[:16], size, key[:58]))

    manifest = {
        "source": "Wikimedia Commons API (commons.wikimedia.org/w/api.php)",
        "policy": "fail-close: only explicit Public domain / CC0 / PD-* with Copyrighted != True; others refused and never shipped",
        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(rows),
        "works": rows,
    }
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    contact_sheet(rows)
    print("Wrote %d licensed assets -> %s" % (len(rows), OUT_DIR))
    return 0 if len(rows) >= 8 else 1


def contact_sheet(rows: list[dict]) -> None:
    cols, cell = 4, 260
    canvas = Image.new("RGB", (cols * cell, ((len(rows) + cols - 1) // cols) * (cell + 26)), CREAM)
    draw = ImageDraw.Draw(canvas)
    for i, row in enumerate(rows):
        path = os.path.join(OUT_DIR, row["file"])
        with Image.open(path) as im:
            thumb = ImageOps.contain(im.convert("RGB"), (cell - 16, cell - 16), Image.LANCZOS)
            x = (i % cols) * cell + (cell - thumb.width) // 2
            y = (i // cols) * (cell + 26) + 8
            canvas.paste(thumb, (x, y))
        draw.text(((i % cols) * cell + 8, (i // cols) * (cell + 26) + cell + 2),
                  row["slug"], fill=(40, 35, 28))
    canvas.save(os.path.join(OUT_DIR, "contact-sheet.jpg"), "JPEG", quality=78, optimize=True)


def check() -> int:
    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    problems = []
    total = 0
    for row in manifest.get("works", []):
        path = os.path.join(OUT_DIR, row["file"])
        if not os.path.isfile(path):
            problems.append("missing " + row["file"])
            continue
        digest = sha256(path)
        if digest != row["shipped_sha256"]:
            problems.append("sha256 mismatch " + row["file"])
        if os.path.getsize(path) != row["shipped_bytes"]:
            problems.append("size mismatch " + row["file"])
        evidence = (row.get("licence", "") + " " + row.get("usage_terms", "")).lower()
        if not any(token in evidence for token in ALLOWED):
            problems.append("licence not free " + row["slug"])
        if str(row.get("copyrighted_flag", "")).lower() in ("true", "yes"):
            problems.append("copyrighted flag " + row["slug"])
        if not row.get("source_page", "").startswith("https://commons.wikimedia.org/wiki/"):
            problems.append("source_page " + row["slug"])
        with Image.open(path) as im:
            if min(im.size) < 20:
                problems.append("blank image " + row["slug"])
        total += os.path.getsize(path)
    print("CHECK count=%d total_bytes=%d problems=%d" % (manifest.get("count", 0), total, len(problems)))
    for problem in problems[:20]:
        print("  FAIL", problem)
    return 0 if not problems and total <= 3_500_000 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    return check() if args.check else fetch()


if __name__ == "__main__":
    raise SystemExit(main())
