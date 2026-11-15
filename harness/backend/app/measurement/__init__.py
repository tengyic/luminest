"""Learning-efficiency measurement: contract, estimators, probes, and a benchmark.

Import order is deliberate and one-directional: ``contracts`` defines vocabulary and depends
on nothing; ``episodes`` reshapes a log using that vocabulary; ``estimators`` is pure math over
those shapes; ``probe`` and ``bench`` sit on top; ``report`` reads the database. Nothing below
``report`` touches SQL, which is what lets the benchmark validate the estimators against known
ground truth without a database at all.

See ``docs/MEASUREMENT.md`` for the study designs and the citations behind each metric.
"""

from __future__ import annotations

__all__ = ['bench', 'contracts', 'episodes', 'estimators', 'probe', 'report']
