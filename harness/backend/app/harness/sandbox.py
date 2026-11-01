"""A workspace and a sandbox for generated content and learner code.

The harness generates interactive content, which sometimes means generating code. That
code has to run somewhere, and "somewhere" has to be a real boundary rather than a
promise. Three boundaries are applied together, and each one covers the others' failure:

**Path confinement.** Every path is resolved and checked against the workspace root.
Symlinks are resolved first, so a link inside the workspace cannot be used to reach
outside it. Absolute paths and ``..`` are refused rather than normalised away.

**A static capability guard.** The code's syntax tree is inspected before the interpreter
starts. Network, process-spawning and dynamic-import capabilities are refused up front, so
the common case costs nothing and cannot be raced.

**A runtime audit hook.** The child process installs a ``sys.addaudithook`` guard before
running the script. This is the boundary that matters, because it catches what static
analysis cannot: a module reached through ``getattr``, a socket opened after an
indirect import, a write to a path that was assembled at runtime. Audit hooks cannot be
removed once installed.

**Seatbelt, where the host permits it.** On macOS the child also runs under a
deny-by-default ``sandbox-exec`` profile that denies network access and restricts writes.
Some environments refuse to apply a nested sandbox; that is reported, not hidden.

The result records exactly which boundaries actually applied. A sandbox that silently
degrades to "no sandbox" is worse than no sandbox at all, because the caller cannot tell
the difference - so the caller is always told.
"""

from __future__ import annotations

import ast
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Import roots that would let generated code reach the network or the host.
BANNED_MODULES = frozenset({
    'socket', 'ssl', 'http', 'urllib', 'urllib2', 'urllib3', 'ftplib', 'smtplib', 'poplib',
    'imaplib', 'telnetlib', 'xmlrpc', 'asyncore', 'asynchat', 'socketserver', 'webbrowser',
    'subprocess', 'multiprocessing', 'concurrent', 'ctypes', 'pty', 'tty', 'termios',
    'importlib', 'runpy', 'pkgutil', 'site', 'sysconfig', 'requests', 'httpx', 'aiohttp',
    'paramiko', 'fabric', 'boto3', 'docker', 'pexpect', 'shutil', 'tempfile', 'pickle',
    'shelve', 'dbm', 'sqlite3', 'builtins',
})

#: Attribute paths that spawn processes or re-enter the interpreter.
BANNED_ATTRIBUTES = frozenset({
    'os.system', 'os.popen', 'os.execv', 'os.execve', 'os.execvp', 'os.execvpe', 'os.execl',
    'os.spawnl', 'os.spawnv', 'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.kill',
    'os.setuid', 'os.setgid', 'os.chroot', 'os.putenv',
    'sys.setprofile', 'sys.settrace',
})

BANNED_NAMES = frozenset({'__import__', 'breakpoint', 'exit', 'quit'})

#: Audit events denied outright in the child, whatever the code looks like.
DENIED_EVENTS = (
    'socket.', 'subprocess.', 'os.system', 'os.exec', 'os.spawn', 'os.posix_spawn',
    'os.fork', 'os.kill', 'os.putenv', 'os.unsetenv', 'ctypes.dlopen', 'ctypes.dlsym',
    'webbrowser.', 'ftplib.', 'smtplib.', 'imaplib.', 'poplib.', 'telnetlib.',
    'urllib.Request', 'shutil.', 'pty.spawn', 'sys.setprofile', 'sys.settrace',
)

#: Audit events that mutate the filesystem, checked against the workspace root.
PATH_EVENTS = ('os.remove', 'os.rename', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.chown',
               'os.truncate', 'os.link', 'os.symlink', 'os.utime')

#: Hard caps. Small on purpose: this runs interactive teaching code, not workloads.
MAX_OUTPUT_BYTES = 65536
MAX_FILE_BYTES = 2_000_000
MAX_FILES = 200
DEFAULT_TIMEOUT = 5.0
MAX_TIMEOUT = 20.0
MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
CPU_LIMIT_SECONDS = 20
PROCESS_LIMIT = 64

SUPPORTED_LANGUAGES = ('python',)

#: Boundaries applied on every run, weakest to strongest. Every result reports which of
#: these actually applied, so a degradation is visible rather than silent.
BOUNDARIES = ('path-confinement', 'static-guard', 'runtime-audit-hook')

#: Directories the child may not read, even when seatbelt is unavailable. Home trees and
#: system configuration are where credentials live; a teaching script has no reason to
#: touch them, and generated code should not be able to walk a home directory.
READ_DENY_PREFIXES = tuple(sorted({
    os.path.realpath(str(Path.home())), '/etc', '/private/etc', '/var/root', '/private/var/root',
}))

#: The child-side runner. Installs the audit guard, then executes the learner script
#: through ``runpy`` so tracebacks still point at the learner's own file and line.
RUNNER = '''\
"""Sandbox runner. Installs a runtime capability guard, then runs the target script."""
import os
import runpy
import sys

WORKSPACE = os.path.realpath({workspace!r})
SCRATCH = os.path.realpath({scratch!r})
PREFIX = os.path.realpath({prefix!r})
BANNED_ROOTS = {banned!r}
DENIED_EVENTS = {denied!r}
PATH_EVENTS = {path_events!r}
READ_DENY = set({read_deny!r})
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


def _real(path):
    try:
        return os.path.realpath(path)
    except (TypeError, ValueError, OSError):
        return ''


def _inside(path):
    resolved = _real(path)
    if not resolved:
        return False
    for allowed in (WORKSPACE, SCRATCH, PREFIX):
        if resolved == allowed or resolved.startswith(allowed + os.sep):
            return True
    return False


def _read_denied(path):
    """Deny reads of the learner's own files outside the workspace.

    The point is not to lock down the system - the process legitimately reads the standard
    library - but to stop generated code from walking a home directory for secrets.
    """
    if _inside(path):
        return False
    resolved = _real(path)
    if not resolved:
        return False
    return any(resolved == denied or resolved.startswith(denied + os.sep) for denied in READ_DENY)


def _guard(event, args):
    if event == 'import':
        root = str(args[0]).split('.')[0]
        if root in BANNED_ROOTS:
            raise PermissionError('sandbox: importing ' + str(args[0]) + ' is not permitted')
        return
    if event == 'open':
        try:
            path, mode, flags = str(args[0]), args[1], args[2]
        except (IndexError, TypeError):
            return
        writing = any(flag in (mode or '') for flag in ('w', 'a', 'x', '+')) or \\
            (isinstance(flags, int) and bool(flags & WRITE_FLAGS))
        if writing:
            if not _inside(path):
                raise PermissionError('sandbox: writing outside the workspace is not permitted')
        elif _read_denied(path):
            raise PermissionError('sandbox: reading outside the sandbox is not permitted')
        return
    for prefix in DENIED_EVENTS:
        if event.startswith(prefix):
            raise PermissionError('sandbox: ' + event + ' is not permitted')
    for prefix in PATH_EVENTS:
        if event.startswith(prefix):
            for argument in args[:2]:
                if isinstance(argument, (str, bytes)) and not _inside(argument):
                    raise PermissionError(
                        'sandbox: ' + event + ' outside the workspace is not permitted')
            return


for _name in {preload!r}:
    try:
        __import__(_name)
    except Exception:
        pass
del _name

sys.addaudithook(_guard)
sys.argv = [sys.argv[1]]
runpy.run_path(sys.argv[0], run_name='__main__')
''' 

#: Modules the loader itself needs. They are imported *before* the guard is installed,
#: because ``runpy`` reaches for ``pkgutil`` lazily and a guard that blocks the loader
#: would refuse every script rather than the dangerous ones.
RUNNER_PRELOAD = ('pkgutil', 'importlib', 'importlib.machinery', 'importlib.util',
                  'importlib.abc', 'io', 'linecache', 'tokenize', 'types', 'warnings',
                  'encodings', 'encodings.utf_8')


class SandboxRefused(RuntimeError):
    """Raised when a request cannot be served inside the sandbox."""


class StaticGuardError(SandboxRefused):
    """Raised when generated code asks for a capability the sandbox will not grant."""


def guard(code: str) -> list[str]:
    """Refuse code whose syntax tree asks for network, process or import capabilities.

    A capability check, not a content filter: arithmetic, loops, comprehensions, classes
    and ``open`` on a workspace path all pass. The runtime audit hook catches the rest.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise StaticGuardError(f'Code does not parse: {exc.msg} at line {exc.lineno}') from exc
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] in BANNED_MODULES:
                    problems.append(f'import of {alias.name!r} is not permitted')
        elif isinstance(node, ast.ImportFrom):
            if (node.module or '').split('.')[0] in BANNED_MODULES:
                problems.append(f'import from {node.module!r} is not permitted')
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            problems.append(f'use of {node.id!r} is not permitted')
        elif isinstance(node, ast.Attribute) and _dotted(node) in BANNED_ATTRIBUTES:
            problems.append(f'call to {_dotted(node)!r} is not permitted')
    if problems:
        raise StaticGuardError('Refused: ' + '; '.join(sorted(set(problems))))
    return []


def _dotted(node: ast.Attribute) -> str:
    parts = [node.attr]
    cursor = node.value
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        parts.append(cursor.id)
    return '.'.join(reversed(parts))


# --------------------------------------------------------------------- workspace

@dataclass
class Workspace:
    """One learner's file area, plus the sandboxed executor that writes into it."""

    root: Path
    label: str
    #: Extra absolute prefixes the runtime hook denies for reads, beyond the module-level
    #: ``READ_DENY_PREFIXES``. The data directory lands here: it holds the textbook store
    #: and every other learner's workspace, and OpenStax's notices prohibit ingesting its
    #: content into generative-AI offerings, so a sandboxed script must not be able to
    #: read it out and print it back to the model. The learner's own workspace stays
    #: readable because the hook allows ``WORKSPACE`` before consulting this list.
    deny_reads: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Resolved once, at construction. macOS reaches /var through /private/var, so an
        # unresolved root would make every containment check compare two spellings of the
        # same directory and fail.
        self.root = Path(self.root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.deny_reads = tuple(os.path.realpath(str(Path(p))) for p in self.deny_reads)

    # ---------------------------------------------------------------- paths

    def resolve(self, path: str) -> Path:
        """Map a caller-supplied path onto a real file inside the root."""
        if not isinstance(path, str) or not path.strip():
            raise SandboxRefused('A workspace path is required')
        candidate = Path(path)
        if candidate.is_absolute():
            raise SandboxRefused('Absolute paths are not permitted in the workspace')
        if any(part in ('..', '') for part in candidate.parts):
            raise SandboxRefused('Parent traversal is not permitted in the workspace')
        if candidate.parts and candidate.parts[0] == '~':
            raise SandboxRefused('Home-relative paths are not permitted in the workspace')
        target = (self.root / candidate).resolve()
        if target != self.root and self.root not in target.parents:
            raise SandboxRefused('Path escapes the workspace')
        return target

    # ---------------------------------------------------------------- files

    def write(self, path: str, content: str) -> dict[str, Any]:
        target = self.resolve(path)
        if not isinstance(content, str):
            raise SandboxRefused('Workspace content must be text')
        blob = content.encode('utf-8')
        if len(blob) > MAX_FILE_BYTES:
            raise SandboxRefused(f'File exceeds {MAX_FILE_BYTES} bytes')
        if len(self.list_files()) >= MAX_FILES and not target.exists():
            raise SandboxRefused(f'Workspace already holds {MAX_FILES} files')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        return {'path': str(target.relative_to(self.root)), 'bytes': len(blob),
                'written_at': time.time()}

    def read(self, path: str) -> dict[str, Any]:
        target = self.resolve(path)
        if not target.is_file():
            raise SandboxRefused(f'No such workspace file: {path}')
        return {'path': str(target.relative_to(self.root)),
                'content': target.read_text('utf-8', errors='replace')[:MAX_FILE_BYTES]}

    def delete(self, path: str) -> bool:
        target = self.resolve(path)
        if target.is_file():
            target.unlink()
            return True
        if target.is_dir():
            shutil.rmtree(target)
            return True
        return False

    def list_files(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        return [{'path': str(path.relative_to(self.root)), 'bytes': path.stat().st_size}
                for path in sorted(self.root.rglob('*')) if path.is_file()]

    # ---------------------------------------------------------------- execution

    def run(self, language: str, code: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
        """Run code under every available boundary and report which ones applied."""
        if language not in SUPPORTED_LANGUAGES:
            raise SandboxRefused(
                f'Language {language!r} is not supported here; available: '
                f'{", ".join(SUPPORTED_LANGUAGES)}')
        if not isinstance(code, str) or not code.strip():
            raise SandboxRefused('Code is required')
        if len(code) > MAX_FILE_BYTES:
            raise SandboxRefused('Code exceeds the workspace size limit')
        timeout = float(max(0.5, min(MAX_TIMEOUT, timeout)))
        limits = guard(code)
        boundaries = list(BOUNDARIES)

        with tempfile.TemporaryDirectory(prefix='harness-run-') as scratch:
            script = Path(scratch) / 'main.py'
            script.write_text(code, 'utf-8')
            runner = Path(scratch) / '_runner.py'
            runner.write_text(RUNNER.format(workspace=str(self.root), scratch=scratch,
                                            prefix=str(Path(sys.base_prefix).resolve()),
                                            banned=sorted(BANNED_MODULES),
                                            denied=list(DENIED_EVENTS),
                                            path_events=list(PATH_EVENTS),
                                            read_deny=tuple(READ_DENY_PREFIXES)
                                            + tuple(self.deny_reads),
                                            preload=list(RUNNER_PRELOAD)), 'utf-8')
            inner = [sys.executable, '-I', '-B', str(runner), str(script)]
            profile = self._seatbelt_profile(scratch)
            seatbelt = bool(profile and shutil.which('sandbox-exec'))
            command = ['sandbox-exec', '-p', profile, *inner] if seatbelt else inner
            started = time.time()
            try:
                completed = subprocess.run(command, cwd=str(self.root), capture_output=True,
                                           timeout=timeout, env=self._environment(scratch),
                                           preexec_fn=self._limiter, check=False,
                                           stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                return {'ok': False, 'stdout': '', 'stderr': f'Timed out after {timeout:.1f}s',
                        'exit_code': None, 'duration_ms': round((time.time()-started)*1000, 1),
                        'boundary': '+'.join(boundaries), 'boundaries': boundaries,
                        'limits': limits + [f'timeout {timeout:.1f}s']}
            except OSError as exc:
                raise SandboxRefused(f'Could not start the sandbox: {exc}') from exc
            duration = round((time.time() - started) * 1000, 1)
            stderr = completed.stderr[:MAX_OUTPUT_BYTES].decode('utf-8', errors='replace')
            stdout = completed.stdout[:MAX_OUTPUT_BYTES].decode('utf-8', errors='replace')
            ok = completed.returncode == 0
            # A host can refuse to apply the profile two ways: it says so on stderr, or it
            # aborts the child at interpreter start with a signal and no output at all. The
            # second form is the dangerous one - it looks exactly like "the learner's code
            # crashed" - so it is detected explicitly rather than trusted to be absent.
            seatbelt_killed_it = (not ok and completed.returncode in (-6, 134)
                                  and not stderr.strip() and not stdout.strip())
            if seatbelt and not ok and ('sandbox_apply' in stderr or seatbelt_killed_it):
                # The audit hook still holds, so run again without the profile and report
                # the weaker boundary rather than hiding it.
                retry = self._execute(inner, scratch, timeout, limits)
                retry['limits'] = limits + ['seatbelt could not be applied on this host '
                                            '(nested sandbox refused); network and filesystem '
                                            'refusal rests on the runtime audit hook']
                retry['notes'] = ['Run the service outside a nested sandbox to enable the '
                                  'seatbelt layer.']
                return retry
            if seatbelt:
                boundaries.append('seatbelt')
            boundaries.append('runtime-audit-hook')
            return {'ok': ok, 'stdout': stdout, 'stderr': stderr,
                    'exit_code': completed.returncode, 'duration_ms': duration,
                    'boundary': '+'.join(boundaries), 'boundaries': boundaries,
                    'limits': limits + ['no network', 'workspace-only writes',
                                        f'{timeout:.1f}s wall clock']}

    def _execute(self, command: list[str], scratch: str, timeout: float,
                 limits: list[str]) -> dict[str, Any]:
        started = time.time()
        try:
            completed = subprocess.run(command, cwd=str(self.root), capture_output=True,
                                       timeout=timeout, env=self._environment(scratch),
                                       preexec_fn=self._limiter, check=False,
                                       stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return {'ok': False, 'stdout': '', 'stderr': f'Timed out after {timeout:.1f}s',
                    'exit_code': None, 'duration_ms': round((time.time()-started)*1000, 1),
                    'boundary': '+'.join(BOUNDARIES), 'boundaries': list(BOUNDARIES)}
        return {'ok': completed.returncode == 0,
                'stdout': completed.stdout[:MAX_OUTPUT_BYTES].decode('utf-8', errors='replace'),
                'stderr': completed.stderr[:MAX_OUTPUT_BYTES].decode('utf-8', errors='replace'),
                'exit_code': completed.returncode,
                'duration_ms': round((time.time()-started)*1000, 1),
                'boundary': '+'.join(BOUNDARIES), 'boundaries': list(BOUNDARIES)}

    def _environment(self, scratch: str) -> dict[str, str]:
        return {'PATH': '/usr/bin:/bin', 'HOME': scratch, 'TMPDIR': scratch,
                'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1',
                'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8'}

    @staticmethod
    def _limiter() -> None:  # pragma: no cover - runs in the forked child
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_SECONDS, CPU_LIMIT_SECONDS))
            resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
            resource.setrlimit(resource.RLIMIT_NPROC, (PROCESS_LIMIT, PROCESS_LIMIT))
            resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES, MAX_FILE_BYTES))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except (ValueError, OSError):
            pass

    def _seatbelt_profile(self, scratch: str) -> str:
        """A deny-by-default profile: no network, writes confined to the workspace.

        Read confinement deliberately lives in the runtime audit hook rather than here.
        A narrow ``file-read*`` allow-list looks stronger, but the interpreter resolves
        loader, framework and cache paths that vary by host and by how Python was
        installed; when one of them is missing the kernel aborts the child with
        ``SIGABRT`` and *no* stderr, so every generated program dies with an empty
        result instead of a diagnosable refusal. Seatbelt therefore enforces the two
        boundaries it can state exactly - no network, no writes outside the workspace -
        and the audit hook, which runs inside the child and can name the offending
        path, enforces reads.
        """
        write_rules = ' '.join(
            f'(subpath "{path}")' for path in (str(self.root), os.path.realpath(scratch)))
        return (
            '(version 1)\n'
            '(deny default)\n'
            '(allow process*)\n'
            '(allow sysctl*)\n'
            '(allow mach*)\n'
            '(allow file-read*)\n'
            f'(allow file-write* {write_rules}'
            ' (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr")'
            ' (literal "/dev/dtracehelper"))\n'
            '(deny network*)\n'
        )


def workspace_for(settings, user_id: str) -> Workspace:
    """The workspace root for one learner, under the configured data directory.

    The data directory itself is added to the runtime read-deny list: it holds the
    textbook store and other learners' workspaces, and its contents must not be
    reachable from generated code even when a seatbelt profile is unavailable.
    """
    base = Path(getattr(settings, 'data_dir', Path('.'))) / 'workspaces' / (user_id or 'anonymous')
    data_dir = Path(getattr(settings, 'data_dir', Path('.')))
    deny = () if not str(data_dir) else (os.path.realpath(str(data_dir)),)
    return Workspace(base, f'workspaces/{user_id or "anonymous"}', deny_reads=deny)


def describe() -> dict[str, Any]:
    """The sandbox's actual posture, for the health endpoint and the system prompt."""
    return {'languages': list(SUPPORTED_LANGUAGES),
            'boundaries': list(BOUNDARIES) + (['seatbelt'] if shutil.which('sandbox-exec') else []),
            'seatbelt_available': bool(shutil.which('sandbox-exec')),
            'seatbelt_note': 'macOS may refuse to apply a nested seatbelt; every run reports '
                             'which boundaries actually applied.',
            'read_deny_prefixes': list(READ_DENY_PREFIXES),
            'banned_module_roots': sorted(BANNED_MODULES),
            'max_output_bytes': MAX_OUTPUT_BYTES, 'max_timeout_seconds': MAX_TIMEOUT,
            'memory_limit_bytes': MEMORY_LIMIT_BYTES, 'process_limit': PROCESS_LIMIT,
            'notes': 'Path confinement, a static capability guard before the interpreter '
                     'starts, and a runtime audit hook inside the child that denies network, '
                     'out-of-workspace writes and reads of home or system configuration - even '
                     'when the code is assembled at runtime.'}


def _cleanup_stale(root: Path, older_than_seconds: float = 86400) -> int:  # pragma: no cover
    """Housekeeping hook for the desktop supervisor; not used on the request path."""
    cutoff = time.time() - older_than_seconds
    removed = 0
    for path in root.glob('*'):
        if path.stat().st_mtime < cutoff and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed
