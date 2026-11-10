"""The product requires a language model, and an operator can supply one at runtime.

These tests pin the two halves of that promise: the removed ``offline`` mode must stay
removed (a shipped default cannot quietly degrade back into a rules engine), and the
Settings API must make a model live *without a restart* while never returning the key.
"""
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import model_config
from app.config import Settings
from app.harness import provider
from app.main import create_app


@pytest.fixture(autouse=True)
def clean_cache():
    model_config.reset_cache()
    yield
    model_config.reset_cache()


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def auth(client):
    response = client.post('/api/v1/auth/register', json={
        'name': 'Operator', 'email': 'operator@example.test',
        'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


# ------------------------------------------------------------- offline is not a mode

def test_offline_provider_is_rejected_at_startup(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    with pytest.raises(ValueError, match='no longer supported'):
        Settings.from_env()


def test_production_refuses_to_boot_without_a_model(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'production')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_DATABASE_URL',
                       'postgresql+psycopg://user:pass@db.internal:5432/luminfest')
    monkeypatch.setenv('HARNESS_SECRET', 'luminfest-production-secret-0123456789-abcdef')
    monkeypatch.setenv('HARNESS_ALLOWED_HOSTS', 'api.example.test')
    monkeypatch.setenv('HARNESS_LEGAL_TEMPLATE_OK', '1')
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    with pytest.raises(ValueError, match='configured language model'):
        Settings.from_env()


def test_an_unconfigured_instance_is_a_declared_state(settings):
    status = model_config.status(settings)
    assert status['state'] == 'unconfigured'
    assert status['required'] is True
    assert status['label'] == 'model-required'
    assert 'Settings' in status['reason']
    assert provider.available(settings) is False
    assert provider.label(settings) == 'model-required'


def test_a_stray_offline_value_cannot_re_enable_the_rules_engine(settings):
    stray = replace(settings, provider='offline', provider_url='', provider_model='')
    assert model_config.effective(stray).provider == ''
    assert provider.available(stray) is False


# ------------------------------------------------------------- resolution + validation

def test_runtime_override_wins_over_environment_and_clear_reverts(settings):
    env = replace(settings, provider='ollama', provider_url='http://127.0.0.1:11434',
                  provider_model='local-model', provider_key='', provider_timeout=9.0)
    assert model_config.effective(env).provider_model == 'local-model'

    model_config.save_override(settings.data_dir, model_config.ModelConfig(
        provider='openai', provider_url='https://api.example.test/v1',
        provider_model='remote-model', provider_key='sk-secret', provider_timeout=42.0))
    active = model_config.effective(env)
    assert active.provider == 'openai' and active.provider_model == 'remote-model'
    assert model_config.status(env)['source'] == 'runtime'

    model_config.clear_override(settings.data_dir)
    assert model_config.effective(env).provider == 'ollama'


def test_the_persisted_key_is_owner_only(settings):
    model_config.save_override(settings.data_dir, model_config.ModelConfig(
        provider='openai', provider_url='https://api.example.test/v1',
        provider_model='m', provider_key='sk-secret'))
    path = Path(settings.data_dir) / model_config.STORE_FILENAME
    assert path.is_file()
    assert path.stat().st_mode & 0o077 == 0


def test_status_never_returns_a_key(settings):
    model_config.save_override(settings.data_dir, model_config.ModelConfig(
        provider='openai', provider_url='https://api.example.test/v1',
        provider_model='m', provider_key='sk-super-secret'))
    body = str(model_config.status(settings))
    assert 'sk-super-secret' not in body
    assert model_config.status(settings)['api_key_set'] is True


@pytest.mark.parametrize('payload, fragment', [
    ({'preset': 'not-a-provider'}, 'Unknown provider preset'),
    ({'preset': 'deepseek', 'model': 'm'}, 'API key'),
    ({'preset': 'deepseek', 'api_key': 'k'}, 'model id'),
    ({'provider': 'offline', 'base_url': 'https://a.example', 'model': 'm',
      'api_key': 'k'}, 'provider must be'),
    ({'provider': 'openai', 'base_url': 'ftp://a.example', 'model': 'm',
      'api_key': 'k'}, 'valid http'),
    ({'provider': 'openai', 'base_url': 'https://a.example', 'model': 'm',
      'api_key': 'k', 'timeout': 900}, 'timeout'),
])
def test_validation_refuses_incomplete_or_unsafe_configuration(payload, fragment):
    with pytest.raises(ValueError, match=fragment):
        model_config.validate_payload(payload)


def test_omitting_the_key_on_a_later_save_keeps_the_stored_one(settings):
    current = model_config.ModelConfig(provider='openai',
                                       provider_url='https://api.example.test/v1',
                                       provider_model='m', provider_key='sk-keep')
    cfg = model_config.validate_payload(
        {'preset': 'deepseek', 'model': 'deepseek-flash'},
        current_key=current.provider_key)
    assert cfg.provider_key == 'sk-keep'
    assert cfg.provider_url == 'https://api.deepseek.com'


# ------------------------------------------------------------- the HTTP surface

def test_catalog_is_public_and_names_the_requirement(client):
    response = client.get('/api/v1/settings/model-config/catalog')
    assert response.status_code == 200
    body = response.json()
    assert body['required'] is True
    assert any(p['id'] == 'deepseek' for p in body['presets'])
    assert any(p['id'] == 'ollama' for p in body['presets'])


def test_saving_a_model_is_live_without_a_restart(client, settings):
    headers = auth(client)
    before = client.get('/health').json()
    assert before['tutor']['state'] == 'unconfigured'
    assert before['harness']['generation_mode'] == 'model-required'

    response = client.put('/api/v1/settings/model-config', headers=headers, json={
        'preset': 'deepseek', 'model': 'deepseek-flash', 'api_key': 'sk-live',
        'timeout': 45})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['state'] == 'configured'
    assert body['source'] == 'runtime'
    assert 'sk-live' not in str(body)          # never echoed back
    assert body['api_key_set'] is True

    # The same app object, same process: the provider adapter now sees the new model.
    assert provider.available(settings) is True
    assert provider.label(settings) == 'openai:deepseek-flash'
    assert client.get('/health').json()['tutor']['state'] == 'configured'


def test_a_learner_redirects_the_key_field_to_a_kept_secret(client):
    headers = auth(client)
    first = client.put('/api/v1/settings/model-config', headers=headers, json={
        'preset': 'deepseek', 'model': 'deepseek-flash', 'api_key': 'sk-first'})
    assert first.status_code == 200
    second = client.put('/api/v1/settings/model-config', headers=headers, json={
        'preset': 'deepseek', 'model': 'deepseek-v4-pro'})   # no key in the form
    assert second.status_code == 200, second.text
    assert second.json()['api_key_set'] is True
    assert model_config.effective(client.app.state.settings).provider_key == 'sk-first'


def test_invalid_configuration_is_a_422_and_changes_nothing(client, settings):
    headers = auth(client)
    response = client.put('/api/v1/settings/model-config', headers=headers, json={
        'preset': 'deepseek', 'model': 'm'})     # no key
    assert response.status_code == 422
    assert provider.available(settings) is False


def test_delete_reverts_to_the_environment(client):
    headers = auth(client)
    assert client.put('/api/v1/settings/model-config', headers=headers, json={
        'preset': 'deepseek', 'model': 'deepseek-flash',
        'api_key': 'sk-live'}).status_code == 200
    body = client.delete('/api/v1/settings/model-config', headers=headers).json()
    assert body['state'] == 'unconfigured'
    assert body['source'] == 'none'


def test_test_endpoint_reports_an_unconfigured_instance_without_a_network_call(client):
    headers = auth(client)
    body = client.post('/api/v1/settings/model-config/test', headers=headers,
                       json={}).json()
    assert body['ok'] is False
    assert body['state'] == 'unconfigured'


def test_a_learner_cannot_see_operator_details_on_a_hosted_instance(settings):
    # Only the environment flag changes: a hosted multi-user instance shares one model, so
    # writing it is an operator action. A desktop instance lets its owner configure it.
    hosted = replace(settings, environment='production')
    # The hosted profile enforces HTTPS on every request; TestClient defaults to http.
    with TestClient(create_app(hosted), base_url='https://testserver') as c:
        headers = auth(c)
        body = c.get('/api/v1/settings/model-config', headers=headers).json()
        assert body['state'] == 'unconfigured'
        assert 'base_url' not in body and 'model' not in body
        refused = c.put('/api/v1/settings/model-config', headers=headers, json={
            'preset': 'deepseek', 'model': 'deepseek-flash', 'api_key': 'sk-live'})
        assert refused.status_code == 403
