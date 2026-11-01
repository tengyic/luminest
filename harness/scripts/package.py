#!/usr/bin/env python3
"""Reproducible macOS arm64 desktop packaging; no native build in backend-only mode."""
import argparse
import hashlib
import json
import math
import os
import platform
import plistlib
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "harness"
OUTPUTS = ROOT / "outputs"
WORK = OUTPUTS / ".packaging"
BACKEND = WORK / "dist" / "LuminfestBackend"
APP_NAME = "Luminfest"
APP = OUTPUTS / f"{APP_NAME}.app"
NATIVE = HARNESS / "native"
PRIVACY_MANIFEST = NATIVE / "Resources" / "PrivacyInfo.xcprivacy"
ENTITLEMENTS_SANDBOX = NATIVE / "LuminfestLearningHarness.entitlements"
ENTITLEMENTS_DIRECT = NATIVE / "LuminfestLearningHarness-Direct.entitlements"
DISTRIBUTION_NOTE = ("Ad-hoc signed, not notarized. Public distribution requires an Apple "
                     "Developer ID signature and Apple notarization. No Gatekeeper bypass is supplied.")
RUNTIME_MODEL_FILES = ("__init__.py", "features.py", "trained_pfa.py", "kt_engine.py")
#: JSON pack directories read at runtime via ``Path(__file__).parent``. PyInstaller only
#: follows imports, so these must be declared as data or they vanish from the bundle.
PACK_DATA_DIRS = ("curriculum_packs", "media_packs")
#: The legal documents, read through ``config.legal_dir()`` which resolves to
#: ``Path(app/main.py).parents[1] / 'legal'``. Inside the frozen bundle that is
#: ``_internal/legal``, so the destination below is the bare directory name - the same
#: ``--add-data`` mechanism the packs use, for the same reason: it is data, not an
#: import. Without it ``/legal`` answers with zero documents while registration still
#: records terms acceptance at ``terms_version``, which is the worst of both positions.
LEGAL_DATA_DIR = "legal"
#: The static web assets - the workbench shell, the playground gallery, the agent bridge
#: and the bundled seed simulations - read at runtime through :mod:`app.resources`. They
#: are data, not imports, so PyInstaller cannot see them, and they are the one bundle
#: directory that was still missing: the shipped app contained **zero** ``.html`` files,
#: so ``/`` and ``/playground`` answered 404 while ``/api/v1/health`` looked healthy. The
#: destination is the bare name because the frozen resolver reads ``sys._MEIPASS``, which
#: is ``_internal`` - the same mechanism the legal documents use, for the same reason.
WEB_DATA_DIR = "web"
HEAVY_MODULES = ("numpy", "pandas", "sklearn", "scipy", "torch", "tensorflow", "matplotlib",
                 "IPython", "jupyter", "pytest", "tkinter", "PIL", "model.train", "model.test_model",
                 "sitecustomize", "usercustomize")
#: Packages that are declared in ``requirements-optional.txt`` and deliberately excluded
#: from the frozen desktop bundle. Each entry names the reason, and
#: ``backend/tests/test_packaging_manifest.py`` asserts every key is still declared, so
#: an exclusion cannot outlive the requirement it excuses.
BUNDLE_EXCLUDES = {
    "playwright": ("~40 MB package plus a chromium download, backing one teacher-only tool "
                   "that is off by default. Excluding it is what halved the DMG. The tool "
                   "catalogue stops advertising browser_snapshot when it is absent."),
}
#: A representative endpoint per feature router, asserted against the frozen artifact.
#: ``main.create_app`` reaches these modules through a dynamic import, so the freezer
#: cannot infer them; the GETs below are exactly the endpoints a release review found
#: answering 404 while the source tree served them, and naming them here means the smoke
#: test fails on that specific regression instead of trusting the build to be right.
#: A route that exists but rejects the method still proves the module was mounted, so the
#: check is "not 404" rather than "200".
#:
#: Every name in ``app.feature_routers.FEATURE_ROUTERS`` must appear here. The two lists
#: are kept in step by ``tests/test_feature_routers.py``, which is what caught
#: ``playground_routes`` being declared to the router loader but never probed - a router
#: that ships unverified is exactly how a frozen build once served 404s for four features
#: that worked perfectly from source.
FEATURE_ROUTE_PROBES = (
    ("routes_deck", "/deck"),
    ("routes_flash", "/flashcards"),
    ("routes_create", "/my-courses"),
    # The foundry. A learner token answers 403 here rather than 200, which is still a
    # pass: the probe proves the module was collected into the bundle, and only a 404 -
    # what an uncollected router produces - is a failure.
    ("routes_authoring", "/author/methodology"),
    ("routes_media", "/images/library"),
    ("routes_source", "/create/search"),
    ("playground_routes", "/playground"),
    ("routes_multimodal", "/capabilities"),
    ("routes_procedure", "/procedure"),
    # Mounted without a probe until now, which is the exact hole this table exists to
    # close: both routers served in the source tree and neither was smoke-tested in the
    # bundle. `test_feature_routers` compares this tuple against FEATURE_ROUTERS, so a
    # router added without a probe fails the suite rather than the release.
    ("routes_supervision", "/supervision"),
    ("routes_rewards", "/rewards/events"),
    ("routes_ta", "/ta/sweep"),
    # Off by default, so this answers 503 rather than 200 in a shipped bundle. A 503 is a
    # pass: it proves the module landed. Only a 404 — what an uncollected router produces —
    # is a failure.
    ("routes_stream", "/stream/status"),
)


def run(command, **kwargs):
    print("+ " + " ".join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), check=True, **kwargs)


def write_json(path, data):
    """Write JSON atomically.

    ``Path.write_text`` truncates in place. A build killed mid-write therefore leaves a
    truncated file that the next run reads as present-but-corrupt, or - worse, because the
    failure is silent - as a record whose fields are missing. ``os.replace`` is atomic on
    the same filesystem, so a reader sees either the whole previous record or the whole new
    one, never a half-written one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


#: Append-only build ledger. See :func:`append_ledger` for why it is not a JSON file.
LEDGER = WORK / "build-ledger.jsonl"


def append_ledger(entry):
    """Append one line to the append-only build ledger and fsync it.

    ``backend-build.json`` and ``package-result.json`` are rewritten on every run, so each
    freeze destroys the previous freeze's evidence. This is not hypothetical: during the
    2026-10-25 audit ``backend-build.json`` was regenerated twice (13:52, 14:06) with the
    tree unchanged, and two engineers measuring at different times each reported a digest
    that was correct when read and superseded within the hour. Reconciling that cost three
    measurement passes to establish what the shipped artifact actually contained.

    The ledger is never rewritten, so "which build was this?" survives the next build. One
    JSON object per line, keyed by artifact sha256, the same discipline the agent bus uses
    and for the same reason: an append-only log answers questions that a mutable record
    cannot. ``fsync`` because a ledger that loses its last line to a power cut is the exact
    case it exists to prevent.
    """
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return LEDGER


def file_sha256(path):
    """Streamed sha256 of a file, so a 17 MB backend is not read into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def retire(path):
    """Move an artifact aside rather than deleting it.

    Two reasons, both learned the hard way. Deleting a 200-entry ``.app`` is a bulk delete,
    and a build environment's safety guard refuses it - which killed a packaging run *after*
    it had already signed and verified a perfectly good bundle, wasting the whole build.
    And a replaced artifact is the only copy of the previous build: if the new one turns out
    worse, "we deleted it" is not a recoverable position. Renaming is atomic, cheap and
    reversible, so the previous build stays on disk under ``.packaging/_stale``.
    """
    if not path.exists():
        return None
    graveyard = WORK / "_stale"
    graveyard.mkdir(parents=True, exist_ok=True)
    target = graveyard / f"{path.name}.pre-{int(time.time())}"
    shutil.move(str(path), str(target))
    print(f"retired previous artifact: {path.name} -> {target}", flush=True)
    return target


def expected_schema_version():
    """The schema version the sources under test declare.

    Imported from the app itself so the packaging smoke can never drift from the code it
    is supposed to be verifying.
    """
    backend = str(HARNESS / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.db import SCHEMA_VERSION  # noqa: PLC0415 - deliberate late import
    return SCHEMA_VERSION


def legal_gate(allow_template):
    """Refuse to package a release whose legal documents are still templates.

    Audit finding L-1: the shipped bundle quotes ``backend/legal/`` verbatim, so a
    DMG built while ``[LEGAL ENTITY NAME]``-style placeholders remain would publish
    unfilled legal terms. Fill the blanks from ``backend/legal/FILL_IN_SHEET.md``
    with counsel sign-off; ``--allow-template-legal`` exists only for template
    builds that are never released.
    """
    backend = str(HARNESS / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.legal_guard import unfilled_placeholders  # noqa: PLC0415 - deliberate late import
    found = unfilled_placeholders(HARNESS / "backend" / "legal")
    total = sum(len(tokens) for tokens in found.values())
    if not found:
        return {"placeholders": 0, "ship_ready": True}
    detail = "; ".join(f"{name}: {', '.join(tokens)}" for name, tokens in found.items())
    if not allow_template:
        raise RuntimeError(
            f"Legal documents still contain {total} unfilled placeholder(s) ({detail}). "
            "Fill them via backend/legal/FILL_IN_SHEET.md, or pass --allow-template-legal "
            "only for a build that will not be released.")
    print(f"WARNING: packaging a template legal bundle ({total} placeholders); "
          "this build must not be released.", flush=True)
    return {"placeholders": total, "ship_ready": False, "detail": detail}


def _declared_requirements(path):
    """The requirement lines of a requirements file, with comments and blanks dropped."""
    from packaging.requirements import Requirement  # noqa: PLC0415 - build-time only
    declared = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            declared.append(Requirement(line))
    return declared


def normalise_name(name):
    """A distribution name the way pip compares them: lower case, ``_`` folded to ``-``.

    The spelling of a distribution is not stable between the requirements file and a
    ``pip list`` listing - ``argon2-cffi`` is installed as ``argon2_cffi`` - so both sides
    of every comparison go through here. Getting this wrong does not produce a wrong
    answer, it produces a *missing* answer: the requirement looks absent and the build
    stops for a package that is right there.
    """
    return name.lower().replace("_", "-")


def installed_distributions(python):
    """``{normalised name: version}`` for everything installed in the build environment."""
    listing = json.loads(subprocess.check_output(
        [str(python), "-m", "pip", "list", "--format", "json"], text=True))
    return {normalise_name(row["name"]): row["version"] for row in listing}


def compare_requirements(declared, installed):
    """Which declared requirements are absent, and which are at the wrong version.

    ``installed`` is keyed by :func:`normalise_name`; the lookup normalises anyway so a
    caller that passes raw listing keys still gets the right answer rather than a false
    "missing".
    """
    lookup = {normalise_name(name): version for name, version in installed.items()}
    missing, mismatched = [], []
    for requirement in declared:
        version = lookup.get(normalise_name(requirement.name))
        if version is None:
            missing.append(f"{requirement.name}{requirement.specifier}")
        elif requirement.specifier and not requirement.specifier.contains(
                version, prereleases=True):
            mismatched.append(f"{requirement.name}: declared {requirement.specifier}, "
                              f"installed {version}")
    return missing, mismatched


def dependency_gate(python, required=None, optional=None):
    """Compare the build environment against the declared requirements before freezing.

    PyInstaller collects what is *installed*, not what is declared, and it reports
    nothing when the two disagree. So a freeze run from an environment missing a
    dependency produces a bundle whose feature fails on the tester's machine with no
    build-time signal at all - which is how a shipped build came to carry a document
    upload path whose multipart parser was never frozen, and a text-to-speech tool that
    could only ever refuse. The check is cheap and it fails closed.

    ``requirements.txt`` is enforced: a missing or mismatched distribution stops the
    build. ``requirements-optional.txt`` is reported, not enforced, because those
    packages are either deployment-specific (psycopg, for the Postgres compose stack) or
    deliberately excluded from this artifact (see :data:`BUNDLE_EXCLUDES`).
    """
    required = required or (HARNESS / "backend" / "requirements.txt")
    optional = optional or (HARNESS / "backend" / "requirements-optional.txt")
    installed = installed_distributions(python)

    declared_required = _declared_requirements(required)
    missing, mismatched = compare_requirements(declared_required, installed)
    problems = [*[f"not installed: {item}" for item in missing],
                *[f"wrong version: {item}" for item in mismatched]]
    if problems:
        raise RuntimeError(
            f"The build environment does not satisfy {required.name}, so a freeze "
            "would produce a bundle whose features fail on the recipient's machine. "
            + "; ".join(problems)
            + f". Install with: pip install -r {required}")

    declared_optional = _declared_requirements(optional)
    optional_missing, optional_mismatched = compare_requirements(declared_optional, installed)
    # An exclusion that no longer corresponds to a declared requirement is a stale
    # exemption quietly suppressing a real check, so it is refused rather than ignored.
    optional_names = {normalise_name(requirement.name) for requirement in declared_optional}
    orphaned = sorted(name for name in BUNDLE_EXCLUDES if name not in optional_names)
    if orphaned:
        raise RuntimeError(
            "These packages are excluded from the bundle but no longer declared in "
            f"{optional.name}: {', '.join(orphaned)}. Remove the exemption or restore "
            "the requirement.")
    return {
        "requirements_installed": len(installed),
        "required_present": True,
        "required_checked": [requirement.name for requirement in declared_required],
        "optional_missing": sorted(optional_missing),
        "optional_mismatched": sorted(optional_mismatched),
        "bundle_excludes": {name: reason for name, reason in sorted(BUNDLE_EXCLUDES.items())},
    }


def source_digest():
    files = [HARNESS / "backend" / "desktop_entry.py"]
    files.extend(sorted((HARNESS / "backend" / "app").rglob("*.py")))
    files.extend(HARNESS / "model" / name for name in RUNTIME_MODEL_FILES)
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def assert_backend_matches_tree(frozen=None, current=None):
    """Refuse to package a backend that the current tree did not produce.

    ``source_digest`` covers exactly the files that get frozen - ``desktop_entry.py``,
    ``app/**/*.py`` and the runtime model sources - so a disagreement means the bytes in
    the bundle came from code that no longer exists here, not merely that a test or a doc
    was touched.

    This is a hard failure rather than a warning because the record alone proved
    insufficient. The 1.1.10 bundle shipped with ``source_digest`` 1a60e8c9 and
    ``source_digest_at_package`` 4967f041 sitting next to each other in
    ``distribution.json``: the build succeeded, the smoke passed, and the artifact was
    stale relative to its own tree the whole time. A field nobody reads is not a gate.
    The gap opens when a backend edit lands during the native build, which is minutes
    long - long enough for a concurrent editor, and invisible in every other check.

    ``frozen``/``current`` let :func:`backend_provenance` pass digests it has already
    computed, so the check costs nothing extra there.
    """
    if frozen is None:
        record_path = WORK / "backend-build.json"
        if not record_path.is_file():
            return
        frozen = json.loads(record_path.read_text()).get("source_digest")
    if current is None:
        current = source_digest()
    if not frozen or frozen == current:
        return
    raise RuntimeError(
        "The frozen backend does not match the current sources: it was frozen from "
        f"{str(frozen)[:12]}, and the tree now hashes to {current[:12]}.\n"
        "Something under harness/backend/app or harness/model changed after the freeze - "
        "usually a concurrent edit during the native build. Packaging now would ship bytes "
        "that no source file produces.\n"
        "Re-run packaging. If the backend itself is unchanged, --skip-backend-build reuses "
        "the existing freeze without spending another one.")


def backend_provenance():
    """Provenance for the frozen backend that is actually inside the bundle.

    ``distribution.json`` used to record signing / sandboxed / notarized and nothing about
    *what code this is*. So a tester holding the DMG could not tie it to any build, and with
    no VCS in this repository there was no other route to that answer. That is a one-way
    door: once copies are distributed, provenance is unrecoverable.

    ``source_digest`` is taken from the backend-build record - it describes the sources the
    frozen binary was actually built from, which is the question a tester is asking.
    ``source_digest_at_package`` is recomputed from the tree as it is now. Both are still
    recorded - a reader can confirm for themselves that the two agree - but a disagreement
    no longer reaches disk: :func:`assert_backend_matches_tree` refuses first.
    """
    provenance = {"source_digest_at_package": source_digest()}
    record_path = WORK / "backend-build.json"
    if record_path.is_file():
        record = json.loads(record_path.read_text())
        provenance["source_digest"] = record.get("source_digest")
        provenance["backend_built_at"] = record.get("built_at")
    else:
        # A fresh in-run backend build writes the record before assemble_app runs, so an
        # absent record means something reordered. Record the current digest rather than
        # shipping a bundle with no provenance at all.
        provenance["source_digest"] = provenance["source_digest_at_package"]
    assert_backend_matches_tree(provenance["source_digest"],
                                provenance["source_digest_at_package"])
    binary = BACKEND / "LuminfestBackend"
    if binary.is_file():
        provenance["backend_sha256"] = file_sha256(binary)
        provenance["backend_bytes"] = binary.stat().st_size
    provenance["provenance_recorded_at"] = time.time()
    return provenance


def verify_portability(directory):
    resolved_root = directory.resolve()
    binaries = []
    minimum_versions = []
    for path in directory.rglob("*"):
        if path.is_symlink():
            target = os.readlink(path)
            if os.path.isabs(target) or not path.resolve().is_relative_to(resolved_root) or not path.exists():
                raise RuntimeError(f"Nonportable or broken symlink: {path} -> {target}")
        elif path.is_file():
            with path.open("rb") as stream:
                magic = stream.read(4)
            if magic in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}:
                binaries.append(path)
            if path.suffix in {".sqlite3", ".sqlite", ".db", ".csv", ".npz", ".pkl", ".pickle"}:
                raise RuntimeError(f"Unexpected user/training data in distribution: {path}")
    for path in binaries:
        architectures = subprocess.check_output(["/usr/bin/lipo", "-archs", str(path)], text=True).split()
        if "arm64" not in architectures:
            raise RuntimeError(f"Missing arm64 architecture: {path}")
        links = subprocess.check_output(["/usr/bin/otool", "-L", str(path)], text=True).splitlines()[1:]
        for line in links:
            dependency = line.strip().split(" (", 1)[0]
            if dependency.startswith("/") and not dependency.startswith(("/usr/lib/", "/System/Library/")):
                raise RuntimeError(f"Absolute non-system runtime dependency: {path}: {dependency}")
        commands = subprocess.check_output(["/usr/bin/otool", "-l", str(path)], text=True).splitlines()
        in_rpath = False
        in_version = False
        for line in commands:
            stripped = line.strip()
            if stripped.startswith("cmd "):
                in_rpath = stripped == "cmd LC_RPATH"
                in_version = stripped in {"cmd LC_BUILD_VERSION", "cmd LC_VERSION_MIN_MACOSX"}
            elif in_version and stripped.startswith(("minos ", "version ")):
                version = stripped.split()[1]
                parts = tuple(int(part) for part in version.split("."))
                if parts > (14, 0, 0):
                    raise RuntimeError(f"Binary requires macOS newer than 14.0: {path}: {version}")
                minimum_versions.append(version)
                in_version = False
            elif in_rpath and stripped.startswith("path "):
                rpath = stripped[5:].split(" (offset", 1)[0]
                if rpath.startswith("/") and not rpath.startswith(("/usr/lib/", "/System/Library/")):
                    raise RuntimeError(f"Absolute non-system runtime search path: {path}: {rpath}")
                in_rpath = False
    return {"mach_o_count": len(binaries), "external_symlinks": 0,
            "non_system_absolute_dylib_dependencies": 0, "arm64_verified": True,
            "binary_minimum_macos_versions": sorted(set(minimum_versions))}


def feature_router_modules():
    """The feature routers the app mounts, read from their single definition.

    ``main.create_app`` reaches these modules with ``importlib.import_module``. That is a
    dynamic import, so PyInstaller's static analysis does not see it and the modules are
    left out of the bundle - which is precisely how the desktop build came to ship
    without ``routes_deck``, ``routes_flash``, ``routes_create``, ``routes_media`` or
    ``routes_source`` while every one of them was present in the source tree.

    The tuple is imported rather than restated so this script and the application cannot
    drift apart: there is one list, it is the mount list, and it is also the
    ``--hidden-import`` list. ``app`` is a namespace package with no side effects on
    import, so reaching in for one constant is cheap.
    """
    backend = str(HARNESS / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.feature_routers import FEATURE_ROUTERS
    return tuple(FEATURE_ROUTERS)


def missing_from_archive(names, modules):
    """Which of *names* never landed in the frozen module table.

    Shared by the feature routers and the search provider, because both are imported by
    name at run time and both fail the same way when they are left out: every other route
    works, and one feature answers "not available" forever. A guard whose failure path is
    never exercised is not much of a guard, so it is split out and tested directly.
    """
    collected = set(modules)
    return [name for name in names if name not in collected]


def missing_router_modules(routers, modules):
    """Which declared feature routers failed to land in the frozen module table.

    Returns the bare router names, not the ``app.``-prefixed module names, because that is
    what the build's error message has always listed and what the caller reads.
    """
    absent = missing_from_archive([f"app.{name}" for name in routers], modules)
    return [name.removeprefix("app.") for name in absent]


def search_provider_imports(python):
    """The ``--hidden-import`` values for the run-time-resolved search provider.

    Raises rather than warns when the build environment has no provider at all. A bundle
    without one is not visibly broken - it answers "no verified, concept-specific video"
    for every concept and the learner simply never sees a video - so the failure has to be
    loud at build time or not at all.
    """
    providers = installed_modules(python, search_provider_modules())
    if not providers:
        raise RuntimeError(
            "No DuckDuckGo provider is installed in the build environment, so the frozen "
            "app would ship without video search. Install backend/requirements.txt first.")
    return providers


def search_provider_modules():
    """The DuckDuckGo provider module names the app resolves at run time.

    ``ddg_provider.load`` reaches its provider through ``importlib.import_module`` over a
    tuple of names, so PyInstaller's static analysis sees no import at all. The 1.1.6
    bundle therefore shipped without ``ddgs`` - while ``backend/requirements.txt``
    declared it and the build environment had it installed, which is why nothing
    complained. The visible symptom was ``/ta/prepare`` answering "no verified,
    concept-specific video" for every concept in the shipped app while the same call in
    the source tree curated one, so a learner's lesson silently lost its video.

    Read from ``ddg_provider.NAMES`` rather than restated, for the same reason the router
    list is: one definition, so this script and the application cannot drift apart.
    """
    backend = str(HARNESS / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.harness.ddg_provider import NAMES
    return tuple(NAMES)


def installed_modules(python, names):
    """Which of *names* can actually be imported by *python*.

    The legacy ``duckduckgo_search`` alias is still in ``ddg_provider.NAMES`` for
    environments that have not migrated. Passing it to ``--hidden-import`` when it is
    absent only adds a build warning, and a warning that is always present is a warning
    nobody reads, so only the installed names are declared.
    """
    probe = subprocess.check_output([str(python), "-c",
        "import importlib.util,json,sys; "
        "print(json.dumps([m for m in json.loads(sys.argv[1]) "
        "if importlib.util.find_spec(m)]))", json.dumps(list(names))], text=True)
    return tuple(json.loads(probe))


def build_backend(python, include_research):
    # Before anything is frozen: the environment must actually contain what the app
    # declares it needs. A missing package here is invisible at build time and only
    # surfaces as a feature refusing on a tester's machine.
    dependencies = dependency_gate(python)
    before = source_digest()
    if not WORK.is_dir():
        WORK.mkdir(parents=True)
    command = [python, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
               "--name", "LuminfestBackend", "--target-architecture", "arm64",
               "--contents-directory", "_internal", "--distpath", WORK / "dist",
               "--workpath", WORK / "build", "--specpath", WORK,
               "--paths", HARNESS / "backend", "--paths", HARNESS]
    hidden = ["app.adaptation", "sqlalchemy.dialects.sqlite", "sqlalchemy.dialects.sqlite.pysqlite",
              "sqlalchemy.dialects.postgresql", "sqlalchemy.dialects.postgresql.psycopg", "sqlite3",
              "argon2", "_argon2_cffi_bindings", "_argon2_cffi_bindings._ffi", "pydantic",
              "pydantic_core", "zoneinfo", "uvicorn.logging", "uvicorn.loops.asyncio",
              "uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.on"]
    probe = subprocess.check_output([str(python), "-c",
        "import importlib.util,json; print(json.dumps([m for m in ('psycopg','psycopg_binary','tzdata') "
        "if importlib.util.find_spec(m)]))"], text=True)
    for module in json.loads(probe):
        command += ["--collect-all", module]
    for module in hidden:
        command += ["--hidden-import", module]
    # The feature routers are imported dynamically at runtime, which PyInstaller cannot
    # follow. Declaring them here is what actually puts them in the bundle; without it the
    # frozen app mounts none of them and their endpoints 404 for a tester.
    routers = feature_router_modules()
    for name in routers:
        command += ["--hidden-import", f"app.{name}"]
    # Same blind spot, one layer down: the search provider is resolved by name at run
    # time, so the package that answers every video search is invisible to the analysis.
    # Its own dependencies (``primp``, ``lxml``, ``httpx``) come along as static imports
    # of the module once it is declared.
    providers = search_provider_imports(python)
    for module in providers:
        command += ["--hidden-import", module]
    for module in HEAVY_MODULES:
        command += ["--exclude-module", module]
    # Deliberately absent from the desktop bundle, and named so the omission is a
    # recorded decision rather than a side effect of the build machine. Without this the
    # artifact silently changes size and capability depending on what happens to be
    # installed where it was built.
    for module, reason in sorted(BUNDLE_EXCLUDES.items()):
        print(f"Excluding {module} from the bundle: {reason}", flush=True)
        command += ["--exclude-module", module]
    # Raw runtime sources support adaptation's path-based import; training stays offline.
    for name in RUNTIME_MODEL_FILES:
        command += ["--add-data", f"{HARNESS / 'model' / name}:model"]
    # Curriculum and media packs are read at runtime through ``Path(__file__).parent``,
    # so PyInstaller cannot see them: they are data, not imports. Omitting them does not
    # fail the build - it ships an app whose knowledge graph is empty and whose media and
    # simulation routes raise 500 the first time a learner opens them - so they travel
    # explicitly and ``smoke_backend`` asserts both are populated on the frozen artifact.
    for pack in PACK_DATA_DIRS:
        source = HARNESS / "backend" / "app" / pack
        if not source.is_dir() or not any(source.glob("*.json")):
            raise RuntimeError(f"Curriculum/media pack directory is missing or empty: {source}")
        command += ["--add-data", f"{source}:app/{pack}"]
    # The shipped image pack is build output: ``scripts/curate_images.py`` writes an index
    # plus one file per row, and every deck asks the index before it asks the network. An
    # index naming files the pack does not carry would make every deck report "no picture,
    # here is why" while the build looked healthy - so the pairing is checked here, where it
    # is still a build error, rather than at runtime, where it is a learner's blank slide.
    image_seed = HARNESS / "backend" / "app" / "media_packs" / "image_seed.json"
    if image_seed.is_file():
        rows = json.loads(image_seed.read_text(encoding="utf-8"))
        images = image_seed.parent / "images"
        missing = [str(row.get("file")) for row in rows.values()
                   if isinstance(row, dict) and not (images / str(row.get("file"))).is_file()]
        if missing:
            raise RuntimeError(
                f"image_seed.json names {len(missing)} file(s) the pack does not carry "
                f"(first: {missing[0]}); re-run scripts/curate_images.py")
        print(f"Shipped image pack: {len(rows)} curated picture(s)", flush=True)
    # The legal documents are data too, and they were the last thing still missing from
    # the bundle: ``/legal`` answered with an empty list while registration recorded
    # terms acceptance. ``legal_gate`` above already refuses a *releasable* build whose
    # placeholders are unfilled; this makes the drafts reachable in the template builds
    # that gate permits, so in-app Terms and Privacy can be read and reviewed.
    legal_source = HARNESS / "backend" / LEGAL_DATA_DIR
    if not legal_source.is_dir() or not any(legal_source.glob("*.md")):
        raise RuntimeError(f"Legal document directory is missing or empty: {legal_source}")
    command += ["--add-data", f"{legal_source}:{LEGAL_DATA_DIR}"]
    # The static web pages travel the same way, and fail the same way: without them the
    # bundle ships no ``.html`` at all and every page route answers 404 while the API looks
    # healthy. A missing or empty directory stops the build rather than producing an app
    # whose gallery a learner cannot open.
    web_source = HARNESS / WEB_DATA_DIR
    if not web_source.is_dir() or not any(web_source.glob("*.html")):
        raise RuntimeError(f"Web asset directory is missing or empty: {web_source}")
    command += ["--add-data", f"{web_source}:{WEB_DATA_DIR}"]
    if include_research:
        research = HARNESS / "model" / "research" / "ednet_pfa.json"
        if not research.is_file():
            raise RuntimeError("The explicitly requested EdNet research artifact is absent")
        command += ["--add-data", f"{research}:model/research"]
    command.append(HARNESS / "backend" / "desktop_entry.py")
    build_env = os.environ.copy()
    build_env["PYINSTALLER_CONFIG_DIR"] = str(WORK / "pyinstaller-cache")
    run(command, cwd=ROOT, env=build_env)
    if source_digest() != before:
        raise RuntimeError("Backend sources changed during freezing; rerun --backend-only")
    checks = verify_portability(BACKEND)
    for module in HEAVY_MODULES[:7]:
        if any(path.name == module and path.is_dir() for path in BACKEND.rglob("*")):
            raise RuntimeError(f"Unexpected heavy dependency package: {module}")
    module_probe = subprocess.check_output([str(python), "-c",
        "import json,sys; from PyInstaller.archive.readers import ZlibArchiveReader; "
        "print(json.dumps(list(ZlibArchiveReader(sys.argv[1]).toc)))",
        str(WORK / "build" / "LuminfestBackend" / "PYZ-00.pyz")], text=True)
    modules = json.loads(module_probe)
    if any(name.split(".")[0] in HEAVY_MODULES[:7] for name in modules):
        raise RuntimeError("A heavy dependency was collected into the Python module archive")
    # Fail closed on the routers, in the archive rather than at request time. A missing
    # module here is the exact defect that shipped: the app mounted none of these and
    # answered 404, and nothing in the build objected. Checking membership of the frozen
    # module table is the cheapest possible proof that the declaration above worked.
    absent = missing_router_modules(routers, modules)
    if absent:
        raise RuntimeError("Feature routers are missing from the frozen module archive: "
                           + ", ".join(absent))
    print(f"feature routers collected: {len(routers)} ({', '.join(routers)})", flush=True)
    # And the same fail-closed check for the search provider, which is resolved by name at
    # run time for the same reason. Its absence is invisible until a learner opens a
    # lesson: every other route works, and only the video is quietly missing.
    lost = missing_from_archive(providers, modules)
    if lost:
        raise RuntimeError("Search provider is missing from the frozen module archive: "
                           + ", ".join(lost))
    print(f"search provider collected: {', '.join(providers)}", flush=True)
    strip_runtime_sources(python)
    built_at = time.time()
    write_json(WORK / "backend-build.json", {"source_digest": before,
        "python": str(python), "built_at": built_at, "research_artifact_included": include_research,
        "executable": str(BACKEND / "LuminfestBackend"), "portability": checks,
        "dependencies": dependencies})
    # The mutable record above is overwritten by the next freeze; the ledger line is not.
    append_ledger({"kind": "backend", "source_digest": before, "built_at": built_at,
                   "python": str(python), "research_artifact_included": include_research,
                   "backend_sha256": file_sha256(BACKEND / "LuminfestBackend"),
                   "backend_bytes": (BACKEND / "LuminfestBackend").stat().st_size,
                   "portability": checks})


def strip_runtime_sources(python):
    """Replace the four path-imported model sources with same-interpreter bytecode.

    ``adaptation`` imports the ``model`` package through a runtime path insert, which
    PyInstaller cannot freeze into the PYZ - that is why these files travel as data.
    Shipping them as ``.py`` would publish readable source to every recipient, so each
    one is compiled to a hash-based ``.pyc`` with the exact interpreter that runs the
    frozen backend (matching bytecode magic) and the source is deleted. Python loads
    sourceless bytecode from the same directory the ``.py`` occupied, so the import
    keeps working - but the backend smoke test does **not** prove that: it launches the
    frozen backend with ``HARNESS_ADAPTATION=0``, so ``app.adaptation`` is never imported
    and this layout is never touched. The frozen-only import is pinned instead by
    ``backend/tests/test_resource_paths.py``, which stages this exact bytecode-only
    layout and loads it through ``adaptation._runtime_module``.
    """
    import py_compile
    model_dir = BACKEND / "_internal" / "model"
    for name in RUNTIME_MODEL_FILES:
        src = model_dir / name
        if not src.is_file():
            raise RuntimeError(f"expected frozen model source is missing: {src}")
        pyc = src.with_suffix(".pyc")
        py_compile.compile(str(src), cfile=str(pyc), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
                           quiet=1)
        src.unlink()
    leftovers = sorted(p.name for p in model_dir.glob("*.py"))
    if leftovers:
        raise RuntimeError(f"model package still ships readable sources: {leftovers}")
    print("model runtime sources replaced with bytecode (4 files)")


def clean_runtime_environment(data_dir, port):
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(Path.home()),
           "LANG": "en_US.UTF-8", "TMPDIR": tempfile.gettempdir(),
           "HARNESS_DATA_DIR": str(data_dir), "HARNESS_AUTO_CREATE": "1", "HARNESS_ENV": "test",
           "HARNESS_PORT": str(port), "HARNESS_ADAPTATION": "0", "HARNESS_TUTOR_PROVIDER": "offline",
           "HARNESS_ALLOWED_HOSTS": "127.0.0.1,localhost"}
    return env


def smoke_backend(executable):
    smoke_root = OUTPUTS / "packaging-smoke"
    if not smoke_root.is_dir():
        smoke_root.mkdir(parents=True)
    state = Path(tempfile.mkdtemp(prefix="run-", dir=smoke_root))
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    opener = build_opener(ProxyHandler({}))
    base = f"http://127.0.0.1:{port}/api/v1"
    #: The app root, where the prefix-less routers serve their pages. Kept separate from
    #: ``base`` because a page probe against ``/api/v1`` would pass on the JSON route and
    #: never touch the page at all.
    root = f"http://127.0.0.1:{port}"

    def request(route, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        body = None if payload is None else json.dumps(payload).encode()
        with opener.open(Request(base + route, data=body, headers=headers), timeout=3) as response:
            return json.load(response)

    def route_status(route, token=None, base_url=None):
        """The status code for a route, including the 4xx/5xx that ``opener`` raises.

        Deliberately not ``request``: a route that exists but rejects the method answers
        405, and that is a pass here - it still proves the owning module was mounted. Only
        a 404, which is what an uncollected router produces, counts as a failure.
        ``base_url`` overrides the ``/api/v1`` prefix for the app-root page probes.
        """
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            with opener.open(Request((base_url or base) + route, headers=headers), timeout=3) as response:
                return response.status
        except HTTPError as exc:
            return exc.code

    log_path = state / "backend.log"
    result = {"executable": str(executable), "state_directory": str(state), "passed": False}
    with log_path.open("wb") as log:
        process = subprocess.Popen([str(executable), "--port", str(port)],
            cwd=state, env=clean_runtime_environment(state, port), stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT)
        try:
            # 120 s, not 45. A cold first launch of the freshly written bundle - ~17 MB of
            # executable plus a few hundred MB of collected dylibs that have never been in
            # the page cache - was measured at ~60 s on this machine, while a second launch
            # of the same binary took ~18 s. A 45 s budget therefore failed on a legitimate
            # cold start and passed on a warm one, which makes the gate a coin flip rather
            # than a check: it would fail the first packaging run after any cache clear and
            # pass the retry, teaching whoever hits it to simply run it again. The budget
            # bounds readiness, not launch latency; launch latency is worth measuring, and
            # a separate question from whether the archive was assembled correctly.
            deadline = time.monotonic() + 120
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"Frozen backend exited with {process.returncode}; inspect {log_path}")
                try:
                    health = request("/health")
                    if health.get("ready") is True:
                        break
                except (URLError, TimeoutError, ConnectionError):
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Frozen backend did not become ready; inspect {log_path}")
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
            if health["model_status"].get("trained") is not False:
                raise RuntimeError("Desktop smoke unexpectedly selected a trained math model")
            password = secrets.token_urlsafe(24)
            credentials = {"email": f"smoke-{secrets.token_hex(8)}@example.invalid", "password": password}
            registered = request("/auth/register", {**credentials, "name": "Packaging smoke account"})
            logged_in = request("/auth/login", credentials)
            if registered["user"]["id"] != logged_in["user"]["id"]:
                raise RuntimeError("Register/login identity mismatch")
            token = logged_in["token"]
            question = request("/questions/next?mode=practice", token=token)
            answer = request("/attempts", {"question_id": question["id"],
                "option_id": question["options"][0]["id"], "receipt": question["receipt"],
                "client_event_id": secrets.token_hex(16), "elapsed_seconds": 0,
                "confidence": 0.5}, token=token)
            if not answer.get("id") or not isinstance(answer.get("correct"), bool):
                raise RuntimeError("Answer submission did not return scored feedback")
            dashboard = request("/dashboard", token=token)
            if dashboard["stats"]["attempts"] != 1:
                raise RuntimeError("Smoke answer was not persisted")
            # Runtime data packs. These are read through ``Path(__file__).parent``, so a
            # missing pack is invisible at build time and only shows up as an empty
            # knowledge graph or a 500 in front of a learner. Both are asserted here.
            graph = request("/knowledge-graph", token=token)
            nodes = graph.get("nodes") or []
            edges = graph.get("edges") or []
            if len(nodes) < 50 or not edges:
                raise RuntimeError(
                    "Frozen backend served an empty knowledge graph "
                    f"({len(nodes)} nodes, {len(edges)} edges); app/curriculum_packs was "
                    "probably not bundled")
            sources = request("/media/sources", token=token)
            if not sources.get("sources"):
                raise RuntimeError("Frozen backend served no media sources; "
                                   "app/media_packs was probably not bundled")
            simulations = request("/simulations", token=token)
            if not simulations.get("units"):
                raise RuntimeError("Frozen backend served no simulations; "
                                   "app/media_packs was probably not bundled")
            # The legal documents are read from the same kind of data directory as the
            # packs, so they disappear the same way when they are not bundled. The app
            # records terms acceptance at registration, so a bundle that cannot serve the
            # terms it recorded is a compliance problem, not a cosmetic one.
            legal = request("/legal")
            if not legal.get("documents"):
                raise RuntimeError("Frozen backend served no legal documents; "
                                   "backend/legal was probably not bundled")
            # The static pages are served from a data directory too, and a 404 on the
            # gallery is how a learner discovers the playground is unreachable. These are
            # probed at the app root, not under ``/api/v1``: the routers are mounted without
            # a prefix, so a probe of ``/api/v1/playground`` proves the *JSON* route mounted
            # and says nothing about the page - which is exactly how this shipped broken.
            # Both pages are checked because two different routers each resolve ``web/``.
            static_pages = {}
            for page in ("/", "/playground"):
                status = route_status(page, base_url=root)
                static_pages[page] = status
                if status != 200:
                    raise RuntimeError(
                        f"Frozen backend answered {status} for {page}; {WEB_DATA_DIR}/ was "
                        "probably not bundled, or is being resolved one directory too deep")
            # Feature routers. The app imports these modules dynamically, so the freezer
            # only knows about them because the build declares them; when that declaration
            # is missing the app mounts nothing and every endpoint below answers 404 while
            # the rest of the API looks perfectly healthy. Asserting on the frozen artifact
            # turns that from a tester's discovery into a build failure.
            feature_routes = {}
            for module, route in FEATURE_ROUTE_PROBES:
                status = route_status(route, token=token)
                if status == 404:
                    raise RuntimeError(
                        f"Frozen backend does not serve {route} (404); the {module} router "
                        "was not collected into the bundle")
                feature_routes[route] = status
            with sqlite3.connect(state / "harness.sqlite3") as connection:
                schema_version = connection.execute("SELECT version FROM schema_version WHERE id=1").fetchone()[0]
            # Compare against the version the frozen sources actually declare, not a
            # hard-coded number: a literal here silently stops testing anything the day
            # the schema moves, and reports success for a stale freeze.
            if schema_version != expected_schema_version():
                raise RuntimeError(f"Expected schema v{expected_schema_version()}, got {schema_version}")
            result.update(passed=True, checks=["health", "register", "login", "one_answer",
                                              "persisted_attempt", "knowledge_graph_populated",
                                              "media_sources_present", "simulations_present",
                                              "legal_documents_present",
                                              "static_pages_served",
                                              "feature_routers_mounted"],
                          schema_version=schema_version, model_status=health["model_status"],
                          knowledge_graph={"nodes": len(nodes), "edges": len(edges)},
                          legal_documents=[document["slug"] for document in legal["documents"]],
                          static_pages=static_pages,
                          feature_routes=feature_routes,
                          sanitized_environment=True)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            result["process_exit_code"] = process.returncode
            write_json(state / "result.json", result)
    print(f"Frozen backend smoke passed: {executable}; evidence: {state / 'result.json'}", flush=True)
    return result


def make_icon(destination):
    from PIL import Image, ImageDraw
    size = 1024
    image = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((32, 32, 992, 992), radius=218, fill="#EDEDE4")
    draw.ellipse((152, 152, 872, 872), fill="#D2DBCD")
    draw.ellipse((208, 208, 816, 816), fill="#9CAA94")
    for angle in range(0, 360, 30):
        radians = math.radians(angle)
        points = [(512 + math.cos(radians) * radius, 470 + math.sin(radians) * radius)
                  for radius in (158, 212)]
        draw.line(points, fill="#F6F0D8", width=20)
    draw.ellipse((396, 354, 628, 586), fill="#F6F0D8")
    draw.arc((298, 510, 726, 814), 190, 350, fill="#BEB5D1", width=42)
    draw.arc((358, 568, 666, 780), 190, 350, fill="#E4DDEE", width=24)
    image.save(destination, format="ICNS", sizes=[(16, 16), (32, 32), (64, 64), (128, 128),
                                                (256, 256), (512, 512), (1024, 1024)])


def native_executable(skip_build):
    native = HARNESS / "native"
    if not skip_build:
        # --disable-sandbox: SwiftPM's manifest sandbox-exec fails inside hardened build
        # environments (agent runners, some CI). The product build itself is unaffected;
        # the bundle is still signed and verified by sign_bundle().
        run(["swift", "build", "-c", "release", "--arch", "arm64", "--disable-sandbox",
             "--package-path", native], cwd=ROOT)
    executable = native / ".build" / "release" / "LearningHarness"
    if not executable.is_file():
        raise RuntimeError(f"Native executable is not ready: {executable}")
    if not skip_build:
        # SwiftPM injects an LC_RPATH into the *build machine's* toolchain runtime
        # (…/XcodeDefault.xctoolchain/usr/lib/swift-6.2/macosx). End-user machines have
        # neither Xcode nor that path; the binary already carries /usr/lib/swift and
        # @loader_path, which are the ABI-stable runtime locations that matter. Strip
        # the toolchain rpath so verify_portability passes and the app runs anywhere.
        rpaths = subprocess.check_output(["/usr/bin/otool", "-l", str(executable)], text=True)
        xcode_rpaths = sorted({line.strip()[5:].split(" (offset", 1)[0] for line in rpaths.splitlines()
                               if line.strip().startswith("path /Applications/")})
        for rpath in xcode_rpaths:
            run(["/usr/bin/install_name_tool", "-delete_rpath", rpath, executable])
    sources = [native / "Package.swift", *list((native / "Sources").rglob("*.swift"))]
    newer = [str(path.relative_to(ROOT)) for path in sources if path.stat().st_mtime_ns > executable.stat().st_mtime_ns]
    if newer:
        raise RuntimeError("Native executable predates source fixes; rebuild before packaging: " + ", ".join(newer))
    architectures = subprocess.check_output(["/usr/bin/lipo", "-archs", str(executable)], text=True).split()
    if "arm64" not in architectures:
        raise RuntimeError("The native executable does not support arm64")
    return executable


def app_info_plist(version):
    """The bundle Info.plist.

    Every ``NS*UsageDescription`` here is one the app actually triggers: ``Voice.swift``
    requests microphone and speech-recognition authorization, and presentation capture
    requests the camera. macOS terminates a process that asks for one of these without a
    matching string, so the set is pinned by a test rather than left to review.
    """
    return {
        "CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.luminfest.learningharness", "CFBundleExecutable": "LearningHarness",
        "CFBundlePackageType": "APPL", "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleShortVersionString": version, "CFBundleVersion": version,
        "CFBundleIconFile": "Luminfest.icns", "LSMinimumSystemVersion": "14.0",
        "LSUIElement": False, "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Record your microphone only when you explicitly start a presentation recording.",
        "NSSpeechRecognitionUsageDescription": "Transcribe your speech on this Mac only when you start a spoken session with the tutor. Audio is processed on-device.",
        "NSCameraUsageDescription": "Record your camera only when you explicitly enable it for a presentation recording.",
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    }


def package_name(package_dir=None):
    """The SwiftPM package name, read from the manifest instead of assumed."""
    manifest = Path(package_dir or NATIVE) / "Package.swift"
    match = re.search(r'name:\s*"([^"]+)"', manifest.read_text())
    if not match:
        raise RuntimeError(f"No package name in {manifest}")
    return match.group(1)


def resource_bundle_name(target="LearningHarness", package_dir=None):
    """The directory name SwiftPM gives a target's compiled resources."""
    return f"{package_name(package_dir)}_{target}.bundle"


def resource_bundle(executable, package_dir=None):
    """The compiled resource bundle ``Bundle.module`` looks for, and cannot live without.

    SwiftPM writes target resources into ``<Package>_<Target>.bundle`` beside the
    executable. The generated ``Bundle.module`` accessor does not return nil when that
    directory is absent - it calls ``fatalError``. Copying only the executable therefore
    shipped a signed, portable, arm64 app that died on the first frame that drew a
    companion sprite: the window never appeared, the crash log named a bundle that was
    never inside the app, and nothing in the build failed. The name is derived from the
    manifest so a rename cannot silently drop it again, and the stale bundle left over
    from the previous package name is deliberately not copied.
    """
    path = executable.parent / resource_bundle_name(executable.name, package_dir)
    if not path.is_dir():
        raise RuntimeError(f"Resource bundle is missing from the build: {path}")
    return path


def assemble_app(executable, version, sign_identity=None, sandbox=False, notarize=False, legal=None):
    if not PRIVACY_MANIFEST.is_file():
        raise RuntimeError(f"Privacy manifest is missing: {PRIVACY_MANIFEST}")
    entitlements = ENTITLEMENTS_SANDBOX if sandbox else ENTITLEMENTS_DIRECT
    if sign_identity and not entitlements.is_file():
        raise RuntimeError(f"Entitlements file is missing: {entitlements}")
    with tempfile.TemporaryDirectory(prefix="app-stage-", dir=WORK) as temporary:
        staged = Path(temporary) / APP.name
        contents = staged / "Contents"
        resources = contents / "Resources"
        (contents / "MacOS").mkdir(parents=True)
        (resources / "backend").mkdir(parents=True)
        shutil.copy2(executable, contents / "MacOS" / "LearningHarness")
        # Bundle.module aborts the process rather than degrading, so the resource bundle is
        # part of the app, not an optional extra: see resource_bundle().
        resources_bundle = resource_bundle(executable)
        run(["/usr/bin/ditto", resources_bundle, resources / resources_bundle.name])
        run(["/usr/bin/ditto", BACKEND, resources / "backend" / "LuminfestBackend"])
        # The manifest must sit at Contents/Resources/PrivacyInfo.xcprivacy, which is the
        # only location App Store review looks in.
        shutil.copy2(PRIVACY_MANIFEST, resources / "PrivacyInfo.xcprivacy")
        shutil.copy2(entitlements, resources / entitlements.name)
        make_icon(resources / "Luminfest.icns")
        plist = app_info_plist(version)
        with (contents / "Info.plist").open("wb") as stream:
            plistlib.dump(plist, stream)
        # Provenance travels *inside* the bundle, not only in .packaging/. A record that
        # does not ship cannot answer "which build is this?" for the person holding the
        # file, which is the only person who needs the answer.
        provenance = backend_provenance()
        # ``releasable`` and the legal record travel *with the artifact*. The audit finding
        # was not that a template build existed - the gate refuses one by design, and
        # ``--allow-template-legal`` is a documented alpha override - but that the override
        # left no trace: ``distribution.json`` had no legal field, so the person holding the
        # DMG could not tell it from a release. A record that only lives in
        # ``.packaging/package-result.json`` cannot answer that question for them.
        releasable = bool(legal and legal.get("ship_ready"))
        write_json(resources / "distribution.json",
                   {"signing": sign_identity or "ad-hoc", "sandboxed": bool(sandbox),
                    "notarized": bool(notarize),
                    "notice": DISTRIBUTION_NOTE if not sign_identity else
                              "Signed with a Developer ID. Notarization is required before public download.",
                    "privacy_manifest": "Contents/Resources/PrivacyInfo.xcprivacy",
                    "entitlements": entitlements.name,
                    "version": version,
                    "releasable": releasable,
                    "legal_gate": legal or {"ship_ready": None, "placeholders": None},
                    "research_weights_are_not_a_math_model": True,
                    "offline_training_not_included": True,
                    **provenance})
        if not releasable:
            # A plain-text marker next to the binary, because the DMG filename is the only
            # other signal and a renamed file loses it. Deliberately blunt: someone who
            # opens Contents/Resources looking for provenance should not have to interpret
            # a JSON field to learn this build must not be published.
            (resources / "NOT_RELEASABLE.txt").write_text(
                "This build is NOT releasable.\n\n"
                f"Legal documents still contain {legal.get('placeholders') if legal else 'unchecked'} "
                "unfilled placeholders, so it was packaged with --allow-template-legal.\n"
                "It may be given to named alpha testers and must not be published or sold.\n"
                "See backend/legal/FILL_IN_SHEET.md and rebuild without the override.\n",
                encoding="utf-8")
        checks = verify_portability(staged)
        smoke = smoke_backend(resources / "backend" / "LuminfestBackend" / "LuminfestBackend")
        sign_bundle(staged, sign_identity, entitlements)
        # Retired, not deleted: see retire(). The staged bundle is moved into place only
        # after signing and verification have both succeeded, so a failure here leaves the
        # previous app exactly where it was.
        retire(APP)
        shutil.move(str(staged), APP)
    return checks, smoke


def sign_bundle(staged, sign_identity, entitlements):
    """Sign inner code first, then the bundle.

    ``--deep`` is convenient but is explicitly not supported for distribution signing:
    it signs nested code with the outer settings and cannot express per-binary
    entitlements. Signing bottom-up is what Apple's own guidance requires.
    """
    identity = sign_identity or "-"
    common = ["--force", "--sign", identity, "--timestamp"]
    if sign_identity:
        common = ["--force", "--sign", identity, "--timestamp", "--options", "runtime",
                  "--entitlements", str(entitlements)]
    nested = sorted(
        (path for path in (staged / "Contents" / "Resources" / "backend").rglob("*")
         if path.is_file() and _is_macho(path)),
        key=lambda path: len(path.parts), reverse=True)
    for path in nested:
        run(["/usr/bin/codesign", *common, path])
    run(["/usr/bin/codesign", *common, staged])
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", staged])


def _is_macho(path):
    with path.open("rb") as stream:
        return stream.read(4) in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
                                  b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}


def notarize(dmg, archive, profile, identity):
    """Submit the disk image and the zip to Apple's notary service and staple the ticket.

    Both artifacts are submitted because the DMG is what most users download and the zip
    is what a managed deployment extracts; an unstapled artifact is refused by Gatekeeper
    when the machine is offline.
    """
    if not profile:
        raise RuntimeError("Notarization requires --notary-profile (a notarytool keychain profile)")
    for artifact in (dmg, archive):
        run(["/usr/bin/xcrun", "notarytool", "submit", artifact, "--keychain-profile", profile,
             "--wait", "--output-format", "json"])
    run(["/usr/bin/xcrun", "stapler", "staple", dmg])
    run(["/usr/bin/xcrun", "stapler", "validate", dmg])
    # The zip cannot be stapled; it carries the notarization ticket of the app inside it,
    # which is why the app must be notarized before it is zipped.
    return {"notarized": [str(dmg), str(archive)], "stapled": str(dmg), "profile": profile}


def make_archives(template_legal=False):
    # A template build must not carry a release filename. The filename is the only signal
    # most recipients ever see, and it survives being copied, forwarded in a chat, or
    # renamed - unlike the marker inside the bundle. Naming it like a release is how a
    # documented alpha override ended up being handed out as though it were shippable.
    stem = "Luminfest-arm64" + ("-ALPHA-TEMPLATE-LEGAL" if template_legal else "")
    dmg = OUTPUTS / f"{stem}.dmg"
    archive = OUTPUTS / f"{stem}.zip"
    # A staging directory that is *retired*, never deleted. ``tempfile.TemporaryDirectory``
    # cleans up with an rmtree over a full copy of the app - a few hundred entries - and a
    # build environment's bulk-delete guard refuses that. The failure was expensive and
    # silent: it aborted the run *after* ``hdiutil`` had written the DMG and *before*
    # ``ditto`` wrote the zip, so the output directory ended up holding a brand-new DMG
    # beside a stale zip. That is exactly the situation that put a broken archive in
    # testers' hands while the fixed build sat next to it, so it is worth removing the
    # cause rather than remembering the symptom.
    staging = WORK / "dmg-stage"
    retire(staging)
    staging.mkdir(parents=True)
    run(["/usr/bin/ditto", APP, staging / APP.name])
    (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
    run(["/usr/bin/hdiutil", "create", "-ov", "-volname", APP_NAME, "-format", "UDZO",
         "-fs", "HFS+", "-srcfolder", staging, dmg])
    run(["/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", APP, archive])
    with zipfile.ZipFile(archive) as zipped:
        bad_member = zipped.testzip()
        names = set(zipped.namelist())
        required = {f"{APP.name}/Contents/MacOS/LearningHarness",
                    f"{APP.name}/Contents/Resources/backend/LuminfestBackend/LuminfestBackend"}
        missing = sorted(required - names)
        # The resource bundle holds the companion sprites. Without it the app aborts on the
        # first frame that draws one, so an archive that lost it is not a working archive
        # however healthy its signature looks.
        resource_prefix = f"{APP.name}/Contents/Resources/{resource_bundle_name()}/"
        if not any(name.startswith(resource_prefix) for name in names):
            missing.append(resource_prefix)
        if bad_member or missing:
            raise RuntimeError(f"Archive integrity or executable layout failure: {bad_member or missing}")
    # Only now is the staged copy expendable: both artifacts are on disk and the zip has
    # been opened and checked, so the executable really is inside it.
    retire(staging)
    return dmg, archive


def artifact_manifest(*paths):
    """Size and digest of each artifact, so a handoff note can be checked rather than trusted.

    The distribution guide used to name a download and its size in prose. Prose does not
    fail a build, so the guide went on naming the previous release - a zip with an empty
    knowledge graph - while the fixed build sat next to it. Recording what was actually
    produced, in the record the build itself writes, is what makes "hand out this file"
    a checkable instruction.
    """
    manifest = {}
    for path in paths:
        candidate = Path(path) if path is not None else None
        if candidate is None or not candidate.is_file():
            continue
        digest = hashlib.sha256()
        with candidate.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
        manifest[candidate.name] = {"bytes": candidate.stat().st_size,
                                    "sha256": digest.hexdigest()}
    return manifest


def verify_dmg(dmg):
    run(["/usr/bin/hdiutil", "verify", dmg])
    with tempfile.TemporaryDirectory(prefix="dmg-mount-", dir=WORK) as temporary:
        mount = Path(temporary)
        attached = subprocess.run(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint",
                                  str(mount), str(dmg)], capture_output=True, text=True)
        if attached.returncode:
            print("DMG mount verification unavailable: " + attached.stderr.strip(), flush=True)
            return {"checksum_verified": True, "mounted": False, "mount_error": attached.stderr.strip()}
        try:
            mounted_app = mount / APP.name
            if not (mounted_app / "Contents" / "MacOS" / "LearningHarness").is_file():
                raise RuntimeError("Mounted DMG does not contain the native executable")
            if not (mount / "Applications").is_symlink() or os.readlink(mount / "Applications") != "/Applications":
                raise RuntimeError("Mounted DMG Applications shortcut is missing")
            run(["/usr/bin/codesign", "--verify", "--deep", "--strict", mounted_app])
            # "The record describes this DMG" must be a build-time assertion, not a human
            # obligation. Compare the provenance inside the mounted image against the app
            # that was just assembled: if the DMG was built from different bytes than the
            # bundle it is supposed to contain, that is a packaging fault and it should stop
            # the run here rather than surface as a mystery during an audit.
            shipped = mounted_app / "Contents" / "Resources" / "distribution.json"
            assembled = APP / "Contents" / "Resources" / "distribution.json"
            if not shipped.is_file():
                raise RuntimeError("Mounted DMG bundle has no distribution.json; provenance would be unverifiable")
            if not assembled.is_file():
                raise RuntimeError(f"Assembled bundle has no distribution.json: {assembled}")
            shipped_record = json.loads(shipped.read_text())
            assembled_record = json.loads(assembled.read_text())
            if shipped_record.get("source_digest") != assembled_record.get("source_digest"):
                raise RuntimeError(
                    "DMG provenance does not match the assembled bundle: "
                    f"dmg={shipped_record.get('source_digest')} app={assembled_record.get('source_digest')}")
            return {"checksum_verified": True, "mounted": True,
                    "source_digest": shipped_record.get("source_digest"),
                    "backend_sha256": shipped_record.get("backend_sha256")}
        finally:
            run(["/usr/bin/hdiutil", "detach", mount])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a portable macOS 14+ arm64 Luminfest app, DMG and zip")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--backend-only", action="store_true", help="Freeze and smoke-test only; never build or copy native code")
    modes.add_argument("--skip-backend-build", action="store_true", help="Reuse the previously frozen backend if sources are unchanged")
    parser.add_argument("--skip-native-build", action="store_true", help="Package the parent's existing fresh release executable")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Build-time Python environment; never needed at runtime")
    parser.add_argument("--include-research-artifact", action="store_true",
                        help="Explicit opt-in to separately licensed research-only EdNet JSON; never promoted to a math model")
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--sign-identity", default=None,
                        help="Developer ID Application or Apple Distribution identity. Omit for an ad-hoc build.")
    parser.add_argument("--sandbox", action="store_true",
                        help="Apply App Sandbox entitlements. Required for the Mac App Store; not required for Developer ID.")
    parser.add_argument("--notarize", action="store_true",
                        help="Submit the DMG and zip to Apple's notary service after signing.")
    parser.add_argument("--notary-profile", default=None,
                        help="notarytool keychain profile name, e.g. 'luminfest-notary'.")
    parser.add_argument("--allow-template-legal", action="store_true",
                        help="Package despite unfilled legal placeholders. Template builds only; never for a release.")
    args = parser.parse_args(argv)
    legal_checks = legal_gate(args.allow_template_legal)
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("Run packaging on macOS arm64")
    if not args.python.is_file():
        parser.error("--python must point to an existing Python executable")
    if args.notarize and not args.sign_identity:
        parser.error("--notarize requires --sign-identity; Apple refuses an ad-hoc signature")
    if args.sandbox and not args.sign_identity:
        parser.error("--sandbox requires --sign-identity; an ad-hoc sandbox build cannot be distributed")
    if not OUTPUTS.is_dir():
        OUTPUTS.mkdir()
    if not WORK.is_dir():
        WORK.mkdir()
    if not args.skip_backend_build:
        build_backend(args.python, args.include_research_artifact)
    else:
        record_path = WORK / "backend-build.json"
        if not record_path.is_file() or not (BACKEND / "LuminfestBackend").is_file():
            parser.error("No frozen backend; run --backend-only first")
        record = json.loads(record_path.read_text())
        if record["source_digest"] != source_digest():
            parser.error("Backend sources changed since freezing; rerun --backend-only")
        if args.include_research_artifact and not record["research_artifact_included"]:
            parser.error("Research artifact was not frozen; rebuild with explicit opt-in")
        verify_portability(BACKEND)
    smoke = smoke_backend(BACKEND / "LuminfestBackend")
    if args.backend_only:
        print(f"Backend freeze complete: {BACKEND / 'LuminfestBackend'}", flush=True)
        print("Native build and final app/DMG/zip deferred to the parent.", flush=True)
        return
    # Cheap, and it fails *before* the native build rather than after it. A backend that
    # no source file produced makes everything downstream worthless, so the earlier this
    # is discovered the less of the build is thrown away.
    assert_backend_matches_tree()
    executable = native_executable(args.skip_native_build)
    checks, bundle_smoke = assemble_app(executable, args.version, sign_identity=args.sign_identity,
                                        sandbox=args.sandbox, notarize=args.notarize,
                                        legal=legal_checks)
    dmg, archive = make_archives(template_legal=not legal_checks.get("ship_ready"))
    dmg_checks = verify_dmg(dmg)
    notary = notarize(dmg, archive, args.notary_profile, args.sign_identity) if args.notarize else None
    result = {"app": str(APP), "dmg": str(dmg), "archive": str(archive),
        "native_executable_mtime": executable.stat().st_mtime, "portability": checks,
        "backend_smoke": smoke, "bundle_smoke": bundle_smoke, "dmg_checks": dmg_checks,
        "sign_identity": args.sign_identity, "sandboxed": args.sandbox, "notarization": notary,
        "legal_gate": legal_checks,
        "version": args.version,
        # The authoritative answer to "which file do I hand out": the artifacts this run
        # actually produced, with their sizes and digests.
        "artifacts": artifact_manifest(dmg, archive),
        "dependencies": json.loads((WORK / "backend-build.json").read_text())["dependencies"]
        if (WORK / "backend-build.json").is_file() else None,
        "distribution_notice": DISTRIBUTION_NOTE if not args.sign_identity else
                              ("Signed; notarized." if args.notarize else "Signed; notarization still required."),
        "provenance": backend_provenance()}
    write_json(WORK / "package-result.json", result)
    # Keyed by artifact sha256: the artifact is what a tester holds, so it is the only
    # durable key. Retiring a directory must not retire the record of what was in it.
    append_ledger({"kind": "package", "version": args.version, "built_at": time.time(),
                   "artifacts": result["artifacts"], "sign_identity": args.sign_identity,
                   "sandboxed": args.sandbox, "notarized": bool(args.notarize),
                   "legal_gate": legal_checks, "provenance": result["provenance"]})
    print(f"Packaged: {APP}\nDMG: {dmg}\nArchive: {archive}", flush=True)
    if not args.sign_identity:
        print(DISTRIBUTION_NOTE, flush=True)


if __name__ == "__main__":
    main()
