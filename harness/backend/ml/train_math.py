"""Runnable training pipeline for the math knowledge-tracing baseline.

THIS IS NOT A PRODUCTION MATH MODEL AND MUST NOT BE SHIPPED AS ONE.

It is the honest, runnable path:

1. load a dataset (see ml.datasets -- all verified candidates are
   research-only; the license consequence is documented there and in
   outputs/impl/u1_model_memory.md);
2. fit per-skill BKT on training students;
3. evaluate with the disjoint-student protocol (ml.evaluate);
4. write a results JSON stamped with dataset, license, protocol and the
   explicit research-only banner.

Run on real data (after obtaining it from the source under its terms):

    python -m ml.train_math --csv algebra_2008_2009.csv \\
        --columns kdd --out results.json --max-rows 200000

Run the synthetic example (no download, no license issue):

    python -m ml.train_math --synthetic --out results.json
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict

from .bkt import BKT, fit_em
from .datasets import (ASSISTMENTS_COLUMNS, DATASET_LICENSES, EEDI_COLUMNS,
                       EDNET_COLUMNS, JUNYI_COLUMNS, KDD_COLUMNS,
                       load_csv, synthetic_math)
from .evaluate import evaluate_model

COLUMN_SCHEMAS = {'kdd': KDD_COLUMNS, 'assistments': ASSISTMENTS_COLUMNS,
                  'eedi': EEDI_COLUMNS, 'junyi': JUNYI_COLUMNS, 'ednet': EDNET_COLUMNS}


class BKTModel:
    """Per-skill BKT, fit on training students only. Cold-start students get
    the fitted prior; no per-student memorization is possible by construction."""

    def __init__(self, iterations=15):
        self.iterations = iterations
        self.params = {}
        self.default = BKT()

    def fit(self, records):
        per_skill = defaultdict(lambda: defaultdict(list))
        for r in records:
            per_skill[r.skill][r.student_id].append((r.order, r.correct))
        self.params = {}
        for skill, students in per_skill.items():
            sequences = [[correct for _, correct in sorted(obs)] for obs in students.values()]
            self.params[skill] = fit_em(sequences, iterations=self.iterations)

    def predict(self, history, skill):
        params = self.params.get(skill, self.default)
        return params.predict(history)


def run(records, test_fraction=0.2, seed=42, iterations=15):
    result = evaluate_model(records, lambda: BKTModel(iterations=iterations),
                            test_fraction=test_fraction, seed=seed)
    result['model'] = 'per-skill BKT (Corbett & Anderson 1995), EM fit'
    result['license_status'] = research_only_banner(records)
    result['generated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    return result


def research_only_banner(records):
    """What the license of the data means for the model. If the data is not
    verifiably commercial-use, the trained artifact is not either -- that is
    the exact trap that gated the EdNet model out of maths."""
    return ('Research skeleton. If trained on any dataset in DATASET_LICENSES '
            '(all currently research-only or license-ambiguous), the resulting '
            'model artifact inherits the restriction and MUST be gated off from '
            'commercial use, exactly as app/adaptation.py gates the EdNet '
            'artifact today. A commercial math model requires self-collected '
            'opt-in data (see app.adaptation.train_on_opt_in_csv) or a dataset '
            'with verified commercial terms.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--csv', help='path to a raw dataset CSV')
    parser.add_argument('--columns', choices=sorted(COLUMN_SCHEMAS), help='schema of --csv')
    parser.add_argument('--synthetic', action='store_true', help='use the synthetic dataset')
    parser.add_argument('--max-rows', type=int, default=None)
    parser.add_argument('--out', default='ml_results.json')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args(argv)
    if args.synthetic:
        records = synthetic_math(seed=args.seed)
    elif args.csv and args.columns:
        records = load_csv(args.csv, COLUMN_SCHEMAS[args.columns], limit=args.max_rows)
    else:
        parser.error('provide --synthetic, or --csv with --columns')
        return
    result = run(records, seed=args.seed)
    with open(args.out, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'per_skill'}, indent=2))
    print('per-skill AUC:', {k: round(v['auc'], 4) if v['auc'] is not None else None
                             for k, v in result['per_skill'].items()})
    return result


if __name__ == '__main__':
    main()
