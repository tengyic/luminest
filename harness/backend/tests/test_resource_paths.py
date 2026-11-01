"""The frozen-aware resource resolver, tested in both layouts it has to serve.

The bug this pins is worth restating because it is invisible to every other test here:
three modules each resolved a top-level resource directory with
``Path(__file__).resolve().parents[2]``. That is correct in the source tree and one
directory too deep in the frozen app, where PyInstaller mirrors the package tree under
``_internal`` and there is no ``backend/`` level to consume the extra step. The shipped
bundle therefore contained zero ``.html`` files and answered 404 for ``/`` and
``/playground`` while ``/api/v1/health`` looked perfectly healthy.

A resolver that is only exercised in the layout it was written against is not fixed, so
the frozen layout is staged here as a temporary directory and the resolver is asserted
against it, and the source layout is asserted against the real tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app import resources


def _stage_frozen_bundle(contents: Path) -> Path:
    """A directory mirroring the bundle's ``_internal`` contents, as ``--add-data`` lays it out."""
    for name in ('web', 'model', 'legal'):
        (contents / name).mkdir(parents=True, exist_ok=True)
    (contents / 'web' / 'index.html').write_text('<!doctype html>', encoding='utf-8')
    (contents / 'web' / 'playground.html').write_text('<!doctype html>', encoding='utf-8')
    (contents / 'model' / '__init__.py').write_text('', encoding='utf-8')
    (contents / 'legal' / 'terms.md').write_text('# Terms', encoding='utf-8')
    return contents


# ------------------------------------------------------------------ the frozen layout

def test_the_resolver_finds_each_directory_inside_a_frozen_bundle(tmp_path, monkeypatch):
    """``sys.frozen`` + ``sys._MEIPASS`` must resolve to the bundle's contents directory."""
    contents = _stage_frozen_bundle(tmp_path / '_internal')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(contents), raising=False)

    assert resources.resource_root() == contents
    for name in ('web', 'model', 'legal'):
        assert resources.resource_dir(name) == contents / name
        assert resources.resource_dir(name).is_dir(), name
    # The two pages the shipped app must actually serve.
    assert (resources.resource_dir('web') / 'index.html').is_file()
    assert (resources.resource_dir('web') / 'playground.html').is_file()
    assert (resources.resource_dir('model') / '__init__.py').is_file()


def test_a_frozen_marker_without_meipass_falls_back_to_the_source_tree(tmp_path, monkeypatch):
    """Half a frozen marker must not resolve to a path that cannot exist.

    ``sys.frozen`` without ``sys._MEIPASS`` is not a layout PyInstaller produces, but
    trusting the flag alone would resolve to the empty string - a directory that exists and
    contains nothing, which is a worse failure than a wrong one.
    """
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.delattr(sys, '_MEIPASS', raising=False)

    assert resources.resource_root() == Path(resources.__file__).resolve().parents[2]


def test_a_false_frozen_flag_is_not_treated_as_frozen(tmp_path, monkeypatch):
    """Some interpreters expose ``sys.frozen`` as ``False``; that is the source layout."""
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path / 'nowhere'), raising=False)

    assert resources.resource_root() == Path(resources.__file__).resolve().parents[2]


# ------------------------------------------------------------------ the source layout

def test_the_resolver_still_finds_the_source_tree(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.delattr(sys, '_MEIPASS', raising=False)

    root = resources.resource_root()
    # app/resources.py -> app -> backend -> harness
    assert root == Path(resources.__file__).resolve().parents[2]
    assert root.name == 'harness'
    assert (resources.resource_dir('web') / 'playground.html').is_file()
    assert (resources.resource_dir('model') / '__init__.py').is_file()


# ------------------------------------------------- nobody re-derives the depth by hand

def test_every_module_resolves_its_directory_through_the_resolver():
    """The three callers share one answer.

    This is the regression that matters: the depth was wrong in three copies of the same
    arithmetic. Pinning that the modules agree with the resolver stops a fourth copy - or a
    quiet edit to one of the three - from reintroducing the split.
    """
    from app import adaptation, playground_routes, web_routes

    assert web_routes.WEB_DIR == resources.resource_dir('web')
    assert playground_routes.WEB_DIR == resources.resource_dir('web')
    assert web_routes.WEB_DIR == playground_routes.WEB_DIR
    assert adaptation.MODEL_DIR == resources.resource_dir('model')


def test_the_directories_the_modules_read_are_populated():
    """A resolver that points at an empty directory is not a fix."""
    from app import adaptation, playground_routes, web_routes

    assert (web_routes.WEB_DIR / 'index.html').is_file()
    assert (playground_routes.WEB_DIR / 'playground.html').is_file()
    assert (adaptation.MODEL_DIR / '__init__.py').is_file()


# --------------------------------------- the bundle must actually carry the directory

@pytest.fixture(scope='module')
def package_module():
    """Load ``scripts/package.py`` the way ``test_packaging_manifest.py`` does."""
    import importlib.util

    script = Path(__file__).resolve().parents[2] / 'scripts' / 'package.py'
    spec = importlib.util.spec_from_file_location('luminfest_package_web', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_web_directory_is_declared_as_bundle_data(package_module):
    """A resolver pointed at a directory the packager never ships is still a 404.

    Both halves of the fix are pinned here: that ``package.py`` names ``web`` as bundle
    data, and that the directory it names holds the pages the two page routes serve.
    """
    assert package_module.WEB_DATA_DIR == 'web'
    source = package_module.HARNESS / package_module.WEB_DATA_DIR
    assert source.is_dir(), f'missing web directory: {source}'
    assert (source / 'index.html').is_file()
    assert (source / 'playground.html').is_file()


# --------------------------------- the model package ships as bytecode, not source
#
# ``package.py:strip_runtime_sources`` replaces the four path-imported model sources
# with same-interpreter ``.pyc`` files and deletes the ``.py`` originals, so the frozen
# bundle contains ``model/__init__.pyc`` and no ``model/__init__.py``. The adapter used
# to name ``__init__.py`` unconditionally, which is a ``FileNotFoundError`` in exactly
# that layout - and the backend smoke test cannot catch it, because it runs with
# ``HARNESS_ADAPTATION=0`` and therefore never imports ``app.adaptation`` at all. The
# frozen-only import is pinned here instead, against a staged copy of the real layout.
#
# The layout is staged rather than mocked: a test that asserts a loader *would* find a
# ``.pyc`` without ever producing one is the same class of unbacked claim as the
# docstring this file is making true.


def _stage_bytecode_only_model(root: Path, marker: str = 'loaded-from-bytecode') -> Path:
    """A ``model/`` package exactly as ``strip_runtime_sources`` leaves it: ``.pyc`` only."""
    import py_compile

    model = root / 'model'
    model.mkdir(parents=True, exist_ok=True)
    src = model / '__init__.py'
    src.write_text(f'MARKER = {marker!r}\n', encoding='utf-8')
    # The same invalidation mode the packager uses, so this is the shipped bytecode shape
    # rather than a default-timestamp ``.pyc`` that could pass for a different reason.
    py_compile.compile(str(src), cfile=str(model / '__init__.pyc'), doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
                       quiet=1)
    src.unlink()
    return model


@pytest.fixture
def fresh_owned_model():
    """``_runtime_module`` caches into ``sys.modules``; each test needs a clean slot."""
    name = 'harness_owned_model'
    saved = sys.modules.pop(name, None)
    yield name
    sys.modules.pop(name, None)
    if saved is not None:
        sys.modules[name] = saved


def test_the_owned_model_package_loads_from_bytecode_only(tmp_path, monkeypatch, fresh_owned_model):
    """The frozen layout: ``__init__.pyc`` present, ``__init__.py`` deleted.

    This is the path that raised ``FileNotFoundError`` in the shipped app.
    """
    from app import adaptation

    model = _stage_bytecode_only_model(tmp_path)
    # The premise, asserted rather than assumed: naming ``__init__.py`` here would fail,
    # so a green result below cannot be an accident of the source file still existing.
    assert not (model / '__init__.py').exists()
    assert (model / '__init__.pyc').is_file()

    monkeypatch.setattr(adaptation, 'MODEL_DIR', model)
    module = adaptation._runtime_module()

    assert module.MARKER == 'loaded-from-bytecode'
    # It loaded the staged package, not some other ``model`` on ``sys.path``.
    assert Path(module.__file__).parent == model


def test_the_loader_still_prefers_the_source_file_when_both_are_present(tmp_path, monkeypatch, fresh_owned_model):
    """The source tree ships ``__init__.py``; the loader must not prefer stale bytecode.

    A ``.pyc`` left next to a ``.py`` by an earlier run is ordinary in a working tree, and
    silently loading the compiled copy would make an edit invisible.
    """
    from app import adaptation

    model = tmp_path / 'model'
    model.mkdir()
    (model / '__init__.py').write_text("MARKER = 'from-source'\n", encoding='utf-8')
    (model / '__init__.pyc').write_bytes(b'not real bytecode')

    monkeypatch.setattr(adaptation, 'MODEL_DIR', model)
    assert adaptation._runtime_module().MARKER == 'from-source'


def test_the_loader_names_both_initialiser_spellings():
    """The tuple is the whole fix; assert it rather than trusting the call site."""
    from app import adaptation

    assert adaptation._PACKAGE_INIT_FILES == ('__init__.py', '__init__.pyc')


def test_the_loader_refuses_an_empty_model_directory_with_a_clear_message(
        tmp_path, monkeypatch, fresh_owned_model):
    """No initialiser at all is a real misconfiguration and must say so.

    The message has to name the directory and both filenames, because the operator
    reading it is looking at a bundle they cannot easily inspect.
    """
    from app import adaptation

    empty = tmp_path / 'model'
    empty.mkdir()
    monkeypatch.setattr(adaptation, 'MODEL_DIR', empty)

    with pytest.raises(FileNotFoundError) as excinfo:
        adaptation._runtime_module()
    message = str(excinfo.value)
    assert str(empty) in message
    assert '__init__.py' in message and '__init__.pyc' in message
