"""The language of generated content must follow the language of the interface.

The interface switch shipped earlier only moved the chrome: the tutor still answered in
English and generated questions still read as English. These cases pin the layer that
fixes that — and, just as importantly, they pin the cases where it must do *nothing*,
because an instruction added to an English prompt is both wasted tokens and a nudge toward
the model talking about language instead of answering.
"""

import pytest

from app import content_locale


@pytest.mark.parametrize('header,expected', [
    ('zh-Hans', 'zh-Hans'),
    ('zh-Hans,zh;q=0.9,en;q=0.5', 'zh-Hans'),
    ('zh-CN', 'zh-Hans'),
    ('en-US,en;q=0.9', 'en'),
    ('en', 'en'),
    ('*', 'en'),
    ('', 'en'),
    (None, 'en'),
    ('de-DE,fr;q=0.8', 'en'),
    # A client that lists English first means it: preference order wins over the fact that
    # Chinese also appears.
    ('en,zh;q=0.8', 'en'),
])
def test_header_maps_to_a_supported_language(header, expected):
    assert content_locale.from_header(header) == expected


def test_english_gets_no_directive():
    """English is what the prompts are already written in."""
    assert content_locale.directive('en') is None


def test_chinese_directive_covers_the_whole_reply_and_protects_identifiers():
    text = content_locale.directive('zh-Hans')
    assert 'Simplified Chinese' in text
    # Keys and formulas must survive: a model that translates JSON keys breaks parsing,
    # and one that rewrites formulas breaks the maths.
    assert 'JSON keys' in text
    assert 'formulas' in text


def test_apply_extends_an_existing_system_turn():
    messages = [{'role': 'system', 'content': 'You are a tutor.'},
                {'role': 'user', 'content': 'Explain photosynthesis.'}]
    token = content_locale.set_locale('zh-Hans')
    try:
        out = content_locale.apply(messages)
    finally:
        content_locale.reset_locale(token)

    assert out[0]['role'] == 'system'
    assert out[0]['content'].startswith('You are a tutor.')
    assert '简体中文' in out[0]['content']
    assert out[1] == messages[1]
    # The caller's list must not be mutated: several call sites reuse the same prompt
    # across retries and would otherwise accumulate one directive per attempt.
    assert messages[0]['content'] == 'You are a tutor.'


def test_apply_inserts_a_system_turn_when_there_is_none():
    token = content_locale.set_locale('zh-Hans')
    try:
        out = content_locale.apply([{'role': 'user', 'content': 'hi'}])
    finally:
        content_locale.reset_locale(token)

    assert out[0]['role'] == 'system'
    assert len(out) == 2


def test_apply_is_a_no_op_for_english():
    messages = [{'role': 'system', 'content': 'You are a tutor.'}]
    token = content_locale.set_locale('en')
    try:
        out = content_locale.apply(messages)
    finally:
        content_locale.reset_locale(token)

    assert out == messages


def test_unsupported_locales_fall_back_rather_than_leak():
    token = content_locale.set_locale('de-DE')
    try:
        assert content_locale.current() == 'en'
        assert content_locale.directive() is None
    finally:
        content_locale.reset_locale(token)
