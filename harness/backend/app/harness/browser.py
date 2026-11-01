"""Headless-browser snapshot for the tutor's tool loop (teacher-only, gated).

This is the *tool-side* browser: the tutor asks for a page's structure and a still
image so a teacher can decide whether a site is worth pinning for a class. It is
complementary to the app-side WKWebView page, which is the human browsing surface --
the two share a role model but not code.

Posture notes that matter:

- ``HARNESS_BROWSER_ENABLED`` is the kill switch, default off, like ``media_enabled``.
- Only a teacher principal may call it (checked in toolbox by role, server-side).
- A screenshot of an external page is a *copy of pixels*. It is stored locally with a
  TTL and is never returned as source text to the model: the tool returns the page
  title and the link, and the image only ever surfaces on a teacher's screen. Text
  extraction is limited to the page <title> plus first-paragraph excerpt *only when*
  the domain is licence-cleared by the same ``_domain_rights`` table web_search uses;
  everything else returns the link with the screenshot and no copied text.
- No cookies are persisted: every launch is a fresh context, so no login session can
  leak from one snapshot to the next.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

#: Screenshot files older than this are stale; the caller deletes on read.
SNAPSHOT_TTL_SECONDS = 24 * 3600
_MAX_TEXT_EXCERPT = 600


def snapshots_dir(settings) -> Path:
    base = getattr(settings, 'media_cache_dir', '') or str(settings.data_dir)
    path = Path(base) / 'browser_snapshots'
    path.mkdir(parents=True, exist_ok=True)
    return path


def purge_expired(settings) -> int:
    """Delete TTL-expired snapshots. Called opportunistically before a new snapshot."""
    cutoff = time.time() - SNAPSHOT_TTL_SECONDS
    removed = 0
    for file in snapshots_dir(settings).glob('*.png'):
        try:
            if file.stat().st_mtime < cutoff:
                file.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def snapshot(url: str, *, settings, allow_hosts: tuple[str, ...] = (),
             timeout: float = 20.0, full_page: bool = False) -> dict[str, Any]:
    """Open ``url`` in a fresh headless chromium and capture a still + title.

    Returns a dict that is honest about what happened: ``ok`` with artifacts, or
    ``ok=False`` with a ``refused``/``error`` reason. Never raises to the tool loop.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        return {'ok': False, 'refused': 'A http(s) URL is required.'}
    if allow_hosts:
        host = (parsed.hostname or '').casefold()
        if not any(host == h or host.endswith('.' + h) for h in allow_hosts):
            return {'ok': False,
                    'refused': f'{parsed.hostname} is outside the operator allowlist '
                               'for the browser tool.'}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {'ok': False,
                'refused': 'The playwright package is not installed in this environment; '
                           'no browser was launched and nothing is faked.'}
    purge_expired(settings)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={'width': 1280, 'height': 900})
                page = context.new_page()
                page.goto(url, timeout=int(timeout * 1000), wait_until='domcontentloaded')
                title = page.title()[:200]
                # Content extract only under the shared web domain rights table; an
                # uncleared domain yields a screenshot but zero copied text.
                from .tools_creation import _domain_rights
                licence, klass = _domain_rights(str(page.url))
                excerpt = ''
                if klass in {'public_domain', 'cc0', 'cc_by', 'cc_by_sa'}:
                    try:
                        body = page.inner_text('body', timeout=3000)
                        excerpt = ' '.join(body.split())[:_MAX_TEXT_EXCERPT]
                    except Exception:
                        excerpt = ''
                digest = hashlib.sha256(str(page.url).encode() +
                                        str(time.time_ns()).encode()).hexdigest()[:16]
                out = snapshots_dir(settings) / f'snap-{digest}.png'
                page.screenshot(path=str(out), full_page=full_page)
                return {'ok': True, 'url': str(page.url), 'title': title,
                        'screenshot': str(out), 'licence': licence, 'licence_class': klass,
                        'text_excerpt': excerpt, 'text_returned': bool(excerpt),
                        'mode': 'ingestible' if excerpt else 'link_only'}
            finally:
                browser.close()
    except Exception as exc:
        return {'ok': False, 'error': f'Browser snapshot failed: {type(exc).__name__}: {exc}'}
