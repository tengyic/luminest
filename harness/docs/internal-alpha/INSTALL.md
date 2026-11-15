# Install & run (macOS 14+ / Apple Silicon)

## 1. Unzip
Unpack `Luminfest Learning Harness-internal-alpha.zip`. You get
`Luminfest Learning Harness.app`.

## 2. Bypass Gatekeeper (one time)
The app is **ad-hoc signed** (self-signed), **not notarized**, so macOS refuses to open it
with *"cannot be opened because the developer cannot be verified."* Choose one:

**Easiest** — right-click the `.app` ▸ **Open** ▸ **Open** in the dialog. This authorises
that one app permanently.

**From Terminal** (strips the quarantine flag):
```sh
xattr -dr com.apple.quarantine "/path/to/Luminfest Learning Harness.app"
```

**Keep Gatekeeper informed** (instead of stripping the flag):
```sh
spctl add --label luminfest-alpha "/path/to/Luminfest Learning Harness.app"
spctl --add --label luminfest-alpha
```

## 3. Start the backend
See CONFIG.md. The app discovers the backend on `127.0.0.1:8765–8785`; start it first.

## 4. Launch
Open `Luminfest Learning Harness.app`. Register an account, complete onboarding, and you
reach your plan. All Plus capabilities are free for the alpha (`HARNESS_ALPHA_FREE=1`).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| "App is damaged" / "cannot be verified" | You skipped step 2 — re-run the `xattr` / `spctl` step. |
| Blank window / no plan | Backend not running or on a blocked port — confirm `curl -fsS http://127.0.0.1:8000/api/v1/health`. |
| App won't launch at all | Not on Apple Silicon / macOS 14+ — see ADMISSION.md, or use the Web workbench. |
| Tutor / course creation inert | No LLM provider configured — see CONFIG.md §2. |
