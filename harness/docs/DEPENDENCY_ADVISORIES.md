# Dependency advisories — exact status

## Bottom line

Advisories are **open, not fixed by this work**. Do not report the historical "13 advisories"
as resolved: a fresh scan on 2026-11-16 found **14 advisories in 5 packages** in the
installed development environment. No suppression flags were used and no pin was changed
here. Remediation (bumping pins) remains a separate dependency PR.

## Scanner and commands

- Scanner available: `backend/.venv/bin/pip-audit` → `pip-audit 2.9.0`, pinned at
  `backend/requirements-dev.txt:46`. The system `python3` has no `pip_audit` module.
- Network permitted for the installed-environment scan (the OSV-style service responded).

Commands operators must run on a clean runner — these are the **authoritative CI scans**
from `docs/evidence/2026-11-11/pip-audit.txt` and the `dependency-audit` job in
`.github/workflows/quality.yml`:

```sh
cd <git-root>
pip-audit -r harness/backend/requirements.txt --progress-spinner off
pip-audit -r harness/backend/requirements-optional.txt --progress-spinner off
```

## What was actually run here, and what was blocked

| Command | Date | Result |
| --- | --- | --- |
| `cd harness/backend && .venv/bin/pip-audit --cache-dir /tmp/pa_cache_20261116 --progress-spinner off --timeout 45` | 2026-11-16 | **Executed.** Exit `1` (findings). 14 advisories / 5 packages — full table below. |
| `cd harness/backend && .venv/bin/pip-audit -r requirements.txt --cache-dir /tmp/pa_cache_20261116 --progress-spinner off --timeout 45` | 2026-11-16 | **Blocked, not a scan result.** Exit `1` with a traceback: pip-audit builds an internal resolution venv and `ensurepip` aborts in this sandbox. Same environment limit recorded on 2026-11-11. |
| `-r requirements-optional.txt` | 2026-11-16 | **Not executed** (same helper-venv blocker; the CI job is the place it runs). |

Scope caveat: the installed dev environment (`.venv`, Python 3.14) is a **superset** of the
pinned runtime set. It is a valid heads-up, not the authoritative runtime result. The
authoritative set is `requirements.txt` + `requirements-optional.txt`, which only CI's
`-r` scans can establish here. Findings are recorded, never suppressed — no
`--ignore-vuln`, `--fix`, `continue-on-error` or `|| true` was added.

## Latest scan — installed dev venv, 2026-11-16 (exit 1)

| Package | Installed version | Advisory | Fix available |
| --- | --- | --- | --- |
| certifi | 2026.7.22 | PYSEC-2026-4320 | 2026.10.18 |
| opentelemetry-api | 1.45.1 | GHSA-mf5v-w3w3-f6cg | 1.45.2 |
| pip | 25.3 | PYSEC-2026-196 | 26.1.2 |
| pip | 25.3 | PYSEC-2026-1796 | 26.0 |
| pip | 25.3 | PYSEC-2026-2875 | 26.1 |
| pip | 25.3 | PYSEC-2026-2876 | 26.1 |
| pip | 25.3 | PYSEC-2026-3721 | 26.2 |
| pyasn1 | 0.6.4 | GHSA-2qm8-x737-gmw5 | 0.6.5 |
| pyasn1 | 0.6.4 | GHSA-fm9c-5rcf-2q5p | 0.6.5 |
| pyasn1 | 0.6.4 | GHSA-mm57-4v3p-rchx | 0.6.5 |
| pyasn1 | 0.6.4 | GHSA-9m75-vc3g-4x39 | 0.6.5 |
| urllib3 | 2.7.0 | PYSEC-2026-4177 | 2.8.0 |
| urllib3 | 2.7.0 | PYSEC-2026-4176 | 2.8.0 |
| urllib3 | 2.7.0 | PYSEC-2026-4175 | 2.8.0 |

`pip` is the installer, and `pyasn1`/`urllib3`/`certifi` reach the venv through the dev
superset; whether each is in the runtime-pinned set is something only the CI `-r` scans can
say. The new `opentelemetry-api` finding is why the count moved from 13 to 14 — evidence
that the earlier number was a point-in-time observation, not a closed item.

## Last known authoritative-ish record (2026-11-11)

`docs/evidence/2026-11-11/pip-audit.txt` records an installed-environment scan with
13 advisories in 4 packages (the same certifi/pip/pyasn1/urllib3 rows, without
`opentelemetry-api`), run at 2026-11-11T07:42:13Z. It explicitly states `-r` scans could not
run in the sandbox, that findings are recorded rather than suppressed, and that
remediation is left to a dedicated dependency PR. `backend/requirements.txt` carries a
comment that a version was bumped by that shipping audit following a pip-audit report.

## Required operator actions

1. Run both authoritative `-r` scans on a clean runner (CI does this in `dependency-audit`).
2. Record the full stdout, exact command, exit code and UTC timestamp as evidence.
3. Open a dedicated dependency PR bumping the affected pins; do not bundle it into a
   shipping/evidence commit and do not mask the finding to turn the job green.
4. Re-run `docs/SECURITY.md` claims after remediation; until then the honest status is
   "advisories open, dev superset last measured at 14, CI authoritative result not
   established in this environment."
