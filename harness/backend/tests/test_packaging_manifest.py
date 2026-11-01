"""Guards the macOS bundle manifest against the capabilities the app actually uses.

macOS terminates a process that requests a protected resource without a matching
``NS*UsageDescription`` string. The failure only appears at runtime, on the reviewer's
machine, the first time a learner presses the microphone button - so it is pinned here
instead. The Swift sources are read to derive which permissions must be declared, which
means adding a new protected API to the app without declaring it fails this test rather
than shipping.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_SCRIPT = ROOT / "harness" / "scripts" / "package.py"
SOURCES = ROOT / "harness" / "native" / "Sources" / "LearningHarness"

sys.path.insert(0, str(PACKAGE_SCRIPT.parent))


@pytest.fixture(scope="module")
def package_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("luminfest_package", PACKAGE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def swift_sources() -> str:
    return "\n".join(path.read_text("utf-8") for path in sorted(SOURCES.rglob("*.swift")))


def test_info_plist_declares_every_permission_the_app_requests(package_module):
    plist = package_module.app_info_plist("9.9.9")
    source = swift_sources()

    # Each entry maps a Swift API the app calls to the plist key macOS demands for it.
    required = {
        "NSMicrophoneUsageDescription": "AVCaptureDevice.requestAccess",
        "NSSpeechRecognitionUsageDescription": "SFSpeechRecognizer.requestAuthorization",
        "NSCameraUsageDescription": "AVCaptureDevice",
    }
    missing = []
    for key, marker in required.items():
        if marker in source and not plist.get(key):
            missing.append(f"{key} (app calls {marker})")
    assert not missing, (
        "Info.plist omits usage descriptions for APIs the app calls; macOS kills the "
        "process at first use: " + ", ".join(missing))


def test_info_plist_keeps_the_keys_macos_and_gatekeeper_expect(package_module):
    plist = package_module.app_info_plist("1.2.3")
    assert plist["CFBundleIdentifier"] == "com.luminfest.learningharness"
    assert plist["CFBundleExecutable"] == "LearningHarness"
    assert plist["CFBundlePackageType"] == "APPL"
    assert plist["LSMinimumSystemVersion"] == "14.0"
    assert plist["CFBundleShortVersionString"] == plist["CFBundleVersion"] == "1.2.3"
    # The bundled backend listens on loopback; without this the app cannot reach it.
    assert plist["NSAppTransportSecurity"]["NSAllowsLocalNetworking"] is True


def test_usage_descriptions_are_specific_rather_than_placeholders(package_module):
    plist = package_module.app_info_plist("1.0.0")
    for key, value in plist.items():
        if key.startswith("NS") and key.endswith("UsageDescription"):
            assert isinstance(value, str) and len(value) >= 30, key
            assert not re.fullmatch(r"(?i)\s*(todo|tbd|n/?a|placeholder)\s*", value), key


def test_distribution_notice_never_claims_a_signature_it_does_not_have(package_module):
    # The notice is shipped inside every bundle and is what a reviewer reads first.
    notice = package_module.DISTRIBUTION_NOTE
    assert "Ad-hoc" in notice and "not notarized" in notice.lower()
    assert "Developer ID" in notice


# ------------------------------------------------------- declared dependencies

def test_every_declared_runtime_requirement_is_installed_here(package_module):
    """The gate the packaging script runs before it freezes anything.

    PyInstaller collects what is *installed*, not what is declared, and says nothing when
    the two disagree - so a build from an environment missing a dependency produces a
    bundle whose feature fails on the tester's machine. That is how a shipped build came
    to carry a document-upload path whose multipart parser was never frozen, and a
    text-to-speech tool that could only ever refuse. Running the gate in the test suite
    catches it one step earlier than the build does.
    """
    try:
        result = package_module.dependency_gate(sys.executable)
    except RuntimeError as exc:  # pragma: no cover - the failure message is the point
        pytest.fail(str(exc))
    assert result["required_present"] is True
    assert result["required_checked"], "requirements.txt declared nothing to check"


def test_the_comparison_reports_missing_and_mismatched_separately(package_module):
    """The pure half of the gate, so its two failure modes stay distinguishable."""
    from packaging.requirements import Requirement

    declared = [Requirement("fastapi==0.143.0"), Requirement("httpx>=0.28,<1"),
                Requirement("absent-package==1.0")]
    missing, mismatched = package_module.compare_requirements(
        declared, {"fastapi": "0.143.0", "httpx": "0.27.0"})
    assert missing == ["absent-package==1.0"]
    assert len(mismatched) == 1 and "httpx" in mismatched[0] and "0.27.0" in mismatched[0]
    # Distribution names are compared the way pip normalises them, so a listing that
    # spells a name with underscores still satisfies a requirement that uses hyphens.
    assert package_module.compare_requirements(
        [Requirement("argon2-cffi==25.1.0")], {"argon2_cffi": "25.1.0"}) == ([], [])


def test_an_exclusion_that_no_longer_matches_a_declaration_is_refused(package_module, tmp_path):
    """A stale exemption would quietly suppress a real check, so it fails the build."""
    required = tmp_path / "requirements.txt"
    required.write_text("fastapi==0.143.0\n", encoding="utf-8")
    optional = tmp_path / "requirements-optional.txt"
    optional.write_text("psycopg[binary]>=3.2,<4\n", encoding="utf-8")
    real = package_module.installed_distributions
    package_module.installed_distributions = lambda python: {"fastapi": "0.143.0"}
    try:
        with pytest.raises(RuntimeError) as exc:
            package_module.dependency_gate(sys.executable, required=required, optional=optional)
        # BUNDLE_EXCLUDES names playwright; the optional file above does not declare it.
        assert "playwright" in str(exc.value)
        # Declaring it clears the error, which is what makes the check meaningful rather
        # than merely strict.
        optional.write_text("psycopg[binary]>=3.2,<4\nplaywright==1.62.0\n", encoding="utf-8")
        result = package_module.dependency_gate(sys.executable, required=required,
                                                optional=optional)
        assert "playwright==1.62.0" in result["optional_missing"]
    finally:
        package_module.installed_distributions = real


def test_a_missing_required_package_stops_the_build(package_module, tmp_path):
    required = tmp_path / "requirements.txt"
    required.write_text("fastapi==0.143.0\ndefinitely-not-installed==9.9.9\n", encoding="utf-8")
    optional = tmp_path / "requirements-optional.txt"
    optional.write_text("playwright==1.62.0\npsycopg[binary]>=3.2,<4\n", encoding="utf-8")
    real = package_module.installed_distributions
    package_module.installed_distributions = lambda python: {"fastapi": "0.143.0"}
    try:
        with pytest.raises(RuntimeError) as exc:
            package_module.dependency_gate(sys.executable, required=required, optional=optional)
        assert "definitely-not-installed" in str(exc.value)
        assert "would produce a bundle whose features fail" in str(exc.value)
    finally:
        package_module.installed_distributions = real


# ------------------------------------------------ bundle data that must travel

def test_the_legal_documents_are_declared_as_bundle_data(package_module):
    """``/legal`` reads from the same kind of data directory as the curriculum packs.

    They disappear the same way when they are not bundled: the route answers with an
    empty list while registration still records terms acceptance at ``terms_version``,
    which is the worst of both positions. The packaging script names the directory as
    data, and this pins that it exists and carries real documents.
    """
    legal = package_module.HARNESS / "backend" / package_module.LEGAL_DATA_DIR
    assert legal.is_dir(), f"missing legal directory: {legal}"
    slugs = {path.stem for path in legal.glob("*.md")}
    # The four the /legal route will serve, plus the fill-in sheet that owns the blanks.
    assert {"terms", "privacy", "ai", "accessibility"} <= slugs
    assert "FILL_IN_SHEET" in slugs


def test_the_pack_data_directories_are_still_declared(package_module):
    """The fix from the previous review, kept from regressing."""
    for name in package_module.PACK_DATA_DIRS:
        source = package_module.HARNESS / "backend" / "app" / name
        assert source.is_dir() and any(source.glob("*.json")), name


def test_every_bundle_exclusion_is_declared_and_explained(package_module):
    """An exclusion with no reason, or with no requirement behind it, is a silent hole."""
    optional = package_module.HARNESS / "backend" / "requirements-optional.txt"
    declared = {line.split("#")[0].strip().split("=")[0].split("[")[0].split(">")[0].split("<")[0]
                for line in optional.read_text("utf-8").splitlines()}
    for name, reason in package_module.BUNDLE_EXCLUDES.items():
        assert name in declared, f"{name} is excluded but no longer declared"
        assert len(reason) >= 40, f"{name} is excluded with no real explanation"


# ------------------------------------------- SwiftPM resources that must travel

def test_the_resource_bundle_name_follows_the_package_manifest(package_module, tmp_path):
    """``Bundle.module`` looks for ``<Package>_<Target>.bundle``, not a fixed name.

    The package was renamed once already, so the name is read from ``Package.swift``
    rather than written down here: a rename that left the old string in the packaging
    script would copy nothing and still pass every other check.
    """
    (tmp_path / "Package.swift").write_text(
        'let package = Package(\n    name: "RenamedHarness",\n)\n', encoding="utf-8")
    assert package_module.resource_bundle_name("LearningHarness", tmp_path) == \
        "RenamedHarness_LearningHarness.bundle"


def test_a_build_without_the_resource_bundle_is_refused(package_module, tmp_path):
    """The failure this replaces was silent: a valid signature, a portable binary, no window.

    ``Bundle.module``'s accessor calls ``fatalError`` instead of returning nil, so the app
    aborted on the first frame that drew a companion sprite and the crash log named a
    bundle that had never been inside the app. Packaging must fail loudly instead.
    """
    build = tmp_path / ".build" / "release"
    build.mkdir(parents=True)
    executable = build / "LearningHarness"
    executable.write_bytes(b"\xcf\xfa\xed\xfe")
    (tmp_path / "Package.swift").write_text(
        'let package = Package(\n    name: "LuminfestLearningHarness",\n)\n', encoding="utf-8")
    with pytest.raises(RuntimeError) as exc:
        package_module.resource_bundle(executable, tmp_path)
    assert "Resource bundle is missing" in str(exc.value)

    (build / "LuminfestLearningHarness_LearningHarness.bundle").mkdir()
    assert package_module.resource_bundle(executable, tmp_path).name == \
        "LuminfestLearningHarness_LearningHarness.bundle"


def test_artwork_is_never_loaded_through_swiftpms_generated_accessor():
    """``Bundle.module`` is unusable in a packaged app, and fails only off the build machine.

    The generated accessor looks beside ``Luminfest.app`` (where nothing is) and then at an
    absolute path inside the builder's ``.build`` directory. Every extra reference is
    another frame that dies on a tester's Mac but not here, so ``AppResources`` is the only
    file allowed to mention it - and only as the last resort that ``swift test`` needs.
    """
    offenders = sorted(path.name for path in SOURCES.rglob("*.swift")
                       if path.name != "AppResources.swift"
                       and "Bundle.module" in path.read_text(encoding="utf-8"))
    assert not offenders, f"load artwork through AppResources.url instead: {offenders}"


# --------------------------------- modules the app imports by name at run time

def test_the_search_provider_the_app_resolves_is_declared_and_installed(package_module):
    """``ddg_provider`` imports its provider by name, so PyInstaller sees no import at all.

    The 1.1.6 bundle shipped without ``ddgs`` while ``requirements.txt`` declared it and
    the build environment had it installed: nothing in the build objected, and the only
    symptom was ``/ta/prepare`` answering "no verified video" for every concept, so every
    lesson quietly lost its video. The provider names are read from the app's own tuple so
    this test and the runtime resolver cannot disagree.
    """
    names = package_module.search_provider_modules()
    assert "ddgs" in names, "the maintained package is the one requirements.txt pins"
    installed = package_module.installed_modules(sys.executable, names)
    assert "ddgs" in installed, (
        "ddgs is declared in requirements.txt but not importable here, so the frozen "
        "bundle would ship without video search")
    declared = (package_module.HARNESS / "backend" / "requirements.txt").read_text("utf-8")
    assert "ddgs" in declared


def test_a_build_environment_without_a_search_provider_is_refused(package_module):
    """The loud half: an empty provider list must stop the build, not warn."""
    real = package_module.installed_modules
    package_module.installed_modules = lambda python, names: ()
    try:
        with pytest.raises(RuntimeError) as exc:
            package_module.search_provider_imports(sys.executable)
        assert "video search" in str(exc.value)
    finally:
        package_module.installed_modules = real


def test_the_archive_check_covers_a_provider_that_never_landed(package_module):
    """Same guard as the routers, pointed at the provider: absence is a build failure."""
    assert package_module.missing_from_archive(["ddgs"], ["ddgs", "app.main"]) == []
    assert package_module.missing_from_archive(["ddgs"], ["app.main"]) == ["ddgs"]



def test_a_backend_frozen_from_different_sources_is_refused(package_module, tmp_path, monkeypatch):
    """A stale artifact must stop the build, not describe itself as stale.

    This is not hypothetical. The 1.1.10 bundle shipped a ``distribution.json`` carrying
    ``source_digest`` 1a60e8c9 and ``source_digest_at_package`` 4967f041 side by side:
    the packaging run succeeded, the frozen smoke passed all eleven checks, and the
    backend inside the DMG had been built from code the tree no longer contained. The
    disagreement was recorded and nothing read it - which is why the check is an
    assertion now.
    """
    import json

    monkeypatch.setattr(package_module, "WORK", tmp_path)
    monkeypatch.setattr(package_module, "source_digest", lambda: "b" * 64)
    (tmp_path / "backend-build.json").write_text(json.dumps({"source_digest": "a" * 64}))
    with pytest.raises(RuntimeError) as exc:
        package_module.assert_backend_matches_tree()
    message = str(exc.value)
    assert "does not match the current sources" in message
    assert "a" * 12 in message and "b" * 12 in message
    # The remedy has to be in the error, or the next person re-freezes blindly.
    assert "--skip-backend-build" in message


def test_matching_sources_and_a_missing_record_both_pass(package_module, tmp_path, monkeypatch):
    """The check must not fire on a healthy build.

    ``--skip-backend-build`` reuses a freeze, so ``assemble_app`` can legitimately run
    with a record that already matches; and an absent record means a fresh in-run build
    whose write was skipped, which the caller treats as current rather than stale.
    """
    import json

    monkeypatch.setattr(package_module, "WORK", tmp_path)
    monkeypatch.setattr(package_module, "source_digest", lambda: "c" * 64)
    package_module.assert_backend_matches_tree()          # no record at all
    (tmp_path / "backend-build.json").write_text(json.dumps({"source_digest": "c" * 64}))
    package_module.assert_backend_matches_tree()          # record agrees
