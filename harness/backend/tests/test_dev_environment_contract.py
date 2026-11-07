"""Regression contract for the pinned development environment.

A clean venv built from ``requirements-dev.txt`` is the environment the pinned
acceptance suite actually runs in. Two defects were visible only there:

* ``pytest.ini`` declares ``timeout`` / ``timeout_method``. Those are options of
  the ``pytest-timeout`` plugin, not of pytest itself. Without the plugin pytest
  emits ``PytestConfigWarning: Unknown config option: timeout`` and the suite
  runs with NO per-test ceiling -- silently disabling the very protection the
  comment in pytest.ini exists to provide.
* ``tests/test_api.py::test_training_consent_ledger_and_minimized_export``
  reaches ``model/train.py`` through ``app.adaptation._runtime_module()``. Its
  third-party imports were not declared in any development requirement, so a
  clean venv failed with ``ModuleNotFoundError: No module named 'pandas'``.

The import check is derived from the source AST rather than a hand-written list,
so adding a new import to the trainer breaks this contract instead of quietly
rotting until the next clean-environment run.
"""

from __future__ import annotations

import ast
import configparser
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent

# Config option prefix -> distribution that supplies the plugin. This is a
# lookup, not an inventory; pytest's own built-in options need no provider.
PLUGIN_PROVIDERS = {"timeout": "pytest-timeout"}

# Import name -> distribution name for the cases where the two differ.
DIST_NAMES = {"sklearn": "scikit-learn"}


def _declared() -> set[str]:
    """Every distribution named in the runtime or development manifests."""
    names: set[str] = set()
    for manifest in ("requirements.txt", "requirements-dev.txt"):
        for line in (BACKEND / manifest).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-r"):
                continue
            match = re.match(r"^([A-Za-z0-9_.-]+)", line)
            if match:
                names.add(match.group(1).lower().replace("_", "-"))
    return names


def _distribution(name: str) -> str:
    return DIST_NAMES.get(name, name).replace("_", "-")


def test_pytest_ini_plugin_options_have_a_declared_provider():
    cfg = configparser.ConfigParser()
    assert cfg.read(BACKEND / "pytest.ini"), "backend/pytest.ini is missing"
    declared = _declared()
    for key in cfg["pytest"]:
        for prefix, package in PLUGIN_PROVIDERS.items():
            if key == prefix or key.startswith(prefix + "_"):
                assert package in declared, (
                    f"pytest.ini sets {key!r}, supplied by {package}, but no "
                    f"development requirement declares it. Without the plugin "
                    f"pytest silently ignores the option and the timeout never "
                    f"protects the suite."
                )


def test_model_trainer_third_party_imports_are_declared():
    tree = ast.parse((REPO / "model" / "train.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])

    # Local modules are anything resolvable inside the repository; the standard
    # library comes from the interpreter's own module-name registry.
    local = {path.stem for path in REPO.iterdir()}
    local |= {path.stem for path in (REPO / "model").iterdir() if path.suffix == ".py"}
    third_party = imported - set(sys.stdlib_module_names) - local
    declared = _declared()
    missing = {_distribution(name) for name in third_party
               if _distribution(name) not in declared}
    assert not missing, (
        f"model/train.py imports {sorted(missing)}, reachable from the test "
        f"suite through app.adaptation._runtime_module(), but they are not "
        f"declared in requirements-dev.txt. A clean venv fails at import time."
    )
