#!/usr/bin/env python3
"""Balance audit: is the decoration spread down the page, or front-loaded?

Counts, per section, whether it carries artwork (a public-domain plate), a tinted
block, or an ornament rule; then checks that no long stretch of the page is bare
and that the lower half is not empty. Also renders every variant, so the report
and the screenshots come from the same run.

    python harness/scripts/audit_page_balance.py
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "outputs" / "closed-beta-site" / "index.html"
OUT = ROOT / "outputs"
STAMP = "2026-11-16"

VARIANTS = [
    ("initial", ""),
    ("conversation", "?variant=conversation"),
    ("fieldnotes", "?variant=fieldnotes"),
]

MAX_BARE_RUN = 2


def prime(page) -> None:
    """Force every lazy image to load, then wait for the loads to finish.

    Scrolling alone is not enough: Chromium starts the fetch but `complete` stays
    false until decode, which made an earlier run report six false failures.
    """
    page.evaluate(
        """async () => {
          document.querySelectorAll('img[loading="lazy"]').forEach(img => { img.loading = 'eager'; });
          const step = Math.round(window.innerHeight * 0.8);
          for (let y = 0; y < document.body.scrollHeight; y += step) {
            window.scrollTo(0, y);
            await new Promise(r => setTimeout(r, 40));
          }
          window.scrollTo(0, 0);
          await Promise.all([...document.images].map(img =>
            img.complete ? Promise.resolve()
                         : new Promise(res => { img.onload = img.onerror = res; })
          ));
        }"""
    )
    page.wait_for_timeout(300)


def audit(page) -> dict:
    return page.evaluate(
        """() => {
          const sections = [...document.querySelectorAll('section[id]')]
            .filter(s => s.getBoundingClientRect().height > 40)
            .map((s, i) => {
              const art = [...s.querySelectorAll('img')]
                .filter(img => {
                  const src = img.getAttribute('src') || '';
                  return src.includes('assets/art/') || src.includes('assets/reference-style/');
                })
                .filter(img => !img.closest('.plate-sm'));
              const plates = s.querySelectorAll('.plate-sm');
              const orn = s.querySelectorAll('.orn');
              const tinted = s.querySelectorAll('[class*="tint-"]');
              return {
                i, id: s.id,
                art: art.length + plates.length,
                ornaments: orn.length,
                tinted: tinted.length,
                height: Math.round(s.getBoundingClientRect().height),
              };
            });
          const docWidth = document.documentElement.scrollWidth;
          const collages = [...document.querySelectorAll('.collage')].map(card => {
            const fig = card.querySelector('.figure');
            const foot = card.querySelector('.foot');
            const last = card.querySelector('ul li:last-child');
            const fr = fig ? fig.getBoundingClientRect() : null;
            const lr = last ? last.getBoundingClientRect() : null;
            const or = foot ? foot.getBoundingClientRect() : null;
            const overlaps = (a, b) => a && b &&
              !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);
            return {
              title: (card.querySelector('h3') || {}).textContent || '',
              figLoaded: fig ? fig.complete && fig.naturalWidth > 0 : false,
              objLoaded: (() => {
                const o = card.querySelector('.object');
                return o ? o.complete && o.naturalWidth > 0 : false;
              })(),
              listOverFigure: overlaps(lr, fr),
              footOverFigure: overlaps(or, fr),
              overflow: card.scrollWidth > card.clientWidth + 1,
            };
          });
          return {
            sections, collages,
            docWidth,
            viewport: window.innerWidth,
            horizontalOverflow: docWidth > window.innerWidth + 1,
            brokenImages: [...document.images]
              .filter(img => img.complete && img.naturalWidth === 0)
              .map(img => img.getAttribute('src') || '(no src)'),
            tintedTotal: document.querySelectorAll('[class*="tint-"]').length,
            plateTotal: document.querySelectorAll('.plate-sm').length,
            ornamentTotal: document.querySelectorAll('.orn').length,
          };
        }"""
    )


def main() -> int:
    report: dict[str, object] = {}
    failures: list[str] = []

    with sync_playwright() as play:
        browser = play.chromium.launch()
        for name, query in VARIANTS:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(SITE.as_uri() + query)
            page.wait_for_timeout(300)
            prime(page)
            page.screenshot(path=str(OUT / f"closed-beta-site-{name}-{STAMP}.png"), full_page=True)
            report[name] = audit(page)
            page.close()

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mobile.goto(SITE.as_uri())
        mobile.wait_for_timeout(300)
        prime(mobile)
        mobile.screenshot(path=str(OUT / f"closed-beta-site-mobile-{STAMP}.png"), full_page=True)
        report["mobile"] = audit(mobile)
        mobile.close()
        browser.close()

    base = report["initial"]
    sections = base["sections"]
    half = len(sections) / 2
    top_art = sum(s["art"] for s in sections[: int(half)])
    bottom_art = sum(s["art"] for s in sections[int(half):])
    top_orn = sum(s["ornaments"] for s in sections[: int(half)])
    bottom_orn = sum(s["ornaments"] for s in sections[int(half):])

    bare_run = 0
    for s in sections:
        if s["art"] or s["ornaments"]:
            bare_run = 0
        else:
            bare_run += 1
            if bare_run > MAX_BARE_RUN:
                failures.append(
                    f"{bare_run} consecutive sections without art or ornament, ending at #{s['id']}"
                )

    if bottom_art < 2:
        failures.append(f"lower half has {bottom_art} artworks, expected >= 2")
    if base["horizontalOverflow"]:
        failures.append("horizontal overflow at 1440px")
    if report["mobile"]["horizontalOverflow"]:
        failures.append("horizontal overflow at 390px")
    for name in ("initial", "conversation", "fieldnotes", "mobile"):
        broken = [img for img in report[name]["brokenImages"] if img != "(no src)"]
        if broken:
            failures.append(f"{name}: broken images {broken}")
    if base["tintedTotal"] < 14:
        failures.append(f"only {base['tintedTotal']} tinted blocks")

    collages = base.get("collages") or []
    if len(collages) != 3:
        failures.append(f"{len(collages)} collage cards rendered, expected 3")
    for card in collages:
        name = card["title"][:34]
        if not card["figLoaded"]:
            failures.append(f"collage {name!r}: figure image did not load")
        if not card["objLoaded"]:
            failures.append(f"collage {name!r}: object image did not load")
        if card["listOverFigure"]:
            failures.append(f"collage {name!r}: last bullet runs under the figure")
        if card["footOverFigure"]:
            failures.append(f"collage {name!r}: footnote runs under the figure")
        if card["overflow"]:
            failures.append(f"collage {name!r}: content overflows the card")

    report["summary"] = {
        "sections": len(sections),
        "art_top_half": top_art,
        "art_bottom_half": bottom_art,
        "ornament_top_half": top_orn,
        "ornament_bottom_half": bottom_orn,
        "tinted_blocks": base["tintedTotal"],
        "plates": base["plateTotal"],
        "ornaments": base["ornamentTotal"],
        "max_bare_run": MAX_BARE_RUN,
        "failures": failures,
    }
    (OUT / f"page-balance-audit-{STAMP}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print(json.dumps(report["summary"], indent=2))
    if failures:
        print("FAILURES")
        for item in failures:
            print(" -", item)
        return 1
    print("OK decoration is spread: no bare stretch longer than "
          f"{MAX_BARE_RUN} sections; lower half carries {bottom_art} plates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
