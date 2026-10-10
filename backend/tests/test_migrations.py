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


def test_step_0002_round_trip(app):
    """Head -> 0001 -> head: the social migration must be reversible and leave 0001's data model intact."""
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory(MIG).get_heads()
    assert len(heads) == 1, "multiple alembic heads"
    with app.app_context():
        db.session.remove(); db.engine.dispose()
        if heads[0] == "0001":  # pragma: no cover - social migration not landed yet
            return
        before = _tables()
        downgrade(directory=MIG, revision="0001")
        after_down = _tables()
        assert {"users", "items", "food_events", "share_listings"} <= after_down
        assert after_down < before, "downgrade to 0001 removed no tables"
        db.session.remove(); db.engine.dispose()
        upgrade(directory=MIG)
        assert _tables() == before
        assert db.session.execute(text("SELECT version_num FROM alembic_version")).scalar() == heads[0]
        db.session.remove(); db.engine.dispose()
