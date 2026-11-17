#!/usr/bin/env python3
"""Luminest brand palette scale — generator and verifier.

The site shipped nine brand colours (`sage, pine, lilac, clay, olive, iris,
amber, sand`, plus `sage-bar` in the sage family) as single tones, so components
had no legal way to use the same family at surface, border, accent and text
weight. This script derives a ten-step tonal ramp per hue.

Derivation rule (deterministic, documented, reproducible):

1. Each brand hex is converted to HSL.
2. A fixed lightness ladder is laid over 50..900:
       .97 .94 .88 .79 .68 .57 .46 .36 .27 .19
3. Hue is preserved exactly. Saturation is nudged (never replaced) so very
   light steps keep a readable tint and very dark steps stop glowing:
       L >= .85  ->  S * 1.25      (ceiling .46)
       L <= .35  ->  S * 0.90
4. The brand hex itself is *pinned* at the step whose ladder value is closest
   to its own lightness — that step renders the literal brand colour, so the
   ramp can never drift away from the brand. Neighbouring steps are pushed
   apart by at least .02 L so the ramp stays monotonic.

Nothing is sampled from a screenshot and no value is hand-typed; re-running
this file reproduces the same CSS byte for byte.

Usage:
    python harness/scripts/palette_scale.py             # print CSS custom props
    python harness/scripts/palette_scale.py --json      # machine-readable dump
    python harness/scripts/palette_scale.py --check PATH # verify shipped CSS
"""

from __future__ import annotations

import argparse
import colorsys
import json
import re
import sys
from pathlib import Path

PAPER = "#F7F5F0"
INK = "#1B241D"

# Brand hues in shipped order. `sage-bar` folds into the sage family: it is the
# same olive-green used for the progress bar.
HUES: dict[str, str] = {
    "sage": "#E7EDE3",
    "pine": "#2B3A2E",
    "lilac": "#E6E3F2",
    "clay": "#B5725A",
    "olive": "#7C8B6B",
    "iris": "#8E86A8",
    "amber": "#D89A3F",
    "sand": "#EDE3D8",
}

STEPS: list[str] = ["050", "100", "200", "300", "400", "500", "600", "700", "800", "900"]
LADDER: list[float] = [0.97, 0.94, 0.88, 0.79, 0.68, 0.57, 0.46, 0.36, 0.27, 0.19]
MIN_GAP = 0.02


# --------------------------------------------------------------------------
# colour maths
# --------------------------------------------------------------------------

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) != 6:
        raise ValueError(f"expected 6-digit hex, got {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def hex_to_hsl(value: str) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in hex_to_rgb(value))
    return colorsys.rgb_to_hls(r, g, b)  # returns (h, l, s)


def hsl_to_hex(h: float, l: float, s: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return rgb_to_hex((r * 255, g * 255, b * 255))


def tune_saturation(lightness: float, saturation: float) -> float:
    if lightness >= 0.85:
        return min(0.46, saturation * 1.25)
    if lightness <= 0.35:
        return saturation * 0.90
    return saturation


def lightness_ladder(base_hex: str) -> list[tuple[float, bool]]:
    """(lightness, is_brand_hex) per step, with the brand hex pinned at its
    nearest ladder value and the ramp forced monotonic."""
    _, l0, _ = hex_to_hsl(base_hex)
    ladder = list(LADDER)
    index = min(range(len(ladder)), key=lambda i: abs(ladder[i] - l0))
    ladder[index] = l0
    for i in range(index + 1, len(ladder)):
        ladder[i] = min(ladder[i], ladder[i - 1] - MIN_GAP)
    for i in range(index - 1, -1, -1):
        ladder[i] = max(ladder[i], ladder[i + 1] + MIN_GAP)
    return [(value, i == index) for i, value in enumerate(ladder)]


def scale(hue: str) -> dict[str, str]:
    base = HUES[hue]
    h, _, s = hex_to_hsl(base)
    out: dict[str, str] = {}
    for step, (lightness, pinned) in zip(STEPS, lightness_ladder(base)):
        out[step] = base if pinned else hsl_to_hex(h, lightness, tune_saturation(lightness, s))
    return out


def full_palette() -> dict[str, dict[str, str]]:
    return {hue: scale(hue) for hue in HUES}


def pinned_step(hue: str) -> str:
    for step, (_, pinned) in zip(STEPS, lightness_ladder(HUES[hue])):
        if pinned:
            return step
    raise AssertionError(hue)


def chip_step(hue: str, background: str = PAPER) -> str:
    """Lightest step of the hue that clears 4.5:1 with `background` text.

    Deriving the chip step instead of picking it by eye is what keeps the solid
    fills on the page legible at 11px mono.
    """
    for step in STEPS:
        if contrast(background, scale(hue)[step]) >= 4.5:
            return step
    raise AssertionError(f"{hue} has no AA chip step against {background}")


# --------------------------------------------------------------------------
# WCAG contrast
# --------------------------------------------------------------------------

def _linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(value: str) -> float:
    r, g, b = hex_to_rgb(value)
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def token_value(token: str, palette: dict[str, dict[str, str]]) -> str:
    if token == "paper":
        return PAPER
    if token == "ink":
        return INK
    if token == "surface":
        return "#FFFDF9"
    if "-" not in token:
        return HUES[token]
    hue, step = token.split("-", 1)
    return palette[hue][step]


# Text pairings the landing page actually renders: (fg, bg, min ratio, note).
REQUIRED_PAIRS: list[tuple[str, str, float, str]] = [
    ("paper", "pine-900", 4.5, "body copy on pine blocks (CTA, badge)"),
    ("pine-900", "paper", 4.5, "default body"),
    ("pine-900", "surface", 4.5, "card body"),
    ("pine-900", "amber-200", 4.5, "highlight panel"),
]

# How each tinted block resolves its own steps. This table is the contract: the
# CSS block `.tint-<hue>{...}` must declare exactly these steps, and the markup
# must actually carry the class on a real content block.
TINTS: dict[str, dict[str, str]] = {
    "sage": {"bg": "100", "soft": "200", "line": "300", "accent": "700", "ink": "900"},
    "pine": {"bg": "050", "soft": "100", "line": "200", "accent": "700", "ink": "900"},
    "lilac": {"bg": "050", "soft": "100", "line": "200", "accent": "600", "ink": "900"},
    "clay": {"bg": "050", "soft": "100", "line": "200", "accent": "700", "ink": "900"},
    "olive": {"bg": "050", "soft": "100", "line": "200", "accent": "700", "ink": "900"},
    "iris": {"bg": "050", "soft": "100", "line": "200", "accent": "600", "ink": "900"},
    "amber": {"bg": "050", "soft": "100", "line": "200", "accent": "800", "ink": "900"},
    "sand": {"bg": "050", "soft": "100", "line": "300", "accent": "700", "ink": "900"},
}

MIN_TINTED_BLOCKS = 14
MIN_TINT_HUES = 6


# --------------------------------------------------------------------------
# emit / verify
# --------------------------------------------------------------------------

def css_block() -> str:
    lines = [
        "  /* Luminest brand scale, 8 hues x 10 steps. Generated by",
        "     harness/scripts/palette_scale.py — hue preserved, the brand hex is",
        "     pinned at its matching lightness step. Do not hand-edit. */",
    ]
    for hue in HUES:
        values = scale(hue)
        parts = [f"--{hue}-{step}:{values[step]}" for step in STEPS]
        for i in range(0, len(parts), 5):
            lines.append("  " + "; ".join(parts[i : i + 5]) + ";")
    return "\n".join(lines)


# Human-facing role note per hue, surfaced next to each ramp on the page.
ROLES: dict[str, str] = {
    "sage": "surface tint",
    "pine": "primary ink",
    "lilac": "tutor surface",
    "clay": "warm accent",
    "olive": "secondary accent",
    "iris": "tutor ink",
    "amber": "highlight",
    "sand": "warm surface",
}

TITLES: dict[str, str] = {
    "sage": "Sage",
    "pine": "Pine",
    "lilac": "Lilac",
    "clay": "Clay",
    "olive": "Olive",
    "iris": "Iris",
    "amber": "Amber",
    "sand": "Sand",
}

BEGIN = "<!-- palette:begin (generated by harness/scripts/palette_scale.py) -->"
END = "<!-- palette:end -->"


def html_section() -> str:
    palette = full_palette()
    rows: list[str] = []
    for hue in HUES:
        values = palette[hue]
        pin = pinned_step(hue)
        cells: list[str] = []
        for step in STEPS:
            value = values[step]
            label = f"{hue}-{step}"
            star = " is-brand" if step == pin else ""
            cells.append(
                f'\n          <li class="pl-sw{star}" data-token="{label}" '
                f'data-hex="{value}" title="{label} · {value}">'
                f'<span class="pl-chip" style="background:{value}"></span>'
                f'<span class="pl-step">{step}</span>'
                f'<span class="pl-hex">{value}</span></li>'
            )
        rows.append(
            f'\n      <div class="pl-hue" data-hue="{hue}">'
            f'\n        <div class="pl-name"><strong>{TITLES[hue]}</strong>'
            f'<span class="pl-metaline">{ROLES[hue]} · brand hex pinned at {pin}'
            f" · <code>{HUES[hue]}</code></span></div>"
            f'\n        <ol class="pl-strip">{"".join(cells)}\n        </ol>'
            f"\n      </div>"
        )
    return (
        f"{BEGIN}\n"
        '  <section id="palette">\n'
        '    <p class="micro">Brand palette</p>\n'
        "    <h2>Eight Luminest hues, ten steps each.</h2>\n"
        '    <p class="lead">The brand colours used to ship as single tones, so a '
        "surface, a border and a label had to reuse one value. Each hue now carries "
        "a full ramp: the hue is preserved exactly, saturation is only nudged at the "
        "extremes, and the original brand hex is pinned at the step whose lightness "
        "matches it — the marked swatch is the literal brand colour, so nothing here "
        "drifts off-brand.</p>\n"
        '    <div class="pl-book">'
        + "".join(rows)
        + "\n    </div>\n"
        '    <div class="pl-uses">'
        + "".join(
            f'<span style="background:var(--{hue}-{chip_step(hue)})">'
            f"{hue}-{chip_step(hue)}</span>"
            for hue in HUES
        )
        + "</div>\n"
        '    <p class="fineprint">Steps 050&ndash;300 are surfaces and borders, 400&ndash;600 '
        "are accents and fills, 700&ndash;900 are text and chips. Every text pairing used "
        "on this page clears WCAG AA at 4.5:1; <code>palette_scale.py --check</code> "
        "recomputes those ratios from this exact ramp and fails the build otherwise.</p>\n"
        "  </section>\n"
        f"{END}"
    )


def strip(html_path: Path) -> int:
    """Remove the generated palette section entirely.

    The palette belongs *inside* the content blocks, not in a swatch list beside
    them, so the section is removable without touching the tokens.
    """
    html = html_path.read_text(encoding="utf-8")
    if BEGIN not in html or END not in html:
        print("no palette section to strip")
        return 0
    head, rest = html.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    html_path.write_text(head.rstrip() + "\n" + tail.lstrip("\n"), encoding="utf-8")
    print(f"stripped palette section from {html_path}")
    return 0


def inject(html_path: Path) -> int:
    html = html_path.read_text(encoding="utf-8")
    section = html_section()
    if BEGIN in html and END in html:
        head, rest = html.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        html_path.write_text(head + section + tail, encoding="utf-8")
        print(f"replaced palette section in {html_path}")
        return 0
    marker = "<!-- palette:auto -->"
    if marker in html:
        html_path.write_text(html.replace(marker, section, 1), encoding="utf-8")
        print(f"inserted palette section at marker in {html_path}")
        return 0
    print("no palette marker found; add '<!-- palette:auto -->' where it belongs")
    return 1


def check(html_path: Path) -> int:
    html = html_path.read_text(encoding="utf-8")
    palette = full_palette()
    failures: list[str] = []

    missing = [
        f"--{hue}-{step}:{palette[hue][step]}"
        for hue in HUES
        for step in STEPS
        if f"--{hue}-{step}:{palette[hue][step]}" not in html
    ]
    if missing:
        failures.append(f"{len(missing)} token(s) missing from CSS: {missing[:6]}")

    for token, value in (
        ("--palette-sand-1", "#fdfdfc"),
        ("--palette-sand-12", "#21201c"),
        ("--palette-umber-9", "#261608"),
        ("--palette-umber-3", "#f6efea"),
        ("--palette-umber-12", "#2c1c0e"),
    ):
        if f"{token}:{value}" not in html.lower():
            failures.append(f"reference token drifted: {token} should be {value}")

    # 1. the palette must live inside blocks, not in a colour list on the page
    if 'id="palette"' in html:
        failures.append('a standalone #palette colour-list section is present')
    if "data-token=" in html:
        failures.append("swatch-book markup (data-token) is present again")

    # 2. every tint class declares the contracted steps
    for hue, steps in TINTS.items():
        match = re.search(r"\n\.tint-%s\{([^}]*)\}" % hue, html)
        if not match:
            failures.append(f".tint-{hue} is not declared")
            continue
        body = match.group(1)
        for role, step in steps.items():
            expected = f"--tint-{role}:var(--{hue}-{step})"
            if expected not in body:
                failures.append(f".tint-{hue} should declare {expected}")

    # 3. the classes are on real blocks, across enough hues
    used = re.findall(r'class="[^"]*\btint-([a-z]+)\b[^"]*"', html)
    if len(used) < MIN_TINTED_BLOCKS:
        failures.append(f"only {len(used)} tinted blocks, expected >= {MIN_TINTED_BLOCKS}")
    if len(set(used)) < MIN_TINT_HUES:
        failures.append(f"only {len(set(used))} hue families used, expected >= {MIN_TINT_HUES}")
    for hue in used:
        if hue not in TINTS:
            failures.append(f"unknown tint class tint-{hue} in markup")

    # 4. contrast: base pairs plus every tint used as text on its own surface
    pairs = list(REQUIRED_PAIRS)
    for hue, steps in TINTS.items():
        pairs.append((f"{hue}-{steps['ink']}", f"{hue}-{steps['bg']}", 4.5, f"{hue} body text on tint"))
        pairs.append((f"{hue}-{steps['accent']}", f"{hue}-{steps['bg']}", 4.5, f"{hue} accent label on tint"))
        pairs.append((f"{hue}-{steps['accent']}", f"{hue}-{steps['soft']}", 4.5, f"{hue} label on soft tint"))
        pairs.append((f"{hue}-{steps['ink']}", f"{hue}-{steps['soft']}", 4.5, f"{hue} bubble text on soft tint"))
    for fg, bg, minimum, note in pairs:
        ratio = contrast(token_value(fg, palette), token_value(bg, palette))
        if ratio < minimum:
            failures.append(f"contrast {fg} on {bg} = {ratio:.2f} < {minimum} ({note})")

    if failures:
        print("FAILURES")
        for item in failures:
            print(" -", item)
        return 1
    print(
        f"OK {len(HUES)} hues x {len(STEPS)} steps = {len(HUES) * len(STEPS)} tokens;"
        f" {len(used)} tinted blocks across {len(set(used))} hues;"
        f" {len(pairs)} contrast pairings pass; no colour-list section on the page."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="dump JSON")
    parser.add_argument("--check", metavar="INDEX_HTML", help="verify shipped CSS")
    parser.add_argument("--html", action="store_true", help="print palette section markup")
    parser.add_argument("--inject", metavar="INDEX_HTML", help="rewrite palette section")
    parser.add_argument("--strip", metavar="INDEX_HTML", help="remove palette section")
    args = parser.parse_args()

    if args.check:
        return check(Path(args.check))
    if args.strip:
        return strip(Path(args.strip))
    if args.inject:
        return inject(Path(args.inject))
    if args.html:
        print(html_section())
        return 0
    if args.json:
        print(json.dumps(full_palette(), indent=2))
        return 0
    print(css_block())
    return 0


if __name__ == "__main__":
    sys.exit(main())
