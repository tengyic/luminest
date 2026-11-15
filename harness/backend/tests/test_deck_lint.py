"""The deck's house style, pinned as executable rules.

Every one of these was a real defect found by looking at an exported deck: a body line too
small to read from the back of a room, a photograph with no credit, an element hanging off
the canvas. The linter exists so the next deck cannot ship that way, and these tests exist
so the linter cannot quietly stop checking.
"""
from app import deck


def text_element(text: str, *, size: float, bold: bool = False, role: str = '',
                 x: int = 48, y: int = 36, w: int = 864, h: int = 78) -> dict:
    style = {'size': size}
    if bold:
        style['bold'] = True
    if role:
        style['role'] = role
    return {'kind': 'text', 'x': x, 'y': y, 'w': w, 'h': h, 'style': style,
            'text': {'paragraphs': [{'runs': [{'text': text}]}]}}


def bullets(*lines: str, size: float = 19, x: int = 48, y: int = 132,
            w: int = 560, h: int = 320) -> dict:
    return {'kind': 'text', 'x': x, 'y': y, 'w': w, 'h': h, 'style': {'size': size},
            'text': {'paragraphs': [{'runs': [{'text': line}]} for line in lines]}}


def photo(sha: str = 'a' * 64, attribution: str = 'Someone — CC BY-SA 4.0',
          x: int = 624, y: int = 132, w: int = 288, h: int = 320) -> dict:
    return {'kind': 'image', 'x': x, 'y': y, 'w': w, 'h': h, 'style': {},
            'image': {'sha256': sha, 'attribution': attribution}}


def doc(*elements: dict) -> dict:
    return {'slides': [{'id': 'slide-1', 'layout': 'idea', 'elements': list(elements)}]}


def rules(report: list[dict]) -> set[str]:
    return {row['rule'] for row in report}


def test_a_clean_slide_passes():
    assert deck.lint(doc(text_element('Cells', size=34, bold=True),
                         bullets('one', 'two'), photo())) == []


def test_a_title_below_the_floor_is_flagged():
    assert 'title_too_small' in rules(deck.lint(doc(text_element('Cells', size=20, bold=True))))


def test_a_body_below_the_floor_is_flagged():
    assert 'body_too_small' in rules(deck.lint(doc(bullets('one', size=12))))


def test_a_footnote_is_held_to_legibility_not_projection():
    """A credit line is quiet by design; flagging it would force every deck to shout."""
    report = deck.lint(doc(text_element('Source: example', size=12, role='footnote')))
    assert 'body_too_small' not in rules(report)


def test_a_footnote_below_legibility_is_still_flagged():
    report = deck.lint(doc(text_element('Source: example', size=8, role='footnote')))
    assert 'footnote_too_small' in rules(report)


def test_an_element_leaving_the_canvas_is_flagged():
    assert 'outside_canvas' in rules(deck.lint(doc(bullets('one', x=48, y=132, w=1000, h=320))))


def test_a_photograph_without_credit_is_flagged():
    assert 'image_without_credit' in rules(deck.lint(doc(photo(attribution=''))))


def test_an_image_without_bytes_is_flagged():
    assert 'image_without_bytes' in rules(deck.lint(doc(photo(sha=''))))


def test_too_many_bullets_is_flagged():
    assert 'too_many_bullets' in rules(deck.lint(doc(bullets(*['x'] * (deck.MAX_BULLETS + 1)))))


def test_exactly_the_cap_is_allowed():
    assert 'too_many_bullets' not in rules(deck.lint(doc(bullets(*['x'] * deck.MAX_BULLETS))))


def test_an_overlong_bullet_is_flagged():
    long_line = 'y' * (deck.MAX_BULLET_CHARS + 1)
    assert 'bullet_too_long' in rules(deck.lint(doc(bullets(long_line))))


def test_the_projection_would_have_clipped_it_before_the_linter_saw_it():
    """The deck projection clips to the cap, so a compliant deck cannot carry a violation.

    This is the pairing that matters: the fix is upstream of the check, not a raised limit.
    """
    payload = {'title': 'T', 'slides': [{'layout': 'idea', 'title': 'T',
                                         'bullets': ['z' * 400, 'b']}]}
    projected = deck.from_presentation(payload)
    assert deck.lint(projected) == []
