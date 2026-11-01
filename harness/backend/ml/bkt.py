"""Bayesian Knowledge Tracing (Corbett & Anderson 1995) with EM fitting.

A deliberately simple, legible baseline: the point of this module is a correct
evaluation harness, not a leaderboard model. Per-skill BKT parameters are fit
by Baum-Welch on the TRAINING students only, then scored on held-out students.

Model (standard BKT, no forgetting), as a two-state HMM:

    hidden state: unknown U or known L (knowledge at response time)
    emission:     P(correct | L) = 1 - slip;  P(correct | U) = guess
    transition:   after responding, U -> L with P(learn); L stays L
    initial:      P(L) = prior  (the belief before the first response)

The forward/backward passes are exact (unscaled): tutor-log sequences are
short, float64 handles them, and exact passes give Baum-Welch its guaranteed
monotone likelihood. The indexing here deliberately matches ``BKT.predict``
(emission -> Bayes update -> learning transition) so fitting and scoring
describe the same model.

Reference: Corbett, A.T. & Anderson, J.R. (1995). Knowledge tracing: Modeling
the acquisition of procedural knowledge. UMUAI 4, 253-278.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EPS = 1e-9


@dataclass(frozen=True)
class BKT:
    """Per-skill parameters, each kept in (0,1)."""
    prior: float = 0.15
    learn: float = 0.12
    guess: float = 0.20
    slip: float = 0.10

    def clamped(self) -> 'BKT':
        lo, hi = EPS, 1 - EPS
        return BKT(min(hi, max(lo, self.prior)), min(hi, max(lo, self.learn)),
                   min(hi, max(lo, self.guess)), min(hi, max(lo, self.slip)))

    def predict(self, observations) -> float:
        """P(next response correct) after observing this sequence."""
        p_l = self.prior
        for correct in observations:
            p_obs = p_l * ((1 - self.slip) if correct else self.slip) \
                + (1 - p_l) * (self.guess if correct else 1 - self.guess)
            p_obs = min(1 - EPS, max(EPS, p_obs))
            p_l = (p_l * ((1 - self.slip) if correct else self.slip)) / p_obs
            p_l = p_l + (1 - p_l) * self.learn
        return min(1 - EPS, max(EPS, p_l * (1 - self.slip) + (1 - p_l) * self.guess))


def _emission(p: BKT, correct: bool):
    """(P(obs|U), P(obs|L))"""
    return (p.guess if correct else 1 - p.guess,
            1 - p.slip if correct else p.slip)


def _forward(observations, p: BKT):
    """Exact forward pass. Returns per-step alpha [(U, L)] -- alpha_t is
    P(X_t = s, o_1..o_t), normalized per step -- and the log-likelihood."""
    alphas = []
    log_lik = 0.0
    a_u, a_l = 1 - p.prior, p.prior
    for t, correct in enumerate(observations):
        e_u, e_l = _emission(p, correct)
        a_u, a_l = a_u * e_u, a_l * e_l
        norm = a_u + a_l
        log_lik += math.log(min(1 - EPS, max(EPS, norm)))
        a_u, a_l = a_u / norm, a_l / norm
        alphas.append((a_u, a_l))
        if t + 1 < len(observations):
            a_u, a_l = a_u * (1 - p.learn), a_l + a_u * p.learn
    return alphas, log_lik


def _backward(observations, p: BKT):
    """Exact backward pass. beta_t = P(o_{t+1}..o_n | X_t = s); per-step
    normalization by a common scalar (cancels in every posterior)."""
    n = len(observations)
    betas = [None] * n
    b_u = b_l = 1.0
    betas[n - 1] = (b_u, b_l)
    for i in range(n - 2, -1, -1):
        e_u, e_l = _emission(p, observations[i + 1])
        # transition X_i -> X_{i+1}, then emission of o_{i+1}, then beta_{i+1}
        b_u = (1 - p.learn) * e_u * betas[i + 1][0] + p.learn * e_l * betas[i + 1][1]
        b_l = e_l * betas[i + 1][1]
        norm = min(1 - EPS, max(EPS, b_u + b_l))
        betas[i] = (b_u / norm, b_l / norm)
    return betas


def _posteriors(observations, p: BKT):
    """gamma_t(s) = P(X_t = s | all observations), exact."""
    alphas, _ = _forward(observations, p)
    betas = _backward(observations, p)
    gammas = []
    for (a_u, a_l), (b_u, b_l) in zip(alphas, betas):
        g_u, g_l = a_u * b_u, a_l * b_l
        norm = min(1 - EPS, max(EPS, g_u + g_l))
        gammas.append((g_u / norm, g_l / norm))
    return alphas, betas, gammas


def fit_em(sequences, params: BKT | None = None, iterations: int = 30) -> BKT:
    """Baum-Welch over per-student response sequences of ONE skill."""
    p = (params or BKT()).clamped()
    n_seqs = len(sequences)
    for _ in range(iterations):
        acc_prior = acc_learn_num = acc_learn_den = 0.0
        slip_num = slip_den = guess_num = guess_den = 0.0
        for observations in sequences:
            if not observations:
                continue
            alphas, betas, gammas = _posteriors(observations, p)
            acc_prior += gammas[0][1]
            for t in range(len(observations) - 1):
                e_u, e_l = _emission(p, observations[t + 1])
                a_u, a_l = alphas[t]
                b_u, b_l = betas[t + 1]
                xi_uu = a_u * (1 - p.learn) * e_u * b_u
                xi_ul = a_u * p.learn * e_l * b_l
                xi_ll = a_l * e_l * b_l
                norm = min(1 - EPS, max(EPS, xi_uu + xi_ul + xi_ll))
                acc_learn_num += xi_ul / norm
                acc_learn_den += gammas[t][0]
            for t, correct in enumerate(observations):
                g_u, g_l = gammas[t]
                slip_den += g_l
                guess_den += g_u
                if correct:
                    guess_num += g_u
                else:
                    slip_num += g_l
        new = BKT(
            prior=acc_prior / max(1, n_seqs),
            learn=acc_learn_num / max(EPS, acc_learn_den),
            guess=guess_num / max(EPS, guess_den),
            slip=slip_num / max(EPS, slip_den),
        ).clamped()
        if new == p:
            break
        p = new
    return p
