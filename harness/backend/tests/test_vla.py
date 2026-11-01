"""Tests for the VLA layer: model cards, image plumbing, see-act-see, on-task reading.

Everything here runs against fakes. No test in this file touches a real endpoint, reads a
real key, or opens a camera: the vision model is an ``httpx.MockTransport`` and the
"snapshot" is a one-pixel PNG built in memory.
"""

import base64
import hashlib
import json
import struct
import zlib
from types import SimpleNamespace

import httpx
import pytest

from app import capabilities
from app.config import Settings
from app.harness import agent_loop, attention, provider, toolbox, vla
from app.harness.agent_loop import run_agent
from app.harness.toolbox import ToolResult


# --------------------------------------------------------------------- helpers

def png_bytes() -> bytes:
    """A valid 1x1 PNG, so the size and magic-byte checks are exercised for real."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (struct.pack('>I', len(data)) + body
                + struct.pack('>I', zlib.crc32(body) & 0xFFFFFFFF))

    header = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    pixels = b'\x00' + b'\x00\x00\x00'
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


def data_url(raw: bytes | None = None) -> str:
    return 'data:image/png;base64,' + base64.b64encode(raw or png_bytes()).decode('ascii')


def vision_settings(tmp_path, monkeypatch, *, model='deepseek-flash'):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'openai')
    monkeypatch.setenv('HARNESS_TUTOR_URL', 'https://provider.example.test/v1')
    monkeypatch.setenv('HARNESS_TUTOR_MODEL', model)
    monkeypatch.setenv('HARNESS_TUTOR_KEY', 'test-key-not-real')
    monkeypatch.setenv('HARNESS_TUTOR_TIMEOUT_SECONDS', '5')
    return Settings.from_env()


def offline_settings(tmp_path, monkeypatch, **env):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings.from_env()


def install_transport(monkeypatch, handler):
    original = httpx.Client

    def client_factory(**kwargs):
        kwargs.pop('timeout', None)
        kwargs.pop('follow_redirects', None)
        kwargs.pop('trust_env', None)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(provider.httpx, 'Client', client_factory)


def completion(content='ok', **extra):
    body = {'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 20, 'completion_tokens': 5, 'total_tokens': 25}}
    body.update(extra)
    return httpx.Response(200, json=body)


def ctx_for(settings, user_id='learner-1'):
    from app.harness import sandbox
    return SimpleNamespace(settings=settings, db=None, now=0.0,
                           user=SimpleNamespace(id=user_id),
                           workspace=sandbox.workspace_for(settings, user_id))


# --------------------------------------------------------------------- model cards

def test_build_label_resolves_to_the_wire_id():
    card = vla.model_card('deepseek-v4.1-flash-1047')
    assert card is not None and card.id == 'deepseek-flash'
    assert card.display_name == 'DeepSeek-V4.1-Flash'
    assert card.sees and card.acts and card.vla


def test_a_text_only_model_is_not_treated_as_a_vlm():
    card = vla.model_card('deepseek-v4-pro')
    assert card is not None
    assert card.sees is False
    assert card.vla is False


def test_an_unknown_model_is_blind_by_default(monkeypatch):
    assert vla.model_card('some-other-model') is None
    monkeypatch.delenv('HARNESS_TUTOR_VISION', raising=False)
    settings = SimpleNamespace(provider='openai', provider_url='https://x.test',
                               provider_model='some-other-model', provider_key='k')
    assert vla.vision_ready(settings) is False
    monkeypatch.setenv('HARNESS_TUTOR_VISION', '1')
    assert vla.vision_ready(settings) is True


def test_vision_status_refuses_a_text_only_model_with_a_reason(tmp_path, monkeypatch):
    settings = vision_settings(tmp_path, monkeypatch, model='deepseek-v4-pro')
    ready, note = vla.vision_status(settings)
    assert ready is False
    assert 'text-only' in note


def test_vision_status_names_the_missing_switch_when_offline(tmp_path, monkeypatch):
    settings = offline_settings(tmp_path, monkeypatch)
    ready, note = vla.vision_status(settings)
    assert ready is False
    assert 'HARNESS_TUTOR_PROVIDER' in note


# --------------------------------------------------------------------- image plumbing

def test_a_remote_url_is_refused_because_the_server_would_fetch_it():
    with pytest.raises(vla.ImageRefused) as caught:
        vla.check_data_url('https://example.test/photo.png')
    assert 'remote URL' in str(caught.value)


def test_the_magic_bytes_decide_the_mime_not_the_caller():
    url = vla.to_data_url(png_bytes(), 'image/jpeg')
    assert url.startswith('data:image/png;base64,')


def test_oversize_and_non_image_bytes_are_refused_by_name():
    with pytest.raises(vla.ImageRefused) as big:
        vla.to_data_url(b'\x89PNG\r\n\x1a\n' + b'0' * vla.MAX_IMAGE_BYTES)
    assert 'limit' in str(big.value)
    with pytest.raises(vla.ImageRefused) as junk:
        vla.to_data_url(b'not an image at all')
    assert 'PNG, JPEG or WebP' in str(junk.value)


def test_workspace_paths_are_resolved_inside_the_learner_workspace(tmp_path, monkeypatch):
    settings = vision_settings(tmp_path, monkeypatch)
    ctx = ctx_for(settings)
    ctx.workspace.write('work.png', 'placeholder')
    (ctx.workspace.root / 'work.png').write_bytes(png_bytes())
    url, raw, origin = vla.resolve_image(ctx.workspace, 'work.png')
    assert origin == 'workspace' and raw == png_bytes()
    assert url == data_url()
    with pytest.raises(vla.ImageRefused):
        vla.resolve_image(ctx.workspace, '../../etc/passwd')


# --------------------------------------------------------------------- observing

def test_observe_sends_image_parts_and_reports_a_digest(tmp_path, monkeypatch):
    settings = vision_settings(tmp_path, monkeypatch)
    seen = {}

    def handler(request):
        seen['body'] = json.loads(request.content)
        return completion('The third line reads 3/4 + 1/2.')

    install_transport(monkeypatch, handler)
    usage = {}
    result = vla.observe(settings, [data_url()], 'What is written?', usage_out=usage)

    assert result is not None
    assert result['text'].startswith('The third line')
    parts = seen['body']['messages'][1]['content']
    assert parts[0]['type'] == 'text'
    assert parts[1]['type'] == 'image_url'
    assert parts[1]['image_url']['url'].startswith('data:image/png;base64,')
    assert result['digests'] == [hashlib.sha256(png_bytes()).hexdigest()]
    assert usage['total_tokens'] == 25
    # The observer prompt is the thing that keeps a learner's face out of the answer.
    assert 'Never name, identify or guess the identity of a person' in seen['body']['messages'][0]['content']


def test_observe_returns_none_when_the_provider_refuses(tmp_path, monkeypatch):
    settings = vision_settings(tmp_path, monkeypatch)
    install_transport(monkeypatch, lambda request: httpx.Response(
        402, json={'error': {'message': 'Insufficient Balance'}}))
    assert vla.observe(settings, [data_url()], 'What is written?') is None


def test_observe_never_sends_more_than_the_image_cap(tmp_path, monkeypatch):
    settings = vision_settings(tmp_path, monkeypatch)
    seen = {}

    def handler(request):
        seen['body'] = json.loads(request.content)
        return completion('many')

    install_transport(monkeypatch, handler)
    vla.observe(settings, [data_url() for _ in range(vla.MAX_IMAGES + 3)], 'Describe')
    parts = seen['body']['messages'][1]['content']
    assert len([part for part in parts if part['type'] == 'image_url']) == vla.MAX_IMAGES


# --------------------------------------------------------------------- see, act, see

def test_a_tool_that_returns_an_image_gets_it_reinjected_before_the_next_step(
        tmp_path, monkeypatch):
    settings = vision_settings(tmp_path, monkeypatch)
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            return completion(None, choices=[{
                'message': {'content': None, 'tool_calls': [{
                    'id': 'call_1', 'type': 'function',
                    'function': {'name': 'look_at_image', 'arguments': '{"source": "work.png"}'}}]},
                'finish_reason': 'tool_calls'}])
        return completion('The second line is wrong.')

    install_transport(monkeypatch, handler)

    def look_at_image(arguments, ctx):
        return ToolResult('look_at_image', True, {'attached': True}, images=[data_url()])

    messages = [{'role': 'user', 'content': 'check my work'}]
    events = list(run_agent(settings, messages, {'look_at_image': look_at_image},
                            ctx_for(settings), max_steps=3))
    types = [event['type'] for event in events]

    assert 'observation' in types
    observation = next(event for event in events if event['type'] == 'observation')
    assert observation['images'] == 1
    # The second model call carries the picture as a user turn with image parts.
    second = bodies[1]['messages']
    injected = [message for message in second
                if message['role'] == 'user' and isinstance(message['content'], list)]
    assert injected, 'the image never reached the model'
    assert any(part['type'] == 'image_url' for part in injected[-1]['content'])
    assert events[-1]['type'] == 'turn_end' and events[-1]['content'] == 'The second line is wrong.'
    # The text tool message must not carry the image bytes: only the count.
    tool_messages = [message for message in second if message['role'] == 'tool']
    assert 'data:image' not in tool_messages[0]['content']


def test_a_turn_with_no_images_emits_no_observation_event(tmp_path, monkeypatch):
    settings = vision_settings(tmp_path, monkeypatch)
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            return completion(None, choices=[{
                'message': {'content': None, 'tool_calls': [{
                    'id': 'call_1', 'type': 'function',
                    'function': {'name': 'echo', 'arguments': '{"text": "hi"}'}}]},
                'finish_reason': 'tool_calls'}])
        return completion('done')

    install_transport(monkeypatch, handler)
    events = list(run_agent(settings, [{'role': 'user', 'content': 'x'}],
                            {'echo': lambda arguments, ctx: ToolResult('echo', True, arguments)},
                            ctx_for(settings), max_steps=2))
    assert 'observation' not in [event['type'] for event in events]


# --------------------------------------------------------------------- the tools

def test_look_at_image_attaches_the_picture_when_no_question_is_asked(tmp_path, monkeypatch):
    settings = vision_settings(tmp_path, monkeypatch)
    ctx = ctx_for(settings)
    (ctx.workspace.root / 'work.png').write_bytes(png_bytes())

    result = toolbox.invoke(ctx, 'look_at_image', {'source': 'work.png'})
    assert result.ok, result.refused
    assert result.data['attached'] is True
    assert len(result.images) == 1
    assert result.data['image']['sha256'] == hashlib.sha256(png_bytes()).hexdigest()


def test_look_at_image_answers_a_question_in_a_side_call(tmp_path, monkeypatch):
    settings = vision_settings(tmp_path, monkeypatch)
    install_transport(monkeypatch, lambda request: completion('The denominator was doubled.'))
    ctx = ctx_for(settings)
    (ctx.workspace.root / 'work.png').write_bytes(png_bytes())

    result = toolbox.invoke(ctx, 'look_at_image',
                            {'source': 'work.png', 'question': 'What went wrong?'})
    assert result.ok
    assert result.data['description'] == 'The denominator was doubled.'
    assert result.images == []  # the answer is the point; the picture stays out of context


def test_look_at_image_refuses_without_a_vision_model(tmp_path, monkeypatch):
    settings = offline_settings(tmp_path, monkeypatch)
    result = toolbox.invoke(ctx_for(settings), 'look_at_image', {'source': data_url()})
    assert not result.ok
    assert 'vision model' in result.refused


# --------------------------------------------------------------------- on-task reading

def test_monitoring_off_is_a_refusal_that_names_the_switch(tmp_path, monkeypatch):
    settings = offline_settings(tmp_path, monkeypatch, HARNESS_ATTENTION_MONITOR='0')
    reading = attention.assess(settings, task='finish question 4',
                               signals={'idle_seconds': 400})
    assert reading['ok'] is False and reading['enabled'] is False
    assert 'HARNESS_ATTENTION_MONITOR' in reading['refused']
    assert reading['privacy']['frames_stored'] is False


def test_idle_time_reads_as_off_task_with_its_evidence(tmp_path, monkeypatch):
    settings = offline_settings(tmp_path, monkeypatch, HARNESS_ATTENTION_MONITOR='1')
    reading = attention.assess(settings, task='finish question 4',
                               signals={'idle_seconds': 400, 'window_seconds': 300})
    assert reading['ok'] is True
    assert reading['state'] == 'off_task'
    assert any('400 s' in line for line in reading['evidence'])
    # The move is a teaching move: no reporting, no flag, no block.
    assert 'accuse' in reading['suggested_action'] or 'break' in reading['suggested_action']
    assert not any(word in reading['suggested_action'].lower()
                   for word in ('report', 'flag', 'block', 'notify'))


def test_no_attempt_and_little_activity_is_unclear_not_off_task(tmp_path, monkeypatch):
    settings = offline_settings(tmp_path, monkeypatch, HARNESS_ATTENTION_MONITOR='1')
    reading = attention.assess(settings, task='finish question 4',
                               signals={'idle_seconds': 10, 'active_seconds': 10,
                                        'attempts': 0, 'window_seconds': 300})
    assert reading['state'] == 'unclear'
    assert reading['confidence'] < 0.5


def test_telemetry_alone_can_call_it_on_task(tmp_path, monkeypatch):
    settings = offline_settings(tmp_path, monkeypatch, HARNESS_ATTENTION_MONITOR='1')
    reading = attention.assess(settings, task='finish question 4',
                               signals={'idle_seconds': 12, 'attempts': 2,
                                        'active_seconds': 200, 'window_seconds': 300})
    assert reading['state'] == 'on_task'
    assert reading['dimensions']['visual'] is None
    assert 'Continue' in reading['suggested_action']


def test_a_picture_that_contradicts_the_telemetry_is_reported_as_unclear(
        tmp_path, monkeypatch):
    settings = vision_settings(tmp_path, monkeypatch)
    monkeypatch.setenv('HARNESS_ATTENTION_MONITOR', '1')
    settings = Settings.from_env()
    monkeypatch.setattr(vla, 'read_json', lambda *args, **kwargs: {
        'work_visible': True, 'attempt_visible': True, 'matches_task': 'yes',
        'evidence': ['A worked fraction addition fills the page.'], 'confidence': 0.9})

    reading = attention.assess(settings, task='finish question 4', snapshot=data_url(),
                               signals={'idle_seconds': 400})
    assert reading['state'] == 'unclear'
    assert any('disagree' in note for note in reading['notes'])
    assert reading['dimensions']['telemetry']['state'] == 'off_task'
    assert reading['dimensions']['visual']['state'] == 'on_task'


def test_the_tool_returns_a_move_and_a_privacy_block(tmp_path, monkeypatch):
    settings = offline_settings(tmp_path, monkeypatch, HARNESS_ATTENTION_MONITOR='1')
    result = toolbox.invoke(ctx_for(settings), 'check_on_task',
                            {'task': 'finish question 4',
                             'signals': {'idle_seconds': 20, 'attempts': 1,
                                         'window_seconds': 300}})
    assert result.ok, result.refused
    assert result.data['state'] == 'on_task'
    assert result.data['privacy']['used_for_grading'] is False
    assert result.citations[0]['kind'] == 'attention_reading'


# --------------------------------------------------------------------- the deck

def test_the_pptx_twin_is_a_sixteen_by_nine_deck_with_notes_and_a_title_slide(
        tmp_path, monkeypatch):
    from pptx import Presentation
    from pptx.util import Inches

    settings = offline_settings(tmp_path, monkeypatch)
    result = toolbox.invoke(ctx_for(settings), 'generate_slides', {
        'title': 'Fractions: why denominators matter',
        'sections': [{'heading': 'A denominator names the unit',
                      'bullets': ['1/2 and 1/3 count different units',
                                  'Add only like units'],
                      'notes': 'Start with the pizza, then name the unit.'},
                     {'heading': 'The error process',
                      'bullets': ['Adding denominators changes the unit'],
                      'notes': 'Ask why the sum should be smaller than one half.'}]})
    assert result.ok, result.refused

    from app.harness import sims_store
    path = sims_store.store_root(settings) / result.data['artifact_id'] / 'v1.pptx'
    presentation = Presentation(str(path))
    assert presentation.slide_width == Inches(13.333)
    assert len(presentation.slides) == 3  # cover + two content slides
    cover_text = ' '.join(shape.text_frame.text for shape in presentation.slides[0].shapes
                          if shape.has_text_frame)
    assert 'Fractions: why denominators matter' in cover_text
    assert presentation.slides[1].notes_slide.notes_text_frame.text.startswith('Start with the pizza')


def test_deck_quality_notes_name_the_slide_to_fix(tmp_path, monkeypatch):
    settings = offline_settings(tmp_path, monkeypatch)
    sections = [{'heading': 'Too much', 'bullets': [f'bullet {n}' for n in range(8)],
                 'notes': ''}]
    result = toolbox.invoke(ctx_for(settings), 'generate_slides',
                            {'title': 'T', 'sections': sections})
    assert result.ok
    joined = ' '.join(result.notes)
    assert 'Slide 1 has 8 bullets' in joined
    assert 'no speaker notes' in joined


# --------------------------------------------------------------------- the matrix

def test_the_capability_matrix_reports_vision_as_implemented():
    vision = capabilities.by_id('vision_understanding')
    assert vision is not None and vision.status == capabilities.STATUS_IMPLEMENTED
    assert capabilities.by_id('vla_actions').status == capabilities.STATUS_IMPLEMENTED
    assert capabilities.by_id('on_task_monitoring').status == capabilities.STATUS_IMPLEMENTED


def test_the_vision_probe_reads_the_model_card_not_the_provider_name(tmp_path, monkeypatch):
    text_only = vision_settings(tmp_path, monkeypatch, model='deepseek-v4-pro')
    ready, note = capabilities.PROBES['vision'](text_only)
    assert ready is False and 'text-only' in note

    monkeypatch.setenv('HARNESS_TUTOR_MODEL', 'deepseek-flash')
    ready, note = capabilities.PROBES['vision'](Settings.from_env())
    assert ready is True and 'image input' in note


def test_harness_status_exposes_the_vla_and_attention_posture(tmp_path, monkeypatch):
    from app import harness
    settings = offline_settings(tmp_path, monkeypatch, HARNESS_ATTENTION_MONITOR='1')
    status = harness.status(settings)
    assert status['vla']['vision']['ready'] is False
    assert status['vla']['max_images'] == vla.MAX_IMAGES
    assert status['attention']['enabled'] is True
    assert status['attention']['privacy']['identifies_people'] is False
