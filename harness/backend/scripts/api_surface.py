#!/usr/bin/env python
"""Canonical description of the HTTP surface, used to prove a refactor changed nothing.

The point of this script is that it is *boring to read and impossible to argue with*:
build the application, describe every route, sort it, write it. Two runs on the same tree
produce byte-identical files, so ``--compare`` is a real equality test rather than a
diff of formatting noise.

What is captured, per route
---------------------------
``method``            one entry per HTTP method, so ``GET /health`` and ``POST /health``
                      are separate rows and adding a method is a visible change.
``path``              the *served* path, with the router prefixes already applied.
``name``              ``APIRoute.name`` - FastAPI defaults it to the endpoint's function
                      name, and it is what ``url_path_for`` resolves.
``endpoint``          the last component of the endpoint's qualname. The last component
                      rather than the whole qualname because moving a handler into a new
                      module is exactly the change this instrument must tolerate, while
                      renaming it is exactly the change it must catch.
``response_model``    dotted reference of the declared response model, or ``null``.
``body_models``       dotted references of the declared request-body models, in order.
``dependencies``      dotted references of the dependency callables FastAPI will execute,
                      in declaration order, flattened depth-first. A route that silently
                      stops resolving a principal shows up here.
``status_codes``      the success code plus every code the route declares in ``responses``.

Two extra top-level keys, both deterministic:

``route_count``      ``len(routes)``. This is the safety net: it is the number quoted in
                      the ADR and the number the guard test asserts.
``registration_order`` the routes in the order Starlette will try them, as
                      ``"METHOD path"`` strings. Sorted output cannot see shadowing;
                      this can. It is recorded so an order change is visible even when
                      the sorted set is identical.

Usage
-----
    python scripts/api_surface.py --out baseline.json
    python scripts/api_surface.py --out current.json
    python scripts/api_surface.py --compare baseline.json current.json

``--compare`` prints every differing entry and exits 1 when anything differs.

The app is built with ``create_app(Settings.from_env())``; a throwaway data directory is
injected so the operator's own database is never opened. Nothing in the output names a
path, a host, a timestamp or a dictionary iteration order, so the file is safe to commit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ref(obj) -> str | None:
    """A stable dotted name for a class or callable, or ``None``.

    ``<locals>`` is removed: a dependency defined inside ``create_app`` is the same
    callable whether or not the enclosing function moved, and the interesting part is the
    name, not where the closure happened to be created.
    """
    if obj is None:
        return None
    module = getattr(obj, '__module__', None)
    qualname = getattr(obj, '__qualname__', None) or getattr(obj, '__name__', None)
    if qualname is None:
        text = str(obj)
        return text if text else type(obj).__name__
    qualname = qualname.replace('.<locals>.', '.').replace('<locals>.', '')
    return f'{module}.{qualname}' if module else qualname


def _dependencies(dependant) -> list[str]:
    """Every dependency callable FastAPI will run, depth-first, in declaration order."""
    names: list[str] = []

    def walk(node) -> None:
        for child in getattr(node, 'dependencies', ()) or ():
            names.append(_ref(getattr(child, 'call', None)) or '<unknown>')
            walk(child)

    walk(dependant)
    return names


def _body_models(dependant) -> list[str]:
    models: list[str] = []
    for field in getattr(dependant, 'body_params', ()) or ():
        info = getattr(field, 'field_info', None)
        annotation = getattr(info, 'annotation', None)
        if annotation is None:
            annotation = getattr(field, 'annotation', None)
        models.append(_ref(annotation) or '<unknown>')
    return models


def _status_codes(route) -> list[int]:
    codes = set()
    declared = getattr(route, 'status_code', None)
    codes.add(int(declared) if declared is not None else 200)
    for code in (getattr(route, 'responses', None) or {}):
        try:
            codes.add(int(code))
        except (TypeError, ValueError):
            continue
    return sorted(codes)


def _entry(route, method: str) -> dict:
    endpoint = getattr(route, 'endpoint', None)
    qualname = getattr(endpoint, '__qualname__', '') or ''
    last = qualname.split('.')[-1] if qualname else getattr(route, 'name', '')
    return {
        'method': method,
        'path': getattr(route, 'path', ''),
        'name': getattr(route, 'name', ''),
        'endpoint': last,
        'response_model': _ref(getattr(route, 'response_model', None)),
        'body_models': _body_models(getattr(route, 'dependant', None)),
        'dependencies': _dependencies(getattr(route, 'dependant', None)),
        'status_codes': _status_codes(route),
    }


def _flatten(routes) -> list:
    """Every routable object, in the order Starlette will try them.

    This FastAPI version keeps an included router as one ``_IncludedRouter`` object in
    ``app.routes`` and expands it at match time, so a plain ``isinstance(route, APIRoute)``
    filter silently sees only the routes declared inline in ``main.py``. The expansion
    below is what makes the count honest.
    """
    flat: list = []
    for route in routes:
        if type(route).__name__ == 'APIRoute':
            flat.append(route)
            continue
        expand = getattr(route, 'effective_route_contexts', None)
        if callable(expand):
            flat.extend(expand())
            continue
        nested = getattr(route, 'routes', None)
        if nested:
            flat.extend(_flatten(nested))
    return flat


def build_surface(app) -> dict:
    entries: list[dict] = []
    order: list[str] = []
    for route in _flatten(app.routes):
        methods = sorted(getattr(route, 'methods', None) or ())
        for method in methods:
            entries.append(_entry(route, method))
            order.append(f'{method} {getattr(route, "path", "")}')
    entries.sort(key=lambda e: (e['path'], e['method']))
    return {
        'route_count': len(entries),
        'routes': entries,
        'registration_order': order,
    }


def build_app():
    # A throwaway data directory, and a settings object built from an environment that
    # cannot reach the operator's real database. ``create_app`` opens nothing until the
    # lifespan runs, but the engine is created here, so the path has to be safe.
    temp = tempfile.mkdtemp(prefix='api-surface-')
    os.environ.setdefault('HARNESS_ENV', 'test')
    os.environ.setdefault('HARNESS_TUTOR_PROVIDER', 'offline')
    os.environ['HARNESS_DATA_DIR'] = temp
    os.environ.pop('HARNESS_DATABASE_URL', None)

    from app.config import Settings
    from app.main import create_app

    return create_app(Settings.from_env())


def dump(surface: dict) -> str:
    return json.dumps(surface, indent=2, sort_keys=True, ensure_ascii=True) + '\n'


def _key(entry: dict) -> str:
    return f'{entry["method"]} {entry["path"]}'


def compare(left: dict, right: dict) -> int:
    """Print every differing entry. Returns the number of differences."""
    problems = 0

    if left.get('route_count') != right.get('route_count'):
        print(f'route_count: {left.get("route_count")} -> {right.get("route_count")}')
        problems += 1

    before = {_key(e): e for e in left.get('routes', [])}
    after = {_key(e): e for e in right.get('routes', [])}

    for key in sorted(set(before) - set(after)):
        print(f'REMOVED  {key}')
        problems += 1
    for key in sorted(set(after) - set(before)):
        print(f'ADDED    {key}')
        problems += 1
    for key in sorted(set(before) & set(after)):
        old, new = before[key], after[key]
        for field in sorted(set(old) | set(new)):
            if field in {'method', 'path'}:
                continue
            if old.get(field) != new.get(field):
                print(f'CHANGED  {key}  {field}')
                print(f'    before: {json.dumps(old.get(field), sort_keys=True)}')
                print(f'    after : {json.dumps(new.get(field), sort_keys=True)}')
                problems += 1

    old_order = left.get('registration_order') or []
    new_order = right.get('registration_order') or []
    if old_order != new_order:
        # Report the first index that moved and the items involved rather than a
        # 200-line list: one moved entry is usually the whole story.
        limit = min(len(old_order), len(new_order))
        for index in range(limit + 1):
            old_item = old_order[index] if index < len(old_order) else '<end of list>'
            new_item = new_order[index] if index < len(new_order) else '<end of list>'
            if old_item != new_item:
                print(f'ORDER    first difference at index {index}')
                print(f'    before: {old_item}')
                print(f'    after : {new_item}')
                problems += 1
                break

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    parser.add_argument('--out', metavar='PATH', help='write the canonical surface here')
    parser.add_argument('--expect', metavar='PATH',
                        help='write the trimmed guard expectation (route count + sorted '
                             '"METHOD path" list) consumed by tests/test_api_surface.py')
    parser.add_argument('--compare', nargs=2, metavar=('LEFT', 'RIGHT'),
                        help='compare two surface files and exit non-zero on any difference')
    parser.add_argument('--quiet', action='store_true', help='do not print the route count')
    args = parser.parse_args(argv)

    if args.compare:
        left = json.loads(Path(args.compare[0]).read_text(encoding='utf-8'))
        right = json.loads(Path(args.compare[1]).read_text(encoding='utf-8'))
        problems = compare(left, right)
        if problems:
            print(f'\n{problems} difference(s).')
            return 1
        print('identical: 0 differences.')
        return 0

    surface = build_surface(build_app())
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(dump(surface), encoding='utf-8')
    if args.expect:
        expectation = {
            'route_count': surface['route_count'],
            'routes': sorted(f'{e["method"]} {e["path"]}' for e in surface['routes']),
            'generated_by': 'scripts/api_surface.py --expect',
        }
        Path(args.expect).parent.mkdir(parents=True, exist_ok=True)
        Path(args.expect).write_text(
            json.dumps(expectation, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if not args.out and not args.expect:
        sys.stdout.write(dump(surface))
    if not args.quiet:
        print(f'{surface["route_count"]} route(s)', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
