"""Modality routing: which representation to show this learner, and why.

The loop in :mod:`app.harness.loop` decides *what kind of interaction* comes next
(explain, retrieve, simulate, ...). This module answers the orthogonal question it left
implicit: given the same evidence, which **representation** gives the idea the best chance
of landing - static text, a diagram, spoken narration, or a guided interactive?

It is deliberately a set of named rules with reasons, not a model, so a decision can be
reviewed exactly like a move decision: same evidence, same channel.

What this module is NOT: a learning-styles detector. The meshing hypothesis - that
matching instruction to a diagnosed "visual/auditory/kinesthetic" style improves learning -
has failed its required crossover test (Pashler, McDaniel, Rohrer & Bjork 2008,
https://doi.org/10.1111/j.1539-6053.2009.01038.x; Rogowsky, Calhoun & Tallal 2015,
https://doi.org/10.1037/a0037478). The router therefore selects on *prior knowledge*,
*cognitive load* and the *transience* of the material, and it states that exclusion in its
own output. Self-reported style is never an input.
"""

from __future__ import annotations

from typing import Any, Mapping

#: The representations the router chooses between. Fixed on purpose: a bounded set can be
#: reasoned about and reviewed, whereas a free-form format space cannot.
CHANNELS = ('text', 'diagram', 'narration', 'interactive')

#: When each channel is the right answer, for the reviewable "alternatives" list.
CHANNEL_WHEN = {
    'text': 'Static, self-paced prose - safest for long or transient material and for experts.',
    'diagram': 'A labelled figure - adds a second code without duplicating the words.',
    'narration': 'A graphic with spoken narration - for a novice on short material.',
    'interactive': 'A guided simulation - to let a novice explore with a prediction prompt.',
}

#: The signal that must never drive the choice, stated in the output so a reader can check it.
EXCLUDED_INPUT = 'self-reported learning style (the meshing hypothesis fails its crossover test; Pashler et al. 2008)'

#: A session this long is treated as load, not as a reason to add more words.
LONG_SESSION_MINUTES = 45

ROUTING_RESEARCH_NOTE = (
    'Routing is on prior knowledge, cognitive load and material transience - not on a '
    'learning style, which is not a valid selector. The modality effect (graphic + spoken '
    'narration beats graphic + on-screen text, Ginns 2005, d~0.72) is real but conditional: '
    'it reverses for long or transient material (transient-information effect, Leahy & '
    'Sweller 2011) and for learners with high prior knowledge (expertise reversal, Kalyuga '
    'et al. 2003). The rules below encode those boundaries rather than assuming the effect '
    'always helps.'
)


def _novice(mastery: float, attempts: int) -> bool:
    """Low prior knowledge: little evidence, or a low estimate with some evidence."""
    return attempts <= 2 or mastery < 0.45


def _expert(mastery: float, attempts: int) -> bool:
    """High prior knowledge with enough evidence to believe it."""
    return mastery >= 0.75 and attempts >= 4


def _load_state(evidence: Mapping[str, Any]) -> str:
    """A coarse load/affect reading, from the same signals the loop already gathers."""
    sample = int(evidence.get('sample', 0) or 0)
    accuracy = evidence.get('recent_accuracy')
    trend = str(evidence.get('elapsed_trend') or 'insufficient')
    minutes = float(evidence.get('active_minutes_today', 0) or 0)
    if sample >= 3 and (accuracy or 0) <= 0.34 and trend in {'much_faster', 'faster'}:
        return 'frustrated'
    if minutes >= LONG_SESSION_MINUTES:
        return 'overloaded'
    return 'steady'


def _constraints(channel: str, *, expert: bool) -> list[str]:
    """The design constraints the chosen channel implies. Every one is checkable."""
    constraints = [
        'segment the material so the learner controls the pace',
        'keep labels adjacent to what they describe (spatial contiguity)',
    ]
    if channel == 'narration':
        constraints.append('never duplicate the narration as on-screen text (redundancy principle)')
    elif channel == 'diagram':
        constraints.append('signal the essential elements and drop decorative detail')
    elif channel == 'interactive':
        constraints.append('require a prediction before interaction and an explanation after (guided discovery)')
    elif channel == 'text':
        constraints.append('no audio narration layered over dense text (transient-information effect)')
        if expert:
            constraints.append('lead with a problem, not a worked example (expertise reversal)')
    return constraints


def route(evidence: Mapping[str, Any], *, transience: str | None = None,
          interactive_available: bool | None = None) -> dict[str, Any]:
    """Choose a representation for this learner on this concept, with a reason.

    ``evidence`` is the loop's gathered evidence dict (the same one ``loop.gather``
    returns). ``transience`` is the material's own property - ``'short'`` or ``'long'`` -
    and defaults to ``'short'`` because the router cannot measure it from behaviour alone.
    ``interactive_available`` defaults to whether a figure/simulation exists for the
    concept. Both are explicit so the caller can override them rather than have the router
    guess.

    Returns a reviewable dict: the ``channel``, a plain-language ``reason``, the
    ``constraints`` the choice implies, the ``alternatives`` not chosen, the ``signals``
    used, and the ``excluded`` input that must never drive it.
    """
    mastery = float(evidence.get('mastery', 0.15) or 0.15)
    attempts = int(evidence.get('attempts', 0) or 0)
    transience = 'long' if transience == 'long' else 'short'
    if interactive_available is None:
        interactive_available = bool(evidence.get('has_figure'))

    novice = _novice(mastery, attempts)
    expert = _expert(mastery, attempts)
    load = _load_state(evidence)

    if load == 'frustrated':
        channel = 'diagram'
        reason = ('Recent attempts are fast and wrong, so the current representation is not '
                  'landing. A diagram changes the frame without adding verbal load.')
    elif load == 'overloaded':
        channel = 'text'
        reason = ('The session is already long. A short, self-paced static segment respects '
                  'the load instead of adding more.')
    elif expert:
        channel = 'text'
        reason = ('Prior knowledge is high, so extra guidance and dual-modality become '
                  'redundant load. Lead with a problem, not an example (expertise reversal).')
    elif transience == 'long':
        channel = 'text'
        reason = ('The material is long or transient, so spoken narration would overload '
                  'working memory. Static text lets the learner re-read (transient-information '
                  'effect).')
    elif novice and interactive_available:
        channel = 'interactive'
        reason = ('The learner is new to this idea and a guided simulation is available. '
                  'Exploration with a prediction prompt builds the concept (guided discovery).')
    elif novice:
        channel = 'narration'
        reason = ('For a novice on short material, a graphic with spoken narration beats the '
                  'same graphic with on-screen text (modality effect).')
    else:
        channel = 'diagram'
        reason = ('Prior knowledge is developing, so a labelled diagram adds a second code '
                  'without duplicating the words.')

    return {
        'channel': channel,
        'reason': reason,
        'constraints': _constraints(channel, expert=expert),
        'alternatives': [{'channel': other, 'when': CHANNEL_WHEN[other]}
                         for other in CHANNELS if other != channel],
        'signals': {
            'prior_knowledge': 'expert' if expert else ('novice' if novice else 'developing'),
            'mastery': round(mastery, 4),
            'attempts': attempts,
            'load': load,
            'transience': transience,
            'interactive_available': bool(interactive_available),
        },
        'excluded': EXCLUDED_INPUT,
        'research_note': ROUTING_RESEARCH_NOTE,
    }


def describe() -> dict[str, Any]:
    """The router's posture, for the status endpoint and the transparency panel."""
    return {
        'channels': list(CHANNELS),
        'when': dict(CHANNEL_WHEN),
        'inputs': ['prior knowledge', 'cognitive load', 'material transience', 'interactive availability'],
        'excluded': EXCLUDED_INPUT,
        'long_session_minutes': LONG_SESSION_MINUTES,
        'research_note': ROUTING_RESEARCH_NOTE,
    }
