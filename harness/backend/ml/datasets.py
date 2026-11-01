"""Verified open math-interaction datasets and schema-mapping loaders.

Every catalog entry below was verified against its primary distribution page
(fetch date 2026-10-11). The license facts are the whole point: EVERY verified
candidate is research-only or license-ambiguous, so a model trained on any of
them inherits that restriction. See the DATASET_LICENSES docstring and
outputs/impl/u1_model_memory.md for the consequence and the recommended path.

Loaders are schema mappers: they turn each dataset's columns into the
standardized record form (student_id, item_id, skill, correct, order) used by
ml.bkt and ml.evaluate. They parse real files when you have them; nothing here
downloads data (each source has its own access gate, noted per entry).
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

#: The license table. ``commercial_use`` is False unless the primary source
#: grants it in writing. "Unstated" is treated as NO for anything commercial --
#: silence is not permission.
DATASET_LICENSES = [
    {
        'name': 'KDD Cup 2010 (Carnegie Learning tutor logs)',
        'subsets': {
            'Algebra I 2008-2009': {'students': 3310, 'steps': 9_426_966},
            'Bridge to Algebra 2008-2009': {'students': 6043, 'steps': 20_768_884},
        },
        'url': 'http://pslcdatashop.web.cmu.edu/KDDCup/downloads.jsp',
        'access': 'PSLC DataShop account + agreement; challenge archive 707 MB',
        'license': 'No open license. DataShop/LIBSVM distribution states '
                   '"only to be used for research purposes"; attribution to '
                   'Carnegie Learning and DataShop required.',
        'license_url': 'https://www.csie.ntu.edu.tw/~cjlin/libsvmtools/datasets/binary.html '
                       '(mirror restating the research-only term); DataShop terms apply',
        'commercial_use': False,
        'citation': 'Stamper, Niculescu-Mizil, Ritter, Gordon & Koedinger (2010), '
                    'KDD Cup 2010 Educational Data Mining Challenge.',
    },
    {
        'name': 'ASSISTments 2009-2010 (skill builder)',
        'subsets': {'skill-builder': {'students': 4151, 'problems': 16891,
                                      'interaction_rows': 325637}},
        'url': 'https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data'
               '/skill-builder-data-2009-2010',
        'access': 'Direct download (Google Drive links on the official page).',
        'license': 'Official page: "The dataset is free to use" + mandatory '
                   'citation (Feng, Heffernan & Koedinger 2009, UMUAI 19). No '
                   'formal open license is granted; commercial use is therefore '
                   'UNSTATED -- treat as research-only pending written '
                   'clarification. (The newer FoundationalASSIST is explicitly '
                   'CC BY-NC 4.0.)',
        'license_url': 'https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data',
        'commercial_use': False,
        'citation': 'Feng, Heffernan & Koedinger (2009). Addressing the assessment '
                    'challenge in an Intelligent Tutoring System. UMUAI 19, 243-266.',
    },
    {
        'name': 'Eedi (NeurIPS 2020 Education Challenge)',
        'subsets': {'tasks-1-2': {'students': 118971, 'questions': 27613,
                                  'answers': 15_867_850},
                    'tasks-3-4': {'students': 4918, 'questions': 948,
                                  'answers': 1_382_727}},
        'url': 'https://www.eedischool.com/projects/neurips-education-challenge',
        'access': 'Direct download (public blob); question images restricted.',
        'license': 'CC BY-NC-ND 4.0 (stated verbatim on the distribution page: '
                   'no commercial use, no distribution of modified material).',
        'license_url': 'https://creativecommons.org/licenses/by-nc-nd/4.0/',
        'commercial_use': False,
        'citation': 'Wang et al. (2020), Diagnostic Questions: The NeurIPS 2020 '
                    'Education Challenge, arXiv:2007.12061.',
    },
    {
        'name': 'Junyi Academy learning-activity dataset (2018-2019)',
        'subsets': {'log-problem': {'students': 72630, 'attempts': 16_217_311}},
        'url': 'https://www.kaggle.com/datasets/junyiacademy/learning-activity-public-dataset-by-junyi-academy',
        'access': 'Kaggle account.',
        'license': 'CC BY-NC-SA 4.0 (stated in the dataset acknowledgements: '
                   'non-commercial + share-alike; Junyi IP exclusions apply).',
        'license_url': 'https://creativecommons.org/licenses/by-nc-sa/4.0/',
        'commercial_use': False,
        'citation': 'Chen, Hsieh & Tsai (2020), Junyi Online Learning Dataset.',
    },
    {
        'name': 'EdNet (Riiid, TOEIC English -- the current research model)',
        'subsets': {'KT1': {'students': 784309, 'interactions': '95M+'}},
        'url': 'https://github.com/riiid/ednet',
        'access': 'Direct download / Riiid CD.',
        'license': 'CC BY-NC 4.0. This is the license that already gates the '
                   'existing EdNet-trained model out of production maths.',
        'license_url': 'https://creativecommons.org/licenses/by-nc/4.0/',
        'commercial_use': False,
        'citation': 'Choi et al. (2020), EdNet: A Large-Scale Hierarchical Dataset '
                    'in Education, KDD-20 ADS track.',
    },
]


@dataclass(frozen=True)
class Record:
    """One standardized student-item interaction."""
    student_id: str
    item_id: str
    skill: str
    correct: bool
    order: int  # within-student sequence position


# --------------------------------------------------------------------- loaders

KDD_COLUMNS = {'student': 'Anon Student Id', 'problem': 'Problem Name',
               'skill': 'KC(Default)', 'correct': 'Correct First Attempt'}
ASSISTMENTS_COLUMNS = {'student': 'user_id', 'problem': 'problem_id',
                       'skill': 'skill', 'correct': 'correct'}
EEDI_COLUMNS = {'student': 'UserId', 'problem': 'QuestionId',
                'skill': 'QuestionId', 'correct': 'IsCorrect'}
JUNYI_COLUMNS = {'student': 'user_id', 'problem': 'problem_id',
                 'skill': 'exercise_id', 'correct': 'is_correct'}
EDNET_COLUMNS = {'student': 'user_id', 'problem': 'item_id',
                 'skill': 'item_id', 'correct': 'correct'}


def load_csv(path, columns, sep=',', correct_truthy={'1', 'true'}, limit=None):
    """Map a raw CSV into standardized Records, in per-student chronological
    order. ``columns`` selects this dataset's schema (see *_COLUMNS). Rows with
    missing ids or labels are dropped, not imputed -- a guessed label poisons
    both training and evaluation."""
    records = []
    with open(path, newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle, delimiter=sep)
        for row in reader:
            student = row.get(columns['student'])
            item = row.get(columns['problem'])
            raw_correct = row.get(columns['correct'])
            if not student or not item or raw_correct is None:
                continue
            skill = row.get(columns['skill']) or item
            correct = str(raw_correct).strip().lower() in correct_truthy
            records.append([str(student), str(item), str(skill), correct])
            if limit and len(records) >= limit:
                break
    # assign per-student sequence positions (file order is chronological in all
    # five datasets; Eedi/Junyi timestamps are coarse -- documented upstream)
    position = {}
    out = []
    for student, item, skill, correct in records:
        position[student] = position.get(student, 0) + 1
        out.append(Record(student, item, skill, correct, position[student]))
    return out


def synthetic_math(n_students=120, skills=('fractions', 'signed_numbers', 'ratios',
                                           'equations', 'linear_functions'), seed=42):
    """A synthetic dataset with REAL learning structure: skill mastery grows with
    practice, skills have different difficulty, and ability is per-student. A
    correct protocol must find signal here; a leaky one looks artificially great.
    Used by the tests and as the runnable example."""
    rng = random.Random(seed)
    records = []
    for s in range(n_students):
        student = f'synth-{s}'
        ability = rng.uniform(-1.0, 1.0)
        skill_counts = {k: 0 for k in skills}
        for t in range(rng.randint(30, 60)):
            skill = rng.choice(skills)
            # learning curve: log-linear practice effect, skill-specific rate
            practice = skill_counts[skill]
            rate = {'fractions': 0.35, 'signed_numbers': 0.45, 'ratios': 0.30,
                    'equations': 0.25, 'linear_functions': 0.20}[skill]
            difficulty = {'fractions': -0.3, 'signed_numbers': 0.0, 'ratios': -0.2,
                          'equations': 0.3, 'linear_functions': 0.5}[skill]
            logit = 1.1 * ability + rate * practice - difficulty - 0.6
            p = 1 / (1 + pow(2.718281828459045, -logit))
            correct = rng.random() < p
            records.append(Record(student, f'{skill}-{t}', skill, correct, t + 1))
            skill_counts[skill] += 1
    return records


def write_synthetic_csv(path, seed=42):
    """Convenience for exercising load_csv end-to-end in tests."""
    records = synthetic_math(seed=seed)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['user_id', 'problem_id', 'skill', 'correct'])
        for r in records:
            writer.writerow([r.student_id, r.item_id, r.skill, int(r.correct)])
    return path
