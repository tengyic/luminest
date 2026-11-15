# Operator setup — backend, LLM provider, alpha-free flag

The native app talks to a backend running **on this machine** (loopback, ports
`127.0.0.1:8765–8785`). Stand it up before launching the app.

## 1. Backend

```sh
cd harness/backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:create_app --factory
# → http://127.0.0.1:8000  (health: GET /api/v1/health)
```

For a desktop-style single-user launch you can also run `python desktop_entry.py --port 8877`.

## 2. LLM provider (required for tutor / course creation)

The instance boots without a provider but the tutor and course-building are
**grounded-only** until one is configured. Pick one:

**OpenAI-compatible (remote):**
```sh
HARNESS_TUTOR_PROVIDER=openai
HARNESS_TUTOR_URL=https://your-endpoint/v1
HARNESS_TUTOR_MODEL=your-model
HARNESS_TUTOR_KEY=sk-...        # production requires HTTPS for remote hosts
```

**Local Ollama (loopback, exempt from the HTTPS rule):**
```sh
HARNESS_TUTOR_PROVIDER=ollama
HARNESS_TUTOR_URL=http://ollama:11434
HARNESS_TUTOR_MODEL=<pulled model>
```

## 3. Alpha-free capability flag (recommended for the cohort)

Make every **Plus** capability free for all alpha accounts so the UI matches what actually
works — no route enforces the paid tier yet:

```sh
HARNESS_ALPHA_FREE=1
```

Without it, the capabilities endpoint reports `images` / `video` / `course_creation` as
"withheld" even though the routes are open — that is the doc/behaviour mismatch this flag
removes. **Flip it OFF before any paid launch** so the withhold paths re-arm.

## 4. Optional — duplex voice (OpenAI Realtime)

Server-side key (optional; the native client can also hold its own key in the Keychain):
```sh
HARNESS_REALTIME_KEY=sk-...
```
In the app: **Settings ▸ "Duplex voice (OpenAI Realtime)" ▸ paste the key** — stored in
Keychain, never written to disk or returned by any route.

## 5. Optional — spoken lessons (TTS)

A local **VoiceStudio** backend on `127.0.0.1:3900` enables server-side TTS with no key and
no off-machine text. Start VoiceStudio; the app discovers it. No config beyond the default
`HARNESS_VOICE_BASE_URL` is needed.
