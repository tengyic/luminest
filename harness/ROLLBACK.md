# Rollback — Lumen Harness (unsigned staging artifact)

This document covers the **only** supported rollback for the unsigned staging artifact
produced from commit `a7bfb6d5b433e25518a05b97f3fef6fe94881c96`.

## What "rollback" means here

- Return the working tree and branch tip to the staging commit.
- Verify the staging archive's integrity with its accompanying `.sha256`.
- It does **NOT** involve restoring secrets, `.env`, or `model_config.json`, and it does
  **NOT** rotate any credentials or keys. The staging archive is built from tracked files
  only (`git archive HEAD`) and contains no secrets, so there is nothing secret to restore.

## Steps

1. From the repository root, return to the staging commit:

   ```sh
   git checkout a7bfb6d5b433e25518a05b97f3fef6fe94881c96
   ```

   If you have local commits layered on top of it:

   ```sh
   git reset --hard a7bfb6d5b433e25518a05b97f3fef6fe94881c96
   ```

2. Verify the staging archive you are holding:

   ```sh
   shasum -a 256 -c outputs/staging/lumen-harness-staging-a7bfb6d5b433.tar.gz.sha256
   ```

   Expected output: `outputs/staging/lumen-harness-staging-a7bfb6d5b433.tar.gz: OK`

3. If the archive fails the check, discard it and rebuild or re-fetch from the commit
   above. Do not ship or trust an archive whose checksum does not verify.

## Notes

- This is an **UNSIGNED** staging artifact: no codesign, no notarization,
  not shippable, not distributable. A signed, notarized release remains blocked on
  credentials — see `CHANGELOG.md` → `## Unreleased` → `### Pending`.
- A real production rollback additionally requires the production operator to restore
  their own secrets from their own secret store. That step lives outside this repository
  and is explicitly out of scope for this document.
