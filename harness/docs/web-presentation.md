# The app in a browser tab

`GET /app` presents the running desktop app in a browser, 1:1. Same process, same backend,
same database, same lesson in progress — the browser is a window onto the app, not a second
frontend.

## Why this is a stream and not a web build

The client is SwiftUI: 36 files, ~19,500 lines, and no HTML frontend. `harness/web/` is a
*different* surface (the simulation workbench at `/` and the gallery at `/playground`), not
the app. So "serve the app's frontend to the browser" has no file to serve, and the
ChatGPT/WorkBuddy pattern — one shared React frontend, two shells — is inverted here.

There are exactly three ways to show a native window in a browser:

1. **Rewrite the frontend in HTML.** A second frontend, and the one thing the request ruled
   out: it would drift from the app immediately.
2. **Stream the window and forward input.** What this does.
3. **Drive the app through an API and re-render its state.** A new surface, not the app.

## How it works

```
  ┌──────────────┐   POST /api/v1/stream/window    ┌──────────────┐
  │ SwiftUI app  │ ─────── its own frame ────────▶ │   backend    │
  │  (host)      │                                 │              │
  │              │ ◀──── CGEvent via System ────── │  screen.py   │
  └──────────────┘        Events (input)           └──────┬───────┘
                                                          │ GET /api/v1/stream/frame
                                                          │ (screencapture -R, JPEG)
  ┌──────────────┐                                        │
  │  browser     │ ◀─────────── one JPEG per frame ───────┘
  │  /app        │ ──────────── POST /api/v1/stream/input ─▶
  └──────────────┘
```

**The app reports its own window** (`WindowFrameReporter`, `native/…/WindowStream.swift`),
because the window server will not answer without Accessibility — the permission the *input*
path needs and the capture path deliberately does not. The frame is converted from AppKit's
bottom-left origin to `screencapture`'s top-left one, and the whole frame is reported, title
bar included, because that is what a person sees.

**The capture is cropped to that frame.** A region that was never reported is a refusal, not
a fallback to the whole screen: what a browser sees is the app, not the desktop behind it.

**Input goes through System Events** (`osascript`), so the permission macOS asks for is the
one the user already knows. Clicks are mapped from the rendered canvas back to window
points; printable characters are batched for ~60 ms and sent as one `keystroke`, because one
process per character would spend the whole event budget on a sentence.

## Two one-time permissions

macOS grants both per *binary*, to a human, in System Settings. Neither can be granted by an
installer and neither can be scripted.

| Permission | Needed for | Where |
|---|---|---|
| **Screen Recording** | `screencapture` returning pixels | Privacy & Security → Screen Recording |
| **Accessibility** | System Events clicking and typing | Privacy & Security → Accessibility |

The status route reports which one is missing, in words, and `/app` shows that sentence in
its panel instead of a blank canvas. A capture that comes back empty is reported as a
permission problem, because on macOS that is what it is.

**A whole-screen capture succeeding proves nothing.** Measured on macOS 15:

| State | `screencapture out.jpg` | `screencapture -R x,y,w,h out.jpg` |
|---|---|---|
| display awake | 773 KiB, real content | works — 147 ms, then 142 KiB after re-encode |
| display asleep | 93 KiB, blank | `could not create image from rect` |
| screen locked | succeeds, blank | `could not create image from rect` |

Region capture needs the console *awake and unlocked*; the plain path silently returns
something else instead of failing. So "it works when I run screencapture by hand" is not
evidence, and the probe asks the tool for the *same* rectangle the route will use.

That table is also why the refusal is worded the way it is. A sleeping display, a locked
screen and a missing Screen Recording grant produce the *same* tool error, and only one of
the three is a permission. So the route reads the console before it speaks:
`CGDisplayIsAsleep` (a public API, no subprocess) and `CGSSessionScreenIsLocked` (one
`ioreg` on the failure path). Sleep and lock are reported as themselves; only when the
console is awake does the sentence lead with the grant — and even then it says the error is
also what a display in a transitional state returns, because it is.

**The stream stops when the Mac sleeps, and says so.** Nothing here keeps the display awake:
a remote viewer silently stopping the host from sleeping is a surprise the operator did not
ask for. The page shows "the display is asleep" and resumes on its own when the Mac wakes.

**`-D` is not a workaround.** On this machine `screencapture -D 1` is rejected with
"Invalid display specified. Only 1 display, the only valid value is 1" — the flag disagrees
with itself. `-R` alone is the supported call.

## What the status route does not do

It does not capture. The page polls `/stream/status` every 15 seconds; a status call that
also took a screenshot would make the cheapest route on the page cost as much as the most
expensive one, on a host that is simultaneously rendering the app being streamed. So the
route reports the outcome of the last capture the frame loop actually made
(`capture_checked_ago` says how long ago), and answers `capture: "unknown"` when nothing
has been captured in the last 30 seconds — including on the very first poll, before the
first frame. `unknown` is not "fine": the page says input is permitted and capture has not
been exercised yet, rather than claiming both grants.

`permissions` means *permissions*. A capture refused because the display was asleep is
reported as `console: "asleep"` with the reason in `capture_reason`, and deliberately not
listed under `permissions` — a sleeping Mac is not something to go and grant.

## The switch

`HARNESS_STREAM_ENABLED` — **off by default, in every environment, including `desktop`.**
It is the one capability that captures the host's screen and can post input to it, so an
instance that was never asked for it must never begin capturing. With the switch down:

* `GET /api/v1/stream/status` → 200 with `enabled: false` and the reason;
* `GET /api/v1/stream/frame` → 503 naming the switch;
* `POST /api/v1/stream/window` → 503;
* the app's reporter backs off for a minute after the first refusal rather than asking every
  two seconds.

`POST /api/v1/stream/window` is the app's own report and is the only one of the four that a
normal launch will ever call.

## Who may open it

**Teacher accounts only** (403 for a learner), because this is the host's screen: on a shared
deployment "the host's screen" is every learner's data. The role is read from the
authenticated account, never from the request.

The desktop backend binds `127.0.0.1` and its `HARNESS_ALLOWED_HOSTS` is `localhost,127.0.0.1`.
Presenting the app to another device therefore means changing the bind address, which is a
deployment decision with its own consequences — not something this feature does silently.

## Measured

On the build machine (1470×956 window, Retina):

| Frame | Cost | Size |
|---|---|---|
| `screencapture` alone | 147 ms | 764 KiB |
| + `sips` 1600 px @ 60% | 232 ms | 218 KiB |
| **+ `sips` 1280 px @ 55%** (shipped) | **202 ms** | **142 KiB** |
| + `sips` 1100 px @ 50% | 201 ms | 98 KiB |

So the ceiling is about **4–5 frames per second**, and the page measured 4 fps in a real
browser (`scripts/probe_stream.py`, and a headless Chrome run that signs in through the
page's own form). That is enough to read a lesson, click, and type; it is not video. The page
therefore throttles rather than pretending: `MAX_FPS` is a ceiling and the loop is
latency-bound.

## What it does not do

* No recording. Frames are captured on demand, held for the length of one response, and never
  written to disk or kept.
* No second frontend, no rebuilt `index.html`, no duplicated state.
* No input without Accessibility, and no claim of input when the grant is missing — the
  refusal is a sentence, not a silent no-op.
* Scroll is approximated with page keys: System Events cannot scroll a point.

## Verifying it

```
ui-tests/.venv/bin/python scripts/probe_stream.py --keep-frame .tmp/frame.jpg
```

Starts a real backend with the switch on, registers an operator, reports a frame, fetches a
JPEG, checks that a learner is refused, and prints what the server says about input. It does
not claim to test input delivery: that needs a permission granted by a human, and a probe
that posted nothing and reported green would be the worst kind of pass.
