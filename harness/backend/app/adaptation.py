"""Explicit domain gate: EdNet research inference is never a trained math model."""
import importlib.util
import math
import os
import sys
from functools import lru_cache

from .resources import resource_dir

#: The trained-adapter package, resolved through :mod:`app.resources`. It used to be
#: ``Path(__file__).parents[2] / 'model'``, which is right in the source tree and one
#: directory too deep in the frozen app - where ``model/`` ships at ``_internal/model``.
#: That matters more than a 404 does: a ``MODEL_DIR`` that does not resolve means the
#: adapter never loads and the harness quietly falls back to its heuristic prior.
#:
#: The directory is the same in both layouts, but its *contents* are not: the source tree
#: ships ``model/__init__.py`` and the frozen bundle ships ``model/__init__.pyc`` instead
#: (see ``scripts/package.py:strip_runtime_sources``). :func:`_runtime_module` reads
#: whichever is present; naming ``__init__.py`` unconditionally was a frozen-only crash.
MODEL_DIR = resource_dir("model")
MODEL_METADATA = {
    "name": "Domain-gated PFA research predictor / unvalidated mathematics prior",
    "domain": "domain_generic", "trained": False, "validated_for_math": False,
    "trained_research_domain": "ednet_english_toeic", "research_only": True,
    "license": "CC BY-NC 4.0 (separate EdNet artifact)",
    "default_model": "unvalidated_bkt_irt_prior",
}


#: The filenames the owned model package's initialiser can carry. The source tree ships
#: ``__init__.py``; ``strip_runtime_sources`` in the packager replaces it with a
#: same-interpreter ``__init__.pyc`` and deletes the source, so a frozen bundle has only
#: the second. Naming ``__init__.py`` unconditionally is what made the adapter crash with
#: ``FileNotFoundError`` in the shipped app - a path the source tree never exercises.
_PACKAGE_INIT_FILES = ("__init__.py", "__init__.pyc")


def _runtime_module():
    # Backend may launch with only backend/ on sys.path. Load the owned model package
    # by an absolute path rather than importing an unrelated installed `model` package.
    name = "harness_owned_model"
    if name not in sys.modules:
        init = next((MODEL_DIR / candidate for candidate in _PACKAGE_INIT_FILES
                     if (MODEL_DIR / candidate).is_file()), None)
        if init is None:
            raise FileNotFoundError(
                f"The owned model package has no initialiser under {MODEL_DIR}; expected "
                f"one of {', '.join(_PACKAGE_INIT_FILES)}.")
        # ``spec_from_file_location`` picks SourceFileLoader for a ``.py`` and
        # SourcelessFileLoader for a legacy ``.pyc``, so this one call serves the source
        # tree and the frozen bundle alike - no layout special case to drift out of step.
        spec = importlib.util.spec_from_file_location(
            name, init, submodule_search_locations=[str(MODEL_DIR)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


@lru_cache(maxsize=4)
def _load_model(path):
    return _runtime_module().TrainedPFA.load(path)


def _number(value, name, lower=None, upper=None):
    value = float(value)
    if not math.isfinite(value) or (lower is not None and value < lower) or (upper is not None and value > upper):
        raise ValueError(f"Invalid {name}")
    return value


def predict(state: dict, item: dict) -> dict:
    domain = item.get("domain", state.get("domain", "math"))
    research_requested = state.get("allow_research_model") is True and domain == "ednet_english_toeic"
    if research_requested:
        path = os.getenv("HARNESS_RESEARCH_MODEL_PATH", str(MODEL_DIR / "research" / "ednet_pfa.json"))
        model = _load_model(path)
        if model.domain != "ednet_english_toeic" or not model.research_only:
            raise ValueError("Expected a separately licensed EdNet research artifact")
        result = model.predict({**state, "domain": domain}, {**item, "domain": domain})
        result["evidence"] = "Actual EdNet training; disjoint-student same-source evaluation, not mathematics validation"
        return result
    mastery = _number(state.get("mastery", 0.15), "mastery", 0.0, 1.0)
    slip, guess = 0.10, 0.25
    theta = state.get("theta")
    if theta is None:
        probability = guess + (1 - slip - guess) * mastery
        equation = "guess + (1 - slip - guess) * mastery"
        bias = None
    else:
        theta = _number(theta, "theta")
        # This is an explicit untrained IRT prior, not a difficulty feature of PFA.
        bias = _number(item.get("difficulty_bias", 0.0), "difficulty_bias")
        probability = _runtime_module().sigmoid(theta, bias)
        equation = "sigmoid(theta - difficulty_bias)"
    last = state.get("last_at")
    now = _number(item.get("now", state.get("last_at", 0)) or 0, "now")
    half_life = _number(state.get("half_life_days", 1.0), "half_life_days", 1e-9)
    recall = None if last is None else 2 ** (-max(0.0, now - _number(last, "last_at")) / (86400 * half_life))
    return {
        "p_correct": probability, "model": "unvalidated_bkt_irt_prior", "trained": False,
        "validated_domain": None, "requested_domain": domain, "research_only": False,
        "mastery": mastery, "recall": recall, "cold_start": state.get("attempts", 0) == 0,
        "prior_parameters": {"mastery": mastery, "guess": guess, "slip": slip,
                             "difficulty_bias": bias, "equation": equation},
        "evidence": "Transparent heuristic BKT/IRT prior; no mathematics calibration or trained transfer claim",
        "domain_gate": "EdNet requires explicit domain=ednet_english_toeic and allow_research_model=true",
    }


def train_on_opt_in_csv(data_path, consent_manifest, output_dir, max_users=1500):
    """Blocking worker hook: verifies owner consent manifest and trains a fresh domain artifact.

    This does not auto-promote the artifact, import EdNet weights, or certify deployment.
    The caller must obtain consent verification from its trusted ownership/consent ledger.
    """
    from argparse import Namespace
    import importlib
    if max_users < 30:
        raise ValueError("Require at least 30 students for the held-out evaluation pipeline")
    _runtime_module()
    train_module = importlib.import_module("harness_owned_model.train")
    return train_module.train(Namespace(
        data=str(data_path), questions=None, out=str(output_dir), max_users=max_users,
        max_per_user=80, seed=42, consent_manifest=str(consent_manifest)))
