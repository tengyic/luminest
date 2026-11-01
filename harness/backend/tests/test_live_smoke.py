"""One live smoke test against the real provider endpoint.

Skipped unless an operator explicitly asks for it:

    HARNESS_LIVE_SMOKE=1 HARNESS_TUTOR_PROVIDER=openai \
    HARNESS_TUTOR_MODEL=deepseek-v4-pro pytest -q backend/tests/test_live_smoke.py

The API key comes from the environment or ``backend/.env`` (``DEEPSEEK_API_KEY``) via
the config layer; this module never prints, logs or asserts on it. Every other test in
the suite runs against fakes and never touches the network.
"""

import os

import pytest

from app.config import Settings
from app.harness import provider

pytestmark = pytest.mark.live

# The suite's hermetic fixture scrubs every HARNESS_* variable before a test body runs,
# so an operator's shell-provided provider config would be gone by the time this test
# executes. Capturing it at module import - collection happens before any fixture -
# preserves the operator's intent without the suite-wide contract being touched.
_OPERATOR_PROVIDER = os.getenv('HARNESS_TUTOR_PROVIDER', '')
_OPERATOR_MODEL = os.getenv('HARNESS_TUTOR_MODEL', '')
_OPERATOR_SMOKE = os.getenv('HARNESS_LIVE_SMOKE', '')

WEATHER_TOOL = {'name': 'get_weather',
                'description': 'Get the current weather for a city.',
                'parameters': {'type': 'object',
                               'properties': {'city': {'type': 'string'}},
                               'required': ['city']}}


def test_live_provider_returns_a_typed_tool_call():
    if _OPERATOR_SMOKE != '1':
        pytest.skip('Live smoke disabled; set HARNESS_LIVE_SMOKE=1')
    if not _OPERATOR_PROVIDER:
        pytest.skip('No HARNESS_TUTOR_PROVIDER was set when the suite was collected')
    os.environ['HARNESS_TUTOR_PROVIDER'] = _OPERATOR_PROVIDER
    os.environ['HARNESS_TUTOR_MODEL'] = _OPERATOR_MODEL
    settings = Settings.from_env()
    if not provider.available(settings):
        pytest.skip('No provider configured (set HARNESS_TUTOR_PROVIDER/URL/MODEL/KEY)')
    usage: dict = {}
    result = provider.chat_tools(
        settings,
        [{'role': 'system', 'content': 'Use the get_weather tool to answer.'},
         {'role': 'user', 'content': 'What is the weather in Tokyo right now?'}],
        tools=[WEATHER_TOOL], max_tokens=300, usage_out=usage)
    assert result is not None, 'provider call failed'
    assert result['tool_calls'], f'expected a tool call, got: {result["finish_reason"]}'
    call = result['tool_calls'][0]
    assert call['name'] == 'get_weather'
    assert isinstance(call['arguments'], dict) and isinstance(call['arguments'].get('city'), str)
    assert usage['total_tokens'] > 0
