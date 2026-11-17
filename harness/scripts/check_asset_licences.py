#!/usr/bin/env python3
"""Fail-close licence gate for every image the page actually references.

The reference page ships cut-out PNGs taken from stock photography with no
licence metadata, so none of them are used here. This gate makes that a rule
rather than a promise: every `assets/art/*` and `assets/reference-style/*`
reference in index.html must appear in a manifest whose entry is explicitly
public domain / CC0 and not flagged copyrighted.

    python harness/scripts/check_asset_licences.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "outputs" / "closed-beta-site"
PAGE = SITE / "index.html"

FREE = ("public domain", "cc0", "pd-", "pd ")
REJECTED_FLAGS = {"true", "yes", "1"}


def load(manifest: Path) -> tuple[dict[str, dict], list[str]]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    works = data.get("works") or data.get("items") or []
    index: dict[str, dict] = {}
    problems: list[str] = []
    for work in works:
        slug = work.get("slug")
        if not slug:
            problems.append(f"{manifest.name}: entry without a slug")
            continue
        index[slug] = work
    return index, problems


def licence_ok(work: dict) -> bool:
    licence = (work.get("licence") or "").strip().lower()
    usage = (work.get("usage_terms") or "").strip().lower()
    flag = str(work.get("copyrighted_flag", "false")).strip().lower()
    if flag in REJECTED_FLAGS:
        return False
    return any(token in licence for token in FREE) or any(token in usage for token in FREE)


def main() -> int:
    failures: list[str] = []
    checked = 0

    art_index, art_problems = load(SITE / "assets" / "art.json")
    ref_index, ref_problems = load(SITE / "assets" / "reference-style.json")
    failures += art_problems + ref_problems

    html = PAGE.read_text(encoding="utf-8")
    referenced = sorted(set(re.findall(r"assets/(art|reference-style)/([a-z0-9-]+)\.jpg", html)))
    if not referenced:
        failures.append("page references no artwork at all")

    for family, slug in referenced:
        index = art_index if family == "art" else ref_index
        work = index.get(slug)
        checked += 1
        if work is None:
            failures.append(f"{family}/{slug}.jpg is referenced but missing from the manifest")
            continue
        if not licence_ok(work):
            failures.append(
                f"{family}/{slug}.jpg licence is not verifiably free: "
                f"{work.get('licence')!r} / {work.get('usage_terms')!r}"
            )
        if not work.get("source_page"):
            failures.append(f"{family}/{slug}.jpg has no source page")
        shipped = SITE / "assets" / family / f"{slug}.jpg"
        if not shipped.is_file():
            failures.append(f"{family}/{slug}.jpg is referenced but not on disk")

    # nothing from the reference bundle may be shipped
    for banned in ("parent-paper", "teacher-figure", "student-header", "cream-paper", "map-paper"):
        if (SITE / "assets" / "art" / f"{banned}.jpg").exists() or (
            SITE / "assets" / "reference-style" / f"{banned}.jpg"
        ).exists():
            failures.append(f"reference bundle asset {banned} is present in the site")

    if failures:
        print("FAILURES")
        for item in failures:
            print(" -", item)
        return 1
    print(f"OK {checked} referenced images, all with a free licence and a source page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
