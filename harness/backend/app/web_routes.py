"""Static web workbench + serving layer for the simulation artifact store.

Mounted by main.py with one guarded include:

    from . import web_routes
    app.include_router(web_routes.router)

This module owns every `/api/v1/sims/*` HTTP route and the static files under
`harness/web/`. It does not touch any other subsystem. Storage and validation
live in exactly one place: :mod:`app.harness.sims_store` (the same store the
sim-creation tools write through). This layer adds no storage logic of its own
-- it only translates HTTP to store calls.

Serving contract (see sims_store's module docstring):

    GET  /api/v1/sims                      -> all artifacts, newest first
    POST /api/v1/sims                      -> validate + store (teacher flow)
    GET  /api/v1/sims/{id}                 -> the store manifest entry
    GET  /api/v1/sims/{id}/raw             -> latest version, text/html
    GET  /api/v1/sims/{id}/raw?version=n   -> that specific version
    POST /api/v1/sims/{id}/frame-token     -> short-lived iframe credential
    POST /api/v1/sims/{id}/requests        -> file a change request

The student/teacher boundary is enforced twice. The UI offers students only the
four review categories, but the server decides: the role comes from the
*authenticated account* (``users.role``), never from the request payload, and
the allow/refuse decision itself is made by :func:`creation_gate.evaluate`, so
there is one decision table for both the tools and this endpoint.
"""
import base64
import hashlib
import hmac
import html as html_module
import json
import re
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from .db import Token, User, now_ts
from .harness import creation_gate, sims_store
from .resources import resource_dir
from .security import digest, rate_limit, signing_secret

router = APIRouter()

#: The static workbench, resolved through :mod:`app.resources` so the frozen bundle finds
#: ``_internal/web`` rather than looking one directory above it and serving 404s.
WEB_DIR = resource_dir('web')

#: One decision table, imported -- never redefined here, so this endpoint and
#: the creation tools cannot drift apart on what a student may file.
STUDENT_CATEGORIES = creation_gate.STUDENT_CATEGORIES
TEACHER_CATEGORIES = creation_gate.TEACHER_CATEGORIES
ALL_CATEGORIES = creation_gate.ALL_CATEGORIES

SIM_ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')

#: Manifest meta key marking an artifact as a bundled workbench seed, so seeding
#: is idempotent and the workbench always has something to preview.
SEED_META_KEY = 'web_seed'

#: The agent bridge injected into every served simulation. The iframe is
#: sandboxed with allow-scripts ONLY (no allow-same-origin: that combination
#: lets sim script reach the workbench's sessionStorage — the escape
#: orch-verify-2 demonstrated), so the sim cannot be inspected from the parent
#: and cannot talk to it directly. This script, injected at serve time, is the
#: sim's one outbound channel: hover/selection postMessages. Store bytes stay
#: canonical — injection happens on the way out, never in the version history.
AGENT_SCRIPT_TAG = '<script src="/web/luminfest-agent.js" data-luminfest-agent="1"></script>'


def inject_agent_script(html: str) -> str:
    """Serve-time injection of the agent bridge. Idempotent: an artifact that
    already includes the bridge (or any script referencing it) is unchanged."""
    if 'luminfest-agent.js' in html:
        return html
    marker = html.lower().rfind('</body>')
    if marker == -1:
        return html + AGENT_SCRIPT_TAG
    return html[:marker] + AGENT_SCRIPT_TAG + html[marker:]

#: MIME types the static file route may serve. Everything else is a download.
CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
    '.json': 'application/json; charset=utf-8',
    '.md': 'text/markdown; charset=utf-8',
}


def principal(request: Request, *, required: bool = False) -> dict:
    """Resolve the authenticated account for a request.

    Bearer tokens are validated exactly like the rest of the API (Token digest
    lookup). Anonymous access is a development convenience only; production
    requires the session token. No new auth scheme is introduced.

    Returns ``{'user_id': str, 'account_role': str}`` where ``account_role`` is
    the *server-side* role from ``users.role`` (``learner``/``teacher``/...),
    or ``''`` for an anonymous development request.
    """
    settings = request.app.state.settings
    factory = getattr(request.app.state, 'factory', None)
    header = request.headers.get('authorization', '')
    if header.startswith('Bearer ') and len(header) <= 200:
        if factory is None:
            raise HTTPException(401, 'Valid bearer token required', headers={'WWW-Authenticate': 'Bearer'})
        raw = header[7:]
        rate_limit(factory, 'web:' + digest(raw), 240)
        with factory() as db:
            token = db.get(Token, digest(raw))
            if not token or token.expires_at <= now_ts() or token.revoked_at is not None:
                raise HTTPException(401, 'Invalid or expired token')
            user = db.get(User, token.user_id)
            if not user or getattr(user, 'status', 'active') != 'active':
                raise HTTPException(401, 'Account unavailable')
            return {'user_id': token.user_id, 'account_role': str(getattr(user, 'role', '') or '')}
    if settings.environment == 'production' or required:
        raise HTTPException(401, 'Valid bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    return {'user_id': 'anonymous', 'account_role': ''}


def server_role(info: dict) -> str:
    """The role this request acts with. Fail closed: only the canonical
    ``'teacher'`` account role grants the teacher path; every other value
    (learner, staff, admin, anonymous) decides as a student. A client-supplied
    role field is never consulted."""
    return 'teacher' if info.get('account_role') == 'teacher' else 'student'


# ------------------------------------------------------- simulation frames
#
# A simulation is displayed in a sandboxed iframe, and an iframe navigation cannot
# carry the workbench's ``Authorization`` header: only ``src`` travels. Fetching the
# HTML by hand and injecting it would mean re-implementing the browser's document
# lifecycle, so the frame needs *some* credential in its URL.
#
# Putting the session bearer there is the wrong credential: it is long-lived and
# account-wide, and a URL ends up in history, in proxy logs and in any referrer the
# simulation emits. So the client exchanges its bearer for a token that is signed,
# scoped to one simulation, read-only, and valid for two minutes. ``sim_raw``
# accepts exactly that token as an alternative to the bearer - never a token for a
# different artifact.

FRAME_TOKEN_TTL_SECONDS = 120
FRAME_TOKEN_MAX_TTL_SECONDS = 600

#: Used only when no ``HARNESS_SECRET`` is configured *and* the app has no session
#: factory (a bare development app). A random value per process is honest there:
#: the token then validates only inside that process, which is exactly as durable
#: as the rest of that app's in-memory state.
_PROCESS_FRAME_KEY = secrets.token_urlsafe(48)


def _frame_key(request: Request) -> bytes:
    """The HMAC key for frame tokens.

    ``HARNESS_SECRET`` when configured, so every worker agrees; otherwise the
    signing secret the receipt machinery already persists in the database; and
    only as a last resort a per-process random value.
    """
    settings = request.app.state.settings
    configured = getattr(settings, 'secret', '') or ''
    if configured:
        return configured.encode()
    factory = getattr(request.app.state, 'factory', None)
    if factory is None:
        return _PROCESS_FRAME_KEY.encode()
    with factory() as db:
        return signing_secret(db, None).encode()


def issue_frame_token(request: Request, sim_id: str,
                      ttl: int = FRAME_TOKEN_TTL_SECONDS) -> tuple[str, int]:
    """A signed ``(token, ttl)`` pair for one simulation."""
    ttl = max(1, min(int(ttl), FRAME_TOKEN_MAX_TTL_SECONDS))
    payload = base64.urlsafe_b64encode(
        json.dumps({'sim': sim_id, 'exp': int(time.time()) + ttl},
                   separators=(',', ':')).encode()).rstrip(b'=').decode()
    signature = hmac.new(_frame_key(request), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature, ttl


def verify_frame_token(request: Request, raw: str) -> dict | None:
    """The claim inside a frame token, or ``None`` if it is forged or expired."""
    payload, _, signature = (raw or '').partition('.')
    if not payload or not signature:
        return None
    expected = hmac.new(_frame_key(request), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or int(data.get('exp', 0)) < int(time.time()):
        return None
    return data



# ---------------------------------------------------------------- seed sims

def seed_sims(settings) -> None:
    """Copy bundled seed simulations into the artifact store on first use, and
    add a new store version when the bundled file has changed (an improving
    seed ships as v+1 — never a silent overwrite of stored bytes).

    Seeding goes through the same store (and therefore the same validator) as
    the creation tools; a bundled file that failed validation would be skipped
    rather than served unvalidated. Idempotent via the manifest meta marker.
    """
    source = WEB_DIR / 'sims'
    if not source.is_dir():
        return
    seeds = {e.get('meta', {}).get(SEED_META_KEY): e
             for e in sims_store.list_artifacts(settings)
             if e.get('meta', {}).get(SEED_META_KEY)}
    for html_path in sorted(source.glob('*.html')):
        text = html_path.read_text(encoding='utf-8')
        if sims_store.validate_html(text, kind='simulation'):
            continue  # never serve a bundled file the validator would refuse
        existing = seeds.get(html_path.stem)
        if existing is None:
            sims_store.create_artifact(settings, kind='simulation',
                                       title=title_from_html(html_path), html=text,
                                       meta={SEED_META_KEY: html_path.stem})
        elif sims_store.read_version(settings, existing['id']) != text:
            sims_store.save_version(settings, existing['id'], text, note='workbench seed updated')


def title_from_html(html_path: Path) -> str:
    text = html_path.read_text(encoding='utf-8')
    match = re.search(r'<title>([^<]{1,120})</title>', text)
    return html_module.unescape(match.group(1).strip()) if match else html_path.stem


def _request_count(settings, sim_id: str) -> int:
    path = sims_store.store_root(settings) / f'{sim_id}.requests.jsonl'
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding='utf-8').splitlines() if line.strip())


# ---------------------------------------------------------------- static app

@router.get('/', include_in_schema=False)
def workbench_index():
    index = WEB_DIR / 'index.html'
    if not index.exists():
        raise HTTPException(404, 'Workbench not built; expected harness/web/index.html')
    return FileResponse(index, media_type='text/html; charset=utf-8')


@router.get('/web/{asset_path:path}', include_in_schema=False)
def workbench_asset(asset_path: str):
    web_root = str(WEB_DIR.resolve())
    target = (WEB_DIR / asset_path).resolve()
    if not str(target).startswith(web_root + '/') or not target.is_file():
        raise HTTPException(404, 'Not found')
    media = CONTENT_TYPES.get(target.suffix.lower())
    if media is None:
        raise HTTPException(415, 'Unsupported asset type')
    return FileResponse(target, media_type=media)


# ------------------------------------------------------------ sim endpoints

@router.get('/api/v1/sims')
def list_sims(request: Request):
    info = principal(request)
    seed_sims(request.app.state.settings)
    rows = sims_store.list_artifacts(request.app.state.settings)
    for row in rows:
        row['requests'] = _request_count(request.app.state.settings, row['id'])
    return {'sims': rows}


@router.post('/api/v1/sims', status_code=201)
def save_sim(request: Request, payload: dict):
    """Validate and store an artifact (create), or validate and add a version
    to an existing one. The store's validator is the only gatekeeper here: a
    document that fails validation is refused with its problems and stored
    nowhere. Modification with a declared non-teacher account is refused."""
    info = principal(request)
    settings = request.app.state.settings
    html = payload.get('html') or ''
    title = str(payload.get('title') or 'Untitled simulation')[:120]

    problems = sims_store.validate_html(html, kind='simulation')
    if problems:
        raise HTTPException(422, {'message': 'The artifact was not stored; it failed validation.',
                                  'problems': problems})
    if info['account_role'] and server_role(info) != 'teacher':
        raise HTTPException(403, 'Creating or restructuring simulations belongs to your teacher.')

    sim_id = str(payload.get('id') or '').strip()
    if sim_id:
        if not SIM_ID_RE.match(sim_id):
            raise HTTPException(422, 'Simulation id must match [a-z0-9][a-z0-9-]{0,63}')
        if sims_store.load(settings, sim_id) is None:
            raise HTTPException(404, 'Simulation not found')
        entry = sims_store.save_version(settings, sim_id, html, note='web edit')
    else:
        entry = sims_store.create_artifact(settings, kind='simulation', title=title, html=html)
    return entry


@router.get('/api/v1/sims/{sim_id}')
def sim_meta(sim_id: str, request: Request):
    principal(request)
    entry = sims_store.load(request.app.state.settings, sim_id)
    if entry is None:
        raise HTTPException(404, 'Simulation not found')
    entry = dict(entry)
    entry['requests'] = _request_count(request.app.state.settings, sim_id)
    entry['version'] = entry['latest_version']  # convenience alias for clients
    return entry


@router.get('/api/v1/role')
def acting_role(request: Request):
    """The role every gated endpoint will use for this session's requests.

    The workbench used to offer a local Student/Teacher switch, so a student could
    select Teacher, see the teacher-only panels, and then have each request refused by
    the server. The switch was never the source of truth: :func:`server_role` decides
    from the authenticated account. This route publishes that decision -- the same
    function the gated endpoints call -- so the client can show the teacher controls
    only where they would actually be honoured.
    """
    info = principal(request)
    return {
        'role': server_role(info),
        'account_role': info.get('account_role', ''),
        'authenticated': info.get('user_id') not in (None, '', 'anonymous'),
        'note': ('The role is decided server-side from the account, not by a client '
                 'toggle. This is what this session will be held to.'),
    }


@router.post('/api/v1/sims/{sim_id}/frame-token')
def sim_frame_token(sim_id: str, request: Request):
    """Exchange the session bearer for a credential the iframe can carry.

    The response URL is what the workbench assigns to ``frame.src``. The token is
    read-only, scoped to this one simulation, and short-lived; it names no account,
    so a leaked URL cannot be replayed against any other route.
    """
    principal(request)
    if not SIM_ID_RE.match(sim_id):
        raise HTTPException(422, 'Simulation id must match [a-z0-9][a-z0-9-]{0,63}')
    if sims_store.load(request.app.state.settings, sim_id) is None:
        raise HTTPException(404, 'Simulation not found')
    token, ttl = issue_frame_token(request, sim_id)
    return {
        'token': token,
        'expires_in': ttl,
        'url': f'/api/v1/sims/{sim_id}/raw?frame_token={token}',
        'note': ('Read-only and scoped to this simulation, valid for seconds. '
                 'It carries no account identity.'),
    }


@router.get('/api/v1/sims/{sim_id}/raw', response_class=HTMLResponse)
def sim_raw(sim_id: str, request: Request):
    settings = request.app.state.settings
    frame_token = request.query_params.get('frame_token') or ''
    if frame_token:
        # A frame token authorises exactly one artifact. A token minted for a
        # different sim is refused even though its signature is valid, so the
        # credential cannot be walked sideways across artifacts.
        claim = verify_frame_token(request, frame_token)
        if claim is None or claim.get('sim') != sim_id:
            raise HTTPException(401, 'Invalid or expired frame token')
    else:
        principal(request)
    version = request.query_params.get('version')
    if version is not None:
        try:
            version = int(version)
        except ValueError:
            raise HTTPException(422, 'version must be an integer')
    html = sims_store.read_version(settings, sim_id, version)
    if html is None:
        raise HTTPException(404, 'Simulation not found' if version is None
                            else f'Simulation version {version} not found')
    return HTMLResponse(inject_agent_script(html))


#: The file names an artifact may expose for download. The deck builder writes its
#: ``.pptx`` twin beside the HTML as ``v<N>.pptx``; nothing else in the artifact directory
#: is downloadable, so a crafted name cannot turn this route into a filesystem browser.
ARTIFACT_FILE_RE = re.compile(r'^v\d{1,4}\.pptx$')

PPTX_MEDIA_TYPE = ('application/vnd.openxmlformats-officedocument'
                   '.presentationml.presentation')


@router.get('/api/v1/sims/{sim_id}/download/{name}')
def sim_download(sim_id: str, name: str, request: Request):
    """One generated file from an artifact's own directory, by exact name.

    The deck builder writes a ``.pptx`` twin next to the HTML and records its name in the
    manifest. Without this route that record was a dangling reference - a manifest
    promising a file no client could fetch, which is worse than not producing it, because
    a client has no way to tell the difference between "not built" and "built but
    unreachable". The name is matched against a pattern rather than sanitised, so there is
    no traversal to get wrong, and the resolved path is checked to sit inside the
    artifact's own directory as a second, independent guard.
    """
    principal(request)
    settings = request.app.state.settings
    if not SIM_ID_RE.match(sim_id) or not ARTIFACT_FILE_RE.match(name):
        raise HTTPException(404, 'No such file')
    if sims_store.load(settings, sim_id) is None:
        raise HTTPException(404, 'Simulation not found')
    directory = (sims_store.store_root(settings) / sim_id).resolve()
    target = (directory / name).resolve()
    if not target.is_relative_to(directory) or not target.is_file():
        raise HTTPException(404, 'No such file')
    return FileResponse(target, media_type=PPTX_MEDIA_TYPE, filename=f'{sim_id}.pptx')


@router.post('/api/v1/sims/{sim_id}/requests', status_code=201)
def file_change_request(sim_id: str, request: Request, payload: dict):
    """File a change request against a simulation.

    The acting role is derived server-side from the authenticated account; a
    ``role`` field in the payload is ignored (recorded only as a declaration,
    for the alpha's audit trail). The allow/refuse decision belongs to
    :func:`creation_gate.evaluate` -- the same gate the creation tools answer
    to -- so a student's `create`/`restructure` request is refused with the
    reason that names the four categories they can file instead.
    """
    info = principal(request)
    settings = request.app.state.settings
    entry = sims_store.load(settings, sim_id)
    if entry is None:
        raise HTTPException(404, 'Simulation not found')

    role = server_role(info)
    declared_role = str(payload.get('role') or '').strip().casefold()
    category = str(payload.get('category') or '').strip().casefold()
    note = ' '.join(str(payload.get('note') or '').split())[:2000]
    selection = payload.get('selection') if isinstance(payload.get('selection'), dict) else None

    decision = creation_gate.evaluate(
        {'role': role, 'category': category, 'note': note,
         'selection': json.dumps(selection, ensure_ascii=False) if selection else '',
         'approval_id': payload.get('approval_id')},
        approvals=creation_gate.load_approvals(settings))
    if not decision['approved']:
        status = 403 if category in TEACHER_CATEGORIES else 422
        raise HTTPException(status, decision['reason'])

    record = {
        'id': f'{sim_id}-{int(time.time() * 1000)}',
        'sim_id': sim_id,
        'sim_version': entry['latest_version'],
        'category': decision['category'],
        'role': decision['role'],
        'declared_role': declared_role or None,
        'user_id': info['user_id'],
        'note': decision['note'],
        'selection': selection,
        'requirement': decision['requirement'],
        'gate_notes': decision['notes'],
        'created_at': int(time.time()),
    }
    path = sims_store.store_root(settings) / f'{sim_id}.requests.jsonl'
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    return record
