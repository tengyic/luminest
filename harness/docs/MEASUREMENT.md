# Measuring learning efficiency and progress

This document describes what the harness measures, how it measures it while a learner is using
the product, which experiments would validate the measurement, and which claims it must not
make. Code lives in `backend/app/measurement/`; the API is `/api/v1/measurement`; the
benchmark runs from `scripts/measure_bench.py`.

---

## 1. The problem: the obvious metric is the wrong one

The harness could already report accuracy during practice. The reason that number cannot be
called "learning" is not a purist objection, it is an empirical finding with a clean
demonstration. Soderstrom & Bjork (2015, *Perspectives on Psychological Science* 10(2), 176–199)
separate **retrieval strength** — how accessible something is right now, inflated by recency,
fluency, cue support and feedback — from **storage strength**, which is what survives a delay.
Conditions that raise the first can lower the second.

Bastani et al. (2024, SSRN 4895486) measured exactly this with an LLM tutor in a large
high-school field study: practice performance **+48%** with unrestricted GPT-4, unaided exam
performance **−17%** against control. The guarded variant ("GPT Tutor", which withholds answers)
produced **+127%** during practice and roughly **no difference** on the exam.

Read that as a measurement problem rather than a tutoring problem, and the conclusion is sharp:
**a dashboard that reports practice accuracy ranks the most-harmful condition first, by the
widest margin, for the learners being helped most.** Any instrument that reports progress must
therefore record *the conditions under which the observation was made*, and must produce
observations under more than one of them.

Kestin et al. (2025, *Scientific Reports* 15:17458) is the counter-case worth keeping in view:
a randomised crossover in physics (N=194) found effect sizes of 0.73–1.3 SD for an
answer-withholding tutor, with 49 minutes of instruction against 60 for the control. Both the
positive and the negative result come from the same design feature, which is why the harness
treats *aid conditions* as the primary measurement variable rather than an afterthought.

---

## 2. What is measured

Four quantities, kept separate because they answer different questions and respond to different
interventions. Formulas are in `estimators.py`; this table is the map.

| Quantity | Estimator | Reference | What a change in it means |
|---|---|---|---|
| How fast is the error rate falling? | Slope in log-odds per opportunity, `logit P = a_c + b·n`, one intercept per concept, shared `b` | Cen, Koedinger & Junker (2006), LFA/AFM; structure of Corbett & Anderson (1994) BKT | The headline. A within-person slope, so it needs no norm group and does not move with the starting point |
| How big was the change? | Hake normalized gain `<g> = (post−pre)/(max−pre)`; Cohen's *d*; Hedges' *g* | Hake (1998), *Am. J. Phys.* 66, 64–74; Cohen (1988) | Magnitude on a fixed scale; `<g>` is negatively correlated with the pretest by construction, so it is not comparable across different pretests |
| How much did it cost? | Time-to-criterion; Paas instructional efficiency `E = (Z_perf − Z_effort)/√2`; gain per engaged hour | Paas & van Merriënboer (1993), *Human Factors* 35, 737–743; Paas (1992) 9-point effort scale; Carroll (1963) | Whether the improvement was cheap or expensive. High efficiency at low performance is not good news |
| Is the support doing the work? | Aided minus unaided accuracy, with its standard error | Bastani et al. (2024) as the reference case | The diagnostic. A large positive gap means observed performance belongs to the support |

### Why the headline is a slope and not a gain

Two learners can start at 30% and 70% and improve at the same rate. A pretest–posttest gain
cannot express that — the second learner has less headroom and scores a smaller gain for
identical learning. `<g>` compresses the same way. The slope does not, because it is estimated
from *change within the learner across opportunities* (Cen et al. 2006). For a product with one
learner and no cohort, this is not a preference: it is the only efficiency quantity that is
identified at all.

### Why average time-on-task is a trap

`episodes.py` produces two denominators. `solve_seconds` sums only time reported inside an
answer. `engaged_seconds` adds inter-answer gaps, **capped at 120 s per gap**, so a pause to
think counts and a coffee break does not. Wall-clock time is excluded deliberately: it makes
every efficiency ratio better for exactly the learner who leaves the window open.

---

## 3. Probing during use

`probe.py` + the `measurement_probes` table. The mechanism exists because a measurement
condition must differ from the practice condition, or the measurement is circular.

**Cold probe.** One unsupported retrieval, inserted into ordinary use: feedback withheld, no
lesson text, no tutor turn in the window, item not seen inside the recognition window (24 h).
Recorded with the conditions *at issue time* — the table exists specifically so that "this was
unaided" is a stored fact rather than an inference from absence, since absence is what a
missing event looks like.

**Effort rating.** The Paas (1992) 9-point single item, one tap, after a sitting. The cheapest
usable cognitive-load instrument, and the only way to compute the cost side of efficiency.

**Retention check.** The 7-day / 28-day delayed test already wired through `learning_science`
and `Assessment.delay_days`.

### Budget

At most one cold probe per sitting and one per 20-minute cooldown; none during an assessment;
none on a concept with fewer than 3 prior attempts (below that a low score is first exposure,
not weak retention). The budget is a design constraint, not politeness: a harness that checks
the learner every few questions has replaced practice with assessment, and a learner who
expects a probe starts practising for it.

### Honesty on the surface

The probe is presented as *a quick recall check, no hints, no feedback until you finish*. That
is accurate, and it is also genuinely useful to the learner — retrieval practice with delayed
feedback is among the best-evidenced study techniques (Karpicke & Roediger 2008, *Science*
319, 966–968). Hiding it would be deceptive **and** would corrupt the reading through
reactivity and pretest sensitization. What is *not* disclosed, because it would change the
answer, is how a given probe result moves the learner's mastery estimate.

---

## 4. Benchmarks

### 4.1 What is available, and why none of it fits

| Benchmark | What it scores | Why it cannot validate this instrument |
|---|---|---|
| ASSISTments 2009/2012/2015/2017 | Next-step correctness prediction (AUC, RMSE) for knowledge tracing | Scores a model's prediction on other people's logs. Carries no answer key for "this learner's true learning rate" |
| EdNet (Choi et al. 2020) | 131,441,538 interactions, 784,309 students, 293 skill tags | Same: prediction accuracy at scale, not measurement validity |
| Eedi / NeurIPS 2020 Education Challenge (Wang et al. 2021) | Correctness, distractor choice, difficulty, discrimination | Distractor-level prediction; still no rate ground truth |
| MATH, GSM8K, MMLU-style suites | Capability at a point in time | No learner, no treatment, no delay. A MATH delta is a capability claim, not a learning claim |
| MathTutorBench (Macina et al., EMNLP 2025), TutorGym | Pedagogical *behaviour* quality via rubric/LLM-judge | Measures what the tutor does, not what the learner retains |

Two results in this literature should make anyone wary of benchmark numbers generally:
Beck & Chang (2007, *UM 2007*) prove that observed response sequences are consistent with an
infinite family of BKT parameters, so a fit on one learner is not identified; and Shaw et al.
(2022, *AIED*) show that *untrained* recurrent models match trained knowledge-tracing baselines
on the standard splits, which means small AUC differences on those benchmarks are not evidence
of a better learner model.

### 4.2 The benchmark used here: recovery against known ground truth

`bench.py` simulates learners whose learning rate is known **because it was set**, pushes them
through the same pipeline the product uses, and compares estimates to truth. Five checks, seeded
and deterministic, runnable as a release gate:

```bash
python scripts/measure_bench.py            # exit 0 only if every check passes
python scripts/measure_bench.py --json     # for CI
```

Current output at the default cohort (200 synthetic learners per check):

| Check | Question | Result | Criterion |
|---|---|---|---|
| recovery | Does the estimator return the rate that was set? | median bias **+0.007**, rank ρ **0.755**, MAE **0.034** on identifiable curves | ρ ≥ 0.60, \|bias\| ≤ 0.02, MAE ≤ 0.06 |
| coverage | Does the 90% interval contain the truth 90% of the time? | **0.90** empirical, 100 intervals | 0.80–0.98 |
| discrimination | Flat vs improving learner separated? | Cohen's *d* **1.99** | *d* ≥ 0.8 |
| aided inflation | Does support inflate accuracy, and does the estimator see it? | observed **0.071**, estimated **0.071** | ≥ 0.05 and within 0.04 |
| null false positive | How often is a flat learner told they are improving? | **2%** | ≤ 12% |

Three of these checks exist because the first implementation **failed** them, and both failures
are worth recording since they are easy to reintroduce:

1. **The interval excluded its own point estimate.** The bootstrap resampled outcomes and then
   re-assigned opportunity numbers, destroying the (opportunity, outcome) pairing — every
   resample fitted noise, so the distribution sat near zero. Fixed by resampling whole rows and
   taking the predictor from the row.
2. **Coverage was 0.80, not 0.90.** Duplicate resampling flattens the curve, displacing the
   percentile interval downward. The **pivotal** interval `[2θ̂−q95, 2θ̂−q05]` corrects it and
   returned coverage to 0.92 on the full rate range.

A third finding is a genuine limit rather than a defect, and the suite reports it instead of
hiding it: **137 of 200 learners saturate** within 40 opportunities, and their slope is not
identified — every rate above theirs fits the remaining all-correct observations equally well.
Their estimates are unbiased (median bias ≈ 0) but imprecise (MAE 0.21 against 0.03 on
identifiable curves). The report's own `interval_90.includes_zero` is what communicates this to
a learner, and the estimator never converts an unidentified slope into a confident half-life.

### 4.3 What the benchmark cannot establish

It validates the **estimator**, not the product. A synthetic learner is a known statistical
process and a real learner is not. Specifically it does **not** show that:

- a measured learning rate predicts an external exam (no criterion measure exists);
- real learners follow this curve (the generating process is assumed, not observed);
- the probe schedule is adhered to in use, or that clients honour the withheld-feedback
  condition;
- measurement is non-reactive.

Those are field questions. They need §5.

---

## 5. Experiments

### 5.1 The unit of analysis is the session, not the person

Every RCT in the table above is between-learner: hundreds of students, two arms, one effect
size. That design is unavailable here — there is one learner per account and no cohort. The
consequence is structural and easy to get wrong: **the experiment unit for a single-learner
product is the session (or concept-block), not the learner.** Each sitting is randomly assigned
to an arm, with assignment stratified by concept, and the paired difference across sittings is
the estimate.

This is a crossover design, so it inherits crossover's requirements: counterbalancing (block by
concept, alternate arms within block), a check for order effects, and enough *pairs* rather than
enough *people*.

Approximate paired-comparison power, normal approximation, α = 0.05 two-sided:

| Effect `d_z` | Pairs for 80% power | Pairs for 90% power |
|---|---|---|
| 0.8 (large) | 13 | 17 |
| 0.5 (moderate) | 32 | 43 |
| 0.4 | 50 | 66 |
| 0.3 | 88 | 117 |
| 0.2 (small) | 197 | 263 |

At one sitting a day, detecting `d_z = 0.4` takes about 100 sittings. This is the honest reason
the estimator benchmark (§4.2) carries the validation burden: the field experiment is a
slow background accumulation, not a gate. It should be pre-registered and run, but no product
decision should wait on it.

### 5.2 E1 — Estimator validation (automated, complete)

The suite in §4.2. Runs in about 9 seconds. Gate: `scripts/measure_bench.py` exits non-zero.

### 5.3 E2 — Single-learner crossover: does the arm change the *rate*?

**Question.** Within one learner, does a session in arm A produce a different learning rate than
a session in arm B?

**Arms.** The candidate manipulations already in the codebase as experiment flags
(`experiments.py`): `interleaved_practice` on/off, `self_explanation_gate` on/off,
`target_correctness` 0.6/0.7/0.8.

**Design.** Randomise the arm per sitting, blocked by concept family so each family sees both
arms. Arm assignment is already sticky per `(experiment key, user id)` — for a *session-level*
design that stickiness must be replaced by per-sitting assignment, or the "crossover" is a
between-learner design with one learner in each arm.

**Outcome.** The paired difference in fitted learning rate between arm-A sittings and arm-B
sittings on the same family. Not accuracy — accuracy is the metric the literature says is
confounded.

**Threats specific to this design.** Order effects (arm A always first), concept × arm
interaction, and a learning-rate estimate too noisy per single sitting to difference. The last
is the binding constraint: a session yields perhaps 8–15 opportunities on one family, which is
around the identifiability floor. Pool across sessions of the same arm and compare pooled
fits rather than per-session slopes.

### 5.4 E3 — Probe reactivity: does measuring change the thing measured?

**Question.** Do sessions containing a cold probe differ in learning rate from sessions without
one?

**Design.** Exploit the cooldown as a natural experiment: sittings that fall inside the cooldown
get no probe. Compare like-for-like sittings (same length, same concept family). If probed
sittings show systematically different rates, the probe is reactive and must be either reduced
or included as a covariate.

This is the check that keeps §3 honest. A probe programme with no reactivity check is an
intervention being mistaken for an instrument.

### 5.5 E4 — Retention curve: 7 versus 28 days

**Question.** How much survives, and does the answer depend on how the material was practised?

**Design.** Already half-built: `learning_science.next_transfer` schedules 7- and 28-day tests
on families absent from practice history, and `Assessment.delay_days` records which. The
comparison of interest is per-practice-condition, not overall: `<g>` at 7 days against `<g>` at
28 days, with the practice condition held fixed within a comparison.

**Known confound.** The 28-day test covers material practised earlier in the history, so delay
and practice recency are correlated by construction. Any retention curve drawn from it must
state that, or it is a curve of "material from older sessions" rather than of time.

### 5.6 E5 — Convergent validity: does the rate predict the delayed score?

**Question.** Do learners with a higher measured learning rate score better on the delayed
transfer test?

**Why it matters.** This is the only check that connects the instrument to an outcome it does
not itself define. If the correlation is near zero, the measured rate is measuring something
internal and uninteresting, and the report should not lead with it.

**Requirement.** Needs both quantities on enough accounts. Within one account it is a
correlation across concept families, which requires a family to be practised enough to fit and
then tested at a delay — a specific sequencing the scheduler does not currently force.

---

## 6. Threats to validity

Standard taxonomy: Campbell & Stanley (1963); Shadish, Cook & Campbell (2002).

| Threat | How it appears here | Mitigation in this design |
|---|---|---|
| **Novelty** (Clark 1983) | Early engagement inflated by newness; the first weeks overstate everything | Do not report trends over the first sessions as learning; the rate is fit within sessions, not across the product's lifetime |
| **Hawthorne / reactivity** (Adair 1984; McCarney et al. 2007) | Any instrumentation is an intervention; a probed learner behaves differently | E3; probe budget; conditions recorded so probed and unprobed observations can be compared |
| **Pretest sensitization** | Being probed may change how the learner studies afterwards | The probe is a retrieval attempt, which is itself beneficial — so the "contamination" is an intervention with a known sign, not an unknown one |
| **Ceiling / floor** | Compresses `<g>`; `<g>` undefined at pretest 1.0 | `normalized_gain` returns `status='ceiling'` rather than 1.0; slope does not compress the same way |
| **Attrition** | Voluntary use; a learner who quits leaves a flattering record | Report per-account evidence counts; no aggregate claim is made across accounts |
| **Instrumentation drift** | Changing item sets, thresholds or the aid rule mid-history | All thresholds are module constants; aid derivation is deterministic over stored rows, so re-running it on old data reproduces the old labels |
| **Experimenter bias** | The author of the harness wrote the instrument that grades it | Pre-registration for E2–E5; the automated suite (§4.2) is the check the author cannot fudge by reading a table |
| **Small-N non-identification** (Beck & Chang 2007) | BKT parameters are not identified from one short sequence | The report refuses to fit BKT as an inferential instrument; the slope-based model is used instead precisely because it is identified from within-person change |

Effect-size interpretation follows Kraft (2020, *Educational Researcher* 49(4), 241–253), not
Cohen's generic 0.2/0.5/0.8: in education, 0.05 SD is small but real (~1.5 months of schooling),
0.10 SD is medium, 0.20 SD is large. By that standard Kestin et al.'s 0.73–1.3 SD is enormous
and should be treated with corresponding suspicion about novelty and design artefacts.

---

## 7. What would falsify this

Written down so the instrument can be wrong in a way that is detectable:

1. **`scripts/measure_bench.py` exits non-zero.** The estimator no longer recovers a known rate
   at the stated precision. Nothing downstream should be trusted.
2. **The interval stops containing its own estimate.** Already happened once; the test
   `test_the_interval_contains_its_own_point_estimate` guards it.
3. **E5 returns ρ ≈ 0.** The learning rate does not predict delayed performance, so it is an
   internal statistic being presented as a learning measure.
4. **E3 shows probed sessions differ materially.** The instrument is changing what it measures.
5. **The aided–unaided gap is near zero while unaided accuracy is low.** Then the support is not
   helping; the gap being small is not reassurance, and the report says so in its own verdict
   string.

## 8. What this does not claim

The reading is **within-person**: rate and retention from one account's own attempts. It is not
a normed ability score, not a comparison to other learners, and not a prediction of an AP or
external exam. `report.build()` attaches a `cannot_claim` list to every reading, and each entry
names the evidence that would settle it. When a figure is not identified the report says
`insufficient_evidence` with the shortfall, rather than returning a number that would be read as
a finding.

---

## References

- Bastani, H. et al. (2024). *Generative AI Can Harm Learning.* SSRN 4895486.
- Barnett, S. M., & Ceci, S. J. (2002). When and where do we apply what we learn? *Psychological Bulletin* 128(4), 612–637.
- Beck, J. E., & Chang, K.-m. (2007). Identifiability: A fundamental problem of student modeling. *UM 2007*, LNCS 4511, 137–146.
- Carroll, J. B. (1963). A model of school learning. *Teachers College Record* 64, 723–733.
- Cen, H., Koedinger, K. R., & Junker, B. (2006). Learning Factors Analysis. *ITS 2006*, LNCS 4053, 164–175.
- Choi, Y. et al. (2020). EdNet: A large-scale hierarchical dataset in education. *AIED 2020*.
- Clark, R. E. (1983). Reconsidering research on learning from media. *Review of Educational Research* 53(4), 445–459.
- Cohen, J. (1988). *Statistical Power Analysis for the Behavioral Sciences.*
- Corbett, A. T., & Anderson, J. R. (1994). Knowledge tracing. *User Modeling and User-Adapted Interaction* 4, 253–278.
- Hake, R. R. (1998). Interactive-engagement versus traditional methods. *American Journal of Physics* 66, 64–74.
- Karpicke, J. D., & Roediger, H. L. (2008). The critical importance of retrieval for learning. *Science* 319, 966–968.
- Kestin, G., Miller, K., Klales, A., Milbourne, T., & Ponti, G. (2025). AI tutoring outperforms in-class active learning. *Scientific Reports* 15, 17458.
- Kraft, M. A. (2020). Interpreting effect sizes of education interventions. *Educational Researcher* 49(4), 241–253.
- Macina, J. et al. (2025). MathTutorBench: A benchmark for measuring open-ended pedagogical capabilities of LLM tutors. *EMNLP 2025*.
- Murphy, A. H. (1973). A new vector partition of the probability score. *Journal of Applied Meteorology* 12, 595–600.
- Paas, F. (1992). Training strategies for attaining transfer of problem-solving skill in statistics. *Journal of Educational Psychology* 84(4), 429–434.
- Paas, F., & van Merriënboer, J. J. G. (1993). The efficiency of instructional conditions. *Human Factors* 35, 737–743.
- Rohrer, D. (2015). Interleaving helps students distinguish among similar concepts. *Educational Psychology Review* 24, 355–367.
- Shadish, W. R., Cook, T. D., & Campbell, D. T. (2002). *Experimental and Quasi-Experimental Designs for Generalized Causal Inference.*
- Shaw, S., Ouyang, Y., Hsu, T., & Li, Y. (2022). Deep learning or deep ignorance? *AIED 2022*.
- Soderstrom, N. C., & Bjork, R. A. (2015). Learning versus performance. *Perspectives on Psychological Science* 10(2), 176–199.
- van Gog, T., & Paas, F. (2008). Instructional efficiency: Revisiting the original construct. *Educational Psychologist* 43(1), 16–26.
- Wang, Z. et al. (2021). Learning to solve geometry problems / Eedi, NeurIPS 2020 Education Challenge.
