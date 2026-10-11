"""Migration 0006: request_audiences join table, backfill from requests.group_id, column dropped.
Round-trips 0005 <-> head with data."""
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db

MIG = str(Path(__file__).resolve().parents[1] / "migrations")
PREV = "0005_user_identities"
REV = "0006_request_audiences"


def _reset():
    db.session.remove()
    db.engine.dispose()


def _q(stmt, **p):
    return db.session.execute(text(stmt), p)


def _tables():
    return {r[0] for r in _q("SELECT tablename FROM pg_tables WHERE schemaname='public'").all()}


def _has_group_id():
    return _q("SELECT count(*) FROM information_schema.columns WHERE table_name='requests' "
              "AND column_name='group_id'").scalar() == 1


@pytest.fixture
def at_head(app):
    yield
    with app.app_context():
        _reset()
        upgrade(directory=MIG)
        _reset()


def _seed_at_0005():
    """At 0005: users a, b; groups g1 (a), g2 (a); requests: friends-only, g1, g2, a cancelled one, a fulfilled one."""
    u = {}
    for n in ("a", "b"):
        u[n] = _q("INSERT INTO users (email, password_hash, display_name) VALUES (:e, 'x$y', :n) RETURNING id",
                  e=f"{n}@x.com", n=n).scalar()
    g = {}
    for n in ("g1", "g2"):
        g[n] = _q("INSERT INTO groups (name, invite_code, created_by) VALUES (:n, :c, :u) RETURNING id",
                  n=n, c=("ABCDEFG" + n[-1]).replace("1", "H").replace("2", "J"), u=u["a"]).scalar()
        _q("INSERT INTO group_members (group_id, user_id, role) VALUES (:g, :u, 'owner')", g=g[n], u=u["a"])
    r = {}
    rows = [("friends", None, "open", None), ("g1", g["g1"], "open", None), ("g2", g["g2"], "open", None),
            ("cancelled", None, "cancelled", None), ("done", g["g1"], "fulfilled", u["b"])]
    for i, (t, gid, st, fb) in enumerate(rows):
        r[t] = _q("INSERT INTO requests (author_id, group_id, text, status, fulfilled_by, created_at) "
                  "VALUES (:a, :g, :t, :s, :f, now() - make_interval(mins => :m)) RETURNING id",
                  a=u["a"], g=gid, t=t, s=st, f=fb, m=10 - i).scalar()
    db.session.commit()
    return u, g, r


def _audiences():
    return sorted((str(x[0]), x[1], str(x[2]) if x[2] else None) for x in
                  _q("SELECT ra.request_id, ra.kind, ra.group_id FROM request_audiences ra").all())


def test_single_head_and_parent(app):
    sd = ScriptDirectory(MIG)
    assert len(sd.get_heads()) == 1
    assert sd.get_revision(REV).down_revision == PREV
    assert sd.get_heads() == [REV] or sd.get_revision(sd.get_heads()[0]) is not None


def test_schema_at_head(app):
    with app.app_context():
        assert "request_audiences" in _tables()
        assert not _has_group_id()
        fks = _q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='request_audiences'::regclass "
                 "AND contype='f'").scalars().all()
        assert any("REFERENCES requests(id) ON DELETE CASCADE" in f for f in fks), fks
        assert any("REFERENCES groups(id)" in f for f in fks), fks


def test_backfill_from_0005_data(app, at_head):
    with app.app_context():
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        assert _has_group_id() and "request_audiences" not in _tables()
        u, g, r = _seed_at_0005()
        _reset()
        upgrade(directory=MIG, revision=REV)
        _reset()
        assert not _has_group_id()
        assert _audiences() == sorted([
            (str(r["friends"]), "friends", None),
            (str(r["g1"]), "group", str(g["g1"])),
            (str(r["g2"]), "group", str(g["g2"])),
            (str(r["cancelled"]), "friends", None),
            (str(r["done"]), "group", str(g["g1"])),
        ])
        # statuses / fulfilment untouched
        st = {x[0]: (x[1], x[2]) for x in _q("SELECT text, status, fulfilled_by FROM requests").all()}
        assert st["done"] == ("fulfilled", u["b"]) and st["cancelled"] == ("cancelled", None)
        assert st["friends"][0] == st["g1"][0] == "open"


def test_downgrade_restores_group_id_and_upgrade_again(app, at_head):
    with app.app_context():
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        u, g, r = _seed_at_0005()
        before = {x[0]: x[1] for x in _q("SELECT id, group_id FROM requests").all()}
        _reset()
        upgrade(directory=MIG, revision=REV)
        _reset()
        # a multi-audience request created at head: friends + g1 -> downgrades to friends (null);
        # g2 + g1 (no friends) -> downgrades to its oldest group audience
        multi_f = _q("INSERT INTO requests (author_id, text, status) VALUES (:a, 'mf', 'open') RETURNING id",
                     a=u["a"]).scalar()
        _q("INSERT INTO request_audiences (request_id, kind) VALUES (:r, 'friends')", r=multi_f)
        _q("INSERT INTO request_audiences (request_id, kind, group_id) VALUES (:r, 'group', :g)", r=multi_f,
           g=g["g1"])
        multi_g = _q("INSERT INTO requests (author_id, text, status) VALUES (:a, 'mg', 'open') RETURNING id",
                     a=u["a"]).scalar()
        _q("INSERT INTO request_audiences (request_id, kind, group_id, created_at) "
           "VALUES (:r, 'group', :g, now() - interval '1 minute')", r=multi_g, g=g["g2"])
        _q("INSERT INTO request_audiences (request_id, kind, group_id) VALUES (:r, 'group', :g)", r=multi_g,
           g=g["g1"])
        db.session.commit()
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        assert "request_audiences" not in _tables() and _has_group_id()
        after = {x[0]: x[1] for x in _q("SELECT id, group_id FROM requests").all()}
        for rid, gid in before.items():  # single-audience requests round-trip exactly
            assert after[rid] == gid, rid
        assert after[multi_f] is None and after[multi_g] == g["g2"]
        assert _q("SELECT version_num FROM alembic_version").scalar() == PREV
        _reset()
        upgrade(directory=MIG)
        _reset()
        assert _q("SELECT count(*) FROM requests").scalar() == 7
        assert _q("SELECT count(*) FROM request_audiences").scalar() == 7  # one per request after the lossy trip
        assert _q("SELECT version_num FROM alembic_version").scalar() == ScriptDirectory(MIG).get_heads()[0]


def test_round_trip_twice_is_clean(app, at_head):
    with app.app_context():
        for _ in range(2):
            _reset()
            downgrade(directory=MIG, revision=PREV)
            _reset()
            upgrade(directory=MIG)
        _reset()
        assert "request_audiences" in _tables() and not _has_group_id()


def test_constraints(app):
    with app.app_context():
        a = _q("INSERT INTO users (email, password_hash, display_name) VALUES ('c@x.com','x$y','C') "
               "RETURNING id").scalar()
        g = _q("INSERT INTO groups (name, invite_code, created_by) VALUES ('g','KKKKKKKK',:u) RETURNING id",
               u=a).scalar()
        r = _q("INSERT INTO requests (author_id, text, status) VALUES (:a,'t','open') RETURNING id", a=a).scalar()
        _q("INSERT INTO request_audiences (request_id, kind) VALUES (:r, 'friends')", r=r)
        _q("INSERT INTO request_audiences (request_id, kind, group_id) VALUES (:r, 'group', :g)", r=r, g=g)
        db.session.commit()
        bad = [
            ("INSERT INTO request_audiences (request_id, kind) VALUES (:r, 'friends')", {}),          # 2nd friends
            ("INSERT INTO request_audiences (request_id, kind, group_id) VALUES (:r, 'group', :g)", {"g": g}),
            ("INSERT INTO request_audiences (request_id, kind) VALUES (:r, 'group')", {}),            # group w/o id
            ("INSERT INTO request_audiences (request_id, kind, group_id) VALUES (:r, 'friends', :g)", {"g": g}),
            ("INSERT INTO request_audiences (request_id, kind) VALUES (:r, 'public')", {}),
            ("INSERT INTO request_audiences (request_id, kind) VALUES (gen_random_uuid(), 'friends')", {}),
        ]
        for stmt, extra in bad:
            with pytest.raises(IntegrityError):
                _q(stmt, r=r, **extra)
                db.session.commit()
            db.session.rollback()
        _q("DELETE FROM requests WHERE id=:r", r=r)
        db.session.commit()
        assert _q("SELECT count(*) FROM request_audiences").scalar() == 0


def test_downgrade_round_trips_exactly_on_single_audience_data(app, at_head):
    """Orchestrator ask: friends-only and single-group requests survive 0006 -> 0005 -> 0006 exactly."""
    with app.app_context():
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        u, g, r = _seed_at_0005()
        original = {x[0]: x[1] for x in _q("SELECT id, group_id FROM requests").all()}
        _reset()
        upgrade(directory=MIG, revision=REV)
        _reset()
        aud_before = _audiences()
        assert len(aud_before) == len(original)            # one row each
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        assert {x[0]: x[1] for x in _q("SELECT id, group_id FROM requests").all()} == original
        _reset()
        upgrade(directory=MIG, revision=REV)
        _reset()
        assert _audiences() == aud_before                  # kind, group_id, one row per request


def test_downgrade_is_lossy_for_multi_audience_by_design(app, at_head):
    """Documented loss (API.md / SCHEMA.md): friends+group -> friends (null); group+group -> oldest group.
    Covered in detail by test_downgrade_restores_group_id_and_upgrade_again; this pins the rule alone."""
    with app.app_context():
        a = _q("INSERT INTO users (email, password_hash, display_name) VALUES ('m@x.com','x$y','M') "
               "RETURNING id").scalar()
        g1 = _q("INSERT INTO groups (name, invite_code, created_by) VALUES ('g1','MMMMMMM2',:u) RETURNING id",
                u=a).scalar()
        g2 = _q("INSERT INTO groups (name, invite_code, created_by) VALUES ('g2','MMMMMMM3',:u) RETURNING id",
                u=a).scalar()
        rf = _q("INSERT INTO requests (author_id, text, status) VALUES (:a,'f','open') RETURNING id", a=a).scalar()
        _q("INSERT INTO request_audiences (request_id, kind, group_id) VALUES (:r,'group',:g)", r=rf, g=g1)
        _q("INSERT INTO request_audiences (request_id, kind) VALUES (:r,'friends')", r=rf)
        rg = _q("INSERT INTO requests (author_id, text, status) VALUES (:a,'g','open') RETURNING id", a=a).scalar()
        _q("INSERT INTO request_audiences (request_id, kind, group_id, created_at) "
           "VALUES (:r,'group',:g, now())", r=rg, g=g1)
        _q("INSERT INTO request_audiences (request_id, kind, group_id, created_at) "
           "VALUES (:r,'group',:g, now() - interval '1 hour')", r=rg, g=g2)
        db.session.commit()
        _reset()
        downgrade(directory=MIG, revision=PREV)
        _reset()
        got = {x[0]: x[1] for x in _q("SELECT id, group_id FROM requests").all()}
        assert got == {rf: None, rg: g2}
