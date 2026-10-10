# Decisions

Newest first. Each entry: date, decision, why, alternatives considered.

## 2026-10-10 — Bootstrap decisions
- **XcodeGen for the iOS project.** `ios/project.yml` is the source of truth; the `.xcodeproj` is
  generated and gitignored. *Why:* agents can't safely hand-edit `.pbxproj`, and it merges badly
  across parallel branches.
- **iOS builds and tests in CI on macOS runners** (`.github/workflows/ios.yml`), free for this
  public repo — parked in `ci/github-workflows/` until a token with the Workflows permission moves them into `.github/workflows/`. *Why:* gives iOS QA a reproducible gate that doesn't depend on whose Mac is open.
- **ML training/inference runs off-box** (Colab / GPU), behind `ML_SERVICE_URL`, with a
  **Gemini-vision fallback** in the backend. *Why:* no GPU on the dev server; the demo must not
  depend on a GPU being up.
- **One Postgres database with TimescaleDB**; `food_events` is a hypertable, state lives in normal
  tables. *Why:* Tigerdata is the stack's time-series store and it's an extension, not a second DB.
  Image pinned to `timescale/timescaledb:2.17.2-pg16`.
- **Removal is a soft delete + an event in the same transaction**; impact numbers are always
  computed from events, never stored as totals. *Why:* one source of truth for the dashboard.
- **Flask + Flask-SQLAlchemy + Flask-Migrate**, JWT auth, gunicorn in Docker.
- **Ports bind to `127.0.0.1`** (API 5055, DB 5433).

## Open — to decide and record here
- **YOLO version:** confirm the current Ultralytics release before training. Note Ultralytics is
  **AGPL-3.0** — fine for a public hackathon repo, matters if this is ever closed-source.
- **Gemini model id** (`GEMINI_MODEL`): pick the current Flash-class model for cost/latency.
- **CO₂ factors:** proposed source — Poore & Nemecek (2018, *Science*), via Our World in Data's
  per-kg food emissions tables, mapped onto our spoilage categories.
- **Final category list** for spoilage groups (draft in `SCHEMA.md`).
- **Expiry defaults** per category/storage (proposed source: USDA FoodKeeper).
