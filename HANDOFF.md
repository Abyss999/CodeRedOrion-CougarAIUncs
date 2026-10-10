# Handoff

_Last updated: 2026-10-10 (session 1 — bootstrap, on the Linux VPS)_

## Current status
**Phase 0 (bootstrap) is done; no features exist yet.** The repo has the rules (`CLAUDE.md`), the
docs set, and a scaffold for backend, iOS and ML. Next session moves to a **Mac** and starts the
Wave 1 fan-out.

## Done this session
- `CLAUDE.md`: rules, stack, file ownership, multi-agent + QA process, merge gate.
- `docs/`: IDEA, ARCHITECTURE, API (v0 contract), SCHEMA (tables + `food_events` hypertable +
  removal model), SETUP, DECISIONS, QA (plan, thresholds, sign-off log, bug list), design stubs.
- Scaffold: Flask app factory + `/health` + test, Dockerfile, `docker-compose.yml`
  (API + TimescaleDB), XcodeGen `ios/project.yml` + SwiftUI shell + `Theme.swift` + smoke tests,
  `ml/` layout, `.env.example`, `.gitignore`, CI for backend (pytest vs Timescale) and iOS (macOS) — **parked in `ci/github-workflows/`**, not yet active.

## In progress
Nothing.

## Next steps (on the Mac)
0. **Enable CI:** the VPS token couldn't push workflow files. Move `ci/github-workflows/` → `.github/workflows/` (see `ci/README.md`) from the Mac.
1. Setup per `docs/SETUP.md`: clone, `.env`, `.venv`, `docker compose up -d --build`,
   `xcodegen generate`, build the app once.
2. Install Ponytail, taste-skill, the SQL MCP and the Claude Design MCP (`docs/SETUP.md` §6);
   **restart Claude Code**; record the Design MCP's exact install command in SETUP.md.
3. **Wave 1 fan-out** (parallel, each builder with a paired QA agent starting at the same time):
   - Backend core: auth, items CRUD, **removal flow**, events, impact, recipes, parse-text ⇄ Backend QA
   - ML: confirm YOLO version, dataset + Colab training notebook, `ml/serve`, GLM-OCR pipeline ⇄ ML QA
   - Design: the 7 key screens + DESIGN_SYSTEM.md → **team approval**
4. Wave 2: iOS builder ⇄ iOS QA (after design approval). Wave 3: backend social. Wave 4:
   integration QA on the demo path. Wave 5: UI review (Impeccable, web-design-guidelines) only
   once the UI is feature-complete.

## Open questions / blockers
- **`GEMINI_API_KEY`** needed in `.env`.
- **Who uploads to TestFlight** and on which Apple Developer account (bundle id + team in `project.yml`).
- **How the phone reaches the API** for the demo: same Wi-Fi to a laptop, a tunnel, or a hosted
  backend — decide before TestFlight.
- **Claude Design MCP**: exact server name/install command not yet confirmed.
- **Original brainstorm doc** wasn't attached; `docs/IDEA.md` was written from the brief.
- Open technical decisions (YOLO version, Gemini model, CO₂ factors, category list): `docs/DECISIONS.md`.

## QA status
Bootstrap scaffold only — see the sign-off log in `docs/QA.md`. No open bugs.

## How to run everything
See `docs/SETUP.md`. Short version:
```bash
cp .env.example .env                       # fill in
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
docker compose up -d --build && curl 127.0.0.1:5055/health
(cd backend && ../.venv/bin/pytest -q)
(cd ios && xcodegen generate && open FoodWasteReducer.xcodeproj)
```
