"""Presentation-surface decisions: what the learner is *looking at* this turn.

The other decision layers answer different questions and must stay separate:

* ``policy``  - which teaching move (explain, retrieve, consolidate);
* ``session`` - which phase of the session and which channel the move runs through;
* ``procedure`` - which activities, in what order, bound to which artifacts;
* ``supervision`` - whether to interrupt at all;
* ``classroom`` - the polling state machine.

This module answers one orthogonal question: **which surface is in front of the
learner while that activity happens** - a video playing in the browser, the slide
deck (the exported .pptx), the shared whiteboard being drawn on, or plain chat.
It decides nothing about *what* is taught: the activity and its bound artifact are
already fixed by ``procedure`` by the time a surface is chosen. That separation is
load-bearing. A deck block whose surface was swapped for a whiteboard would still
promise five slides, and a learner would be asked to look at a deck that was never
presented - "a plan is a promise" broken by a display decision.

Three properties hold throughout:

* **Only existing artifacts are promised.** A surface whose artifact does not exist
  is never chosen. The compiler binds the deck sections and the video's embed URL;
  the router reads those bindings. A missing asset degrades to a declared fallback
  with a named reason, never to a plausible-looking empty player.
* **Switching is a decision, not a side effect.** Every surface change carries a
  reason and is recorded by the caller. Repeating a surface is not a switch. The
  toolbox refuses a presentation tool that belongs to a surface other than the one
  currently active, so the teacher cannot drift between video, slides and board by
  accident while the learner is trying to follow one thing.
* **An interruption does not advance the deck.** An interrupted turn holds the
  surface the learner was already looking at. The one exception is an explicit
  ``intent='draw'`` - answering a conceptual question by sketching it - which
  records ``resume_surface`` so the caller can put the deck back afterwards. This
  is the same invariant the captured deck session pinned: an interruption answers
  on the current slide, and only *resuming* the lecture moves the cursor.

The module is pure: no database, no model, no network, no clock. The same evidence
and the same bound artifacts always produce the same decision, which is what makes
a live lesson reviewable after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

#: The surfaces the teacher may choose between. A bounded set on purpose: a free-form
#: format space cannot be reviewed, and a client cannot render a surface it has never
#: heard of. ``chat`` is a real answer - a diagnostic, a scored question or a closing
#: turn has no presentation surface to switch to.
SURFACES: tuple[str, ...] = ('deck', 'video', 'whiteboard', 'chat')

#: Why each surface exists, and when it is the right answer. Published in ``describe``
#: and in every decision's ``alternatives``, so a learner or an operator can ask
#: "why a video?" and get the condition rather than a shrug.
SURFACE_WHEN: dict[str, str] = {
    'deck': 'A generated slide deck (exported .pptx) - ordered, revisitable, built '
            'from this concept\'s own authored lesson.',
    'video': 'A curated, licence-cleared video played in the browser - orientation '
             'for a first exposure to a process or a phenomenon.',
    'whiteboard': 'The shared Stage board, drawn on live - for a relationship that '
                  'has to be made visible and annotated while it is discussed.',
    'chat': 'No presentation surface - a scored question, a short answer, or the '
            'close of a session.',
}

#: The presentation tools each surface owns. These are the *only* tools the boundary
#: enforces; neutral tools (reading a concept, checking evidence, speaking, asking a
#: question) work on every surface. A tool that is not in this map is neutral by
#: construction, so adding a new toolbox tool cannot silently bypass the boundary -
#: it simply has no surface until someone deliberately assigns it one.
PRESENTATION_TOOLS: dict[str, tuple[str, ...]] = {
    'deck': ('deck_control', 'generate_slides', 'build_presentation'),
    'video': ('find_video', 'search_videos', 'browser_snapshot'),
    'whiteboard': ('whiteboard_read', 'whiteboard_apply', 'whiteboard_write',
                   'whiteboard_place_image', 'draw_diagram'),
    'chat': (),
}

#: The decision tool itself is surface-neutral: it is how a teacher *changes* the
#: surface, so it must be callable from every one of them.
NEUTRAL_DECISION_TOOL = 'stage_surface'

#: Blocks whose bound artifact is a presentation surface. Everything else is chat
#: unless the evidence or an explicit draw intent says otherwise.
_PRIMARY_BY_KIND: dict[str, str] = {
    'deck': 'deck',
    'video': 'video',
    'simulation': 'chat',
    'diagnostic': 'chat',
    'practice': 'chat',
    'discussion': 'whiteboard',
    'worked_example': 'chat',
    'explain': 'chat',
    'recap': 'chat',
    'close': 'chat',
}

#: A wrong model is in the learner's words, not in their marks. On these blocks the
#: honest repair is to draw the relationship on the board rather than restate it.
_DRAWABLE_KINDS = frozenset({'discussion', 'explain', 'worked_example'})

_EXCLUDED_INPUT = ('self-reported learning style (the meshing hypothesis fails its '
                   'crossover test; Pashler et al. 2008)')


def tool_surface(name: str) -> str | None:
    """Which surface owns a presentation tool, or ``None`` for a neutral tool."""
    for surface, names in PRESENTATION_TOOLS.items():
        if name in names:
            return surface
    return None


def available_surfaces(assets: Mapping[str, Any] | None = None,
                       *, board_available: bool = True) -> dict[str, Any]:
    """An honest inventory of what this lesson can actually put on screen.

    ``assets`` is the compiler's ``ProcedureAssets.summary()`` shape: ``deck`` and
    ``video`` are either ``None`` or a bound artifact. A run may also carry a
    materialised deck id, which counts as ready even before the compiler's summary
    is consulted. The whiteboard is a capability rather than an artifact - the
    Stage pairs every concept with a board created on demand - so it is ready unless
    the caller says the board surface is disabled.

    Every refusal carries a reason. "no video" and "a video exists but was withdrawn"
    are different facts, and a client must be able to say which one happened.
    """
    data = dict(assets or {})
    deck = data.get('deck')
    video = data.get('video')
    deck_ready = bool(isinstance(deck, Mapping) and (
        int(deck.get('slides') or 0) > 0 or bool(deck.get('artifact_id'))))
    video_ready = bool(isinstance(video, Mapping) and (
        str(video.get('embed_url') or '') or str(video.get('watch_url') or '')))
    reasons: dict[str, str] = {}
    if not deck_ready:
        reasons['deck'] = str(data.get('unavailable', {}).get('deck')
                              or 'No authored lesson exists to build a deck from.')
    if not video_ready:
        reasons['video'] = str(data.get('unavailable', {}).get('video')
                               or 'No verified, concept-specific video is curated '
                                  'for this course.')
    if not board_available:
        reasons['whiteboard'] = 'The shared Stage board is disabled on this instance.'
    return {'deck': deck_ready, 'video': video_ready,
            'whiteboard': bool(board_available), 'chat': True,
            'reasons': reasons}


def primary_surface(block: Mapping[str, Any] | None = None) -> str:
    """The surface the *compiled activity* promises, independent of live evidence.

    Derived from the block's kind and its bound artifact, never from the model's
    preference. A deck block is a deck surface even on a surface-less client; the
    client then reports a declared fallback rather than the teacher quietly
    substituting prose for five promised slides.
    """
    data = dict(block or {})
    kind = str(data.get('kind') or 'explain')
    return _PRIMARY_BY_KIND.get(kind, 'chat')


@dataclass(frozen=True)
class SurfaceDecision:
    """One reviewable decision about what the learner is looking at."""

    surface: str
    why: str
    source: str = 'compiled'            # compiled | interruption | teacher | ceiling
    primary: str = 'chat'
    switch: bool = False
    resume_surface: str = ''
    tools: tuple[str, ...] = ()
    fallback: dict[str, str] = field(default_factory=dict)
    alternatives: tuple[dict[str, Any], ...] = ()
    signals: dict[str, Any] = field(default_factory=dict)
    available: dict[str, Any] = field(default_factory=dict)
    excluded: str = _EXCLUDED_INPUT

    def to_dict(self) -> dict[str, Any]:
        return {'surface': self.surface, 'why': self.why, 'source': self.source,
                'primary': self.primary, 'switch': self.switch,
                'resume_surface': self.resume_surface, 'tools': list(self.tools),
                'fallback': dict(self.fallback),
                'alternatives': [dict(row) for row in self.alternatives],
                'signals': dict(self.signals), 'available': dict(self.available),
                'excluded': self.excluded}


def _fallback_for(surface: str, available: Mapping[str, Any]) -> dict[str, str]:
    """Where to go if the chosen surface cannot be rendered at runtime."""
    if surface == 'video':
        target = 'deck' if available.get('deck') else 'chat'
        return {'surface': target,
                'reason': ('The browser video cannot be opened under its licence or '
                           'the embed failed verification. '
                           + (f'Fall back to the bound deck: {SURFACE_WHEN["deck"]}'
                              if target == 'deck' else
                              'No deck exists, so answer in chat and say the video '
                              'was unavailable.')),
                'kind': 'declared_fallback'}
    if surface == 'deck':
        return {'surface': 'chat',
                'reason': 'The bound deck could not be built or opened. Teach the '
                          'current block in chat and say the slides were unavailable; '
                          'do not describe a slide the learner cannot see.',
                'kind': 'declared_fallback'}
    if surface == 'whiteboard':
        return {'surface': 'chat',
                'reason': 'The shared board refused the drawing. Answer in chat and '
                          'say the diagram could not be drawn; never claim it is on '
                          'the board.',
                'kind': 'declared_fallback'}
    return {}


def declared_fallback(surface: str, available: Mapping[str, Any]) -> dict[str, str]:
    """Public form of :func:`_fallback_for`, for a client refusing an absent surface."""
    return _fallback_for(surface, available)


def _alternatives(surface: str, available: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    reasons = dict(available.get('reasons') or {})
    return tuple(
        {'surface': other, 'when': SURFACE_WHEN[other],
         'available': bool(available.get(other)),
         'reason_unavailable': reasons.get(other, '')}
        for other in SURFACES if other != surface)


def choose_surface(*, block: Mapping[str, Any] | None = None,
                   evidence: Mapping[str, Any] | None = None,
                   available: Mapping[str, Any] | None = None,
                   current: str = '', interrupted: bool = False,
                   intent: str = '', allowed: Sequence[str] = ()) -> SurfaceDecision:
    """Choose the presentation surface for one live turn, with a stated reason.

    ``block`` is the compiled procedure block (``kind`` plus its bound ``artifact``).
    ``evidence`` is the same learner evidence the move policy reads - only
    ``top_error``, ``mastery``, ``attempts`` and ``frustrated`` are used here.
    ``available`` is :func:`available_surfaces`; ``current`` is the surface the
    learner is already looking at; ``interrupted`` is the turn's barge-in signal.
    ``intent`` is an explicit teacher request (``'draw'``) and never a detector.

    The rules fire in order. Every branch states why the surface fits and what to do
    when its artifact is missing; no branch invents an asset that was not bound.
    """
    data = dict(block or {})
    ev = dict(evidence or {})
    avail = dict(available or available_surfaces())
    reasons = dict(avail.get('reasons') or {})
    kind = str(data.get('kind') or 'explain')
    primary = primary_surface(data)
    ceiling = tuple(allowed) if allowed else SURFACES
    current = current if current in SURFACES else ''
    intent = str(intent or '').strip().lower()

    signals = {'block_kind': kind, 'top_error': str(ev.get('top_error') or ''),
               'mastery': round(float(ev.get('mastery') or 0.0), 4),
               'attempts': int(ev.get('attempts') or 0),
               'frustrated': bool(ev.get('frustrated')),
               'interrupted': bool(interrupted), 'intent': intent,
               'current': current, 'primary': primary}

    # Rule 1 - an interruption holds the surface in front of the learner. This is
    # where the deck invariant lives: answering a question does not turn a page.
    if interrupted:
        if intent == 'draw' and avail.get('whiteboard'):
            held = current or primary
            return _build('whiteboard',
                          'The learner interrupted with a question that needs a '
                          'sketch. Draw the relationship on the shared board to answer '
                          'it, then return to the surface they were on. The deck '
                          'cursor does not move.', source='interruption',
                          primary=primary, current=current, available=avail,
                          signals=signals, resume_surface=held, ceiling=ceiling)
        held = current or primary
        if not avail.get(held, False):
            held = 'chat'
        return _build(held,
                      'The learner interrupted you mid-sentence. Answer on the surface '
                      'already in front of them: switching the display now would take '
                      'away the very thing their question refers to, and an '
                      'interruption must not advance the deck.',
                      source='interruption', primary=primary, current=current,
                      available=avail, signals=signals, ceiling=ceiling)

    # Rule 2 - the compiled activity owns its artifact. A deck presents the slides it
    # bound; a video opens the embed it bound. Missing artifact -> declared fallback.
    if primary in ('deck', 'video'):
        if avail.get(primary):
            why = (f'Block {kind!r} binds a generated slide deck with '
                   f'{int(((data.get("artifact") or {}).get("slide_count") or 0))} '
                   'slide(s); presenting it is the activity, not a decoration.'
                   if primary == 'deck' else
                   'Block \'video\' binds a verified, concept-specific embed; play it '
                   'in the browser under its licence on first exposure, rather than '
                   'ingesting its content or describing it in prose.')
            return _build(primary, why, source='compiled', primary=primary,
                          current=current, available=avail, signals=signals,
                          ceiling=ceiling)
        target = 'chat' if primary == 'deck' else ('deck' if avail.get('deck') else 'chat')
        return _build(target,
                      f'The {primary} surface was compiled for this block but its '
                      f'artifact is not available ({reasons.get(primary, "not bound")}). '
                      'Declared fallback, with the reason published; nothing is faked.',
                      source='ceiling', primary=primary, current=current,
                      available=avail, signals=signals, ceiling=ceiling)

    # Rule 3 - an explicit request to draw. Not a detector: the caller (the teacher)
    # decided, and the decision is recorded with that intent.
    if intent == 'draw' and avail.get('whiteboard'):
        return _build('whiteboard',
                      'The teacher chose to draw this step. A live sketch on the shared '
                      'board lets the relationship be annotated while it is discussed.',
                      source='teacher', primary=primary, current=current,
                      available=avail, signals=signals, ceiling=ceiling)

    # Rule 4 - a conceptual error on a discussion/explanation/example block wants the
    # structure visible. A wrong mental model is repaired by drawing it, not by
    # restating the paragraph that produced it.
    if (kind in _DRAWABLE_KINDS and ev.get('top_error') == 'conceptual'
            and not ev.get('frustrated') and avail.get('whiteboard')):
        return _build('whiteboard',
                      'The recorded errors are conceptual and this block asks the '
                      'learner to reason about the relationship. Drawing it on the '
                      'shared board makes the structure visible and correctable; the '
                      'same words in chat would not.',
                      source='teacher', primary=primary, current=current,
                      available=avail, signals=signals, ceiling=ceiling)

    # Rule 5 - a frustrated learner stays in chat. Adding a new display competes with
    # the one that is already not landing.
    if ev.get('frustrated'):
        return _build('chat',
                      'Recent attempts are fast and wrong; a new surface now would add '
                      'load rather than repair the one that is not landing.',
                      source='compiled', primary=primary, current=current,
                      available=avail, signals=signals, ceiling=ceiling)

    # Rule 6 - nothing is being presented. Diagnostics, scored questions, simulations
    # and the close run in chat or in their own first-party pane.
    return _build(primary or 'chat',
                  f'Block {kind!r} has no presentation artifact to switch to '
                  f'({SURFACE_WHEN["chat"]})',
                  source='compiled', primary=primary, current=current,
                  available=avail, signals=signals, ceiling=ceiling)


def _build(surface: str, why: str, *, source: str, primary: str, current: str,
           available: Mapping[str, Any], signals: Mapping[str, Any],
           ceiling: Sequence[str], resume_surface: str = '') -> SurfaceDecision:
    """Apply the instance ceiling and the no-churn rule to a chosen surface."""
    chosen = surface
    reason = why
    if chosen not in ceiling:
        # Degrade in a fixed order: chat is always renderable; the compiled primary is
        # next if it is both allowed and available.
        candidate = next((name for name in ('chat', primary, 'deck')
                          if name in ceiling and
                          (name == 'chat' or available.get(name, False))), None)
        if candidate:
            reason = (f'{chosen!r} is switched off on this instance, so the surface '
                      f'degrades to {candidate!r}. ' + why)
            chosen = candidate
            source = 'ceiling'
    if not available.get(chosen, False) and chosen != 'chat':
        reason = (f'{chosen!r} has no bound artifact on this concept '
                  f'({dict(available.get("reasons") or {}).get(chosen, "not bound")}). '
                  'Declared fallback to chat. ' + why)
        chosen = 'chat'
        source = 'ceiling'
    switch = bool(current and current != chosen)
    return SurfaceDecision(
        surface=chosen, why=reason, source=source, primary=primary, switch=switch,
        resume_surface=resume_surface, tools=PRESENTATION_TOOLS.get(chosen, ()),
        fallback=_fallback_for(chosen, available),
        alternatives=_alternatives(chosen, available),
        signals=dict(signals), available=dict(available))


def describe() -> dict[str, Any]:
    """The router's posture, for the live-session catalog and transparency panel."""
    return {'surfaces': list(SURFACES), 'when': dict(SURFACE_WHEN),
            'tools': {name: list(names) for name, names in PRESENTATION_TOOLS.items()},
            'decision_tool': NEUTRAL_DECISION_TOOL,
            'inputs': ['the compiled activity and its bound artifact',
                       'learner evidence (top error, frustration)',
                       'the current surface', 'the interruption signal',
                       'the teacher\'s explicit draw intent'],
            'excluded': _EXCLUDED_INPUT,
            'invariants': ['an interruption never advances the deck',
                           'only a bound artifact may be promised',
                           'a surface switch carries a reason and is recorded']}
