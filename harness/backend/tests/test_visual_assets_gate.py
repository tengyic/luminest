"""The packaged .app must carry the whole offline WebView host, not a flattened shell.

SwiftPM's ``.process`` rule flattens a resource directory: ``index.html`` survives while
``vendor/`` does not, the app still launches, and every inserted visual then renders
``RENDERER_ASSETS_NOT_INSTALLED``. ``package.py:verify_visual_assets`` is the build-time
gate. These tests stage a miniature but real tree (with a manifest derived from its own
bytes) so each refusal is exercised against a file that is genuinely absent, tampered
with, or outside the bundle.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.harness.visual_specs import VISUAL_TYPES

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_SCRIPT = ROOT / "harness" / "scripts" / "package.py"
PUBLISHED_BUNDLE_ROOT = ROOT / "harness" / "native" / "Sources" / "LearningHarness"

sys.path.insert(0, str(PACKAGE_SCRIPT.parent))


@pytest.fixture(scope="module")
def package_module():
    spec = importlib.util.spec_from_file_location("luminfest_package_visuals", PACKAGE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tiny_gate(package_module, monkeypatch):
    """Let a miniature tree stand in for the 21 MiB one without weakening the real gate."""
    monkeypatch.setattr(package_module, "VISUAL_TIKZ_MIN_FONTS", 2)
    monkeypatch.setattr(package_module, "VISUAL_RENDERER_TYPES", 3)


def _stage(tmp_path, *, fonts=2, types=("mafs", "desmos", "tikz"),
           gated=("desmos", "tikz"), omit=(), corrupt=None, manifest_override=None):
    visuals = tmp_path / "Visuals"
    files = {
        "index.html": b"<html></html>",
        "styles.css": b"body{}",
        "visuals.bundle.js": b"window.LuminestVisuals={};",
        "vendor/tikzjax/tikzjax.js": b"loader",
        "vendor/tikzjax/engine.wasm": b"wasm",
        "vendor/tikzjax/dump.gz": b"dump",
    }
    for index in range(fonts):
        files[f"vendor/tikzjax/fonts/f{index}.ttf"] = b"font"
    files["catalog.json"] = json.dumps({
        "version": 1, "order": list(types),
        "types": {name: {"requires": "x" if name in gated else ""}
                  for name in types},
    }).encode()
    for name in omit:
        files.pop(name, None)
    for name, data in files.items():
        path = visuals / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    if corrupt:
        (visuals / corrupt).write_bytes(b"tampered")
    if manifest_override is not None:
        (visuals / "MANIFEST.sha256").write_text(manifest_override, encoding="utf-8")
    else:
        # Digests come from the *intended* bytes, so `corrupt` really produces a mismatch.
        rows = [f"{hashlib.sha256(files[name]).hexdigest()}  {name}"
                for name in sorted(files)]
        (visuals / "MANIFEST.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return visuals


def test_packaging_gate_expects_every_catalog_type(package_module):
    assert package_module.VISUAL_RENDERER_TYPES == len(VISUAL_TYPES)


def test_the_real_published_bundle_passes_the_gate(package_module):
    result = package_module.verify_visual_assets(PUBLISHED_BUNDLE_ROOT)
    assert result["visual_asset_digests_verified"] is True
    assert result["visual_renderer_types"] == len(VISUAL_TYPES)
    assert result["tikz_fonts"] >= package_module.VISUAL_TIKZ_MIN_FONTS
    assert result["visual_asset_count"] > result["tikz_fonts"]


def test_a_flattened_visuals_tree_is_refused(package_module, tmp_path):
    (tmp_path / "index.html").write_text("orphan at the bundle root", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r'\.copy\("Visuals"\)'):
        package_module.verify_visual_assets(tmp_path)


def test_a_complete_miniature_tree_passes(package_module, tiny_gate, tmp_path):
    _stage(tmp_path)
    result = package_module.verify_visual_assets(tmp_path)
    assert result["tikz_fonts"] == 2
    assert result["visual_asset_digests_verified"] is True


def test_missing_host_file_is_refused(package_module, tiny_gate, tmp_path):
    _stage(tmp_path, omit=("index.html",))
    with pytest.raises(RuntimeError, match="Visual host is missing index.html"):
        package_module.verify_visual_assets(tmp_path)


def test_an_asset_listed_but_absent_is_refused(package_module, tiny_gate, tmp_path):
    _stage(tmp_path, manifest_override=(
        f"{hashlib.sha256(b'ghost').hexdigest()}  vendor/ghost.js\n"))
    with pytest.raises(RuntimeError, match="is absent"):
        package_module.verify_visual_assets(tmp_path)


def test_a_tampered_asset_is_refused(package_module, tiny_gate, tmp_path):
    _stage(tmp_path, corrupt="visuals.bundle.js")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        package_module.verify_visual_assets(tmp_path)


def test_the_manifest_cannot_escape_the_bundle(package_module, tiny_gate, tmp_path):
    _stage(tmp_path, manifest_override=f"{'0' * 64}  ../../outside.js\n")
    with pytest.raises(RuntimeError, match="escapes the bundle"):
        package_module.verify_visual_assets(tmp_path)


def test_a_partial_tikz_font_set_is_refused(package_module, tiny_gate, tmp_path, monkeypatch):
    monkeypatch.setattr(package_module, "VISUAL_TIKZ_MIN_FONTS", 3)
    _stage(tmp_path, fonts=2)
    with pytest.raises(RuntimeError, match="TikZ font set is incomplete"):
        package_module.verify_visual_assets(tmp_path)


def test_a_catalog_that_lost_runtime_prerequisites_is_refused(package_module, tiny_gate, tmp_path):
    _stage(tmp_path, gated=())
    with pytest.raises(RuntimeError, match="runtime prerequisite"):
        package_module.verify_visual_assets(tmp_path)
