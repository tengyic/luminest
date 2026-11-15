# Admission criteria — closed alpha

## Hard requirement: macOS 14+ on Apple Silicon

The native macOS app targets **Apple Silicon** (M1 / M2 / M3 / M4) and requires
**macOS 14 (Sonoma)** or newer. Intel Macs and macOS < 14 are **not supported** by the
native build.

**Check before installing:**

- **macOS version** — must be **14.0 or higher**:
  ```sh
  sw_vers -productVersion
  ```
- **Chip** — Apple menu ▸ About This Mac shows "Apple M1/M2/M3/M4", or:
  ```sh
  sysctl -n machdep.cpu.brand_string    # contains "Apple" on Apple Silicon
  ```

If you are **not** on Apple Silicon / macOS 14+, use the **Web workbench** instead
(cross-platform; ask the operator for the URL). The native app will not launch.

## Why this is the bar

The native app uses SwiftUI + AppKit APIs and an entitlements set (microphone input,
screen capture) validated against macOS 14+. Broadening the support matrix (Intel, older
macOS, or other OSes) is a later release decision, not an alpha blocker.

## Tester self-check

| Check | Must be |
| --- | --- |
| `sw_vers -productVersion` | ≥ 14.0 |
| Chip | Apple Silicon (M-series) |
| Backend reachable | operator has shared the local backend URL / launch steps (CONFIG.md) |
| Signed agreement | INTERNAL_ALPHA_AGREEMENT.md completed |
