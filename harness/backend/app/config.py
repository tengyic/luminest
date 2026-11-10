import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


from .security import ACCESS_TTL_SECONDS


def legal_dir():
    """Where the legal documents live; overridable so tests can stage a bundle."""
    return Path(os.getenv('HARNESS_LEGAL_DIR', str(Path(__file__).resolve().parents[1] / 'legal')))


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """A minimal, dependency-free ``.env`` reader. Real environment variables always win.

    Reads ``backend/.env`` (``KEY=VALUE`` lines, ``#`` comments, optional quotes) and
    fills in only the variables the process environment does not already set. Two
    provider aliases are applied for operator convenience: ``DEEPSEEK_API_KEY`` and
    ``DEEPSEEK_BASE_URL`` map onto ``HARNESS_TUTOR_KEY`` and ``HARNESS_TUTOR_URL`` when
    those are unset. Setting ``HARNESS_TUTOR_PROVIDER`` is always an explicit operator
    decision, so no alias ever turns the model on by itself.

    To point the tutor at DeepSeek, an operator sets::

        HARNESS_TUTOR_PROVIDER=openai
        HARNESS_TUTOR_URL=https://api.deepseek.com/v1
        HARNESS_TUTOR_MODEL=deepseek-v4-pro        # or deepseek-flash
        HARNESS_TUTOR_KEY=...                      # or DEEPSEEK_API_KEY in backend/.env

    and can raise ``HARNESS_TUTOR_TIMEOUT_SECONDS`` (up to 300) for long agentic
    generations; the default of 12 s suits short completions only.
    """
    path = path or Path(__file__).resolve().parents[1] / '.env'
    loaded: dict[str, str] = {}
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return loaded
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key, _, value = stripped.partition('=')
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if not key:
            continue
        loaded[key] = value
        if key not in os.environ:
            os.environ[key] = value
    for source, target in (('DEEPSEEK_API_KEY', 'HARNESS_TUTOR_KEY'),
                           ('DEEPSEEK_BASE_URL', 'HARNESS_TUTOR_URL')):
        if loaded.get(source) and not os.environ.get(target):
            os.environ[target] = loaded[source]
    return loaded


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    environment: str
    secret: str
    token_ttl: int
    receipt_ttl: int
    provider: str
    provider_url: str
    provider_key: str
    provider_model: str
    provider_timeout: float
    allowed_hosts: tuple[str, ...]
    auto_create: bool
    # ASSUMPTION, deliberately unchanged: 0.7 is a product hypothesis about a
    # comfortable practice success rate, not an evidence-based optimum for human
    # learners. Do not cite Wilson et al. 2019 (the "85% rule", Nature Communications)
    # in its defence: that paper derives an optimal accuracy for *gradient-based
    # classifier training*, and its own discussion warns against generalising it to
    # human learning. The number is env-tunable here and A/B-tunable through the
    # m4_target_correctness experiment (app/experiments.py), which is how evidence
    # for or against any value would actually be produced.
    target_correctness: float = 0.7
    #: Whether signup must confirm 13+ and acceptance of the Terms. On in production,
    #: off in development and test so a local instance needs no ceremony.
    require_launch_gate: bool = False
    #: Whether a Beta invite code is required to register. On in production.
    require_invite: bool = False
    #: Version stamped on a terms acceptance, so the record says which text was agreed to.
    terms_version: str = '2026-11'
    #: Access tokens are short by design: one hour, matching ``security.ACCESS_TTL_SECONDS``.
    #: The refresh token carries the long session and is single-use with rotation, so a
    #: leaked access token is worth at most an hour. The shipped default was 604800 s
    #: (seven days) until the security audit found the two defaults disagreed -- a week-long
    #: bearer token in a hosted Beta is exactly what refresh rotation exists to avoid.
    access_token_ttl: int = 3600
    refresh_token_ttl: int = 5184000
    #: Whether this instance may fetch media from the open image and video APIs. Off in
    #: production unless an operator turns it on, because it is the only outbound network
    #: call the application makes on a learner's behalf and it should be a decision.
    #: **On in the shipped desktop build** (``HARNESS_ENV=desktop``), which is what
    #: ``legal/privacy.md`` discloses to the user and what ``legal/FILL_IN_SHEET.md``
    #: records. The dataclass default below is the fail-closed value; ``from_env`` decides.
    media_enabled: bool = False
    #: Timeout for a media search or download. Short on purpose: a slow image API must not
    #: hold a lesson.
    media_timeout: float = 12.0
    #: Where cached images live. Defaults to the data directory so export and delete,
    #: which already cover the data directory, also cover downloaded media.
    media_cache_dir: str = ''
    #: Who to contact about this instance's media requests, as it appears in the HTTP
    #: ``User-Agent``. Wikimedia's API policy refuses (403) any agent whose UA carries no
    #: contact route, and a refused UA takes the largest cacheable photo collection in the
    #: world offline - the failure looks identical to "no such photograph exists". Empty
    #: means unset; the placeholder that is sent instead is reported in the search notes so
    #: an operator finds out from the product, not from a silent 403.
    media_contact: str = ''
    #: Whether this instance is a paid offering. Non-commercial licences (Khan Academy,
    #: PhET, MIT OCW) are decided by the *use*, so a product that charges has to lose those
    #: sources - and it loses them by evaluation here rather than by somebody remembering.
    commercial_use: bool = False
    #: Optional. When set, video embeddability is checked against the YouTube Data API's
    #: authoritative ``status.embeddable`` field instead of the keyless oEmbed probe.
    youtube_api_key: str = ''
    #: Optional Openverse credentials. Unauthenticated Openverse is capped by its own
    #: documentation at 20 requests/minute and 200/day; registering lifts this to 10,000/day.
    openverse_client_id: str = ''
    openverse_client_secret: str = ''
    #: Operator-level kill switch for the P-3 self-explanation gate. Default off:
    #: flipping it on changes the submit contract for every client at once, which is
    #: exactly what the experiment layer exists to test gradually. An experiment
    #: assignment (p3_self_explanation_gate=on) also turns it on, per user.
    self_explanation_gate: bool = False
    #: Whether the tutor's browser_snapshot tool may launch the Playwright browser.
    #: Off by default: a headless browser fetching arbitrary URLs is an outbound-network
    #: and cost decision, and the same fail-close logic as media_enabled applies.
    browser_enabled: bool = False
    #: Operator comps for the capability matrix (app/capabilities.py), as
    #: comma-separated ``selector:capability,capability`` entries. The selector is an
    #: email address or ``*``. This is the no-store path to a paid capability: staff,
    #: testers and press accounts get Plus without a payment provider existing. It is
    #: a setting, recorded next to the prices in docs/multimodality.md, not a backdoor
    #: -- the grant it produces is a normal entitlement row with source='operator'.
    entitlements: tuple[str, ...] = ()
    #: The metered ceiling a paid grant installs on the account (QuotaPolicy, monthly,
    #: soft enforcement). Deliberately generous defaults: during the Beta the counter
    #: observes and reports, and an operator who wants a hard ceiling raises it in
    #: quota_policies, not by editing this default.
    paid_monthly_requests: int = 2000
    paid_monthly_tokens: int = 2_000_000
    #: Where the local VoiceStudio backend listens. Text to speech talks to
    #: ``POST {base}/v1/audio/speech`` there, so the audio path is loopback rather
    #: than an outbound call carrying learner text to a third party. The default is
    #: a stock VoiceStudio install; it is a setting because the port is not fixed by
    #: the provider and an operator may front it with a proxy.
    voice_base_url: str = 'http://127.0.0.1:3900'
    #: VoiceStudio engine id. 'omnivoice' is its default engine; other installed
    #: engines ('cosyvoice', 'mlx-audio', ...) are selectable here.
    voice_model: str = 'omnivoice'
    #: VoiceStudio voice-profile name or id. 'default' means the engine default.
    voice_name: str = 'default'
    #: Optional. VoiceStudio does not check a key itself; this is sent as a bearer
    #: token so an authenticating proxy in front of it keeps working.
    voice_api_key: str = ''
    #: Synthesis timeout. Long on purpose: a cold model on CPU can take a minute for
    #: a paragraph, and the 12 s media timeout would abort a healthy synthesis.
    voice_timeout: float = 120.0
    #: Default style instruction ("tone") for every synthesis. Sent as the
    #: OpenAI ``instructions`` field, which VoiceStudio forwards to the engine as
    #: its ``instruct``. What an engine can honour varies: freeform-instruction
    #: engines take the sentence as written, while the OmniVoice family only
    #: accepts speaker-design tags (gender/age/pitch/accent/dialect) and drops
    #: prose -- ``voice.py`` reports that reduction instead of pretending it
    #: worked. Empty means "send nothing", which is what a stock install wants.
    voice_instruct: str = ''
    #: Whether this instance may produce speech at all. Deliberately *not* ``media_enabled``.
    #:
    #: Speech was gated on ``media_enabled``, on the theory that both are "audio/media". That
    #: made the shipped desktop app mute: the two were treated as one switch, so whatever the
    #: desktop profile did to media took the tutor's voice with it --
    #: ``speech.plan`` answered ``unavailable`` for every reply, so the speaker button did
    #: nothing and the reason was only visible if a learner went looking for it.
    #:
    #: The two are not the same decision. ``media_enabled`` governs *outbound network* fetches
    #: from third-party image and video APIs; synthesis here is a loopback call to a VoiceStudio
    #: the learner is already running, and the text never leaves the machine. Turning off the
    #: network promise therefore says nothing about whether a local engine may speak. On by
    #: default wherever a local engine is expected; off in production, where a hosted instance
    #: must not assume one exists (it fails closed and names this switch).
    voice_enabled: bool = True
    #: Whether the on-task reading (``app/harness/attention.py``) exists on this
    #: instance. On by default outside production, because the telemetry path needs no
    #: camera and no model and is the honest way to answer "is the learner working"; off
    #: in production until an operator decides that monitoring learners is something this
    #: deployment does. Off means the tool refuses and names this switch -- never a
    #: silent no-op that a client could mistake for "on task".
    attention_monitor: bool = False
    #: OpenAI Realtime API (voice-to-voice / duplex) configuration. The key is optional
    #: server-side: the native macOS client may hold its own key in the Keychain and connect
    #: directly to ``wss://api.openai.com/v1/realtime``, in which case this stays empty and the
    #: backend only advertises whether duplex voice is available. When set, a future server
    #: proxy can mint ephemeral tokens; the key is never logged and never returned by any route.
    realtime_provider: str = 'openai'
    realtime_key: str = ''
    realtime_model: str = 'gpt-4o-realtime-preview-2024-12-17'
    #: Whether this instance will present the app's own window to a browser
    #: (``app.harness.screen``, ``/app``, ``/api/v1/stream``). Off by default and off in
    #: every environment unless an operator turns it on, because it is the one capability
    #: that captures the host's screen and can post input to it. It is also the one
    #: capability whose usefulness depends on a macOS permission granted per binary by a
    #: human, so "off" is the only safe default: an instance that has not been asked for
    #: this must never begin capturing.
    stream_enabled: bool = False
    #: A real headless Chromium may serve web/video search when the ``ddgs`` package
    #: is absent or its SERP endpoint refuses the request. ``playwright`` + a downloaded
    #: Chromium are required; :func:`app.harness.chromium_search.available` decides at
    #: runtime, so switching this on in a build without the browser still degrades to
    #: the original honest refusal. Off on a bare ``Settings(...)`` so unit tests never
    #: reach the network; ``from_env`` turns it on for development/desktop.
    chromium_search_enabled: bool = False
    #: A concept with no curated video may be curated on demand by the teacher's
    #: curation job the first time a lesson asks for it. Every candidate still passes
    #: the title-relevance, neighbour, trusted-source and oEmbed-embeddability gates
    #: before it is written to the same allowlist a human curator writes. A failed
    #: attempt is remembered for 24h so an offline instance does not launch a browser
    #: on every request. Off on a bare ``Settings(...)`` for the same test reason.
    video_auto_curate: bool = False

    @classmethod
    def from_env(cls):
        load_dotenv()
        environment = os.getenv('HARNESS_ENV', 'development')
        data_dir = Path(os.getenv('HARNESS_DATA_DIR', str(Path(__file__).resolve().parents[1] / '.data')))
        url = os.getenv('HARNESS_DATABASE_URL', f'sqlite:///{data_dir / "harness.sqlite3"}')
        if url.startswith('postgres://'):
            url = 'postgresql+psycopg://' + url[len('postgres://'):]
        elif url.startswith('postgresql://'):
            url = 'postgresql+psycopg://' + url[len('postgresql://'):]
        secret = os.getenv('HARNESS_SECRET', '')
        hosts = tuple(x.strip() for x in os.getenv('HARNESS_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',') if x.strip())
        if environment not in {'development', 'test', 'production', 'desktop'}:
            raise ValueError('HARNESS_ENV must be development, test, production or desktop')
        if environment == 'production':
            if not url.startswith('postgresql+psycopg://'):
                raise ValueError('Production requires PostgreSQL')
            if len(secret) < 32 or len(set(secret)) < 12:
                raise ValueError('Production requires a strong HARNESS_SECRET (at least 32 characters)')
            if not os.getenv('HARNESS_ALLOWED_HOSTS') or '*' in hosts:
                raise ValueError('Production requires explicit HARNESS_ALLOWED_HOSTS')
            # Legal shippability (audit finding L-1): a production instance must not serve
            # legal documents that still contain template placeholders. See
            # app.legal_guard and backend/legal/FILL_IN_SHEET.md.
            if os.getenv('HARNESS_LEGAL_TEMPLATE_OK', '') != '1':
                from .legal_guard import assert_shippable
                assert_shippable(legal_dir())
        # The product requires a language model. The old 'offline' (deterministic
        # rules-engine) mode is removed: it is rejected outright, because a formal product
        # must not let customers slip into the degraded no-model experience. An *unconfigured*
        # instance (no provider set) boots degraded and refuses generative work until an
        # operator configures one through HARNESS_TUTOR_* or the runtime settings API.
        # Production refuses to boot without a provider; dev/test/desktop boot and surface
        # the unconfigured state so it can be filled in.
        provider = os.getenv('HARNESS_TUTOR_PROVIDER', '').strip()
        if provider == 'offline':
            raise ValueError('HARNESS_TUTOR_PROVIDER=offline is no longer supported; '
                             'configure a language model (openai or ollama) instead.')
        if provider and provider not in {'ollama', 'openai'}:
            raise ValueError('Unsupported tutor provider; must be openai or ollama.')
        provider_url = os.getenv('HARNESS_TUTOR_URL', '').strip()
        if provider:
            parsed = urlparse(provider_url)
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username:
                raise ValueError('External tutor requires a valid administrator-configured HARNESS_TUTOR_URL')
            if environment == 'production' and parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1', '::1', 'ollama'}:
                raise ValueError('Remote production tutor requires HTTPS')
            if not os.getenv('HARNESS_TUTOR_MODEL', '').strip():
                raise ValueError('External tutor requires HARNESS_TUTOR_MODEL')
        elif environment == 'production':
            raise ValueError('Production requires a configured language model '
                             '(set HARNESS_TUTOR_PROVIDER to openai or ollama).')
        token_ttl = int(os.getenv('HARNESS_TOKEN_TTL_SECONDS', '604800'))
        receipt_ttl = int(os.getenv('HARNESS_RECEIPT_TTL_SECONDS', '3600'))
        timeout = float(os.getenv('HARNESS_TUTOR_TIMEOUT_SECONDS', '12'))
        # Capped at 300 s: agentic tool-calling turns against a reasoning model can run
        # for minutes, while the old 60 s ceiling silently made that impossible. The
        # default is still 12 s, so a misconfigured provider fails a short request, not
        # a hung learner session.
        if not 60 <= token_ttl <= 2592000 or not 30 <= receipt_ttl <= 7200 or not 0 < timeout <= 300:
            raise ValueError('Invalid token/receipt lifetime or tutor timeout (max 300 s)')
        target = float(os.getenv('HARNESS_TARGET_CORRECTNESS', '0.7'))
        if not 0.05 <= target <= 0.95:
            raise ValueError('HARNESS_TARGET_CORRECTNESS must be between 0.05 and 0.95')
        # ``desktop`` is the shipped macOS bundle: a single-user instance on the learner's
        # own machine. It is production-strict about *consent* - the 13+ attestation and
        # Terms acceptance are on - while staying SQLite, because demanding PostgreSQL and
        # a 32-character secret would simply refuse to boot the app a user just launched.
        # It was introduced because the bundle used to ship as ``development``, where
        # ``gate_default`` was '0' and ``media_default`` was '1': no age gate at all, and
        # attention monitoring plus four undisclosed outbound media providers switched on
        # while privacy.md told the user the activity signal was "off by default".
        gate_default = '1' if environment in {'production', 'desktop'} else '0'
        # The invite code is a *hosted* Beta control. A desktop learner installed the app
        # themselves, so it must not share the gate's default: reusing ``gate_default``
        # here would make the shipped bundle demand an invite code and refuse the very
        # registration the gate exists to accompany.
        invite_default = '1' if environment == 'production' else '0'
        # The access token keeps the audit-mandated one-hour default; an operator may
        # lengthen it explicitly for a local single-user instance, but the two default
        # sites (this one and ``security.ACCESS_TTL_SECONDS``) must agree, and a test
        # asserts that they do. A hosted deployment relies on refresh-token rotation.
        access_ttl = int(os.getenv('HARNESS_ACCESS_TOKEN_TTL_SECONDS', str(ACCESS_TTL_SECONDS)))
        refresh_ttl = int(os.getenv('HARNESS_REFRESH_TOKEN_TTL_SECONDS', '5184000'))
        if not 300 <= access_ttl <= 2592000 or not access_ttl <= refresh_ttl <= 31536000:
            raise ValueError('Invalid access/refresh token lifetime')
        media_timeout = float(os.getenv('HARNESS_MEDIA_TIMEOUT_SECONDS', '12'))
        if not 1 <= media_timeout <= 60:
            raise ValueError('HARNESS_MEDIA_TIMEOUT_SECONDS must be between 1 and 60')
        # VoiceStudio is reached over loopback, so no HTTPS requirement: a local
        # plain-HTTP service is the normal deployment. A URL with embedded
        # credentials is rejected for the same reason HARNESS_TUTOR_URL rejects one
        # -- it would end up in a log line.
        voice_base_url = os.getenv('HARNESS_VOICE_BASE_URL', 'http://127.0.0.1:3900').strip()
        parsed_voice = urlparse(voice_base_url)
        if parsed_voice.scheme not in {'http', 'https'} or not parsed_voice.hostname:
            raise ValueError('HARNESS_VOICE_BASE_URL must be an http(s) URL with a host')
        if parsed_voice.username:
            raise ValueError('HARNESS_VOICE_BASE_URL must not embed credentials; '
                             'use HARNESS_VOICE_API_KEY')
        voice_timeout = float(os.getenv('HARNESS_VOICE_TIMEOUT_SECONDS', '120'))
        if not 5 <= voice_timeout <= 600:
            raise ValueError('HARNESS_VOICE_TIMEOUT_SECONDS must be between 5 and 600')
        # Off in production unless explicitly enabled: an unnoticed outbound call from a
        # hosted instance is a privacy and cost decision nobody made. On for the desktop
        # (and development/test) builds: the learner explicitly asked for live image and
        # video search, and the local privacy notice names the four image providers plus
        # YouTube. Production stays opt-in so a hosted operator still makes that call.
        media_default = '1' if environment in {'development', 'test', 'desktop'} else '0'
        # Activity tracking is a separate promise and stays off on desktop even when
        # outbound media search is on.
        attention_default = '1' if environment in {'development', 'test'} else '0'
        # Speech is a separate switch with a separate default, because it is a separate
        # promise. ``media_enabled`` is about third-party network fetches, on in the desktop
        # build and off in production; synthesis is loopback to the learner's own VoiceStudio
        # and carries no learner text off the machine, so the desktop bundle turns it *on*.
        # Production stays off: a hosted instance that silently assumed a local engine would
        # be advertising a capability it does not have.
        voice_default = '1' if environment in {'development', 'test', 'desktop'} else '0'
        return cls(url, data_dir, environment, secret,
                   token_ttl, receipt_ttl,
                   provider, provider_url, os.getenv('HARNESS_TUTOR_KEY', ''),
                   os.getenv('HARNESS_TUTOR_MODEL', ''),
                   timeout,
                   hosts, os.getenv('HARNESS_AUTO_CREATE', '1' if environment != 'production' else '0') == '1', target,
                   os.getenv('HARNESS_REQUIRE_LAUNCH_GATE', gate_default) == '1',
                   os.getenv('HARNESS_REQUIRE_INVITE', invite_default) == '1',
                   os.getenv('HARNESS_TERMS_VERSION', '2026-11'),
                   access_ttl, refresh_ttl,
                   os.getenv('HARNESS_MEDIA_ENABLED', media_default) == '1',
                   media_timeout,
                   os.getenv('HARNESS_MEDIA_CACHE_DIR', ''),
                   os.getenv('HARNESS_MEDIA_CONTACT', '').strip(),
                   os.getenv('HARNESS_COMMERCIAL_USE', '0') == '1',
                   os.getenv('HARNESS_YOUTUBE_API_KEY', ''),
                   os.getenv('HARNESS_OPENVERSE_CLIENT_ID', ''),
                   os.getenv('HARNESS_OPENVERSE_CLIENT_SECRET', ''),
                   os.getenv('HARNESS_SELF_EXPLANATION_GATE', '0') == '1',
                   os.getenv('HARNESS_BROWSER_ENABLED', '0') == '1',
                   # Capability matrix: operator comps, then the paid ceiling. The
                   # ceiling is validated like every other operator number -- a typo
                   # must fail at startup, not silently grant an unlimited account.
                   tuple(x.strip() for x in os.getenv('HARNESS_ENTITLEMENTS', '').split(',') if x.strip()),
                   _bounded_int('HARNESS_PAID_MONTHLY_REQUESTS', 2000, 1, 10_000_000),
                   _bounded_int('HARNESS_PAID_MONTHLY_TOKENS', 2_000_000, 1_000, 10**12),
                   voice_base_url,
                   os.getenv('HARNESS_VOICE_MODEL', 'omnivoice').strip() or 'omnivoice',
                   os.getenv('HARNESS_VOICE_NAME', 'default').strip() or 'default',
                   os.getenv('HARNESS_VOICE_API_KEY', ''),
                   voice_timeout,
                   os.getenv('HARNESS_VOICE_INSTRUCT', '').strip(),
                   os.getenv('HARNESS_VOICE_ENABLED', voice_default) == '1',
                   os.getenv('HARNESS_ATTENTION_MONITOR', attention_default) == '1',
                   os.getenv('HARNESS_REALTIME_PROVIDER', 'openai'),
                   os.getenv('HARNESS_REALTIME_KEY', ''),
                   os.getenv('HARNESS_REALTIME_MODEL', 'gpt-4o-realtime-preview-2024-12-17'),
                   # The one capability that captures the host's screen and can post input
                   # to it, so there is no environment in which it defaults on.
                   os.getenv('HARNESS_STREAM_ENABLED', '0') == '1',
                   # Both default on for a running instance. They are gated again on
                   # ``media_enabled`` (off in production, on in the desktop build) at the
                   # call site, so an instance that promises no outbound media never
                   # launches a browser. Set either to 0 to disable explicitly.
                   os.getenv('HARNESS_CHROMIUM_SEARCH', '1') == '1',
                   os.getenv('HARNESS_VIDEO_AUTO_CURATE', '1') == '1')


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    """Read an int env var with an explicit bound, or fail loudly.

    Settings validation is the one place a misconfiguration can be caught before it
    becomes a per-request surprise, so the bounds live here rather than at the read.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f'{name} must be an integer')
    if not low <= value <= high:
        raise ValueError(f'{name} must be between {low} and {high}')
    return value
