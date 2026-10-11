"""Migration 0008 (share pickup columns + friend_codes): round trip on a populated database."""
from pathlib import Path

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db

MIG = str(Path(__file__).resolve().parents[1] / "migrations")
PREV = "0007_items_nutrition"
REV = "0008_share_pickup"
PCOLS = {"pickup_note", "pickup_lat", "pickup_lng", "pickup_place"}


def _reset():
    db.session.remove()
    db.engine.dispose()


def _q(stmt, **p):
    return db.session.execute(text(stmt), p)


def _cols(table):
    return {r[0] for r in _q("SELECT column_name FROM information_schema.columns WHERE table_name=:t", t=table).all()}


def _tables():
    return {r[0] for r in _q("SELECT tablename FROM pg_tables WHERE schemaname='public'").all()}


@pytest.fixture
def at_head(app):
    yield
    with app.app_context():
        _reset()
        upgrade(directory=MIG)
        _reset()


def test_0008_round_trip_with_data(app, at_head):
    with app.app_context():
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        assert not PCOLS & _cols("share_listings") and "friend_codes" not in _tables()
        u = [_q("INSERT INTO users (email, password_hash, display_name) VALUES (:e,'x$y',:n) RETURNING id",
                e=f"{n}@x.com", n=n).scalar() for n in ("a", "b")]
        item = _q("INSERT INTO items (owner_id, name, category, storage, quantity, unit, source, predicted_expiry, expiry_source) "
                  "VALUES (:o,'Milk','dairy','fridge',1,'l','manual', current_date + 3, 'default') RETURNING id", o=u[0]).scalar()
        lid = _q("INSERT INTO share_listings (item_id, owner_id, status) VALUES (:i,:o,'open') RETURNING id",
                 i=item, o=u[0]).scalar()
        db.session.commit()
        _reset()
        upgrade(directory=MIG)
        _reset()
        assert PCOLS <= _cols("share_listings") and "friend_codes" in _tables()
        row = _q("SELECT pickup_note, pickup_lat, pickup_lng, pickup_place, status FROM share_listings WHERE id=:i", i=lid).one()
        assert tuple(row) == (None, None, None, None, "open")  # old listings: no pickup, otherwise intact
        # constraints hold at the DB level, independent of the app
        for bad in ("pickup_lat=1", "pickup_lat=91, pickup_lng=0", "pickup_lat=0, pickup_lng=181",
                    "pickup_note=repeat('x',121)", "pickup_place=repeat('x',121)"):
            with pytest.raises(IntegrityError):
                _q(f"UPDATE share_listings SET {bad} WHERE id=:i", i=lid)
            db.session.rollback()
        _q("UPDATE share_listings SET pickup_note='ok', pickup_lat=-90, pickup_lng=180 WHERE id=:i", i=lid)
        _q("INSERT INTO friend_codes (code, user_id, expires_at) VALUES ('abc', :u, now())", u=u[0])
        db.session.commit()
        # user delete cascades to its codes
        _q("DELETE FROM friend_codes"); db.session.commit()
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        assert not PCOLS & _cols("share_listings") and "friend_codes" not in _tables()
        assert _q("SELECT count(*) FROM share_listings").scalar() == 1  # listing survives the downgrade
        _reset()
        upgrade(directory=MIG)
        _reset()
        assert PCOLS <= _cols("share_listings")
        # idempotent second round trip
        downgrade(directory=MIG, revision=PREV)
        _reset()
        upgrade(directory=MIG)


def test_friend_codes_cascade_on_user_delete(app, at_head):
    with app.app_context():
        uid = _q("INSERT INTO users (email, password_hash, display_name) VALUES ('c@x.com','x$y','c') RETURNING id").scalar()
        _q("INSERT INTO friend_codes (code, user_id, expires_at) VALUES ('zzz', :u, now() + interval '1 min')", u=uid)
        db.session.commit()
        _q("DELETE FROM users WHERE id=:u", u=uid)
        db.session.commit()
        assert _q("SELECT count(*) FROM friend_codes").scalar() == 0
