#!/usr/bin/env python3
"""Pixel audit of the palette *inside* the content blocks.

For every element carrying a `tint-*` class this screenshots the element, samples
a pixel inside its own padding, and compares it with the `--tint-bg` step the
contract says that class must use. That catches the two failure modes a CSS read
cannot: a class that resolves to nothing, and a child surface covering the tint.

    python harness/scripts/audit_tint_pixels.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import palette_scale  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "outputs" / "closed-beta-site" / "index.html"
OUT = ROOT / "outputs"
STAMP = "2026-11-16"
TOLERANCE = 3


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def main() -> int:
    palette = palette_scale.full_palette()
    failures: list[str] = []
    sampled: list[dict] = []

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.goto(SITE.as_uri())
        page.wait_for_timeout(400)

        blocks = page.evaluate(
            """() => [...document.querySelectorAll('[class*="tint-"]')]
                 .map((el, i) => {
                   const hue = [...el.classList].find(c => c.startsWith('tint-')).slice(5);
                   const r = el.getBoundingClientRect();
                   return {i, hue, cls: el.className, tag: el.tagName,
                           bg: getComputedStyle(el).backgroundColor,
                           w: Math.round(r.width), h: Math.round(r.height),
                           visible: r.width > 40 && r.height > 20};
                 })"""
        )
        handles = page.query_selector_all('[class*="tint-"]')

        for handle, meta in zip(handles, blocks):
            if not meta["visible"]:
                continue
            expected_hex = palette[meta["hue"]][palette_scale.TINTS[meta["hue"]]["bg"]]
            expected = hex_to_rgb(expected_hex)

            # 1. the computed background must be the contracted step. This is what
            #    catches a more specific component rule quietly winning.
            rgb = meta["bg"].replace("rgba(", "").replace("rgb(", "").replace(")", "")
            parts = [int(float(p)) for p in rgb.split(",")[:3]]
            computed_delta = max(abs(a - b) for a, b in zip(parts, expected))
            record = {
                "hue": meta["hue"],
                "tag": meta["tag"],
                "class": meta["cls"],
                "expected": expected_hex,
                "computed": "#%02X%02X%02X" % tuple(parts),
            }
            if computed_delta > TOLERANCE:
                failures.append(
                    f"{meta['tag']} .{meta['cls']} computes #%02X%02X%02X, contract says {expected_hex}"
                    % tuple(parts)
                )

            # 2. and the paint must reach the pixels. Tables paint their rows, so
            #    they are checked by computed style only.
            if meta["tag"] != "TABLE" and meta["h"] > 40:
                shot = OUT / f".tint-sample-{meta['i']}.png"
                handle.screenshot(path=str(shot))
                image = Image.open(shot).convert("RGB")
                point = (image.size[0] // 2, min(12, max(2, image.size[1] // 2)))
                actual = image.getpixel(point)
                shot.unlink(missing_ok=True)
                record["pixel"] = "#%02X%02X%02X" % actual
                if max(abs(a - b) for a, b in zip(actual, expected)) > TOLERANCE:
                    failures.append(
                        f"{meta['tag']} .{meta['cls']} paints #%02X%02X%02X at {point}, "
                        "contract says %s" % (actual + (expected_hex,))
                    )
            sampled.append(record)

        browser.close()

    if len(sampled) < palette_scale.MIN_TINTED_BLOCKS:
        failures.append(
            f"only {len(sampled)} tinted blocks rendered, expected >= {palette_scale.MIN_TINTED_BLOCKS}"
        )

    (OUT / f"tint-pixel-audit-{STAMP}.json").write_text(
        json.dumps({"blocks": sampled, "failures": failures}, indent=2), encoding="utf-8"
    )
    if failures:
        print("FAILURES")
        for item in failures:
            print(" -", item)
        return 1
    hues = sorted({s["hue"] for s in sampled})
    print(
        f"OK {len(sampled)} tinted blocks sampled, {len(hues)} hues ({', '.join(hues)});"
        f" every block paints the step its class contracts, within {TOLERANCE}/255."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
