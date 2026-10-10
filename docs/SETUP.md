# Setup

## Prerequisites
- macOS with **Xcode 16+** (iOS), **Homebrew**, `brew install xcodegen`
- **Docker Desktop** (or another Docker engine with Compose v2)
- **Python 3.12**
- Node (for `npx skills`), `gh` CLI logged in
- A **Google Gemini API key**

## 1. Clone and configure secrets
```bash
git clone https://github.com/Abyss999/CodeRedOrion-CougarAIUncs.git
cd CodeRedOrion-CougarAIUncs
cp .env.example .env      # then fill in real values — .env is gitignored, never commit it
```

## 2. Backend venv (always use it — never the global interpreter)
```bash
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/pytest -q          # tests
```
Run the API outside Docker (handy while developing):
```bash
cd backend && ../.venv/bin/flask --app wsgi run --port 5055
```

## 3. Docker stack (API + TimescaleDB)
```bash
docker compose up -d --build
docker compose ps                         # both healthy
curl http://127.0.0.1:5055/health         # {"status":"ok"}
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"   # DB shell
```
Ports bind to `127.0.0.1` only: API `5055`, DB `5433` (5433 avoids clashing with a local Postgres).
Migrations run automatically: the `api` container's entrypoint (`backend/entrypoint.sh`) runs
`flask --app wsgi db upgrade` before starting gunicorn, so no host-side step is needed for the
container. It is idempotent, so restarts are safe. The upgrade creates the `timescaledb` and
`citext` extensions, all tables, and the `food_events` hypertable.
For the host venv (and for tests) run it by hand: `cd backend && ../.venv/bin/flask --app wsgi db upgrade`.

**Backend tests need their own database.** The suite drops and rebuilds its schema by running the
migrations, so it refuses to run unless `TEST_DATABASE_URL` is set and differs from `DATABASE_URL`.
Create the database once:
```bash
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'CREATE DATABASE fwr_test'
cd backend && ../.venv/bin/pytest -q --cov=app      # about 40 s; concurrent runs queue on an advisory lock
```

## 4. iOS
```bash
cd ios
xcodegen generate            # creates FoodWasteReducer.xcodeproj (gitignored — re-run after editing project.yml)
open FoodWasteReducer.xcodeproj
```
Tests from the command line:
```bash
xcodebuild test -project FoodWasteReducer.xcodeproj -scheme FoodWasteReducer \
  -destination 'platform=iOS Simulator,name=iPhone 16'
```
CI (`.github/workflows/ios.yml`) runs the same on every PR touching `ios/`.

### TestFlight
1. Apple Developer account → set the team in `project.yml` (`DEVELOPMENT_TEAM`) and a unique bundle id.
2. Create the app in App Store Connect with that bundle id.
3. Xcode → Product → Archive → Distribute App → App Store Connect → Upload.
4. App Store Connect → TestFlight → add internal testers.
The API must be reachable from the phone for TestFlight builds (see open questions in `HANDOFF.md`).

## 5. ML (off-box)
Light, CPU-only tests (no torch) run anywhere:
```bash
python3.12 -m venv .venv-ml && .venv-ml/bin/pip install pytest flask pillow numpy
(cd ml && for d in serve ocr yolo; do ../.venv-ml/bin/python -m pytest $d/tests -q; done)
.venv-ml/bin/python -m pytest ml/eval/tests -q        # QA harness + receipt-parser gates
```

Data pipeline (dataset ingestion, receipt inbox, lighting augmentation), CPU-only, from the root `.venv`:
```bash
.venv/bin/pip install -r pipeline/requirements.txt
.venv/bin/python -m pytest pipeline/tests -q
.venv/bin/python -m pipeline --help                    # commands: docs/PIPELINE.md
```

Training and heavy inference run on a GPU (Colab or a teammate's machine), **not** on a shared
server. See `ml/README.md` and `docs/ML.md` (created by the ML builder). Point the backend at the
inference service with `ML_SERVICE_URL`; leave it empty to use the Gemini-vision fallback.

## 6. Claude Code: plugins, skills, MCP servers
Install these **before** starting the matching work, then **restart Claude Code** — new MCP
servers and skills are not picked up mid-session.

| What | Install | Used for |
|---|---|---|
| GitHub | `gh auth login` (the `gh` CLI is what agents use for PRs) | PRs into `main` |
| **Ponytail** (plugin) | In Claude Code: `/plugin marketplace add DietrichGebert/ponytail` then `/plugin install ponytail@ponytail` | Keeps agent code minimal |
| **taste-skill** | `npx skills add https://github.com/Leonxlnx/taste-skill` | UI generation (anti-generic design) |
| **SQL MCP (Postgres)** | Recommended: Postgres MCP Pro in restricted (read-only) mode — `claude mcp add postgres -- uvx postgres-mcp --access-mode=restricted` with `DATABASE_URI=postgresql://fwr:<pw>@127.0.0.1:5433/fwr` in its env. **Confirm the current command against the project's README before installing.** | QA / debugging queries |
| **Claude Design** | No install needed. The screens were made on a Claude Design canvas from claude.ai, https://claude.ai/artifact/ALmB8FYKGrayhDQXqvoncx, and are mirrored in `docs/design/screens/`. If you also want a design MCP server, record its exact `claude mcp add` command here | Screen designs in `docs/design/` |
| web-design-guidelines (end of project only) | `npx skills add vercel-labs/agent-skills --skill web-design-guidelines` | Final UI review |
| Impeccable (end of project only) | per its README | `/impeccable critique`, `/impeccable polish` — **never during generation** |

Check with `claude mcp list`.
