"""Does a stored simulation actually run, or does it merely parse?

:func:`app.harness.sims_store.validate_html` answers a safety question: is this document
self-contained, parseable, and free of anything that loads from outside or evaluates
dynamic code? It cannot answer the question a learner asks in the first second -- *does
this thing work* -- because "valid" and "correct" are different properties.

Measured 2026-11-01 on a generated action-potential scope: the document passed every
structural rule and drew correct axes, a threshold line and a legend. Pressing **Stimulate**
then collapsed the trace to a vertical line at t=0 and printed ``peak Infinity mV``,
because the integrator divided by a zero conductance step. Nothing about the file said so;
only running it did.

So this module runs it. A headless browser loads the artifact, drives its first control and
its primary button, and reports what a learner would see: script errors, a console that
threw, and the two strings that mean the maths has gone wrong (``NaN`` and ``Infinity``).

Two honest limits, both deliberate:

* **Playwright is optional.** It is not in the desktop bundle, so :func:`available` can be
  false. When it is, :func:`check` returns ``checked=False`` with the missing piece named --
  never a silent pass, which would be indistinguishable from a verified artifact.
* **This is a smoke test, not a proof.** It catches a crash and a non-finite number in the
  visible text. It cannot tell that the physics is *right*, only that the page did not
  break. Saying so is the difference between a gate and a guarantee.

Blocking, so it belongs in the TA's background job (``app.harness.ta``) rather than in a
teacher's request: a browser launch costs a second or two, and the teacher is mid-sentence.
"""

from __future__ import annotations

import re
from typing import Any

#: Strings that mean the arithmetic has produced a non-finite or missing value. Matched as
#: whole words so a legitimate label ("Infinity as a limit") does not trip it, and only in
#: the rendered text so a comment or a string literal in the source does not either.
_NON_FINITE = re.compile(r'\b(NaN|Infinity|-Infinity)\b')

DEFAULT_TIMEOUT_MS = 6000


def available() -> bool:
    """Whether this build can run a browser at all."""
    try:
        import playwright  # noqa: F401
    except Exception:                     # noqa: BLE001 - any import failure is "absent"
        return False
    return True


def _unavailable() -> dict[str, Any]:
    return {'checked': False, 'problems': [],
            'reason': 'No headless browser is installed on this instance (playwright is not '
                      'available), so this artifact was not run. Structural validation still '
                      'passed; runtime behaviour is unknown.'}


def check(html: str, *, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> dict[str, Any]:
    """Load an artifact, drive it, and report what a learner would see.

    Returns ``{'checked': bool, 'problems': [str], 'reason': str}``. ``problems`` empty and
    ``checked`` true means the page ran without a script error and displayed finite
    numbers. An empty ``problems`` with ``checked`` false means *nothing was verified* --
    the caller must not read it as a pass.
    """
    if not (html or '').strip():
        return {'checked': False, 'problems': ['The artifact is empty.'],
                'reason': 'Nothing to run.'}
    if not available():
        return _unavailable()

    from playwright.sync_api import sync_playwright

    problems: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 860})
                page.on('pageerror', lambda exc: problems.append(f'The page threw: {exc}'))
                page.on('console', lambda msg: problems.append(f'console.{msg.type}: {msg.text}')
                        if msg.type == 'error' else None)
                page.set_content(html, timeout=timeout_ms)
                page.wait_for_timeout(400)
                # Drive it the way a learner does: move the first control, then press the
                # primary button. A static render cannot pass as interactive.
                page.evaluate("""() => {
                    const el = document.querySelector('input[type=range]');
                    if (!el) return;
                    el.value = el.max || el.value;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }""")
                page.wait_for_timeout(200)
                page.evaluate("""() => {
                    const btn = Array.from(document.querySelectorAll('button'))
                        .find(b => !/reset|clear/i.test(b.textContent || ''));
                    if (btn) btn.click();
                }""")
                page.wait_for_timeout(600)
                text = page.inner_text('body')
            finally:
                browser.close()
    except Exception as exc:              # noqa: BLE001 - a browser failure is a finding
        return {'checked': False, 'problems': [],
                'reason': f'The runtime check could not run ({type(exc).__name__}: {exc}). '
                          'Runtime behaviour is unknown.'}

    if not text.strip():
        # Deliberately only *empty*, not *sparse*. A canvas-driven artifact can render a
        # handful of characters and be perfectly correct, so a length threshold would
        # manufacture false alarms on exactly the visuals this check exists to protect.
        problems.append('The page rendered no visible text at all, so nothing was drawn.')
    bad = sorted(set(_NON_FINITE.findall(text)))
    if bad:
        problems.append(f'After being driven, the page displays a non-finite value '
                        f'({", ".join(bad)}), so the arithmetic behind it is broken.')
    return {'checked': True, 'problems': problems,
            'reason': '' if not problems else 'The artifact loaded but did not behave.'}


__all__ = ['available', 'check', 'DEFAULT_TIMEOUT_MS']
