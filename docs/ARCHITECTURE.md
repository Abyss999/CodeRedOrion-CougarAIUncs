# Architecture

```
 iOS app (SwiftUI)                                   off-box (GPU / Colab)
   │  HTTPS + JWT                                    ┌──────────────────────┐
   ▼                                                 │ ml/serve             │
 Flask API (backend/, gunicorn, Docker) ── HTTP ───▶ │ YOLO detect+spoilage │
   │   │   │                                         │ GLM-OCR receipts     │
   │   │   └── Gemini API (recipes, text parse,      └──────────────────────┘
   │   │        expiry inference, vision fallback)
   │   └────── Open Food Facts (barcode lookup)
   ▼
 PostgreSQL + TimescaleDB (Docker)
   relational tables: users, items, groups, share_listings, requests…
   hypertable: food_events (add / share / expiry_warning / remove)
```

## Components
| Component | Where | Notes |
|---|---|---|
| iOS app | `ios/` | SwiftUI, XcodeGen. Talks only to the Flask API through an `APIClient` protocol (mock impl for previews/tests). |
| API | `backend/` | Flask app factory, blueprints per area, services wrap every external call. Stateless; JWT auth. |
| DB | Docker `db` service | `timescale/timescaledb` (pinned tag). One database. Migrations via Flask-Migrate. |
| ML service | `ml/serve/` | Flask: `POST /detect` (YOLO26 food-name detector, then a fresh/semi_fresh/spoiled crop classifier), `POST /ocr` (GLM-OCR, then the deterministic receipt parser), `GET /health`. Runs where there's a GPU, with fake backends for CPU tests. Backend reaches it at `ML_SERVICE_URL`. **If it's unset or returns an error, `/items/from-photo` falls back to Gemini vision**, so the demo never depends on a GPU being up. Receipts have no fallback. It has no auth, so keep it on loopback or a tunnel. Details: `docs/ML.md`. |
| Data pipeline | `pipeline/` | Offline CLI (`python -m pipeline`): dataset ingestion → `prepare_dataset.py` → lighting augmentation for training, and a receipt inbox that runs GLM-OCR (locally or through `ml/serve`) with timeouts and quarantine, then category-tags each line. Not part of the request path. Details: `docs/PIPELINE.md`. |
| Gemini | external | One service module (`backend/app/services/gemini.py`). Model id pinned in `.env` (`GEMINI_MODEL`) and recorded in `DECISIONS.md`. |

## Key flows
- **Add by photo:** iOS uploads image → `POST /items/from-photo` → ML service (or Gemini) returns
  detected items + freshness → backend adds expiry prediction → iOS shows a confirm sheet →
  `POST /items` (batch) → `add` events written.
- **Remove:** swipe → 3-option sheet → `POST /items/:id/remove` → one transaction: soft delete +
  `remove` event (+ fulfil share listing on `donated`).
- **Impact:** `GET /impact` aggregates `food_events` with `time_bucket`, and returns zeros (not an error) for a user with no events.
- **Social (Wave 3):** friends, groups with their own pantries, the Food Pantry share board and the request board. Visibility is limited to accepted friends and fellow group members. See `docs/API.md`.

## Deployment
- Local / demo: `docker compose up` (API on `127.0.0.1:5055`, DB on `127.0.0.1:5433`).
- iOS: TestFlight. For a device to reach the API, the API must be reachable from the phone
  (same LAN, or a tunnel/host) — **open question in `HANDOFF.md`.**
