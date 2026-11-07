"""Generate a compact context pack for a frontier model working on this repo.

Why this exists
---------------
The source tree is ~1.6M tokens (backend 3.44M chars, tests 1.25M, Swift 1.01M).
No model holds that usefully, and exploratory tool-calling ("where is the FSRS
scheduler?") costs 3-8 full-file reads per question. This script emits four
static layers that together are ~1/40th of the corpus, and are stable enough to
sit at the *front* of a prompt so provider prefix caching discounts them.

Layers
------
00-use-this.md    how a model should use the pack, and the token budget
01-repo-map.md    every source file: LOC, purpose (docstring), public symbols
02-interfaces.md  HTTP endpoints, agent tools, DB tables, capability ids
03-tests.md       the 1518 test names, grouped by file -- the behavioural spec

Layers 01-03 are derived from the code, so they are never stale by hand-editing.
Regenerate after a structural change:  python3 scripts/context_pack.py

Deliberately *not* included: file bodies. Those are what a retriever should
fetch on demand, one span at a time, not what a prompt should pre-load.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "context"

#: Rough chars-per-token. Code is ~3.6, prose ~4.0; 3.7 is a safe blend.
CPT = 3.7


def tokens(text: str) -> int:
    return int(len(text) / CPT)


def py_summary(path: Path) -> tuple[str, list[str], int]:
    """Return (first docstring line, public symbols, line count)."""
    src = path.read_text(encoding="utf-8", errors="replace")
    lines = src.count("\n") + 1
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return "(unparseable)", [], lines

    doc = (ast.get_docstring(tree) or "").strip()
    purpose = doc.split("\n\n")[0].replace("\n", " ").strip() if doc else "(no docstring)"

    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                symbols.append(f"{node.name}()")
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                symbols.append(node.name)
    return purpose, symbols, lines


SWIFT_DECL = re.compile(
    r"^(?:public |internal |private |fileprivate |open )?"
    r"(struct|class|enum|protocol|actor|extension)\s+(\w+)",
    re.MULTILINE,
)


def swift_summary(path: Path) -> tuple[str, list[str], int]:
    src = path.read_text(encoding="utf-8", errors="replace")
    lines = src.count("\n") + 1
    # A leading /// block is the file's stated purpose in this codebase.
    head = [ln[4:].strip() for ln in src.splitlines()[:12] if ln.startswith("/// ")]
    purpose = head[0] if head else "(no header comment)"
    names = [f"{kind}:{name}" for kind, name in SWIFT_DECL.findall(src)][:12]
    return purpose, names, lines


def walk(base: Path, pattern: str, skip: tuple[str, ...] = ()) -> list[Path]:
    out = []
    for p in sorted(base.rglob(pattern)):
        if "__pycache__" in p.parts or any(s in p.parts for s in skip):
            continue
        out.append(p)
    return out


def layer_map() -> str:
    rows = [
        "# 01 — Repository map",
        "",
        "Every source file, its stated purpose, and its public surface. Read this to",
        "decide *which* file to open; do not open a file to learn what it is for.",
        "",
        "Generated from the tree. Regenerate with `python3 scripts/context_pack.py`.",
        "",
    ]

    # Bucket by directory rather than hand-listing groups: a hand-written list
    # silently omits whatever subdirectory the next agent adds.
    def bucket(paths: list[Path], base: Path) -> dict[str, list[Path]]:
        out: dict[str, list[Path]] = {}
        for p in paths:
            rel = p.parent.relative_to(base)
            key = "." if str(rel) == "." else str(rel)
            out.setdefault(key, []).append(p)
        return dict(sorted(out.items(), key=lambda kv: (kv[0] != ".", kv[0])))

    py_files = walk(ROOT / "backend/app", "*.py")
    swift_files = walk(ROOT / "native/Sources", "*.swift")

    for title, base, files, kind in (
        ("Backend (`backend/app/`)", ROOT / "backend/app", py_files, "py"),
        ("Native SwiftUI (`native/Sources/`)", ROOT / "native/Sources", swift_files, "swift"),
    ):
        rows += [f"# {title}", ""]
        for group, group_files in bucket(files, base).items():
            label = "application root" if group == "." else group
            rows += [f"## {label} — {len(group_files)} files", ""]
            for f in group_files:
                rel = f.relative_to(ROOT)
                purpose, symbols, loc = (
                    py_summary(f) if kind == "py" else swift_summary(f)
                )
                sym = ", ".join(symbols[:10])
                if len(symbols) > 10:
                    sym += f", +{len(symbols) - 10} more"
                rows.append(f"**`{rel.name}`** — {loc} ln — {purpose}")
                if sym:
                    rows.append(f"    {sym}")
            rows.append("")
        rows += [f"_{len(files)} files._", ""]

    return "\n".join(rows)


def _eval_str(node: ast.AST, env: dict[str, str]) -> str | None:
    """Resolve a decorator's path argument, including ``API + '/sweep'`` forms.

    A plain string regex misses most of this codebase: modules declare
    ``API = '/api/v1/...'`` once and then write ``@router.post(API + '/sweep')``.
    Counting only literal decorators undercounts the surface by more than half.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _eval_str(node.left, env), _eval_str(node.right, env)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            else:
                parts.append("{param}")
        return "".join(parts)
    return None


def endpoints_in(path: Path) -> list[tuple[str, str, str]]:
    """Return (METHOD, path, handler) for every router decorator in a module."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []

    env: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                value = _eval_str(node.value, env)
                if value is not None:
                    env[target.id] = value

    found: list[tuple[str, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
                continue
            if func.value.id != "router" or not decorator.args:
                continue
            path_value = _eval_str(decorator.args[0], env) or "<dynamic>"
            found.append((func.attr.upper(), path_value, node.name))
    return found


def layer_interfaces() -> str:
    rows = [
        "# 02 — Interfaces",
        "",
        "The contract surface. These are what a change must not break; the bodies",
        "behind them are what a retriever should fetch.",
        "",
    ]

    # HTTP endpoints
    rows += ["## HTTP endpoints", ""]
    by_file: dict[str, list[str]] = {}
    for f in walk(ROOT / "backend/app", "*.py"):
        hits = endpoints_in(f)
        if hits:
            by_file[f.name] = [f"{method} {path}  →  {handler}" for method, path, handler in hits]
    for name, eps in sorted(by_file.items()):
        rows.append(f"**`{name}`** ({len(eps)})")
        rows += [f"    {e}" for e in eps]
        rows.append("")
    rows += [f"_{sum(len(v) for v in by_file.values())} endpoints across {len(by_file)} modules._", ""]

    # Agent tools
    toolbox = ROOT / "backend/app/harness/toolbox.py"
    if toolbox.is_file():
        src = toolbox.read_text(encoding="utf-8", errors="replace")
        names = re.findall(r"ToolSpec\(\s*[\"']([a-z_0-9]+)[\"']", src)
        rows += ["## Agent tools (the teacher's toolbox)", ""]
        rows.append("  " + ", ".join(sorted(set(names))))
        rows += ["", f"_{len(set(names))} tools._", ""]

    # DB tables
    db = ROOT / "backend/app/db.py"
    if db.is_file():
        src = db.read_text(encoding="utf-8", errors="replace")
        tables = re.findall(r"__tablename__\s*=\s*[\"']([^\"']+)[\"']", src)
        rows += ["## Database tables", ""]
        rows.append("  " + ", ".join(tables))
        rows += ["", f"_{len(tables)} tables. `db.py` is the schema; migrations live beside it._", ""]

    # Capabilities
    caps = ROOT / "backend/app/capabilities.py"
    if caps.is_file():
        src = caps.read_text(encoding="utf-8", errors="replace")
        ids = re.findall(r"id=[\"']([a-z_]+)[\"']", src)
        rows += ["## Capability matrix", ""]
        rows.append("  " + ", ".join(dict.fromkeys(ids)))
        rows += ["", "_Every capability degrades to a declared fallback with a reason. "
                 "Never let one raise._", ""]

    return "\n".join(rows)


def layer_tests() -> str:
    rows = [
        "# 03 — Behavioural spec (test names)",
        "",
        "1518 test functions. The names are the specification: they state what the",
        "system promises, in the same words the promises were written in. Read the",
        "relevant block before changing a module; a change that contradicts a name",
        "here is either a bug or a deliberate re-specification.",
        "",
    ]
    total = 0
    for f in walk(ROOT / "backend/tests", "test_*.py"):
        src = f.read_text(encoding="utf-8", errors="replace")
        names = re.findall(r"^def (test_\w+)", src, re.MULTILINE)
        if not names:
            continue
        total += len(names)
        rows.append(f"**`{f.name}`** ({len(names)})")
        rows += [f"    {n}" for n in names]
        rows.append("")
    rows += [f"_{total} tests across {len(walk(ROOT / 'backend/tests', 'test_*.py'))} files. "
             f"Run: `cd backend && python -m pytest -q`._", ""]
    return "\n".join(rows)


def layer_usage() -> str:
    return "\n".join([
        "# 00 — How to use this pack",
        "",
        "You are working on Luminfest, a native macOS learning harness: SwiftUI client,",
        "FastAPI backend, 102 endpoints, 51 agent tools, 37 tables, 1518 tests.",
        "",
        "## The four layers, in order",
        "",
        "1. `01-repo-map.md` — which file does what. Answers 'where is X' without a search.",
        "2. `02-interfaces.md` — the contract surface. Answers 'what must not break'.",
        "3. `03-tests.md` — the behavioural spec. Answers 'what is already promised'.",
        "4. `04-open-gaps.md` — curated audit against the product brief. What is still missing.",
        "5. The source itself — fetched on demand, one span at a time.",
        "",
        "## Rules that keep the token bill down",
        "",
        "- **Do not open a file to learn what it is for.** The map already says.",
        "- **Fetch spans, not files.** Ask for the function you need, not the module.",
        "- **Trust the test names.** Do not re-derive behaviour the names already state.",
        "- **Ask for a task pack** if you need more than ~15 tool calls. That is a signal",
        "  the pack is missing a layer, not a signal to read harder.",
        "",
        "## Invariants — violating these still runs, and quietly harms learners",
        "",
        "- Decision layers never collapse: `teaching/policy` (what to teach) · `session`",
        "  (phase/turn) · `procedure` (activities) · `supervision` (should we interrupt) ·",
        "  `classroom` (state machine). `classroom` imports supervision's primitives.",
        "- `mastery_known` is not `mastery`. `PRIOR` 0.15 means 'no attempts yet'.",
        "- Never punish. Away is not guilt; suspicion routes to a variant question or an",
        "  explain-back, never to a detector or a ban.",
        "- A plan is a promise. Only *existing* artifacts may be promised; missing ones",
        "  become `skipped`. A plan that reshapes mid-session is not a lesson.",
        "- Absence is designed: a missing provider degrades to a declared fallback with a",
        "  reason. It never raises, and never fakes output.",
        "",
        "## Environment traps",
        "",
        "- `grep 'a\\|b'` silently matches nothing on this box (toybox grep, no BRE",
        "  alternation). Use `grep -E`. An empty result is not evidence until the query",
        "  is proven to work.",
        "- Tests need cwd `backend/` and a `TMPDIR`/`--basetemp` inside the repo.",
        "- `swift build` needs `--disable-sandbox`. Never use `Bundle.module`.",
        "",
    ])


def _imports(path: Path) -> set[str]:
    """Return the last component of every module this file imports."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[-1])
            for alias in node.names:
                names.add(alias.name)
    return names


def neighbourhood(target: str) -> None:
    """Print the blast radius of one file: imports, importers, and touching tests.

    This is the query a model actually needs before editing -- 'if I change this,
    what else moves?' -- and it is the one an exploratory agent spends six tool
    calls answering badly.
    """
    base = ROOT / "backend/app"
    files = walk(base, "*.py")
    stem_to_file = {f.stem: f for f in files}
    wanted = Path(target).stem
    if wanted not in stem_to_file:
        print(f"no module named {wanted!r} under backend/app")
        return

    source = stem_to_file[wanted]
    imports = _imports(source)
    internal = {n for n in imports if n in stem_to_file and n != wanted}
    external = sorted(imports - internal - {"__future__", "annotations"})
    importers = sorted(f.stem for f in files if f != source and wanted in _imports(f))

    tests_dir = ROOT / "backend/tests"
    touching = []
    for t in walk(tests_dir, "test_*.py"):
        text = t.read_text(encoding="utf-8", errors="replace")
        if wanted in _imports(t) or re.search(rf"\b{wanted}\b", text):
            touching.append(t.name)

    print(f"# Blast radius — {source.relative_to(ROOT)}")
    print(f"\nInternal imports ({len(internal)}):  {', '.join(sorted(internal)) or '—'}")
    print(f"External imports ({len(external)}):  {', '.join(external) or '—'}")
    print(f"Imported by ({len(importers)}): {', '.join(importers) or '—'}")
    print(f"Tests touching it ({len(touching)}): {', '.join(touching) or '—'}")
    print("\nFiles to read before editing, in order:")
    for name in [wanted] + importers:
        f = stem_to_file.get(name)
        if f:
            purpose, _, loc = py_summary(f)
            print(f"  {f.relative_to(ROOT)}  ({loc} ln) — {purpose[:110]}")
    if touching:
        print(f"\nRun: cd backend && python -m pytest -q {' '.join('tests/' + t for t in touching[:8])}")


def main() -> None:
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--near":
        neighbourhood(sys.argv[2])
        return

    if not OUT.exists():
        OUT.mkdir(parents=True)
    files = {
        "00-use-this.md": layer_usage(),
        "01-repo-map.md": layer_map(),
        "02-interfaces.md": layer_interfaces(),
        "03-tests.md": layer_tests(),
    }
    total = 0
    for name, text in files.items():
        (OUT / name).write_text(text, encoding="utf-8")
        t = tokens(text)
        total += t
        print(f"{name:22s} {len(text):>8,} chars  ~{t:>6,} tokens")

    print(f"{'TOTAL':22s} {'':>8}       ~{total:>6,} tokens")
    corpus = 1_630_000
    print(f"\nCorpus is ~{corpus:,} tokens. This pack is ~{total:,} "
          f"({total / corpus:.1%}) and fits any frontier context window with room to work.")


if __name__ == "__main__":
    main()
