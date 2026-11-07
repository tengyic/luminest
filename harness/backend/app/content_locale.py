"""Which human language generated content must come back in.

The interface has been switchable between English and Simplified Chinese since the
language work landed, but that only moved the *chrome*: the tutor still answered in
English, generated questions still read as English, and the speech synthesiser still
spoke with the system default voice. A learner who picks Chinese and then gets an English
paragraph and an English voice has not switched anything that matters to them.

The choice travels as ``Accept-Language`` on every request (the native client sends it on
both the JSON and the streaming path). It is held in a ``ContextVar`` because the language
is a property of *this request*, not of the process: two learners on two machines — or a
test and a request — must not be able to change each other's output.

The directive is applied in one place, ``app.harness.provider``, so every generated
surface follows it: questions, tutor turns, decks, slides, simulations and lecture pages
all go through that wrapper. Scattering "answer in Chinese" across twenty prompt strings
is how half a product ends up translated.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Iterable, Sequence

DEFAULT = 'en'

#: The languages this build can render. Anything else falls back to ``DEFAULT`` rather than
#: being passed through to the model untranslated: an unsupported tag would otherwise
#: produce a mixture of the requested language and English, which reads worse than English.
SUPPORTED = ('en', 'zh-Hans')

_DISPLAY = {'en': 'English', 'zh-Hans': 'Simplified Chinese'}
_current: ContextVar[str] = ContextVar('luminest_content_locale', default=DEFAULT)


def from_header(value: str | None) -> str:
    """Best supported language from an ``Accept-Language`` header.

    Deliberately ignores q-values beyond ordering: a client that lists
    ``zh-Hans,en;q=0.9`` wants Chinese even when English is present, and this build only
    has two languages, so "first supported tag in preference order" is the whole decision.
    """
    if not value:
        return DEFAULT
    for part in value.split(','):
        tag = part.split(';')[0].strip().lower()
        if not tag or tag == '*':
            continue
        if tag.startswith('zh'):
            return 'zh-Hans'
        if tag.startswith('en'):
            return 'en'
    return DEFAULT


def set_locale(value: str) -> Token:
    return _current.set(value if value in SUPPORTED else DEFAULT)


def reset_locale(token: Token) -> None:
    _current.reset(token)


def current() -> str:
    return _current.get()


def display_name(code: str | None = None) -> str:
    return _DISPLAY.get(code or current(), _DISPLAY[DEFAULT])


def directive(code: str | None = None) -> str | None:
    """The sentence to append to a system prompt, or ``None`` for the development language.

    English is the language every prompt is already written in, so adding an instruction
    would spend tokens restating the default and occasionally make the model *more*
    verbose about it.
    """
    code = (code or current()).lower()
    if code.startswith('zh'):
        return (
            'Language: write every user-visible word in Simplified Chinese (简体中文), '
            'including headings, options, hints, explanations and feedback. Keep code, '
            'formulas, file paths and field names exactly as they are. Do not translate '
            'JSON keys.'
        )
    return None


def apply(messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return ``messages`` with the language directive attached to the system turn.

    Appended to an existing system message rather than inserted as a second one: several
    providers concatenate system messages in ways that vary by version, and a directive
    that lands after the persona reads as an afterthought the model may discount.
    """
    text = directive()
    if not text:
        return list(messages)
    out: list[dict[str, Any]] = [dict(message) for message in messages]
    for message in out:
        if message.get('role') == 'system':
            message['content'] = f"{message.get('content', '')}\n\n{text}".strip()
            return out
    out.insert(0, {'role': 'system', 'content': text})
    return out
