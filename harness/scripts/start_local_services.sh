#!/usr/bin/env bash
# Bring up the three local services the learning harness actually depends on.
#
#   scripts/start_local_services.sh            # check + install + VoiceStudio
#   scripts/start_local_services.sh --serve    # ... then run the backend on :8877
#   PYTHON=/path/to/python scripts/start_local_services.sh
#
# 1. VoiceStudio  - the local TTS engine, loopback :3900 (opened if not running)
# 2. Chromium     - headless browser used for web + video search (no API key)
# 3. The backend  - FastAPI, started only with --serve
#
# Every step is idempotent. Nothing here downloads anything other than declared
# Python packages and the Playwright Chromium build, and nothing writes outside
# the workspace except the browser cache in ~/Library/Caches/ms-playwright.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
cd "$ROOT"
PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$BACKEND/.venv/bin/python" ]]; then
    PYTHON="$BACKEND/.venv/bin/python"
  else
    # Keep every install inside the workspace. A system-wide pip install would
    # work once and then silently depend on whichever python the shell resolves.
    echo "creating $BACKEND/.venv (system site packages visible) ..."
    python3 -m venv --system-site-packages "$BACKEND/.venv"
    PYTHON="$BACKEND/.venv/bin/python"
  fi
fi
PORT="${PORT:-8877}"

echo "repo:    $ROOT"
echo "python:  $PYTHON"

# --- 1. declared runtime dependencies -------------------------------------
MISSING="$("$PYTHON" - <<'PY'
mods = {'fastapi': 'fastapi==0.143.0', 'uvicorn': 'uvicorn[standard]==0.54.0',
        'httpx': 'httpx==0.28.1', 'pydantic': 'pydantic==2.14.0',
        'multipart': 'python-multipart==0.0.22', 'ddgs': 'ddgs==9.16.0',
        'playwright': 'playwright==1.62.0'}
import importlib.util
print(' '.join(pkg for mod, pkg in mods.items()
               if importlib.util.find_spec(mod) is None))
PY
)"
if [[ -n "$MISSING" ]]; then
  echo "installing: $MISSING"
  # shellcheck disable=SC2086
  "$PYTHON" -m pip install --quiet $MISSING
else
  echo "dependencies: complete"
fi

# --- 2. Chromium binary ----------------------------------------------------
BROWSER="$("$PYTHON" - <<'PY'
import sys
sys.path.insert(0, 'backend')
from app.harness.chromium_search import chromium_executable
print(chromium_executable())
PY
)"
if [[ -z "$BROWSER" ]]; then
  echo "installing Chromium (playwright install chromium) ..."
  "$PYTHON" -m playwright install chromium
else
  echo "chromium:   $BROWSER"
fi

# --- 3. VoiceStudio --------------------------------------------------------
# TTS is optional: a machine without VoiceStudio still has working web/video
# search through Chromium, and the backend serves TTS as an honest 503. A
# missing desktop app must not abort the whole setup under `set -e`.
if ! "$PYTHON" "$ROOT/scripts/ensure_voicestudio.py" --json; then
  echo "warning: VoiceStudio is not available; /voice/speak will return 503." >&2
  echo "         Web search and video discovery are unaffected." >&2
fi

# --- 4. backend (optional) -------------------------------------------------
if [[ "${1:-}" == "--serve" ]]; then
  echo "starting backend on http://127.0.0.1:$PORT ..."
  cd "$BACKEND"
  export HARNESS_DATA_DIR="${HARNESS_DATA_DIR:-$BACKEND/data}"
  export HARNESS_AUTO_CREATE=1
  export HARNESS_ALLOWED_HOSTS=localhost,127.0.0.1
  export HARNESS_VOICE_ENABLED=1
  export HARNESS_MEDIA_ENABLED=1
  export HARNESS_CHROMIUM_SEARCH=1
  export HARNESS_VIDEO_AUTO_CURATE=1
  exec "$PYTHON" desktop_entry.py --port "$PORT"
else
  echo
  echo "All local services are ready. Start the backend with:"
  echo "  $0 --serve"
fi
