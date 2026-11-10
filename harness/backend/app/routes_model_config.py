"""Runtime language-model configuration.

The product requires a model. It used to ship pointed at ``offline`` - a deterministic
rules engine - and the only way to change that was to edit five environment variables and
restart the backend. That is not a setting a customer can find, and it made the degraded
mode the shipped default. This router is the replacement:

* ``GET    /api/v1/settings/model-config/catalog`` - public presets (also the packaging probe).
* ``GET    /api/v1/settings/model-config``         - the active configuration, never the key.
* ``PUT    /api/v1/settings/model-config``         - save a provider/model/key, live immediately.
* ``DELETE /api/v1/settings/model-config``         - drop the runtime override, back to env.
* ``POST   /api/v1/settings/model-config/test``    - one tiny completion to verify the key.

Who may change it depends on the deployment. A hosted multi-user instance shares one model
across every account, so only ``admin``/``staff`` may write. A single-user desktop or local
development instance has no other operator, so its signed-in owner may configure it - the
alternative would ship a Settings screen that always answers 403 to the person who installed
the app. The GET is available to any signed-in user because every client needs to know
whether the instance is in the ``model-required`` state; non-operators receive a reduced
view without the endpoint URL or model id.

The key is write-only. ``api_key_set`` is reported, the key itself never is, and omitting
``api_key`` on a later PUT keeps the stored one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from . import model_config
from . import schemas
from .harness import provider
from .routes_supervision import authenticated
from .security import require_principal

API = '/api/v1/settings/model-config'

#: The catalog is public (it is also the frozen-bundle probe), so the resolver cannot be
#: a router-level dependency. Each protected route declares it explicitly. The route-graph
#: gate reads the dependency tree, not the body of ``authenticated``, and an optional
#: router-level resolver would cache an anonymous principal and break the token heartbeat.
_require_principal = require_principal('api', 180)
router = APIRouter()


def _is_operator(user, settings) -> bool:
    if getattr(settings, 'environment', '') in {'desktop', 'development', 'test'}:
        return True
    return getattr(user, 'role', 'learner') in {'admin', 'staff'}


def _require_operator(user, settings) -> None:
    if not _is_operator(user, settings):
        raise HTTPException(403, 'Administrator access required to change the model configuration')


def _public_status(settings, *, operator: bool) -> dict:
    status = model_config.status(settings)
    if operator:
        return status
    # A learner on a hosted instance needs the state, not the operator's endpoint details.
    return {key: status[key] for key in
            ('state', 'configured', 'label', 'required', 'reason', 'catalog')}


@router.get(API + '/catalog')
def catalog():
    """The curated provider presets. No secrets and no authentication required."""
    return {'presets': model_config.catalog_payload(), 'required': True,
            'note': 'A language model is required. Choose a preset, enter a model id and '
                    'an API key, or configure HARNESS_TUTOR_* in the environment.'}


@router.get(API, dependencies=[Depends(_require_principal)])
def get_config(request: Request, auth=Depends(authenticated)):
    _db, user = auth
    settings = request.app.state.settings
    return _public_status(settings, operator=_is_operator(user, settings))


@router.put(API, dependencies=[Depends(_require_principal)])
def put_config(request: Request, payload: schemas.ModelConfigInput,
               auth=Depends(authenticated)):
    _db, user = auth
    settings = request.app.state.settings
    _require_operator(user, settings)
    current = model_config.load_override(getattr(settings, 'data_dir', None))
    try:
        cfg = model_config.validate_payload(
            payload.model_dump(), environment=getattr(settings, 'environment', 'development'),
            current_key=(current.provider_key if current else ''))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        model_config.save_override(settings.data_dir, cfg)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, f'Could not persist the model configuration: {exc}') from exc
    return _public_status(settings, operator=True)


@router.delete(API, dependencies=[Depends(_require_principal)])
def delete_config(request: Request, auth=Depends(authenticated)):
    """Revert to the environment configuration (which may itself be unconfigured)."""
    _db, user = auth
    settings = request.app.state.settings
    _require_operator(user, settings)
    try:
        model_config.clear_override(getattr(settings, 'data_dir', None))
    except OSError as exc:
        raise HTTPException(503, f'Could not remove the model configuration: {exc}') from exc
    return _public_status(settings, operator=True)


@router.post(API + '/test', dependencies=[Depends(_require_principal)])
def test_config(request: Request, auth=Depends(authenticated)):
    """Verify the *active* configuration with one small completion.

    A 200 does not mean the model answered; the body's ``ok`` does. Transport-level
    failures are reported here instead of being raised so a bad key is a readable message
    in Settings rather than a red toast with a stack trace.
    """
    _db, user = auth
    settings = request.app.state.settings
    _require_operator(user, settings)
    status = model_config.status(settings)
    if not status['configured']:
        return {'ok': False, 'state': 'unconfigured',
                'detail': status['reason'] or 'No language model is configured.'}
    usage: dict = {}
    reply = provider.chat(settings,
                          [{'role': 'user', 'content': 'Reply with the single word: ready'}],
                          max_tokens=16, reasoning='off', usage_out=usage)
    if reply is None:
        return {'ok': False, 'state': 'unreachable',
                'detail': 'The configured model did not answer. Check the base URL, model id '
                          'and API key, and that this machine can reach the endpoint.',
                'usage': usage}
    return {'ok': True, 'state': 'configured', 'provider': status['label'],
            'reply': reply.strip()[:80], 'usage': usage}
