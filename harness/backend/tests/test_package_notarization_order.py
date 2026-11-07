"""Gatekeeper/signing contract tests for ``harness/scripts/package.py``.

These tests need no Developer ID certificate, no notarytool credentials and no network.
They verify the *shape* of the release path so that when credentials do exist, the
artifacts Apple receives are the artifacts a user actually launches.
"""
import ast
import importlib.util
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "scripts" / "package.py"


@pytest.fixture(scope="module")
def pkg():
    spec = importlib.util.spec_from_file_location("luminfest_package_under_test", PACKAGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _main_node():
    tree = ast.parse(PACKAGE.read_text(encoding="utf-8"))
    return next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "main")


def _call_lines(node):
    return [(call.func.id, call.lineno) for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)]


def test_notarize_app_requires_a_keychain_profile(pkg):
    with pytest.raises(RuntimeError, match="notary-profile"):
        pkg.notarize_app(Path("/tmp/Luminfest.app"), None)


def test_notarize_app_submits_then_staples_the_app_itself(pkg, monkeypatch, tmp_path):
    """The previous release path stapled ONLY the DMG after the zip had been built.

    An app extracted from the zip therefore had no offline-valid ticket. The fixed path
    must submit a temporary zip of the app, then staple and validate the .app bundle.
    """
    monkeypatch.setattr(pkg, "WORK", tmp_path)
    commands = []
    monkeypatch.setattr(pkg, "run", lambda command: commands.append(list(command)))

    app = tmp_path / "Luminfest.app"
    result = pkg.notarize_app(app, "unit-test-profile")

    assert len(commands) == 4, commands
    ditto, submit, staple, validate = commands
    assert ditto[0] == "/usr/bin/ditto" and str(app) in ditto
    assert ditto[-1].endswith("Luminfest-notarize.zip")
    assert submit[:3] == ["/usr/bin/xcrun", "notarytool", "submit"]
    assert "--keychain-profile" in submit and "unit-test-profile" in submit
    assert "--wait" in submit
    assert staple == ["/usr/bin/xcrun", "stapler", "staple", str(app)]
    assert validate == ["/usr/bin/xcrun", "stapler", "validate", str(app)]
    assert result["stapled_app"] == str(app)


def test_release_notarizes_the_app_before_archiving(pkg):
    """Ordering is a Gatekeeper property: make_archives() must see a stapled .app."""
    calls = _call_lines(_main_node())
    notarize_app_lines = [line for name, line in calls if name == "notarize_app"]
    archive_lines = [line for name, line in calls if name == "make_archives"]
    notarize_lines = [line for name, line in calls if name == "notarize"]
    assert notarize_app_lines and archive_lines and notarize_lines
    assert min(notarize_app_lines) < min(archive_lines) < min(notarize_lines)


def test_missing_notary_profile_fails_before_any_build():
    """Regression: previously the missing profile raised only after DMG/zip were written."""
    main = _main_node()
    literals = [node.value for node in ast.walk(main)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    assert any("--notary-profile; fail before building" in value for value in literals)


def test_developer_id_signing_uses_hardened_runtime_and_bottom_up_order(pkg, monkeypatch, tmp_path):
    """Notarization requires the hardened runtime; nested frozen binaries must be signed first."""
    staged = tmp_path / "Luminfest.app"
    backend = staged / "Contents" / "Resources" / "backend"
    backend.mkdir(parents=True)
    nested = backend / "LuminfestBackend"
    nested.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 32)
    entitlements = tmp_path / "Direct.entitlements"
    entitlements.write_text("<plist/>", encoding="utf-8")

    commands = []
    monkeypatch.setattr(pkg, "run", lambda command: commands.append([str(part) for part in command]))

    pkg.sign_bundle(staged, "Developer ID Application: Example (TEAMID)", entitlements)

    assert len(commands) == 3, commands
    first, outer, verify = commands
    assert str(nested) in first and str(staged) in outer
    for command in (first, outer):
        assert "--options" in command and "runtime" in command
        assert "--entitlements" in command and str(entitlements) in command
        assert "--timestamp" in command
    assert verify[:2] == ["/usr/bin/codesign", "--verify"]
    assert "--deep" in verify and "--strict" in verify
