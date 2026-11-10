# Release runbook

The order matters: every gate below refuses to run on an artifact that has not already
passed the gate above it, so running them out of order does not save time — it produces a
release nobody verified.

`DISTRIBUTION.md` is the reference for the packaging commands. This file is the checklist
and the rollback plan for a release, and it records what is still missing.

## 0. Preconditions that are not negotiable

| Gate | Command | What it proves |
| --- | --- | --- |
| Full suite, shipping Python | CI job `full-suite-on-the-shipping-runtime` | Every test in `backend/tests/` passes on 3.12, the version `python:3.12-slim` runs. The job asserts its own interpreter against the Dockerfile, so a Dockerfile bump without a workflow bump fails the build. |
| Dependency gate | `pip-audit -r backend/requirements.txt` | No known vulnerability in anything the image installs. Requires every pin to be exact; a range makes `pip-audit` refuse to scan, which is why the requirements files carry `==`. |
| Legal gate | `python backend/scripts/check_legal.py` → `LEGAL OK` | No unfilled bracket placeholders in `backend/legal/`. `Settings.from_env()` refuses `HARNESS_ENV=production` without this, so a hosted deploy cannot skip it. |
| Legal sign-off | human | `LEGAL OK` means "filled", not "reviewed". The five open items in `backend/legal/FILL_IN_SHEET.md` require counsel. Nothing in this repository can substitute for that. |
| Deploy boot | `cd deploy && docker compose config && docker compose up -d` | The hosted deployment actually starts: migration completes, `/api/v1/health` reports `tutor.state: configured`. |

## 1. Build and sign (macOS)

```sh
cd harness
python scripts/package.py --version <version>
```

`package.py` also runs the visual-asset gate: the `.app` must carry the whole offline
WebView host (`index.html`, `styles.css`, `visuals.bundle.js`, `vendor/` **and its fonts**),
because SwiftPM's `.process` rule flattens a resource directory and leaves `index.html`
alone. A build that fails that gate launches fine and then renders
`RENDERER_ASSETS_NOT_INSTALLED` on every inserted visual.

Signing needs a **Developer ID Application** certificate in the login keychain and an Apple
ID with an app-specific password for notarization. Neither is present on the current build
machine:

```
$ security find-identity -v -p codesigning
     0 valid identities found
$ ls ~/.appstoreconnect/private_keys
ls: No such file or directory
```

`release_kit.py` refuses ad-hoc builds outright. **This is the release blocker that cannot be
worked around from the repository:** an unsigned or un-notarized build is not a release, and
relabelling one as a release is the failure mode the script exists to prevent. Provide a
Developer ID certificate and notarization credentials, or accept that the deliverable is a
build artifact rather than a release.

## 2. Assemble the release

```sh
python scripts/release_kit.py --version <version> --verify
```

Produces `outputs/release/<version>/`: versioned DMG and ZIP, `INSTALL.txt`,
`SHA256SUMS.txt`, `RELEASE.md`, `release.json`. `--verify` re-checks the copied artifacts;
it cannot be used to skip the signature and notarization checks on the source build.

## 3. Rollback

### Desktop build

The app writes only to `~/Library/Application Support/Luminfest Learning Harness/`.
Reinstalling a previous version from its DMG restores the previous behaviour, and the data
directory is forward-compatible: `init_db.py` refuses to migrate a database whose schema is
ahead of its version stamp when a rollback snapshot exists, naming the file to restore.

To roll back deliberately:

1. Quit the app.
2. Copy the current data directory aside — `cp -R` to a sibling folder, not a move, because
   the app recreates a missing directory as empty on next launch.
3. Install the previous DMG over the existing app.
4. If the previous version refuses to start, its `init_db.py` will name the pre-migration
   snapshot to restore. Restore that file in place of `harness.sqlite3` and relaunch.

Deleting the app does **not** delete the data directory. That is intentional — an uninstall
must not silently destroy a learner's course — so rollback never loses work, and cleanup is
always a separate, explicit act.

### Hosted deployment

```sh
cd deploy
docker compose down            # leaves postgres-data and ollama-models volumes intact
git checkout <previous-commit>
docker compose up -d --build
```

If the schema moved forward and the previous version cannot read it, restore the
pre-migration snapshot from inside the postgres volume. The application does not migrate a
database backwards.

### Schema

`schema_version` is stamped in the database, not in the app bundle. A back-level app pointed
at a forward-level database refuses to start rather than writing into a schema it does not
understand. Treat any schema bump as requiring a snapshot first — `init_db.py` writes its own
pre-migration anchor, but that anchor lives inside the same volume it protects.

## What this runbook cannot do

- It cannot sign. See §1.
- It cannot review the legal text. `LEGAL OK` is a placeholder check.
- It cannot confirm the full suite on the shipping runtime without CI. The local agent
  sandbox blocks the filesystem operations pytest needs for its temp directories, so a local
  full run reports every test as an error at setup; that is an environment artifact, not a
  product failure, and it is also not evidence.
