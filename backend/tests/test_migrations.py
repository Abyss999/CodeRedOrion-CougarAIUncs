"""Round-trip the migrations inside fwr_test: base -> head -> base -> head."""
from pathlib import Path

from flask_migrate import downgrade, upgrade
from sqlalchemy import text

from app.extensions import db

MIG = str(Path(__file__).resolve().parents[1] / "migrations")


def _tables():
    return {r[0] for r in db.session.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'")).all()}


def test_upgrade_downgrade_upgrade(app):
    with app.app_context():
        db.session.remove(); db.engine.dispose()
        downgrade(directory=MIG, revision="base")
        assert _tables() <= {"alembic_version"}
        db.session.remove(); db.engine.dispose()
        upgrade(directory=MIG)
        assert {"users", "items", "food_events", "share_listings"} <= _tables()
        hyp = db.session.execute(text("SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name='food_events'")).scalar()
        assert hyp == 1
        db.session.remove(); db.engine.dispose()
