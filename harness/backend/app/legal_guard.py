"""Legal shippability guard (audit finding L-1).

The documents in ``backend/legal/`` are templates: every operational fact they need
-- who the legal entity is, where it is domiciled, who the DPO is, which providers
process data, which court hears disputes -- is an unfilled bracket placeholder such
as ``[LEGAL ENTITY NAME]`` or ``[JURISDICTION]``. Publishing them as-is would make
false and possibly misleading legal statements to real users; inventing the values
is not an engineering task and is expressly out of scope (see
``backend/legal/FILL_IN_SHEET.md`` for who owns each blank).

This module makes it *structural* that an unfilled bundle cannot ship:

* :func:`unfilled_placeholders` scans the bundle for bracket placeholders.
* ``Settings.from_env`` refuses to start with ``HARNESS_ENV=production`` while any
  placeholder remains, unless the operator passes ``HARNESS_LEGAL_TEMPLATE_OK=1``
  explicitly (for staging a template build where no real user can reach it).
* ``scripts/check_legal.py`` is the standalone CLI, and the packaging script gates
  the DMG/zip on it.

The check is textual on purpose: a placeholder is a bracketed token containing an
uppercase letter or a digit, and is not a Markdown link. The documents themselves
carry the "this is a template, not legal advice" notice; this guard is the second
line of defence, not a substitute for counsel sign-off, which is a human decision
recorded in the fill-in sheet.
"""
from __future__ import annotations

import re
from pathlib import Path

#: A bracketed token that carries an uppercase letter or a digit, is not longer
#: than a plausible placeholder, and is not the link text of ``[text](url)``.
#: Lowercase prose brackets such as ``[see below]`` are left alone.
PLACEHOLDER_RE = re.compile(r'\[(?=[^\]\n]*[A-Z0-9])[^\]\n]{1,60}\](?!\()')


def unfilled_placeholders(legal_dir) -> dict[str, list[str]]:
    """Map every legal document to its remaining bracket placeholders.

    Returns ``{filename: [placeholder, ...]}``; an empty dict means the bundle is
    shippable. Text files only (``*.md``).
    """
    directory = Path(legal_dir)
    if not directory.is_dir():
        # A bundle with no legal documents at all is not shippable either.
        return {'<missing>': [f'legal directory not found: {directory}']}
    found: dict[str, list[str]] = {}
    for path in sorted(directory.glob('*.md')):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            for match in PLACEHOLDER_RE.finditer(line):
                found.setdefault(path.name, []).append(f'line {number}: {match.group(0)}')
    return found


def assert_shippable(legal_dir) -> None:
    """Raise ``ValueError`` with the full placeholder list if the bundle is unfilled."""
    found = unfilled_placeholders(legal_dir)
    if found:
        detail = '; '.join(f'{name}: {", ".join(tokens)}' for name, tokens in found.items())
        raise ValueError(
            'Refusing to ship: the legal documents still contain unfilled placeholders '
            f'({detail}). Fill them from backend/legal/FILL_IN_SHEET.md with counsel '
            'sign-off, or set HARNESS_LEGAL_TEMPLATE_OK=1 only for a template build that '
            'no real user can reach.')
