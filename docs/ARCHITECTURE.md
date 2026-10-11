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
| iOS app | `ios/` | SwiftUI (iOS 18+, built with the iOS 26 SDK), XcodeGen. Talks only to the Flask API through an `APIClient` protocol (Live and Mock clients). The JWT is kept in the Keychain. The base URL is set at runtime (Debug settings). 22 screens, see `docs/design/SCREENS.md`. |
| Auth | `backend/` + Google | Email/password, plus Google Sign-In (the iOS SDK obtains an ID token, the backend verifies it against Google's JWKS and issues our JWT). Identities live in `user_identities(provider, subject)`. No Apple sign-in. |
| API | `backend/` | Flask app factory, blueprints per area, services wrap every external call. Stateless; JWT auth. Runs as one gunicorn `gthread` worker with 4 threads (`GUNICORN_THREADS`), `--timeout 120`, so a slow Gemini call doesn't block other requests while in-process caches stay shared. |
| DB | Docker `db` service | `timescale/timescaledb` (pinned tag). One database. Migrations run automatically when the api container starts (`backend/entrypoint.sh`). |
| ML service | `ml/serve/` | Flask: `POST /detect` (YOLO26 food-name detector, then a fresh / semi_fresh / spoiled crop classifier), `POST /ocr` (GLM-OCR, then the deterministic receipt parser), `GET /health`. Runs where there's a GPU, with fake backends for CPU tests. Backend reaches it at `ML_SERVICE_URL`. **If it's unset or returns an error, `/items/from-photo` falls back to Gemini vision**, so the demo never depends on a GPU being up. Receipts have no fallback. It has no auth, so keep it on loopback or a tunnel. Details: `docs/ML.md`. |
| Gemini | external | One service module (`backend/app/services/gemini.py`). Model id in `.env` (`GEMINI_MODEL`), recorded in `DECISIONS.md`. Every call logs token usage (`scripts/gemini_cost.py`), and recipe suggestions are cached per user. |
| Training | Colab + `ml/yolo/train_colab.ipynb` | Data from 8 sources (VegQual, fridge_objects, hien_fridge, food_spoilage_status, Kaggle fresh/stale, AgriFreshNET, MeatScan, DaFiF; food_hvk7g pending) through `pipeline/` (`fetch-*`, `ingest-dataset`) and `prepare_dataset.py`. Leakage, stratification and parent-photo gates run before training, with checkpoints and resume on Drive under a `sources.json`-hash cache key. Weights never go in git. |

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
- iOS: the Simulator for development. The demo runs on the owner's iPhone with a **free Personal
  Team** (no TestFlight). The phone reaches the Mac's API through a Cloudflare quick tunnel
  (`scripts/demo_tunnel.sh`, HTTPS), and its URL is pasted into the app's Debug settings.
