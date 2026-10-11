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
   relational tables: users, user_identities, items, groups, share_listings,
   requests + request_audiences…
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
| Training | Colab + `ml/yolo/train_colab.ipynb` | Data from 8 enabled sources in `ml/yolo/sources.json` (VegQual, fridge_objects, hien_fridge, food_spoilage_status, Kaggle fresh/stale, AgriFreshNET, MeatScan, DaFiF; food_hvk7g pending) through `pipeline/` (`fetch-*`, `ingest-dataset`) and `prepare_dataset.py`. Leakage, stratification and parent-photo gates run before training, with checkpoints and resume on Drive under a `sources.json`-hash cache key. Weights never go in git. |

## Key flows
- **Add by photo:** iOS uploads image → `POST /items/from-photo` → ML service (or Gemini) returns
  detected items + freshness → backend adds expiry prediction → iOS shows a confirm sheet →
  `POST /items` (batch) → `add` events written.
- **Photo enrichment (opt-in, `enrich=expiry,nutrition` on `POST /items/from-photo`):** after detection, `services/enrich.py` picks up to 12 unique foods (not spoiled, confidence >= 0.5; same name/category/storage/freshness share one answer). On the YOLO path `services/crops.py` cuts one padded crop per detection (512 px JPEG, EXIF/GPS dropped, nothing stored); on the Gemini fallback there are no boxes and the call is text-only. ONE Gemini call (`purpose=enrich`, 25 s, no retry) returns numbers only: shelf-life days, clamped to 0..2 x the table default + 3 and written as `expiry_source: "gemini"`, and nutrition **per 100 g**, checked by `services/nutrition.py` (bounds, macro mass, kcal vs 4P+4C+9F; unusable becomes `null`). The response gains an `enrichment` block; any failure is still a 200 with the table dates. iOS posts the candidate back to `POST /items`, which stores `items.nutrition`. For recipes, `POST /recipes/suggest` may take `item_ids` (1-10) to focus on chosen items; `services/recipe_cache.py` keeps one entry per user keyed on the active items, the options and the focus ids, so a focus request and a plain one evict each other.
- **Remove:** swipe → 3-option sheet → `POST /items/:id/remove` → one transaction: soft delete +
  `remove` event (+ fulfil share listing on `donated`).
- **Impact:** `GET /impact` aggregates `food_events` with `time_bucket`, and returns zeros (not an error) for a user with no events.
- **Social (Wave 3):** friends, groups with their own pantries, the Food Pantry share board and the request board. A request targets friends and/or several groups (`request_audiences`) and shows once on each audience's board. Visibility is limited to accepted friends and fellow group members. See `docs/API.md`.
- **Google sign-in:** the iOS SDK returns an ID token → `POST /auth/oauth/google` verifies it against Google's JWKS (`aud` in `GOOGLE_IOS_CLIENT_IDS`), resolves or creates the user through `user_identities` (auto-link only for verified gmail.com / googlemail.com or an `hd` equal to the email domain) and returns our JWT.

## Deployment
- Local / demo: `docker compose up` (API on `127.0.0.1:5055`, DB on `127.0.0.1:5433`).
- iOS: the Simulator for development. The demo runs on the owner's iPhone with a **free Personal
  Team** (no TestFlight). The phone reaches the Mac's API through a Cloudflare quick tunnel
  (`scripts/demo_tunnel.sh`, HTTPS), and its URL is pasted into the app's Debug settings.
