# AGENT_PROMPT.md — AI Learning Software handoff (paste into a new session)

You are inheriting the **`ai-learning-software`** project: an iOS SwiftUI adaptive-learning app
(`AIStudyApp/`) backed by a FastAPI engine (`AIStudyBackend/`). Full context is in `HANDOFF.md`
in this same folder. Read it first. Summary of the user's standing requirements and hard constraints:

## User's requirements (must satisfy)
1. Keep the frontend synced with the newest `origin/main` from `https://github.com/jd388/ai-learning-software`.
2. The iOS app must be **reconnected to the FastAPI backend** (`http://127.0.0.1:8001`).
3. Deliver these features (scaffolding exists; verify/finish wiring):
   - image / video **low-mastery display**
   - **flowchart problem-solving**
   - **mistake retest**
   - **5-dimension learning analytics** (radar + badges): 深度 / 广度 / 速度 / 准确度 / 坚持度
     (backend already returns `learning_dimensions` via `GET /students/{id}/analytics`, header `x-student-token`).
4. The "learning material" must read like a **real textbook**, not a directory of tiny cards:
   full per-knowledge-point explanations (definition + detail + example), diagrams/illustrations,
   readable font sizes, and working exercise cards (reveal answer, highlight correct option, show solution).
   Implemented in `Learning/LessonDetailView.swift` + enlarged `Learning/LearningView.swift` — extend, don't regress.
5. The user must be able to **actually open/run the app** in the iOS Simulator.

## Hard constraints / gotchas (do NOT re-litigate)
- `origin/main` is a textbook-READER frontend (calls `/api/v1/textbook/{code}` at `:8000`) and is
  **incompatible** with our adaptive engine (BackendStore at `:8001`). Keep our feature code primary;
  merge main only for assets/baseline. Do NOT re-add the deleted main files
  (`SampleData`, `LearnView`, `ProfileView`, `PentagonGraph`, `SkillTopology`, `SubjectDonut`,
  `UsageChart`, main's `TextbookStore`) — they cause duplicate-symbol errors.
- Student create returns `student.id` + `access_token` (NOT `token`); analytics uses `x-student-token` header.
- `learning_dimensions` was lost in a merge and restored (commit `4dc26b5`) — keep it.

## Build / run (IMPORTANT)
- In the **WorkBuddy sandbox**, the Swift macro plugin server is blocked → build with
  `ENABLE_PREVIEWS=NO`:
  `xcodebuild -scheme AIStudyApp -configuration Debug -destination 'platform=iOS Simulator,id=<UDID>' build ENABLE_PREVIEWS=NO`
- On a **real Mac with Xcode**, just `open AIStudyApp/AIStudyApp.xcodeproj` and ⌘R.
- Backend: `cd AIStudyBackend && uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001`

## First actions I recommend
1. Read `HANDOFF.md` §3–§6.
2. Start the backend, create a student (`age_stage: senior_high`, `subjects: ["math"]`, `daily_minutes: 60`),
   and `GET /students/{id}/analytics` to confirm `learning_dimensions` returns 5 values.
3. Boot the iPhone 17 Simulator (iOS 26.5) and build with `ENABLE_PREVIEWS=NO`; walk the learning flow.
4. Report any compile errors the sandbox hid, then fix and commit on branch `feature/three-tab-pages`.
