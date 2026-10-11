"""Migration 0004: items.freshness / freshness_checked_at / confidence (and food_events anonymisation)."""
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db

MIG = str(Path(__file__).resolve().parents[1] / "migrations")
PREV = "0003_food_group"


def _rev_0004():
    sd = ScriptDirectory(MIG)
    revs = [r for r in sd.walk_revisions() if r.down_revision == PREV]
    return revs[0].revision if revs else None


def _cols(table="items"):
    return {r[0]: r for r in db.session.execute(text(
        "SELECT column_name, is_nullable, data_type FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t"), {"t": table}).all()}


def _reset():
    db.session.remove()
    db.engine.dispose()


@pytest.fixture
def at_head(app):
    yield
    with app.app_context():
        _reset()
        upgrade(directory=MIG)
        _reset()


def _insert_user_item(name="Old milk"):
    uid = db.session.execute(text(
        "INSERT INTO users (email, password_hash, display_name) VALUES ('m@example.com','x','M') RETURNING id")).scalar()
    iid = db.session.execute(text(
        "INSERT INTO items (owner_id, name, category, storage, quantity, unit, source, predicted_expiry,"
        " expiry_source) VALUES (:u, :n, 'dairy', 'fridge', 1, 'l', 'manual', current_date + 3, 'default')"
        " RETURNING id"), {"u": uid, "n": name}).scalar()
    db.session.commit()
    return uid, iid


def test_single_head_and_0004_exists(app):
    heads = ScriptDirectory(MIG).get_heads()
    assert len(heads) == 1, "multiple alembic heads"
    assert _rev_0004() is not None, "no migration with down_revision 0003_food_group"


def test_upgrade_from_0003_keeps_rows_with_null_freshness(app, at_head):
    rev = _rev_0004()
    assert rev
    with app.app_context():
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        c = _cols()
        assert "freshness" not in c and "freshness_checked_at" not in c and "confidence" not in c
        uid, iid = _insert_user_item()
        _reset()
        upgrade(directory=MIG)
        _reset()
        c = _cols()
        for col in ("freshness", "freshness_checked_at", "confidence"):
            assert col in c, col
            assert c[col][1] == "YES", f"{col} must be nullable"
        row = db.session.execute(text(
            "SELECT name, freshness, freshness_checked_at, confidence FROM items WHERE id=:i"), {"i": iid}).one()
        assert row.name == "Old milk"
        assert row.freshness is None and row.freshness_checked_at is None and row.confidence is None
        assert db.session.execute(text("SELECT version_num FROM alembic_version")).scalar() == \
            ScriptDirectory(MIG).get_heads()[0]


def test_downgrade_to_0003_and_back(app, at_head):
    with app.app_context():
        _reset()
        _insert_user_item()
        db.session.execute(text("UPDATE items SET freshness='spoiled', freshness_checked_at=now(), confidence=0.5"))
        db.session.commit()
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        c = _cols()
        assert not ({"freshness", "freshness_checked_at", "confidence"} & set(c))
        # 0003 data survives the downgrade
        assert db.session.execute(text("SELECT count(*) FROM items")).scalar() == 1
        assert "food_group" in c
        _reset()
        upgrade(directory=MIG)
        _reset()
        assert "freshness" in _cols()


@pytest.mark.parametrize("val", ["fresh", "semi_fresh", "spoiled", None])
def test_check_accepts_valid_values(app, val):
    with app.app_context():
        _, iid = _insert_user_item()
        db.session.execute(text("UPDATE items SET freshness=:v, freshness_checked_at=CASE WHEN CAST(:v AS text) IS NULL"
                                " THEN NULL ELSE now() END WHERE id=:i"), {"v": val, "i": iid})
        db.session.commit()
        assert db.session.execute(text("SELECT freshness FROM items WHERE id=:i"), {"i": iid}).scalar() == val


@pytest.mark.parametrize("bad", ["rotten", "Fresh", "semi-fresh", "", "unknown"])
def test_check_rejects_bad_values(app, bad):
    with app.app_context():
        _, iid = _insert_user_item()
        with pytest.raises(IntegrityError):
            db.session.execute(text("UPDATE items SET freshness=:v, freshness_checked_at=now() WHERE id=:i"),
                               {"v": bad, "i": iid})
            db.session.commit()
        db.session.rollback()


def test_check_rejects_bad_value_on_insert(app):
    with app.app_context():
        uid, _ = _insert_user_item()
        with pytest.raises(IntegrityError):
            db.session.execute(text(
                "INSERT INTO items (owner_id, name, category, storage, source, predicted_expiry, freshness,"
                " freshness_checked_at) VALUES (:u,'x','dairy','fridge','manual', current_date, 'mouldy', now())"), {"u": uid})
            db.session.commit()
        db.session.rollback()


def test_check_freshness_and_stamp_travel_together(app):
    with app.app_context():
        _, iid = _insert_user_item()
        for stmt in ("UPDATE items SET freshness='fresh' WHERE id=:i",
                     "UPDATE items SET freshness_checked_at=now() WHERE id=:i"):
            with pytest.raises(IntegrityError):
                db.session.execute(text(stmt), {"i": iid})
                db.session.commit()
            db.session.rollback()


@pytest.mark.parametrize("bad", [-0.001, 1.001, 5])
def test_check_confidence_range(app, bad):
    with app.app_context():
        _, iid = _insert_user_item()
        with pytest.raises(IntegrityError):
            db.session.execute(text("UPDATE items SET confidence=:c WHERE id=:i"), {"c": bad, "i": iid})
            db.session.commit()
        db.session.rollback()
        for ok in (0, 1, 0.5):
            db.session.execute(text("UPDATE items SET confidence=:c WHERE id=:i"), {"c": ok, "i": iid})
        db.session.commit()


def test_groups_created_by_nullable_and_downgrade_repairs_orphans(app, at_head):
    with app.app_context():
        c = db.session.execute(text("SELECT is_nullable FROM information_schema.columns WHERE "
                                    "table_name='groups' AND column_name='created_by'")).scalar()
        assert c == "YES"
        uid, _ = _insert_user_item()
        gid = db.session.execute(text("INSERT INTO groups (name, created_by, invite_code) VALUES "
                                      "('G', NULL, 'ABCDEFGH') RETURNING id")).scalar()
        db.session.execute(text("INSERT INTO group_members (group_id, user_id, role) VALUES (:g,:u,'member')"),
                           {"g": gid, "u": uid})
        orphan = db.session.execute(text("INSERT INTO groups (name, created_by, invite_code) VALUES "
                                         "('Empty', NULL, 'ZZZZZZZZ') RETURNING id")).scalar()
        db.session.commit()
        _reset()
        downgrade(directory=MIG, revision=PREV)  # must not fail on NULL created_by
        _reset()
        rows = {str(r[0]): r[1] for r in db.session.execute(text("SELECT id, created_by FROM groups")).all()}
        assert rows[str(gid)] == uid
        assert str(orphan) not in rows
