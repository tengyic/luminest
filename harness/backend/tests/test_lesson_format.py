"""The lesson-format contract: shape of a turn, not tone.

The conduct block already says how to hold a learner - pump before hint, name the error,
never answer first. It does not say what a message looks like, and that is where a tutor
fails in practice: it explains correctly and then keeps going, computes the value it just
asked the learner for, or asks three questions and waits for one answer.

These tests pin the shape in both prompts, and pin that the simulation clause appears only
when the tool that can honour it exists on the instance.
"""
from pathlib import Path

from app.harness import prompt
from app.harness.conduct import LESSON_FORMAT, LESSON_FORMAT_RULES, lesson_format

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- the block itself

def test_the_format_forbids_the_five_failures_that_matter():
    """Each of these has been observed as a real failure, not a hypothetical one."""
    text = LESSON_FORMAT
    assert 'Never state the value you just asked' in text or \
           'answering your own question' in text
    assert 'Never send a complete solution' in text or 'sending a whole solution' in text
    assert 'exactly one per turn' in text.casefold()
    assert 'one step per message' in text
    assert 'before you name any rule' in text


def test_the_format_puts_contrast_before_the_formula():
    """A formula introduced before the learner can see why it exists is memorisation."""
    assert 'contrast' in LESSON_FORMAT.casefold()
    assert LESSON_FORMAT.index('contrast') < LESSON_FORMAT.index('counting argument')


def test_a_guided_solution_asks_for_one_computation_and_stops():
    assert 'single computation you cannot do for them' in LESSON_FORMAT
    assert 'repair that step instead of advancing' in LESSON_FORMAT


def test_wrong_options_must_name_a_real_mistake():
    assert 'forgetting to divide by r!' in LESSON_FORMAT
    assert 'never inside the option' in LESSON_FORMAT


# ---------------------------------------------------------------- conditional clause

def test_the_simulation_clause_appears_only_when_the_tool_exists():
    """A prompt that names a tool the build does not have costs a turn to discover the lie."""
    without = lesson_format()
    with_tool = lesson_format(['write_simulation', 'build_figure'])
    assert 'simulation tool is available' not in without
    assert 'simulation tool is available' in with_tool
    assert with_tool.startswith(without)


# ---------------------------------------------------------------- both prompts carry it

def test_the_agent_prompt_carries_the_format():
    rendered = prompt.build(learner_name='Ada', concept_title='Combinations')
    assert LESSON_FORMAT in rendered


def test_the_agent_prompt_names_the_simulation_tool_only_when_it_is_available():
    """``write_simulation`` is teacher-gated, so a learner-only instance must not be told
    it can build one."""
    rendered = prompt.build()
    catalogue = {spec['name'] for spec in prompt.toolbox.available_catalogue()}
    assert ('simulation tool is available' in rendered) == ('write_simulation' in catalogue)


def test_the_transparency_payload_exposes_the_shape_rules():
    payload = prompt.payload()
    assert payload['format']
    rules = {rule['rule'] for rule in payload['format_rules']}
    assert {'one_question', 'never_answer_your_own_question', 'no_dumping'} <= rules
    assert all(rule['text'] for rule in payload['format_rules'])
    assert len(LESSON_FORMAT_RULES) == len(payload['format_rules'])


def test_the_chat_tutor_wires_the_same_block_into_its_prompt():
    """The chat path in ``app.tutor`` assembles its own system string, so the block has to
    be wired there separately. Checked structurally: the call must be present, and it must
    be the same function rather than a copy that can drift.
    """
    import app.tutor as tutor

    assert tutor.lesson_format is lesson_format
    source = (ROOT / 'app' / 'tutor.py').read_text(encoding='utf-8')
    assert 'lesson_format()' in source
