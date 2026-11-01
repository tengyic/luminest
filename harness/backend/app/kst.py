"""Knowledge Space Theory (KST) as the assessment layer.

Builds the prerequisite-closed knowledge states (down-sets / ideals) of a
prerequisite DAG and uses them for diagnostic gap finding: which concepts to
probe next so that the fewest questions disambiguate the learner's knowledge
state, and which gaps are consistent with the evidence so far.

Academic basis (implemented from the papers, not cloned from any product):

- Doignon & Falmagne (1985), "Spaces for the assessment of knowledge",
  International Journal of Man-Machine Studies 23. -- knowledge states as
  prerequisite-closed sets; the lattice structure of learning spaces.
- Falmagne & Doignon (2011), "Learning Spaces" (Springer). -- efficient
  adaptive assessment over the state lattice.

NOTE (patent flag, for counsel review): ALEKS holds patents on its specific
assessment implementation (e.g. US Patent 10,713,965). This module implements
the published academic theory of knowledge spaces on top of OUR curriculum
graph with our own probe-selection rule; it deliberately does not reproduce
ALEKS's elicitation procedure or any other claim of that patent. Legal review
is requested before any commercial deployment of this layer.

Not a clone: the state lattice here is derived at runtime from OUR graph
(``app.curriculum.KNOWLEDGE_GRAPH``), and probe choice is a plain entropy split
over the version space of consistent states -- a textbook procedure, not
ALEKS's method.

Two modes, chosen automatically:

- ``exact``: the DAG's down-sets are few enough to enumerate completely (small
  spaces, and every unit test). Probabilities are exact frequencies.
- ``sampled``: the DAG has more states than ``MAX_STATES`` (the real 164-node
  math graph does). Consistent states are estimated by a deterministic, seeded
  constructive sampler -- every returned state IS a true knowledge state, the
  probabilities are frequency estimates over that sample, and every number is
  labelled as an estimate. Seeded, so two runs agree.
"""

from __future__ import annotations

import hashlib
import math
import random

#: Safety cap on exact enumeration. The 164-node math DAG exceeds it; the cap
#: exists so a denser future graph degrades into sampling instead of hanging.
MAX_STATES = 500_000
#: Sample size in sampled mode. Large enough for stable orderings, small enough
#: to be fast; seeded, so results are reproducible.
SAMPLE_SIZE = 20_000
SAMPLE_SEED = 20261011


class TooManyStates(ValueError):
    pass


class KnowledgeSpace:
    """The lattice of prerequisite-closed knowledge states of a DAG.

    ``prereqs`` maps concept_id -> list of prerequisite concept_ids. A knowledge
    state is a set S of concepts such that every prerequisite of a member is
    also a member (a down-set/ideal). Under Doignon & Falmagne's framework,
    assuming a concept can be known only once its prerequisites are known makes
    these down-sets exactly the feasible knowledge states.
    """

    def __init__(self, prereqs: dict[str, list[str]], max_states: int = MAX_STATES,
                 sample_size: int = SAMPLE_SIZE, seed: int = SAMPLE_SEED):
        self.prereqs = {k: list(v) for k, v in prereqs.items()}
        self.concepts = sorted(self.prereqs)
        self.sample_size = sample_size
        self.seed = seed
        self._validate()
        self.order = self._topological_order()
        try:
            self.states = self._enumerate_states(max_states)
            self.exact = True
        except TooManyStates:
            self.states = []
            self.exact = False

    # ------------------------------------------------------------ construction

    def _validate(self):
        for node, pres in self.prereqs.items():
            for p in pres:
                if p not in self.prereqs:
                    raise ValueError(f'Unknown prerequisite {p!r} of {node!r}')
        if len(self._topological_order()) != len(self.prereqs):
            raise ValueError('Prerequisite graph contains a cycle')

    def _topological_order(self) -> list[str]:
        remaining = {n: set(p) for n, p in self.prereqs.items()}
        order = []
        while remaining:
            ready = sorted(n for n, pres in remaining.items() if not pres)
            if not ready:
                raise ValueError('Prerequisite graph contains a cycle')
            for n in ready:
                order.append(n)
                del remaining[n]
            for pres in remaining.values():
                pres.difference_update(ready)
        return order

    def _enumerate_states(self, max_states: int) -> list[frozenset]:
        """All down-sets. Branch on each node in topological order: it may be
        included only if all its prerequisites are already included; excluding
        is always allowed. The prerequisite rule prunes the search hard."""
        states: list[frozenset] = []

        def walk(index: int, current: frozenset):
            if len(states) > max_states:
                raise TooManyStates(f'More than {max_states} knowledge states')
            if index == len(self.order):
                states.append(current)
                return
            node = self.order[index]
            if all(p in current for p in self.prereqs[node]):
                walk(index + 1, current | {node})
            walk(index + 1, current)

        walk(0, frozenset())
        return states

    def closure(self, known: set[str]) -> frozenset:
        """The prerequisite closure of ``known``: known plus every transitive
        prerequisite. Any knowledge state containing ``known`` must contain at
        least this much. (Empty input -> empty closure.)"""
        state = set(known)
        frontier = list(known)
        while frontier:
            node = frontier.pop()
            for p in self.prereqs[node]:
                if p not in state:
                    state.add(p)
                    frontier.append(p)
        return frozenset(state)

    # ------------------------------------------------------------------ states

    def _observation_seed(self, observations: dict[str, bool]) -> int:
        payload = ','.join(f'{k}={int(bool(v))}' for k, v in sorted(observations.items()))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return self.seed ^ int(digest[:16], 16)

    def _sample_consistent(self, observations: dict[str, bool]) -> list[frozenset] | None:
        """Seeded constructive sampler for consistent knowledge states.

        Walks the DAG in topological order forcing observed-known concepts (and
        their prerequisite closure) in, observed-unknown concepts out, and
        flipping a fair coin for everything else that is reachable. Every
        emitted state is a genuine down-set consistent with the observations,
        and every consistent state has positive sampling probability.
        Returns None when the observations contradict the prerequisite
        structure (an unknown concept lies inside the closure of the knowns).
        """
        known = {k for k, v in observations.items() if v}
        unknown = {k for k, v in observations.items() if not v}
        required = self.closure(known)
        if required & unknown:
            return None
        rng = random.Random(self._observation_seed(observations))
        samples = []
        for _ in range(self.sample_size):
            state = set()
            for node in self.order:
                eligible = all(p in state for p in self.prereqs[node])
                if node in unknown:
                    continue  # forced out
                if node in required:
                    if eligible:  # always eligible: closure is prerequisite-closed
                        state.add(node)
                    continue
                if eligible and rng.random() < 0.5:
                    state.add(node)
            samples.append(frozenset(state))
        return samples

    def consistent_states(self, observations: dict[str, bool]) -> list[frozenset] | None:
        """States (or, in sampled mode, a seeded representative sample of states)
        agreeing with every observed response. None means the observations are
        inconsistent with the prerequisite structure."""
        if self.exact:
            known = {k for k, v in observations.items() if v}
            unknown = {k for k, v in observations.items() if not v}
            required = self.closure(known)
            if required & unknown:
                return None
            return [s for s in self.states if not (unknown & s) and required <= s]
        return self._sample_consistent(observations)

    # --------------------------------------------------------------- diagnosis

    def probability_known(self, observations: dict[str, bool]) -> dict[str, float]:
        """For each concept, the fraction of consistent states that contain it.
        Exact in exact mode; a seeded frequency estimate in sampled mode."""
        consistent = self.consistent_states(observations)
        if not consistent:
            return {}
        counts: dict[str, int] = {c: 0 for c in self.concepts}
        for state in consistent:
            for c in state:
                counts[c] += 1
        n = len(consistent)
        return {c: counts[c] / n for c in self.concepts}

    def next_probe(self, observations: dict[str, bool]) -> dict:
        """The concept whose yes/no response most evenly splits the version space
        of consistent states -- the greedy maximum-entropy probe, the standard
        efficient-assessment move in KST. With noiseless binary responses this
        halves the version space each round, so about log2(|version space|)
        probes suffice to disambiguate the learner's state."""
        consistent = self.consistent_states(observations)
        if not consistent:
            return {'concept_id': None, 'why': 'Observations contradict the prerequisite structure.'}
        if len(consistent) <= 1 and self.exact:
            return {'concept_id': None, 'why': 'Knowledge state already disambiguated.'}
        observed = {k for k, v in observations.items() if v is not None}
        p_known = self.probability_known(observations)
        candidates = []
        for c, p in p_known.items():
            if c in observed or p in (0.0, 1.0):
                continue
            # Only probe concepts the learner could actually attempt: the concept
            # must be reachable (all prerequisites known) in some consistent
            # state, otherwise the response is forced and carries no information.
            reachable = any(set(self.prereqs[c]) <= set(state) for state in consistent)
            if reachable:
                candidates.append((abs(2 * p - 1), c, p))
        if not candidates:
            return {'concept_id': None,
                    'why': 'No unobserved, reachable, uncertain concept remains; '
                           'consistent states differ only in unprobeable concepts.'}
        _, concept, p = min(candidates)
        mode = 'exact' if self.exact else 'seeded-sample estimate'
        return {'concept_id': concept,
                'p_known': p,
                'version_space': len(consistent),
                'mode': mode,
                'why': (f'Maximum-entropy probe over the prerequisite lattice ({mode}): '
                        f'{len(consistent)} consistent knowledge states '
                        f'{"(sampled)" if not self.exact else ""} and this concept '
                        f'splits them closest to 50/50 (P(known)={p:.2f}). '
                        'KST per Doignon & Falmagne 1985; not ALEKS.')}

    def diagnostic_gaps(self, observations: dict[str, bool]) -> dict:
        """The gap report: what the evidence pins down, and what it does not."""
        consistent = self.consistent_states(observations)
        if not consistent:
            return {'error': 'Observations are inconsistent with the prerequisite '
                             'structure (a failed response sits inside the closure '
                             'of the successes); no knowledge state fits.'}
        p_known = self.probability_known(observations)
        observed = {k for k, v in observations.items() if v is not None}
        surely_known = sorted(c for c in self.concepts
                              if p_known[c] == 1.0 and c not in observed)
        surely_missing = sorted(c for c in self.concepts
                                if p_known[c] == 0.0 and c not in observed)
        uncertain = sorted((c for c in self.concepts if c not in observed),
                           key=lambda c: p_known[c])
        gaps = [{'concept_id': c, 'p_known': p_known[c]}
                for c in uncertain if p_known[c] < 0.5]
        sampled = not self.exact
        distinct = len(set(consistent)) if sampled else len(consistent)
        return {
            'mode': 'exact' if not sampled else 'sampled (seeded, reproducible)',
            'n_states_total': len(self.states) if not sampled else None,
            'n_states_consistent': len(consistent),
            'n_states_consistent_note': ('frequency-estimate sample' if sampled
                                         else 'exactly enumerated'),
            'min_probes_to_disambiguate': (max(0, math.ceil(math.log2(len(consistent))))
                                           if not sampled and len(consistent) > 1
                                           else max(0, math.ceil(math.log2(distinct))) if distinct > 1 else 0),
            'min_probes_note': ('lower bound from the sampled distinct states' if sampled
                                else 'log2 of the consistent version space'),
            'surely_known': surely_known,
            'surely_missing': surely_missing,
            'uncertain_by_p_known': [{'concept_id': c, 'p_known': p_known[c]} for c in uncertain],
            'gaps': gaps,
            'next_probe': self.next_probe(observations),
            'method': ('Knowledge Space Theory (Doignon & Falmagne 1985; Falmagne & '
                       'Doignon 2011): prerequisite-closed states of our curriculum '
                       'DAG, version-space filtering on observed responses, greedy '
                       'maximum-entropy probing. Implemented from the academic '
                       'literature; not ALEKS (patent-flagged for counsel review).'),
        }


def from_knowledge_graph(kg) -> KnowledgeSpace:
    """Build the space from ``app.curriculum.KNOWLEDGE_GRAPH`` (our 164-node
    math prerequisite DAG)."""
    return KnowledgeSpace({node_id: list(node.prerequisites) for node_id, node in kg.nodes.items()})


def default_space() -> KnowledgeSpace:
    """The math assessment space, cached."""
    global _DEFAULT
    if _DEFAULT is None:
        from .curriculum import KNOWLEDGE_GRAPH
        _DEFAULT = from_knowledge_graph(KNOWLEDGE_GRAPH)
    return _DEFAULT


_DEFAULT = None
