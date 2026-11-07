#!/usr/bin/env python3
"""Validate the feature verification register and render its Markdown view.

The JSON file is the single source of truth. This script fails if any feature is missing
one of the six required elements, if an id is duplicated, or if a status is not in the
published legend. Running it without arguments also regenerates
``docs/FEATURE_VERIFICATION_REGISTER.md`` so the readable document cannot drift.

Usage:
    python scripts/verify_feature_register.py            # validate + render
    python scripts/verify_feature_register.py --check    # validate only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs' / 'feature_verification_register.json'
OUTPUT = ROOT / 'docs' / 'FEATURE_VERIFICATION_REGISTER.md'

REQUIRED = (
    'id',
    'name',
    'status',
    'user_facing',
    'native',
    'backend',
    'data',
    'tests',
    'acceptance',
)
STATUSES = ('implemented', 'partial', 'absent', 'external')
STATUS_LABEL = {
    'implemented': 'implemented',
    'partial': 'partial',
    'absent': 'absent',
    'external': 'external',
}


class RegisterError(Exception):
    pass


def load() -> dict[str, Any]:
    try:
        data = json.loads(SOURCE.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise RegisterError(f'{SOURCE} does not exist') from exc
    except ValueError as exc:
        raise RegisterError(f'{SOURCE} is not valid JSON: {exc}') from exc
    if not isinstance(data, dict):
        raise RegisterError('the register root must be an object')
    return data


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    areas = data.get('areas')
    if not isinstance(areas, list) or not areas:
        return ['areas must be a non-empty list']

    seen_areas: set[str] = set()
    seen_features: set[str] = set()
    for area in areas:
        if not isinstance(area, dict):
            errors.append('an area is not an object')
            continue
        area_id = str(area.get('id') or '').strip()
        title = str(area.get('title') or '').strip()
        if not area_id or not title:
            errors.append('an area is missing id or title')
            continue
        if area_id in seen_areas:
            errors.append(f'duplicate area id: {area_id}')
        seen_areas.add(area_id)
        features = area.get('features')
        if not isinstance(features, list) or not features:
            errors.append(f'{area_id}: features must be a non-empty list')
            continue
        for feature in features:
            if not isinstance(feature, dict):
                errors.append(f'{area_id}: a feature is not an object')
                continue
            feature_id = str(feature.get('id') or '').strip()
            if not feature_id:
                errors.append(f'{area_id}: a feature has no id')
                continue
            if feature_id in seen_features:
                errors.append(f'duplicate feature id: {feature_id}')
            seen_features.add(feature_id)
            for key in REQUIRED:
                value = feature.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f'{feature_id}: missing or empty {key!r}')
            status = str(feature.get('status') or '').strip()
            if status not in STATUSES:
                errors.append(f'{feature_id}: status {status!r} is not one of {STATUSES}')
    if not seen_features:
        errors.append('no features found')
    return errors


def counts(area: dict[str, Any]) -> dict[str, int]:
    result = {status: 0 for status in STATUSES}
    for feature in area.get('features') or []:
        status = str(feature.get('status') or '')
        if status in result:
            result[status] += 1
    return result


def render(data: dict[str, Any]) -> str:
    areas = data.get('areas') or []
    all_features = [f for area in areas for f in (area.get('features') or [])]
    totals = {status: 0 for status in STATUSES}
    for feature in all_features:
        status = str(feature.get('status') or '')
        if status in totals:
            totals[status] += 1

    lines: list[str] = [
        '# Feature verification register',
        '',
        f"**Program:** {data.get('program', '')}  ",
        f"**Product:** {data.get('product', '')}  ",
        f"**Version:** {data.get('version', '')}  ",
        f"**Updated:** {data.get('updated', '')}",
        '',
        '> Generated from `docs/feature_verification_register.json` by '
        '`scripts/verify_feature_register.py`. Edit the JSON, then rerun the script; do not '
        'edit this file by hand.',
        '',
        '## Purpose',
        '',
        str(data.get('purpose') or ''),
        '',
        '## Definition of done',
        '',
        'A feature is verified only when all six elements are present and the cited test path '
        'exists: user-facing functionality, native implementation, backend implementation, '
        'data model, automated tests, and a measurable acceptance criterion. `partial` and '
        '`absent` rows are findings, not claims of completion.',
        '',
        '## Boundaries',
        '',
    ]
    for key, value in (data.get('boundaries') or {}).items():
        lines.append(f'- **{key.replace("_", " ").title()}:** {value}')
    lines += [
        '',
        '## Status legend',
        '',
    ]
    for key, value in (data.get('status_legend') or {}).items():
        lines.append(f'- **{STATUS_LABEL.get(key, key)}** — {value}')
    lines += [
        '',
        '## Coverage summary',
        '',
        f'**{len(areas)} areas · {len(all_features)} features** — '
        f'{totals["implemented"]} implemented, {totals["partial"]} partial, '
        f'{totals["absent"]} absent, {totals["external"]} external.',
        '',
        '| Area | Features | implemented | partial | absent | external |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for area in areas:
        row = counts(area)
        lines.append(
            f"| {area.get('title')} | {len(area.get('features') or [])} | "
            f"{row['implemented']} | {row['partial']} | {row['absent']} | {row['external']} |"
        )
    lines += ['']
    for number, area in enumerate(areas, start=1):
        lines += [f'## {number}. {area.get("title")}', '']
        for feature in area.get('features') or []:
            lines += [
                f'### {feature["id"]} · {feature["name"]}',
                '',
                f'**Status:** `{feature["status"]}`',
                '',
                f'- **User-facing functionality:** {feature["user_facing"]}',
                f'- **Native implementation:** {feature["native"]}',
                f'- **Backend implementation:** {feature["backend"]}',
                f'- **Data model:** {feature["data"]}',
                f'- **Automated tests:** {feature["tests"]}',
                f'- **Acceptance criteria:** {feature["acceptance"]}',
                '',
            ]
    lines += [
        '## Maintaining this register',
        '',
        '1. Add or edit a feature in `docs/feature_verification_register.json`.',
        '2. Every feature must carry all six keys; the validator refuses an incomplete row.',
        '3. Run `python scripts/verify_feature_register.py` to validate and regenerate this file.',
        '4. Run it with `--check` in CI if the register must not drift.',
        '',
    ]
    return '\n'.join(lines)


def main(argv: list[str]) -> int:
    check_only = '--check' in argv[1:]
    try:
        data = load()
        errors = validate(data)
        if errors:
            for error in errors:
                print(f'register: {error}', file=sys.stderr)
            print(f'register: {len(errors)} error(s)', file=sys.stderr)
            return 1
        features = sum(len(area.get('features') or []) for area in data.get('areas') or [])
        print(f'register: OK — {len(data.get("areas") or [])} areas, {features} features')
        if check_only:
            return 0
        OUTPUT.write_text(render(data) + '\n', encoding='utf-8')
        print(f'register: wrote {OUTPUT.relative_to(ROOT)}')
        return 0
    except RegisterError as exc:
        print(f'register: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
