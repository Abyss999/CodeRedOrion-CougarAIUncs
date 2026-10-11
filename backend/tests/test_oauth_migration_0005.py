"""Migration 0005: user_identities + nullable users.password_hash. Round-trips 0004 <-> head."""
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from app.extensions import db

MIG = str(Path(__file__).resolve().parents[1] / "migrations")
PREV = "0004_items_wave2"
REV = "0005_user_identities"


def _reset():
    db.session.remove()
    db.engine.dispose()


def _q(stmt, **p):
    return db.session.execute(text(stmt), p)


def _tables():
    return {r[0] for r in _q("SELECT tablename FROM pg_tables WHERE schemaname='public'").all()}


def _pw_nullable():
    return _q("SELECT is_nullable FROM information_schema.columns WHERE table_name='users' "
              "AND column_name='password_hash'").scalar()


@pytest.fixture
def at_head(app):
    yield
    with app.app_context():
        _reset()
        upgrade(directory=MIG)
        _reset()


def test_0005_is_single_head_after_0004(app):
    sd = ScriptDirectory(MIG)
    assert sd.get_heads() == [REV] or (len(sd.get_heads()) == 1 and sd.get_revision(REV).down_revision == PREV)
    assert sd.get_revision(REV).down_revision == PREV


def test_schema_at_head(app):
    with app.app_context():
        assert "user_identities" in _tables()
        assert _pw_nullable() == "YES"
        cols = {r[0]: (r[1], r[2]) for r in _q(
            "SELECT column_name, is_nullable, udt_name FROM information_schema.columns "
            "WHERE table_name='user_identities'").all()}
        assert set(cols) == {"id", "provider", "subject", "user_id", "email", "created_at"}
        assert cols["email"][1] == "citext" and cols["email"][0] == "YES"
        for c in ("provider", "subject", "user_id", "created_at"):
            assert cols[c][0] == "NO", c
        uniq = _q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='user_identities'::regclass "
                  "AND contype='u'").scalars().all()
        assert any("(provider, subject)" in u for u in uniq), uniq
        fk = _q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='user_identities'::regclass "
                "AND contype='f'").scalars().all()
        assert len(fk) == 1 and "REFERENCES users(id)" in fk[0] and "ON DELETE CASCADE" in fk[0]
        idx = _q("SELECT indexdef FROM pg_indexes WHERE tablename='user_identities'").scalars().all()
        assert any("(user_id)" in i for i in idx), idx


def test_downgrade_to_0004_and_back_with_data(app, at_head):
    with app.app_context():
        _reset()
        pw = _q("INSERT INTO users (email, password_hash, display_name) VALUES ('pw@x.com','pbkdf2:sha256:1$a$b','P') "
                "RETURNING id").scalar()
        oauth = _q("INSERT INTO users (email, password_hash, display_name) VALUES ('g@gmail.com', NULL, 'G') "
                   "RETURNING id").scalar()
        _q("INSERT INTO user_identities (provider, subject, user_id, email) VALUES ('google','s1',:u,'g@gmail.com')",
           u=oauth)
        db.session.commit()
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        assert "user_identities" not in _tables()
        assert _pw_nullable() == "NO"
        rows = {r[0]: r[1] for r in _q("SELECT email::text, password_hash FROM users").all()}
        assert rows["pw@x.com"] == "pbkdf2:sha256:1$a$b"  # untouched
        assert rows["g@gmail.com"] == "!"  # unusable, but the user (and their data) survives
        assert check_password_hash("!", "anything") is False
        assert _q("SELECT version_num FROM alembic_version").scalar() == PREV
        _reset()
        upgrade(directory=MIG)
        _reset()
        assert "user_identities" in _tables() and _pw_nullable() == "YES"
        assert _q("SELECT count(*) FROM users").scalar() == 2
        assert _q("SELECT count(*) FROM user_identities").scalar() == 0
        assert _q("SELECT version_num FROM alembic_version").scalar() == ScriptDirectory(MIG).get_heads()[0]
        del pw


def test_round_trip_twice_is_clean(app, at_head):
    with app.app_context():
        for _ in range(2):
            _reset()
            downgrade(directory=MIG, revision=PREV)
            _reset()
            upgrade(directory=MIG)
        _reset()
        assert "user_identities" in _tables()


def test_unique_provider_subject_and_cascade(app):
    with app.app_context():
        u = _q("INSERT INTO users (email, password_hash, display_name) VALUES ('c@gmail.com', NULL, 'C') "
               "RETURNING id").scalar()
        _q("INSERT INTO user_identities (provider, subject, user_id) VALUES ('google','s',:u)", u=u)
        db.session.commit()
        with pytest.raises(IntegrityError):
            _q("INSERT INTO user_identities (provider, subject, user_id) VALUES ('google','s',:u)", u=u)
            db.session.commit()
        db.session.rollback()
        with pytest.raises(IntegrityError):
            _q("INSERT INTO user_identities (provider, subject, user_id) VALUES ('google','x', gen_random_uuid())")
            db.session.commit()
        db.session.rollback()
        _q("DELETE FROM users WHERE id=:u", u=u)
        db.session.commit()
        assert _q("SELECT count(*) FROM user_identities").scalar() == 0
