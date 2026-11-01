#!/usr/bin/env python3
"""Render a stored artefact in a real browser and screenshot it.

Structural validation proves the file is self-contained and parses. It does not prove
the thing runs: a simulation can be perfectly valid HTML whose script throws on load and
leaves an empty frame. This loads it, collects console errors, drives the first control,
and screenshots before and after, so "it works" is something seen rather than assumed.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

src = Path(sys.argv[1])
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('/tmp/artifact.png')
after = out.with_name(out.stem + '_after' + out.suffix)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1280, 'height': 860})
    errors, logs = [], []
    page.on('console', lambda m: (logs.append(f'{m.type}: {m.text}'),
                                  errors.append(m.text) if m.type == 'error' else None))
    page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
    page.goto(src.as_uri())
    page.wait_for_timeout(700)
    page.screenshot(path=str(out))
    # Drive the first real control, so a static render cannot pass as interactive.
    moved = page.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('input[type=range]'));
        if (!els.length) return null;
        const el = els[0];
        el.value = el.max || '5';
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        return el.id || el.name || 'range';
    }""")
    page.wait_for_timeout(500)
    page.screenshot(path=str(after))
    text = page.inner_text('body')[:900]
    print(f'console errors : {errors or "none"}')
    print(f'controls driven: {moved}')
    print(f'body text      : {text!r}')
    browser.close()
