# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are the ones passed to `scripts/package.py --version`; `release_kit.py` stamps them
into `release.json` and the artifacts under `outputs/release/<version>/`.

An entry belongs here when it changes what a user or an operator can do, or when it changes
what the release gate accepts. Everything below that starts with *audit* came out of the
2026-11-10 shipping audit (`outputs/shipping-audit-2026-11-10.md`), which returned
**NO-GO**.

## Unreleased

### Fixed — the hosted deployment could not boot (audit B2)

`deploy/compose.yaml` defaulted `HARNESS_TUTOR_PROVIDER` to `offline`, a value
`app/config.py` rejects outright since the deterministic rules engine was removed. The
`migrate` service was given no tutor variables at all while still booting
production, so `scripts/init_db.py` exited with `ValueError: Production requires a
configured language model`. `backend` waits on
`migrate: service_completed_successfully`, so the migration's failure took the API with it:
`docker compose up` was dead on arrival for every operator.

- The four `HARNESS_TUTOR_*` variables now come from one YAML anchor applied to **both**
  services, so a future tutor variable cannot be added to the API and forgotten on the
  migration job.
- Each one is `${VAR:?}`-required. A missing value stops `docker compose config` with the
  variable's name instead of failing after PostgreSQL is already healthy.
- `deploy/.env.example` documents every required value, how to generate
  `HARNESS_SECRET`, and which `HARNESS_TUTOR_URL` forms production accepts.
- `deploy/README.md` is the operator guide: boot, the two model options, upgrade,
  rollback, and what the file deliberately does not do.
- An `ollama` service behind the `ollama` profile, so a self-hosted deployment can boot with
  no paid key. `config.py` already exempts the `ollama` hostname from the production HTTPS
  requirement, which is what makes a plain-HTTP loopback model legal there.

### Fixed — dependencies with known vulnerabilities (audit B5)

Making the declared release gate runnable turned up the reason nobody had looked: it could
not run. `pip-audit -r requirements.txt` refuses to scan an unpinned requirement, and two of
them were ranges (`pypdf>=6,<7`, `psycopg[binary]>=3.2,<4`). With exact pins it reported:

```
Found 62 known vulnerabilities in 3 packages
Name             Version ID                  Fix Versions
pillow           12.3.0  (many advisories)   13.0.0
python-multipart 0.0.22  (5 advisories)      0.0.26 … 0.0.31
pypdf            6.19.0  (many advisories)   6.20.1 … 6.21.4
```

- `pillow` 12.3.0 → **13.0.0**, `python-multipart` 0.0.22 → **0.0.31**, `pypdf` → **6.21.4**.
  All three have cp312 manylinux wheels, so `python:3.12-slim` installs them without a
  compiler; verified with `pip download --only-binary=:all: --platform manylinux_2_28_x86_64
  --python-version 312`.
- `psycopg[binary]` and `pypdf` are now pinned exactly, matching `requirements-dev.txt`, so
  the container resolves the same driver the suite was run against.

### Fixed — the legal record contradicted the code and the privacy notice (audit B4)

`legal/FILL_IN_SHEET.md` recorded that `media_enabled` defaults to `0` on the desktop
profile "so the shipped app makes none of these calls". The code said otherwise
(`media_default = '1' if environment in {'development','test','desktop'}`), the shipped
`legal/privacy.md` §4 said otherwise ("Image and video search are on in the desktop build"),
and a boot probe confirmed `media_enabled=True` for `HARNESS_ENV=desktop`.

- The decision record and the stale docstrings in `app/config.py` now describe the behaviour
  that ships. **No behaviour was changed:** the notice users are shown is the one that was
  already accurate, so the correct repair was to make the internal record agree with it,
  not to silently turn a disclosed feature off.
- Whether the desktop build *should* default outbound media on is recorded under
  **Open decisions** in `FILL_IN_SHEET.md`. It is a product/legal call, and it now has a
  named place to be recorded when someone makes it.
- `check_legal.py` still prints `LEGAL OK`, which continues to mean "no unfilled
  placeholders" and not "reviewed by counsel". The five open items are unchanged.

### Added — the full suite now runs on the Python that ships (audit B5)

`backend/Dockerfile` is `python:3.12-slim`; every CI job was on 3.13 and the local venv on
3.14. No run anywhere had executed `tests/` on the shipping interpreter, and the two layered
jobs cover nine test files out of the suite. `full-suite-on-the-shipping-runtime` runs all of
them on 3.12 and asserts its own version against the `FROM python:` line in the Dockerfile,
so bumping the image without bumping the workflow fails the build instead of quietly
reopening the gap.

`pytest-timeout` and `pip-audit` are installed in the development venv from
`requirements-dev.txt`, which had declared both all along.

### Added — a gate against committing a tree that does not run (audit B1)

`scripts/verify_releasable_tree.py` refuses any tree where a file under `backend/app/` or the
native `Visuals/` resource root exists on disk but is not tracked by git. Prompted by a real
failure: five runtime modules (`model_config.py`, `routes_model_config.py`,
`harness/live_voice.py`, `harness/teaching/items.py`,
`harness/teaching/generate_problems.py`) were imported by committed code while being
untracked themselves. A `git add -u` commit reproduced the failure exactly:

```
ImportError: cannot import name 'model_config' from 'app'
```

The suite cannot catch this, because in a developer's working tree the files are present.
The check asks git, not the filesystem, and is wired into CI as `releasable-tree`.

### Added — `RELEASE_CHECKLIST.md`

The gate order, what each gate actually proves, and rollback for the desktop build, the
hosted deployment and the schema. It also states the one precondition this repository cannot
satisfy: a Developer ID Application certificate and notarization credentials are required
before `release_kit.py` will assemble a release, and `security find-identity -v -p
codesigning` currently reports `0 valid identities found` on the build machine.

### Added — fourteen courses, eight of them anchored to a textbook that may legally be quoted

The course catalogue grew from six courses to fourteen: `algebra_1`, `chemistry`,
`ap_chemistry`, `organic_chemistry`, `biology`, `ap_biology`, `physics`, `astrophysics`,
`earth_space_science`, `ap_calculus_ab`, `ap_calculus_bc`, `linear_algebra`, `act_math`,
`act_english` — 1,575 concepts across 157 units.

Six of the fourteen carry **no** textbook anchors, on purpose: openstax publishes no Earth
Science, linear algebra or organic-chemistry text, and the only organic-chemistry, calculus
and writing titles are CC BY-NC-SA (link-only). Those six declare it in the outline and
quote nothing. The other eight carry 413 anchored sections across eleven CC BY books.

Each one is generated by a committed pipeline (`scripts/course_pipeline.py` reading
`scripts/outlines/<course>.py`), so the pack, the seed and the outline cannot drift without
the verifier noticing. `verify` re-fetches every anchored section through the same licence
gate the classroom uses: **344 sections, 344 `ready`**, 0 failures across all fourteen
courses. 413 `(book, page)` pairs resolve to eleven distinct OpenStax slugs, and all eleven
are CC BY — checked against the bundled 129-book catalogue (80 NC, 38 CC BY, 11 with no
licence declared). The six courses with no CC BY book — earth science, organic chemistry,
linear algebra, both calculus courses, ACT English — declare that in the outline and carry
**zero** anchors rather than borrowing a book that does not teach them.

**Read this before upgrading an installation.** Six packs were not extended, they were
regenerated from a new outline: `biology` 64→128 concepts, `chemistry` 74→148, `physics`
120→159, `earth_space_science` 44→132, `ap_chemistry` 72→105, `ap_biology` 81→86. Verbatim
title survival in those six is 1 of 463, so **every persisted concept id from the previous
packs is now orphaned**: learner mastery rows, bookmarks and receipts that referenced them
no longer resolve. There is no migration map, and this entry is the record of that rather
than a claim that it is harmless. `algebra_1` and the seven brand-new courses are unaffected.

### Added — the whiteboard's eighth visual type actually renders

`tex` was added to `VISUAL_TYPES` and to the shipped `catalog.json` as `available`, but no
renderer was ever compiled for it: `web-visuals/src/adapters.js` had seven adapters, so every
equation node the board mounted came back `RENDERER_ASSETS_NOT_INSTALLED — no adapter
compiled for tex`. The catalog offering a type the bundle cannot draw is worse than not
offering it, because the failure surfaces to a learner rather than to the gallery.

- KaTeX 0.16.47 is bundled for the JavaScript and vendored for the stylesheet and all 60
  font files, so the type needs no network and no runtime prerequisite. `trust: false`
  refuses `\href`/`\includegraphics`, and `throwOnError: true` is deliberate: with it off
  KaTeX returns normally while drawing the source in red, which would let the adapter report
  `rendered` for a formula that is not typeset.
- `build.mjs` asserts 20 faces per format, resolves every `url(fonts/…)` the stylesheet names,
  and fails the build if any is missing.
- The headless smoke test drives all eight renderers and now treats **any 404 as a failure**.
  It caught a real one in this change: the stylesheet was rewritten to `vendor/katex/fonts/`
  while itself living in `vendor/katex/`, which produced `vendor/katex/vendor/katex/fonts/`.
  All eight renderers reported PASS while every KaTeX font 404'd.

### Added — live voice, and structured problem generation

`harness/live_voice.py` is the realtime turn path: nine `HARNESS_LIVE_*` variables, loopback
enforced (`offhost_base_url` refuses anything but `127.0.0.1`/`localhost`/`[::1]`), and
twelve stable refusal codes so a broken voice surface says why instead of going quiet.
`harness/teaching/generate_problems.py` requires the model (`available(settings)` guard,
no template branch) and `teaching/items.py` is schema only, so neither can quietly emit
deterministic content while presenting it as model output.

### Added — the model configuration layer

`app/model_config.py` plus `GET/PUT/DELETE /api/v1/settings/model-config`: a provider and
model catalogue, a masked key, persistence at `<data_dir>/model_config.json`, and immediate
effect without a restart. `HARNESS_TUTOR_PROVIDER=offline` is refused by `config.py` at
startup and by `provider.available()` at request time, so the deterministic rules engine
cannot be reintroduced by an environment variable.

### Fixed — the suite's result depended on the developer's `backend/.env`

`Settings.from_env()` calls `config.load_dotenv()`, which re-read the developer's `.env`
*after* the fixtures had deleted the `HARNESS_TUTOR_*` variables, and put a live provider
back. Sixteen tests asserting the unconfigured state therefore failed on any machine set up
as `docs/provider-and-voice-setup.md` describes while passing in CI, which checks out a clean
tree. They were also not merely red — they made real outbound model calls, so "assert the
refusal" could pass with a live answer in hand. `tests/conftest.py` now neutralises the
loader for every test (`no_dotenv_loading`), which fixes all sixteen at once and keeps each
test's own `setenv` working. Before: 16 failed, 32 passed. After: 48 passed.

### Fixed — the conduct block claimed a server-side guard that does not exist

`app/harness/conduct.py` told the model that the three-cycle reveal threshold was "the same
threshold the answer-leakage guard enforces server-side", and `socratic.may_reveal_answer`
was documented as what "the answer-leakage guard calls". No such guard is wired:
`socratic.step()` is computed in `app/harness/loop.py` and injected into the prompt as state,
so the rule is an instruction the model is given, not a filter on what it produces. Both
statements now say what runs, and `may_reveal_answer` carries the scope it actually has.

### Pending

- **A signed, notarized artifact.** Blocked on credentials, not on code.
- **A green full run of all 122 test files in one process.** The suite needs
  `--basetemp` on this machine (the sandbox intercepts `mkdir` in the default base
  directory) and a single-process run is killed before it finishes, so verification is done
  in batches. Every batch run for this change was green; "the whole suite is green in one
  run" remains unmeasured here, and the blocking CI job exists to produce it.
- **Concept ids that survive a pack rewrite.** See the upgrade warning above: a stable,
  outline-independent id would make regeneration safe, and that is a design change rather
  than a fix.
