"""Migration 0007: items.nutrition (JSONB, nullable). Round-trips 0006 <-> head."""
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db

MIG = str(Path(__file__).resolve().parents[1] / "migrations")
PREV = "0006_request_audiences"
REV = "0007_items_nutrition"
NUT = '{"basis": "per_100g", "kcal": 52, "protein_g": 0.3, "carbs_g": 13.8, "fat_g": 0.2, "estimated": true}'


def _reset():
    db.session.remove()
    db.engine.dispose()


def _q(stmt, **p):
    return db.session.execute(text(stmt), p)


def _column():
    return _q("SELECT is_nullable, data_type FROM information_schema.columns "
              "WHERE table_schema='public' AND table_name='items' AND column_name='nutrition'").first()


def _constraint():
    return _q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='ck_items_nutrition_object'").scalar()


def _insert_item(name="Apple", nutrition=None):
    uid = _q("INSERT INTO users (email, password_hash, display_name) VALUES ('n@example.com','x','N') "
             "RETURNING id").scalar()
    cols = "owner_id, name, category, storage, quantity, unit, source, predicted_expiry, expiry_source"
    vals = ":u, :n, 'produce_hardy', 'fridge', 1, 'piece', 'manual', current_date + 5, 'default'"
    params = {"u": uid, "n": name}
    if nutrition is not None:  # the column does not exist while the schema is at 0006
        cols += ", nutrition"
        vals += ", CAST(:nut AS jsonb)"
        params["nut"] = nutrition
    iid = _q(f"INSERT INTO items ({cols}) VALUES ({vals}) RETURNING id", **params).scalar()
    db.session.commit()
    return iid


@pytest.fixture
def at_head(app):
    yield
    with app.app_context():
        _reset()
        upgrade(directory=MIG)
        _reset()


def test_0007_follows_0006_and_there_is_one_head(app):
    sd = ScriptDirectory(MIG)
    assert len(sd.get_heads()) == 1, "multiple alembic heads"
    assert sd.get_revision(REV).down_revision == PREV


def test_schema_at_head(app):
    with app.app_context():
        col = _column()
        assert col is not None and tuple(col) == ("YES", "jsonb")
        assert "jsonb_typeof(nutrition) = 'object'" in _constraint()


def test_downgrade_to_0006_and_back_keeps_items_and_drops_only_nutrition(app, at_head):
    with app.app_context():
        _reset()
        iid = _insert_item("Apple", NUT)
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        assert _column() is None and _constraint() is None
        assert _q("SELECT name FROM items WHERE id=:i", i=iid).scalar() == "Apple", "the item survives"
        assert _q("SELECT version_num FROM alembic_version").scalar() == PREV
        _reset()
        upgrade(directory=MIG)
        _reset()
        assert tuple(_column()) == ("YES", "jsonb")
        assert _q("SELECT nutrition IS NULL FROM items WHERE id=:i", i=iid).scalar() is True, "data is not restored"
        assert _q("SELECT version_num FROM alembic_version").scalar() == ScriptDirectory(MIG).get_heads()[0]


def test_round_trip_twice_is_clean(app, at_head):
    with app.app_context():
        for _ in range(2):
            _reset()
            downgrade(directory=MIG, revision=PREV)
            _reset()
            upgrade(directory=MIG)
        _reset()
        assert tuple(_column()) == ("YES", "jsonb") and _constraint()


def test_existing_rows_get_null_when_upgrading_from_0006(app, at_head):
    with app.app_context():
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        iid = _insert_item("Old milk")
        _reset()
        upgrade(directory=MIG)
        _reset()
        assert _q("SELECT nutrition IS NULL FROM items WHERE id=:i", i=iid).scalar() is True


@pytest.mark.parametrize("bad", ["[1]", '"x"', "5", "true", "null"])
def test_check_rejects_non_objects(app, bad):
    with app.app_context():
        iid = _insert_item()
        with pytest.raises(IntegrityError):
            _q("UPDATE items SET nutrition = CAST(:v AS jsonb) WHERE id=:i", v=bad, i=iid)
            db.session.commit()
        db.session.rollback()


@pytest.mark.parametrize("ok", ["{}", NUT])
def test_check_accepts_objects_and_null(app, ok):
    with app.app_context():
        iid = _insert_item()
        _q("UPDATE items SET nutrition = CAST(:v AS jsonb) WHERE id=:i", v=ok, i=iid)
        _q("UPDATE items SET nutrition = NULL WHERE id=:i", i=iid)
        db.session.commit()
