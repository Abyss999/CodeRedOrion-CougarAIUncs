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
Migrations (once the backend has them): `cd backend && ../.venv/bin/flask --app wsgi db upgrade`.

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
CI runs the same on every PR touching `ios/` once the workflows are enabled (`ci/README.md`).

### TestFlight
1. Apple Developer account → set the team in `project.yml` (`DEVELOPMENT_TEAM`) and a unique bundle id.
2. Create the app in App Store Connect with that bundle id.
3. Xcode → Product → Archive → Distribute App → App Store Connect → Upload.
4. App Store Connect → TestFlight → add internal testers.
The API must be reachable from the phone for TestFlight builds (see open questions in `HANDOFF.md`).

## 5. ML (off-box)
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
| **Claude Design MCP** | **TBD — confirm the server name and install command** (`claude mcp add …`), then record the exact command here | Screen designs in `docs/design/` |
| web-design-guidelines (end of project only) | `npx skills add vercel-labs/agent-skills --skill web-design-guidelines` | Final UI review |
| Impeccable (end of project only) | per its README | `/impeccable critique`, `/impeccable polish` — **never during generation** |

Check with `claude mcp list`.
