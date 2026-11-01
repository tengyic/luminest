# HANDOFF — AI Learning Software (`ai-learning-software`)

> Self-contained brief for an **inheriting agent** to continue the iOS adaptive-learning app
> + FastAPI backend. Everything in this pack (except `.workbuddy`) is the project. Paste
> `AGENT_PROMPT.md` into a fresh session to bootstrap.

---

## 0. What this project is

- **Repo:** `jd388/ai-learning-software` (private GitHub). Local working copy = root of this pack.
- **Two parts:**
  - `AIStudyApp/` — iOS **SwiftUI** frontend (the app the user opens in the Simulator).
  - `AIStudyBackend/` — **FastAPI** backend (SQLAlchemy 2.x + Pydantic), serves the adaptive engine.
- **Goal:** a student picks a subject → gets a personalized learning path → studies lessons
  (real content + diagrams) → does exercises → reviews mistakes → sees **5-dimension learning
  analytics** (深度 / 广度 / 速度 / 准确度 / 坚持度).

---

## 1. Status at handoff (2026-09 / 2026-10)

| Area | State |
|------|-------|
| Frontend | `origin/main` merged into branch **`feature/three-tab-pages`**; our adaptive-engine feature code is primary. |
| Backend | Runs on **`127.0.0.1:8001`** via `uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001`. |
| 5-dim analytics | Restored after the main merge (commit `4dc26b5`): `learning_dimensions` in `AnalyticsResponse`. Verified returning 深度/广度/速度/准确度/坚持度. |
| iOS build | Compiles for **iPhone 17 Simulator, iOS 26.5, Xcode 26.6** with `ENABLE_PREVIEWS=NO` (see §5). |
| Lesson content | `LessonDetailView.swift` added (immersive lesson reader); `LearningView.swift` fonts enlarged. A string-indentation bug in the ASCII-diagram literals was fixed by lowering the closing `"""` to the min-content indent. |
| App launch | Booted the iPhone 17 sim and built successfully; not yet auto-launched into the sim in this session. |

---

## 2. The user's requirements (intent, verbatim)

1. **Pull the newest frontend** from `https://github.com/jd388/ai-learning-software`.
2. **Reconnect the iOS frontend to the FastAPI backend.**
3. **Add the features** (previously built, were uncommitted):
   - image / video **low-mastery display**
   - **flowchart problem-solving**
   - **mistake retest**
   - **5-dimension learning analytics** (radar + badges): 深度 / 广度 / 速度 / 准确度 / 坚持度
4. **Make the "learning material" actually a textbook, not a directory of tiny cards:**
   - full explanation per knowledge point (definition + detailed explanation + example)
   - diagrams / illustrations (Venn diagrams, formula trees, etc.)
   - readable font sizes
   - working exercise cards (reveal answer, highlight correct option, show solution)
5. **Be able to actually open / run the app** (Simulator).

---

## 3. Backend facts (FastAPI)

- **App factory:** `app.main:create_app` — must run with `--factory`.
- **Router prefix:** `/api/v1`.
- **Key endpoints:**
  - `POST /students` — body requires `name`, `age_stage` (`primary` | `junior_high` | `senior_high`), `learning_goal`, `subjects[]`, `daily_minutes`. Returns `{ "student": { "id", ... }, "access_token" }`.
  - `GET /students/{id}/analytics` — **auth header `x-student-token: <access_token>`**. Returns `AnalyticsResponse` with `learning_dimensions` (深度/广度/速度/准确度/坚持度), `radar`, `chapter_maturity`, `badges`, `learning_speed`, `skill_points`, `learning_depth`, `completed_lessons`, `total_lessons`, `open_mistakes`.
  - `GET /students/{id}/home`, `GET /catalog`, `GET /textbook/{code}`.
- **Where things live:** `AnalyticsResponse` / `LearningDimension` schemas in `AIStudyBackend/app/schemas.py`; `get_analytics()` in `services.py`; route in `api.py`.
- **DB:** SQLAlchemy 2.x; Pydantic `response_model`.

---

## 4. Frontend facts (SwiftUI)

- **Entry:** `AppRootView.swift` wires `LearningView` / `MistakesView` / `HomeView` + `BackendStore().bootstrap()`.
- **Network:** `Models/BackendStore.swift` + `APIClient.swift` — `baseURL = "http://127.0.0.1:8001"`. Calls `/students`, `/students/{id}/diagnostics/{subject}`, `/diagnostics/{id}/submit`, `/students/{id}/learning-sessions/next`, `/learning-sessions/{id}/content-complete`, and `getAnalytics` → `GET /students/{id}/analytics`.
- **Embedded textbook:** `Models/TextbookStore.swift` + `TextbookData.swift` → `TextbookEmbeddedData`: **5 chapters, 60+ knowledge points** with real content + exercises. This is the source for the lesson reader.
- **Lesson reader (new):** `Learning/LessonDetailView.swift` — full-screen lesson view; renders knowledge points (expandable definition + explanation + example), materials by type (reading / image / video / flowchart / audio), and interactive exercise cards.
- **Learning list:** `Learning/LearningView.swift` — chapter list; each lesson row pushes (`NavigationStack`) to `LessonDetailView`; has a "开始学习" button and per-lesson counts (N 知识点 / N 资料 / N 练习).

---

## 5. Environment limitation — READ BEFORE BUILDING

- The **Swift macro plugin server** (`swift-plugin-server`) is **blocked in the WorkBuddy sandbox** →
  any `@Observable` / `#Preview` macro build fails with `swift-plugin-server could not be loaded:
  Operation not permitted`. The plugin binary runs fine in isolation but is killed when `swiftc`
  spawns it inside a build (even with `dangerouslyDisableSandbox=true`).
- **Workaround that WORKS:** build with **`ENABLE_PREVIEWS=NO`** (skips `#Preview` macro expansion).
  `@Observable` is a built-in macro and compiles fine.
  ```bash
  xcodebuild -scheme AIStudyApp -configuration Debug \
    -destination 'platform=iOS Simulator,id=<UDID>' build ENABLE_PREVIEWS=NO
  ```
- **To run in the Simulator:**
  ```bash
  xcrun simctl boot <UDID>                       # boot (e.g. iPhone 17, iOS 26.5)
  xcodebuild -scheme AIStudyApp -configuration Debug \
    -destination 'platform=iOS Simulator,id=<UDID>' build ENABLE_PREVIEWS=NO
  xcrun simctl install booted <path-to-.app>
  xcrun simctl launch booted <bundle-id>
  ```
- On a **real Mac with Xcode**, you can just `open AIStudyApp/AIStudyApp.xcodeproj` and press ⌘R.
  The plugin server works there, so `ENABLE_PREVIEWS=NO` is not needed.

---

## 6. Decisions already made (do not re-litigate)

- `origin/main` is a **textbook-READER** frontend (calls `/api/v1/textbook/{code}` at `:8000`) —
  **incompatible** with our adaptive engine (BackendStore at `:8001`). Decision: keep our feature
  code as primary; merge `main` only for assets / latest baseline; **delete conflicting main files**
  (already done — 9 files removed, verified no dangling references).
- `learning_dimensions` was dropped by the main merge; **restored** in the backend (commit `4dc26b5`).
- Student-create field names: create returns **`student.id` + `access_token`** (NOT `token`);
  analytics uses the **`x-student-token`** header.
- **Do NOT re-introduce** the deleted main files (`SampleData`, `LearnView`, `ProfileView`,
  `PentagonGraph`, `SkillTopology`, `SubjectDonut`, `UsageChart`, main's `TextbookStore`) — they
  duplicate our symbols and would cause duplicate-symbol compile errors.

---

## 7. Suggested next steps for the inheriting agent

- [ ] On a real Mac, run a full Xcode build (plugin server available) to surface any type errors the
      sandbox hid behind `ENABLE_PREVIEWS=NO`; fix them.
- [ ] Verify the **learning flow end-to-end in the Simulator**: create student → home → chapter →
      "开始学习" → lesson reader → exercise reveal → mistake retest → analytics radar.
- [ ] Fully wire the **multimodal features** (image/video low-mastery display, flowchart
      problem-solving) — scaffolding exists; confirm backend endpoints back them.
- [ ] Confirm backend `learning_dimensions` render correctly in `HomeView`'s radar.
- [ ] Commit the `LessonDetailView` string-indentation fix and push `feature/three-tab-pages` to remote.
- [ ] (Optional) Re-enable `#Preview` macros once building on a real Mac.

---

## 8. Quick start

```bash
# Backend
cd AIStudyBackend
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001

# Frontend — real Mac
open AIStudyApp/AIStudyApp.xcodeproj        # then ⌘R, choose iPhone 17 Simulator

# Frontend — headless / sandbox-safe
xcrun simctl boot <UDID>
xcodebuild -scheme AIStudyApp -configuration Debug \
  -destination 'platform=iOS Simulator,id=<UDID>' build ENABLE_PREVIEWS=NO
```

---

## 9. File map

| Path | What |
|------|------|
| `AIStudyApp/AIStudyApp/` | SwiftUI sources: `AppRootView`, `Learning/*`, `Mistakes/*`, `Home/*`, `Models/*`, `Components/*` |
| `AIStudyBackend/app/` | `main.py`, `api.py`, `schemas.py`, `services.py`, `models.py`, `db.py` |
| `操作说明/项目说明文档.md` | Project doc (Chinese) |
| `学习系统调研报告-两篇.zip` | Learning-system research report |
| `报告-学习节奏与排程研究（换脑子·时间曲线·科目排程）.md` | Study-rhythm / scheduling research |
| `报告-学生梯队阶层与课时压缩稀释分层模型.md` | Student-tier / lesson-dilution model |
| `学习素材生成技术方案.md` | Learning-material generation spec |
| `自适应学习后端引擎.zip` | Adaptive backend engine reference |
| `gen_swift_data.py`, `embed_json.py`, `extract_pdf.py` | Data-gen / PDF helpers |
| `learn-your-way-web/` | Web variant of the learning app |
| `adaptive-engine/` | Adaptive-engine Python reference |
