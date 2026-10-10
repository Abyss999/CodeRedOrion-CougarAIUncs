Alembic migrations (Flask-Migrate). Created by the backend builder in Wave 1 with
`flask --app wsgi db init` / `db migrate` / `db upgrade`, run from the project `.venv`.
The `food_events` hypertable is created in a migration with `SELECT create_hypertable(...)` —
see `docs/SCHEMA.md`.
