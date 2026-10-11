# BiteUp

**Use what you have. Share what you spare.**

BiteUp helps students and shared households keep track of their food, decide what to
cook next, and share surplus with friends. Built for
[CodeRED: Orion 2026](https://codered-orion-ccs.devpost.com/), it brings inventory, AI recipe
suggestions, and food sharing into one iOS app.

[Setup guide](docs/SETUP.md) · [API reference](docs/API.md) · [Project status](HANDOFF.md) · [QA reports](docs/QA.md)

## Why we’re building it

Food gets forgotten at the back of the fridge. Planning a meal takes effort, and extra food
often goes unused even when someone nearby could use it. BiteUp makes the next action
easier: see what needs attention, cook with it, or offer it to a friend.

## The experience

1. **Know what you have.** Add food manually or review suggestions from a photo.
2. **Choose what to use next.** Browse your fridge and pantry by estimated freshness dates.
3. **Make a meal.** Get Gemini recipe suggestions that prioritize ingredients needing attention
   and identify anything missing.
4. **Share the extra.** Offer food to friends or a group, and post requests for ingredients.
5. **Record what happened.** Mark items used, donated, or discarded to keep inventory current
   and build a history of food use and waste.

A guided **Fridge Cleaning** checklist is planned to help new users add their existing food
without typing every item.

## Current implementation

This is an active hackathon prototype. The backend is ahead of the iOS interface.

| Area | What exists | What remains |
|---|---|---|
| Inventory and accounts | Authentication, bulk item creation, editing, storage filters, and removal outcomes | Connect the iOS screens to the API |
| Recipes and photo entry | Gemini integration and an ML-service photo route with Gemini fallback | Verify live AI calls and the complete user flow |
| Sharing | Friends, groups, group pantries, share listings, and requests in the API | Build the iOS interactions |
| Impact | Timestamped food events, outcome totals, weekly trends, and waste tips | Build the dashboard UI and validate the integrated flow |
| iOS | SwiftUI tab shell, shared theme, and recorded shell build checks | Implement functional screens and API connectivity |
| Guided onboarding | Product flow specified | Food catalog, checklist UI, and completion/resume state |
| Vision and receipts | Training pipeline, inference service, receipt-text parser, and evaluation tools | Validate trained models and real image-to-text performance |

The [latest handoff](HANDOFF.md) records **523 backend tests and 96% coverage** on main,
with additional backend and iOS work in QA. These are recorded results, not a fresh validation
of this branch. The [area QA reports](docs/qa/) distinguish component checks from full product
verification. YOLO accuracy and the complete phone demo still need validation.

### How to interpret estimates

- **Freshness dates are estimates.** They depend on the supplied information and category
  defaults. Existing food may already be several days old; users should correct suggested dates.
- **Photos cannot establish food safety.** Recognition and visible-spoilage flags need user
  review and do not guarantee that an item is safe to eat.
- **Outcomes are recorded; impact is modeled.** Used, donated, and discarded items are reported
  actions. Associated value and CO₂e figures use estimates and do not prove additional waste
  prevented or emissions avoided.

## Technology

| Layer | Technology | Purpose |
|---|---|---|
| iOS | SwiftUI, XcodeGen | Native app and shared UI theme |
| API | Flask, SQLAlchemy, Alembic, JWT | Accounts, inventory, sharing, and insights |
| Data | PostgreSQL with TimescaleDB | App state and timestamped food events |
| AI | Google Gemini | Photo fallback, text parsing, recipe suggestions, and shelf-life estimates |
| Vision | Ultralytics YOLO pipeline | Experimental food detection and freshness classification |
| Receipts | GLM-OCR integration and a deterministic parser | Receipt image extraction and line-item parsing |
| Local runtime | Docker Compose | API and database |

## Run locally

### Backend

Install Docker with Compose v2. Clone the repository and create your local configuration:

```bash
git clone https://github.com/Abyss999/CodeRedOrion-CougarAIUncs.git
cd CodeRedOrion-CougarAIUncs
cp .env.example .env
```

Edit `.env`: set the database credentials and a strong `JWT_SECRET`; configure
`GEMINI_API_KEY` and a model available to your account for AI features. Keep database passwords
consistent with the database URLs. Keep real credentials out of commits.

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:5055/health
```

With the default API port, the health response is `{"status":"ok"}`. Database migrations run
automatically when the API container starts. The API binds to `127.0.0.1:5055` and the database
to `127.0.0.1:5433`; a phone needs a separately configured route to the API.

Leave `ML_SERVICE_URL` empty to use Gemini for photos. Receipts require a configured OCR
service. The standalone ML service defaults to fake backends for development; configure real
backends before presenting its output as live recognition. See [ML setup](docs/ML.md).

### iOS

On a Mac with Xcode and XcodeGen:

```bash
cd ios
xcodegen generate
open FoodWasteReducer.xcodeproj
```

The internal project and scheme names are currently `FoodWasteReducer`. Use the documented
Xcode 26 toolchain and a compatible simulator. The phone demo uses a free Personal Team;
device signing and demo tunnel instructions are in the
[setup guide](docs/SETUP.md#4-ios).

### Development and verification

Host-side Python development uses Python 3.12 and the repository `.venv`. Backend tests need
a dedicated `TEST_DATABASE_URL` because they rebuild the test schema. Follow the
[setup guide](docs/SETUP.md) for environment creation and test commands, and the
[QA plan](docs/QA.md) for feature and integration checks.

## Repository guide

| Path | Contents |
|---|---|
| `ios/` | SwiftUI app, XcodeGen project specification, and iOS tests |
| `backend/` | Flask API, migrations, and backend tests |
| `ml/` | Detection training, OCR, inference service, and evaluation |
| `docs/design/` | Screen mockups and the shared design system |
| `docs/` | Product scope, API, schema, architecture, setup, and QA |

For the product plan, read [IDEA.md](docs/IDEA.md). Technical choices are recorded in
[DECISIONS.md](docs/DECISIONS.md), with architecture in [ARCHITECTURE.md](docs/ARCHITECTURE.md).
Contributors and coding agents should start with [CLAUDE.md](CLAUDE.md) and [HANDOFF.md](HANDOFF.md).

## Data attribution

The vision pipeline’s dataset sources include **Fridge objects** (wajeeha workspace, Roboflow),
**Hien_Fridge** (gracelearning, Roboflow), and **VegQual** under CC BY 4.0, plus a CC0 fresh/stale
fruit and vegetable dataset from Kaggle. Authors, source links, preparation changes, and
licensing details are listed in [ML attributions](docs/ML.md#attributions).
