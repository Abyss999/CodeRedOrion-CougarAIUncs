import pytest
from sqlalchemy.exc import IntegrityError, DBAPIError


def test_food_events_is_hypertable(sql):
    r = sql("SELECT hypertable_name FROM timescaledb_information.hypertables WHERE hypertable_name='food_events'")
    assert len(r) == 1


def test_timescale_and_citext_extensions(sql):
    names = {r["extname"] for r in sql("SELECT extname FROM pg_extension")}
    assert {"timescaledb", "citext"} <= names


def _insert_item(sql, owner, outcome, reason, removed="now()"):
    return sql(f"""INSERT INTO items (id, owner_id, name, category, storage, quantity, unit, source, added_at,
                   predicted_expiry, expiry_source, removed_at, outcome, waste_reason)
                   VALUES (gen_random_uuid(), :o, 'x', 'dairy', 'fridge', 1, 'l', 'manual', now(), current_date,
                   'default', {removed}, :out, :r) RETURNING id""", o=owner, out=outcome, r=reason)


@pytest.mark.parametrize("removed,outcome,reason", [
    ("now()", "thrown_out", None),      # reason required
    ("now()", "used", "forgot"),        # reason forbidden
    ("now()", "donated", "expired"),
    ("NULL", "used", None),             # removed_at null but outcome set
    ("now()", None, None),              # removed_at set, outcome null
])
def test_items_check_constraints(sql, user, removed, outcome, reason):
    with pytest.raises((IntegrityError, DBAPIError)):
        _insert_item(sql, user["user"]["id"], outcome, reason, removed)


def test_items_valid_rows_accepted(sql, user):
    _insert_item(sql, user["user"]["id"], "thrown_out", "forgot")
    _insert_item(sql, user["user"]["id"], "used", None)


def test_food_events_check_rejects_mismatch(sql, user):
    uid = user["user"]["id"]
    base = "INSERT INTO food_events (user_id, item_id, event_type, category, outcome, waste_reason) VALUES (:u, gen_random_uuid(), 'remove', 'dairy', :o, :r)"
    for o, r in [("thrown_out", None), ("used", "forgot"), ("donated", "other")]:
        with pytest.raises((IntegrityError, DBAPIError)):
            sql(base, u=uid, o=o, r=r)
    sql(base, u=uid, o="thrown_out", r="forgot")
    sql(base, u=uid, o="used", r=None)
