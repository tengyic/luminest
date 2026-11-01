import sys
sys.path.insert(0, '.')
from app.harness.teaching import ConceptFacts, build_evidence, default_profile, plan_session

p = default_profile()


def show(label, facts, state, **kw):
    ev = build_evidence(facts, state, mastery_threshold=p.difficulty.mastery_threshold, **kw)
    plan = plan_session(ev, facts, p, board_id='board-c1')
    print(f'{label:24s} move={plan.move.move:12s} {plan.move.score:.3f}  '
          f'loop={" -> ".join(plan.phases)}')
    print(f'{"":24s} channels={plan.modalities}')


math = ConceptFacts(id='c1', title='Fractions', strand='Algebra',
                    concept_type='quantitative_relation', has_lesson=True,
                    has_figure=True, dependant_count=3)

show('no attempts', math, {'mastery': 0.2, 'attempts': 0})
show('conceptual+board', math, {'mastery': 0.45, 'attempts': 4, 'correct_count': 2},
     top_error='conceptual')
show('procedural', math, {'mastery': 0.45, 'attempts': 4, 'correct_count': 2},
     top_error='procedural')
show('mastered+project', math, {'mastery': 0.92, 'attempts': 8, 'correct_count': 8},
     project_status='completed')
show('frustrated', math, {'mastery': 0.3, 'attempts': 5, 'correct_count': 1},
     elapsed_trend='much_faster')
show('60 min', math, {'mastery': 0.7, 'attempts': 5, 'correct_count': 4},
     session_minutes=60.0)
