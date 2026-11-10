"""The model configuration layer.

The harness *requires* a configured language model. There is no offline rules-engine
mode: ``HARNESS_TUTOR_PROVIDER=offline`` is rejected, and an unconfigured instance reports
itself as ``unconfigured`` and refuses generative work instead of silently producing
deterministic content. A configured model that transiently fails still degrades gracefully
(so a lapsed key does not break a live lesson) -- that is a request-time safety net, not a
product mode.

Two configuration sources exist, in precedence order:

1. A persisted runtime override in ``<data_dir>/model_config.json``. It is written by the
   admin ``PUT /api/v1/settings/model-config`` endpoint and takes effect without a restart.
2. The environment-derived :class:`app.config.Settings` (``HARNESS_TUTOR_*``).

``effective`` resolves the two: a present runtime override wins; otherwise the environment
settings are used. ``provider.py`` consults ``effective`` on every call, so a model entered
through the settings UI is live immediately.

Security note: the API key is stored in ``model_config.json`` inside the data directory,
the same trust boundary as the application database. It is never returned by ``GET`` -- that
endpoint reports only ``api_key_set``. The file should carry the same on-disk permissions
as the database; operators who prefer not to persist a key can still configure entirely
through environment variables.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


STORE_FILENAME = 'model_config.json'


@dataclass(frozen=True)
class Preset:
    """A curated provider preset for the model-selection UI.

    ``wire`` is what :mod:`app.harness.provider` actually speaks -- every hosted endpoint
    is OpenAI-compatible, so the wire value is ``'openai'``; Ollama is its own wire value.
    """

    label: str
    wire: str
    base_url: str
    models: tuple[str, ...]
    requires_key: bool
    supports_tools: bool
    supports_vision: bool


# The catalogue the configuration UI renders as a dropdown. It is intentionally small and
# opinionated: these are the endpoints the product has been verified against. A free-form
# "openai-compatible" preset covers everything else without bloating the list.
CATALOG: dict[str, Preset] = {
    'deepseek': Preset(
        label='DeepSeek', wire='openai', base_url='https://api.deepseek.com',
        models=('deepseek-flash', 'deepseek-v4-pro'),
        requires_key=True, supports_tools=True, supports_vision=True),
    'openai': Preset(
        label='OpenAI', wire='openai', base_url='https://api.openai.com/v1',
        models=('gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'o3-mini'),
        requires_key=True, supports_tools=True, supports_vision=True),
    'openai-compatible': Preset(
        label='Custom OpenAI-compatible endpoint', wire='openai', base_url='',
        models=(), requires_key=True, supports_tools=True, supports_vision=False),
    'ollama': Preset(
        label='Ollama (local)', wire='ollama', base_url='http://127.0.0.1:11434',
        models=(), requires_key=False, supports_tools=False, supports_vision=False),
}


@dataclass
class ModelConfig:
    """A resolved provider configuration (the five fields ``provider.py`` reads)."""

    provider: str = ''
    provider_url: str = ''
    provider_model: str = ''
    provider_key: str = ''
    provider_timeout: float = 30.0

    def as_payload(self) -> dict[str, Any]:
        return {
            'provider': self.provider,
            'provider_url': self.provider_url,
            'provider_model': self.provider_model,
            'provider_key': self.provider_key,
            'provider_timeout': self.provider_timeout,
        }


# Module-level cache: data_dir (str) -> ModelConfig | None. Populated lazily by
# ``load_override`` and updated by ``save_override`` / ``clear_override`` so a runtime
# change is visible on the next provider call without a restart or a disk read per call.
_CACHE: dict[str, ModelConfig | None] = {}


def _store_path(data_dir: Any) -> Path | None:
    if data_dir is None:
        return None
    try:
        return Path(data_dir) / STORE_FILENAME
    except (TypeError, ValueError):
        return None


def load_override(data_dir: Any) -> ModelConfig | None:
    """Return the persisted runtime override for ``data_dir``, or ``None``.

    The result (including "no file") is cached per data_dir, so repeated provider calls
    after the first are a dict lookup, not a disk read.
    """
    key = str(data_dir)
    if key in _CACHE:
        return _CACHE[key]
    path = _store_path(data_dir)
    if path is None or not path.is_file():
        _CACHE[key] = None
        return None
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
        cfg = ModelConfig(
            provider=str(raw.get('provider', '') or ''),
            provider_url=str(raw.get('provider_url', '') or ''),
            provider_model=str(raw.get('provider_model', '') or ''),
            provider_key=str(raw.get('provider_key', '') or ''),
            provider_timeout=float(raw.get('provider_timeout', 30.0)),
        )
    except (OSError, ValueError, TypeError):
        _CACHE[key] = None
        return None
    _CACHE[key] = cfg
    return cfg


def save_override(data_dir: Any, cfg: ModelConfig) -> None:
    """Persist ``cfg`` and make it the live override for ``data_dir`` immediately.

    The file holds an API key, so it is created owner-read/write only. A world-readable
    key next to the database is the sort of defect that survives a backup restore, and
    the desktop data directory is inside the user's own Library folder.
    """
    key = str(data_dir)
    path = _store_path(data_dir)
    if path is None:
        raise ValueError('ModelConfig requires a data directory')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg.as_payload(), indent=2, sort_keys=True),
                    encoding='utf-8')
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - some filesystems cannot carry a mode
        pass
    _CACHE[key] = cfg


def clear_override(data_dir: Any) -> None:
    """Remove the persisted override so the instance falls back to environment settings."""
    key = str(data_dir)
    path = _store_path(data_dir)
    if path is not None and path.is_file():
        path.unlink()
    _CACHE[key] = None


def reset_cache() -> None:
    """Drop the in-memory cache. Test-only; never call from request handling."""
    _CACHE.clear()


def effective(settings: Any) -> ModelConfig:
    """Resolve the active provider configuration.

    A persisted runtime override wins (when present and carries a provider); otherwise the
    environment-derived Settings are used. Both inputs are treated as untrusted on the
    provider field -- ``offline`` is normalised to "unconfigured" so a stray value cannot
    re-enable the removed rules-engine mode.
    """
    ov = load_override(getattr(settings, 'data_dir', None))
    if ov is not None and ov.provider and ov.provider != 'offline':
        return ov
    return ModelConfig(
        provider=_norm(getattr(settings, 'provider', '') or ''),
        provider_url=getattr(settings, 'provider_url', '') or '',
        provider_model=getattr(settings, 'provider_model', '') or '',
        provider_key=getattr(settings, 'provider_key', '') or '',
        provider_timeout=float(getattr(settings, 'provider_timeout', 30.0) or 30.0),
    )


def _norm(provider: str) -> str:
    return '' if provider == 'offline' else provider


def catalog_payload() -> list[dict[str, Any]]:
    """The provider presets the settings UI renders as a dropdown (no secrets)."""
    return [{'id': key, 'label': preset.label, 'wire': preset.wire,
             'base_url': preset.base_url, 'models': list(preset.models),
             'requires_key': preset.requires_key, 'supports_tools': preset.supports_tools,
             'supports_vision': preset.supports_vision}
            for key, preset in CATALOG.items()]


def status(settings: Any) -> dict[str, Any]:
    """A *public* description of the active model configuration. Never includes a key.

    ``state`` is what the UI and the health endpoint should branch on. ``unconfigured``
    means the product is running degraded: generative work reports ``model-required``
    rather than pretending a rules engine is the product. ``source`` tells an operator
    whether the value came from the settings UI or from the process environment, which is
    otherwise a very confusing thing to debug when both are set.
    """
    ov = load_override(getattr(settings, 'data_dir', None))
    from_runtime = bool(ov is not None and ov.provider and ov.provider != 'offline')
    cfg = effective(settings)
    configured = bool(cfg.provider and cfg.provider_url and cfg.provider_model)
    env_cfg = ModelConfig(
        provider=_norm(getattr(settings, 'provider', '') or ''),
        provider_url=getattr(settings, 'provider_url', '') or '',
        provider_model=getattr(settings, 'provider_model', '') or '',
        provider_key=getattr(settings, 'provider_key', '') or '')
    env_configured = bool(env_cfg.provider and env_cfg.provider_url and env_cfg.provider_model)
    return {
        'state': 'configured' if configured else 'unconfigured',
        'configured': configured,
        'source': 'runtime' if from_runtime else ('environment' if env_configured else 'none'),
        'provider': cfg.provider,
        'model': cfg.provider_model,
        'base_url': cfg.provider_url,
        'api_key_set': bool(cfg.provider_key),
        'timeout': cfg.provider_timeout,
        'label': f'{cfg.provider}:{cfg.provider_model}' if configured else 'model-required',
        'environment_provider': env_cfg.provider,
        'runtime_override': from_runtime,
        'catalog': catalog_payload(),
        'required': True,
        'reason': ('' if configured else
                   'No language model is configured. Add a provider, model and API key in '
                   'Settings to enable model-backed teaching.'),
    }


def validate_payload(payload: Mapping[str, Any], environment: str = 'development',
                     current_key: str = '') -> ModelConfig:
    """Validate a settings payload into a :class:`ModelConfig`.

    Accepts either a ``preset`` key (a :data:`CATALOG` entry, which fills the wire provider
    and a default base URL) or an explicit ``provider`` (``openai``/``ollama``). Raises
    ``ValueError`` on any problem so the API endpoint can surface it as a 422.

    ``current_key`` lets the UI save a changed model without resending the secret: the GET
    endpoint never returns a key, so a form that echoes its own fields would otherwise
    erase it. An explicit non-empty ``api_key`` always wins; ``api_key=''`` with a current
    key keeps it, and ``clear_key=True`` drops it (needed for keyless Ollama).
    """
    preset_key = (payload.get('preset') or '').strip()
    base_url = (payload.get('base_url') or '').strip()
    model = (payload.get('model') or '').strip()
    api_key = payload.get('api_key') or ''
    if not api_key and not payload.get('clear_key'):
        api_key = current_key
    timeout = payload.get('timeout', 30.0)

    if preset_key:
        if preset_key not in CATALOG:
            raise ValueError(f'Unknown provider preset: {preset_key!r}')
        preset = CATALOG[preset_key]
        provider = preset.wire
        if not base_url and preset.base_url:
            base_url = preset.base_url
        requires_key = preset.requires_key
    else:
        provider = (payload.get('provider') or 'openai').strip()
        if provider not in {'openai', 'ollama'}:
            raise ValueError("provider must be 'openai' or 'ollama' when no preset is given")
        requires_key = provider != 'ollama'

    if not base_url:
        raise ValueError('A base URL is required (set base_url, or choose a preset that supplies one).')
    parsed = urlparse(base_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username:
        raise ValueError('base_url must be a valid http(s) URL with a host and no embedded credentials.')
    if (environment == 'production' and parsed.scheme != 'https'
            and parsed.hostname not in {'localhost', '127.0.0.1', '::1', 'ollama'}):
        raise ValueError('Remote production endpoints require HTTPS.')

    if not model:
        raise ValueError('A model id is required.')
    if requires_key and not api_key:
        raise ValueError('This provider requires an API key.')

    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        raise ValueError('timeout must be a number of seconds.')
    if not 1 <= timeout <= 300:
        raise ValueError('timeout must be between 1 and 300 seconds.')

    return ModelConfig(provider=provider, provider_url=base_url, provider_model=model,
                       provider_key=api_key, provider_timeout=timeout)
