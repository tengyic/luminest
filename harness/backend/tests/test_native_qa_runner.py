"""The native QA runner is a gate, so its own environment failures must be named.

Two failures made a healthy app look broken on 2026-11-13:

* ``--backend-python`` defaulted to ``harness/ui-tests/.venv/bin/python``, a path that
  does not exist in this checkout. Running the documented command produced
  "Backend Python is missing" before a single journey ran.
* ``--port`` defaulted to 8765, which a running desktop app already owns. The bind
  raised a raw ``[Errno 48] Address already in use``, the run was marked ``blocked``
  and the gate reported **ten missing journeys** -- indistinguishable from the native
  app never launching.

The runner now resolves an interpreter that can actually import the backend's deps,
and scans the same 8765..8785 range the desktop launcher scans. These tests pin those
behaviours without spawning an app or a backend, so they run in the ordinary suite.
"""

from __future__ import annotations

import errno
import importlib.util
import socket
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[3]
NATIVE_QA = ROOT / 'harness' / 'scripts' / 'native_qa.py'


@pytest.fixture(scope='module')
def runner():
    spec = importlib.util.spec_from_file_location('luminfest_native_qa', NATIVE_QA)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_automatic_port_selection_scans_the_launcher_range(runner):
    start, candidates, automatic = runner.port_candidates(0)
    assert automatic is True
    assert start == 8765
    assert list(candidates) == list(range(8765, 8786))
    # BackendLauncher.swift owns the same range; keeping them in step is the point.
    launcher = (ROOT / 'harness' / 'native' / 'Sources' / 'LearningHarness'
                / 'BackendLauncher.swift').read_text('utf-8')
    assert '8765' in launcher


def test_a_pinned_port_is_bound_exactly_and_never_moved(runner):
    start, candidates, automatic = runner.port_candidates(8891)
    assert automatic is False
    assert start == 8891
    assert tuple(candidates) == (8891,)


class BusyFirstSocket(socket.socket):
    """A real socket whose first candidate port is already owned. Instances of
    socket.socket are read-only for attribute assignment, so subclassing is the way
    to override bind while keeping a genuine, closeable, inspectable socket."""

    def bind(self, address):
        if address == ('127.0.0.1', 8765):
            raise OSError(errno.EADDRINUSE, 'Address already in use')
        return super().bind(address)


class AlwaysBusySocket(socket.socket):
    def bind(self, address):
        raise OSError(errno.EADDRINUSE, 'Address already in use')


def test_automatic_binding_skips_a_busy_port(runner, monkeypatch):
    """A desktop app on 8765 must not produce ten missing journeys."""
    monkeypatch.setattr(runner.socket, 'socket', BusyFirstSocket)
    listener, port, selection = runner.bind_owned_listener(0)
    try:
        assert selection == 'automatic'
        assert port != 8765, 'the occupied port must be skipped'
        assert listener.getsockname()[1] == port
    finally:
        listener.close()


def test_a_busy_pinned_port_names_the_conflict(runner):
    held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    held.bind(('127.0.0.1', 0))
    held.listen(1)
    busy = held.getsockname()[1]
    try:
        with pytest.raises(RuntimeError) as caught:
            runner.bind_owned_listener(busy)
        message = str(caught.value)
        assert str(busy) in message
        assert 'already owned' in message
        # The remedy is named, not a raw errno.
        assert '--port 0' in message
        assert isinstance(caught.value.__cause__, OSError)
    finally:
        held.close()


def test_exhausted_range_is_a_named_environment_fact(runner, monkeypatch):
    """When every port is taken the failure must say no app was started."""
    monkeypatch.setattr(runner.socket, 'socket', AlwaysBusySocket)
    with pytest.raises(RuntimeError) as caught:
        runner.bind_owned_listener(0)
    message = str(caught.value)
    assert '8765..8785' in message
    assert 'No app or backend was started' in message
    assert 'not a journey failure' in message


def test_explicit_backend_python_is_validated_not_trusted(runner, tmp_path):
    """An executable that cannot import the backend deps is refused with the reason."""
    fake = tmp_path / 'python'
    fake.write_text('#!/bin/sh\necho "ModuleNotFoundError: No module named \'uvicorn\'" >&2\nexit 1\n')
    fake.chmod(0o755)
    usable, reason = runner.backend_python_status(fake)
    assert usable is False
    assert 'backend dependencies' in reason
    assert 'uvicorn' in reason


def test_missing_explicit_backend_python_names_the_path(runner, tmp_path):
    absent = tmp_path / 'no-such-python'
    with pytest.raises(RuntimeError) as caught:
        runner.resolve_backend_python(absent)
    message = str(caught.value)
    assert str(absent) in message
    assert 'missing or not executable' in message
    assert '--backend-python' in message  # the pinned path is named as the thing to fix


def test_automatic_backend_python_probe_accepts_a_usable_interpreter(runner, monkeypatch):
    """Resolution is by dependency probe, not by a hard-coded venv path.

    Only the second candidate is usable here, which also proves the resolver does not
    stop at the declared venv when that venv is missing or broken.
    """
    second = runner.BACKEND_PYTHON_CANDIDATES[1]
    monkeypatch.setattr(
        runner, 'backend_python_status',
        lambda path: (Path(path) == second, 'stubbed'))
    assert runner.resolve_backend_python() == second


def test_automatic_backend_python_failure_names_every_candidate(runner, monkeypatch):
    monkeypatch.setattr(runner, 'backend_python_status',
                        lambda path: (False, 'missing backend dependencies (uvicorn)'))
    with pytest.raises(RuntimeError) as caught:
        runner.resolve_backend_python()
    message = str(caught.value)
    assert 'No backend interpreter' in message
    assert 'uvicorn' in message
    assert 'requirements.txt' in message
    assert '--backend-python' in message


def test_the_script_no_longer_defaults_to_a_missing_venv(runner):
    """The old default was ui-tests/.venv/bin/python, which does not exist here."""
    source = NATIVE_QA.read_text('utf-8')
    assert "'--backend-python', type=Path, default=None" in source
    assert "'--port', '--qa-endpoint', dest='port', type=int, default=0" in source
