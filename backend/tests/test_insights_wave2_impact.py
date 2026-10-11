"""GET /impact wave 2: used/donated split, waste-reason breakdown, previous period, zero-filled
last-6-weeks series (Monday 00:00 UTC buckets), user isolation and a fixed query count."""
from datetime import date, timedelta

import pytest
from sqlalchemy import event as sa_event

REASONS = ("expired", "didnt_like", "forgot", "other")
KINDS = ("saved", "wasted", "used", "donated")

_INS = ("INSERT INTO food_events (time, user_id, item_id, event_type, category, quantity, est_weight_kg,"
        " est_price, outcome, waste_reason, co2e_kg) VALUES ({t}, :u, gen_random_uuid(), 'remove', 'dairy',"
        " 1, :kg, :p, :o, :r, :c)")


def ev(sql, uid, o, r=None, *, days=0, t=None, kg=1.0, p=1.0, c=1.0):
    """Insert one remove event `days` ago, or at the SQL time expression `t`."""
    sql(_INS.format(t=t or "now() - make_interval(secs => :d * 86400.0)"), u=uid, o=o, r=r, kg=kg, p=p, c=c,
        **({} if t else {"d": days}))


def impact(client, u, rng="all"):
    r = client.get(f"/impact?range={rng}", headers=u["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def approx(a, b):
    return a == pytest.approx(b, abs=1e-6)


# ---- shape -----------------------------------------------------------------------------------
@pytest.mark.parametrize("rng", ["week", "month", "all"])
def test_zero_data_shape(client, user, rng):
    b = impact(client, user, rng)
    for k in KINDS:
        assert b[k] == {"count": 0, "kg": 0, "money": 0, "co2e_kg": 0}
    assert b["waste_rate"] == 0
    assert sorted(x["reason"] for x in b["waste_reasons"]) == sorted(REASONS)
    for x in b["waste_reasons"]:
        assert x["count"] == 0 and x["share"] == 0
    assert len(b["last_6_weeks"]) == 6
    for w in b["last_6_weeks"]:
        assert (w["used"], w["donated"], w["saved"], w["wasted"]) == (0, 0, 0, 0)
    if rng == "all":
        assert b["previous"] is None
    else:
        p = b["previous"]
        for k in KINDS:
            assert p[k]["count"] == 0
        assert p["waste_rate"] == 0


# ---- used / donated split ---------------------------------------------------------------------
def test_used_donated_split_sums_to_saved(client, user, sql):
    uid = user["user"]["id"]
    ev(sql, uid, "used", kg=1.25, p=4.0, c=2.5)
    ev(sql, uid, "used", kg=0.333, p=1.11, c=0.777)
    ev(sql, uid, "donated", kg=0.5, p=6.0, c=1.5)
    ev(sql, uid, "thrown_out", "forgot", kg=0.8, p=5.0, c=3.0)
    for rng in ("week", "month", "all"):
        b = impact(client, user, rng)
        assert b["used"]["count"] == 2 and b["donated"]["count"] == 1 and b["saved"]["count"] == 3
        assert approx(b["used"]["money"], 5.11) and approx(b["donated"]["money"], 6.0)
        assert approx(b["used"]["kg"], 1.58) and approx(b["used"]["co2e_kg"], 3.28)
        for m in ("count", "money"):
            assert approx(b["used"][m] + b["donated"][m], b["saved"][m])
        for m in ("kg", "co2e_kg"):  # independently rounded to 2 dp
            assert abs(b["used"][m] + b["donated"][m] - b["saved"][m]) <= 0.0100001
        assert b["wasted"]["count"] == 1
        assert approx(b["waste_rate"], 0.25)


def test_split_via_api_remove(client, user, make_item):
    a, d, t = (make_item(user, name=n, est_price=p) for n, p in (("a", 2.0), ("d", 3.0), ("t", 4.0)))
    client.post(f"/items/{a['id']}/remove", json={"outcome": "used"}, headers=user["headers"])
    client.post(f"/items/{d['id']}/remove", json={"outcome": "donated"}, headers=user["headers"])
    client.post(f"/items/{t['id']}/remove", json={"outcome": "thrown_out", "waste_reason": "expired"},
                headers=user["headers"])
    b = impact(client, user, "week")
    assert (b["used"]["count"], b["donated"]["count"], b["wasted"]["count"]) == (1, 1, 1)
    assert approx(b["used"]["money"], 2.0) and approx(b["donated"]["money"], 3.0)
    assert b["last_6_weeks"][-1]["used"] == 1 and b["last_6_weeks"][-1]["donated"] == 1
    assert b["last_6_weeks"][-1]["wasted"] == 1
    top = b["waste_reasons"][0]
    assert top["reason"] == "expired" and top["count"] == 1 and approx(top["money"], 4.0)


# ---- waste reasons ----------------------------------------------------------------------------
def test_waste_reasons_breakdown_sorted_with_shares(client, user, sql):
    uid = user["user"]["id"]
    for r, n in (("forgot", 3), ("expired", 1), ("other", 1)):
        for _ in range(n):
            ev(sql, uid, "thrown_out", r, kg=0.5, p=2.0, c=1.0)
    ev(sql, uid, "used")
    b = impact(client, user)
    wr = b["waste_reasons"]
    assert [x["reason"] for x in wr] == ["forgot", "expired", "other", "didnt_like"]  # ties: enum order
    assert [x["count"] for x in wr] == [3, 1, 1, 0]
    assert approx(wr[0]["share"], 0.6) and approx(wr[1]["share"], 0.2) and wr[3]["share"] == 0
    assert approx(sum(x["share"] for x in wr), 1.0)
    assert approx(wr[0]["money"], 6.0) and approx(wr[0]["kg"], 1.5) and approx(wr[0]["co2e_kg"], 3.0)
    assert sum(x["count"] for x in wr) == b["wasted"]["count"]
    assert approx(sum(x["money"] for x in wr), b["wasted"]["money"])


def test_waste_reasons_respect_range(client, user, sql):
    uid = user["user"]["id"]
    ev(sql, uid, "thrown_out", "forgot", days=1)
    ev(sql, uid, "thrown_out", "expired", days=10)
    ev(sql, uid, "thrown_out", "expired", days=40)
    cnt = lambda rng: {x["reason"]: x["count"] for x in impact(client, user, rng)["waste_reasons"]}  # noqa: E731
    assert cnt("week") == {"forgot": 1, "expired": 0, "didnt_like": 0, "other": 0}
    assert cnt("month") == {"forgot": 1, "expired": 1, "didnt_like": 0, "other": 0}
    assert cnt("all") == {"forgot": 1, "expired": 2, "didnt_like": 0, "other": 0}


# ---- previous period --------------------------------------------------------------------------
@pytest.mark.parametrize("rng,days", [("week", 7), ("month", 30)])
def test_previous_period_window(client, user, sql, rng, days):
    """previous = [now - 2*days, now - days); current = [now - days, now]."""
    uid = user["user"]["id"]
    ev(sql, uid, "used", days=days - 0.01, p=1.0)       # current, just inside
    ev(sql, uid, "used", days=days + 0.01, p=2.0)       # previous, just inside
    ev(sql, uid, "donated", days=2 * days - 0.01, p=4.0)  # previous, oldest edge
    ev(sql, uid, "thrown_out", "forgot", days=1.5 * days, p=8.0)  # previous
    ev(sql, uid, "used", days=2 * days + 0.01, p=16.0)  # before both windows
    b = impact(client, user, rng)
    assert b["saved"]["count"] == 1 and approx(b["saved"]["money"], 1.0)
    p = b["previous"]
    assert p["saved"]["count"] == 2 and approx(p["saved"]["money"], 6.0)
    assert p["used"]["count"] == 1 and p["donated"]["count"] == 1
    assert p["wasted"]["count"] == 1 and approx(p["wasted"]["money"], 8.0)
    assert approx(p["waste_rate"], 1 / 3)


def test_previous_null_for_all(client, user, sql):
    ev(sql, user["user"]["id"], "used", days=400)
    assert impact(client, user, "all")["previous"] is None


# ---- last 6 weeks: zero-filled, Monday 00:00 UTC buckets --------------------------------------
def _monday_utc(sql):
    return sql("SELECT (time_bucket('1 week', now()) AT TIME ZONE 'UTC')::date AS d")[0]["d"]


def test_last_6_weeks_zero_filled_and_aligned(client, user, sql):
    uid = user["user"]["id"]
    ev(sql, uid, "used", days=0)
    b = impact(client, user, "week")
    weeks = [date.fromisoformat(w["week"]) for w in b["last_6_weeks"]]
    cur = _monday_utc(sql)
    assert weeks == [cur - timedelta(weeks=5 - i) for i in range(6)]
    assert all(d.weekday() == 0 for d in weeks), "buckets start on Monday"
    assert [w["saved"] for w in b["last_6_weeks"]] == [0, 0, 0, 0, 0, 1]


def test_last_6_weeks_independent_of_range(client, user, sql):
    uid = user["user"]["id"]
    for wk in range(6):
        ev(sql, uid, "used", t=f"time_bucket('1 week', now()) - interval '{wk} weeks' + interval '1 hour'")
    series = [impact(client, user, r)["last_6_weeks"] for r in ("week", "month", "all")]
    assert series[0] == series[1] == series[2]
    assert [w["used"] for w in series[0]] == [1] * 6


def test_last_6_weeks_bucket_boundaries(client, user, sql):
    """Monday 00:00:00 UTC belongs to the new week; one microsecond earlier to the previous one;
    the oldest bucket starts 5 weeks before the current one and anything earlier is excluded."""
    uid = user["user"]["id"]
    b0 = "time_bucket('1 week', now())"
    ev(sql, uid, "used", t=b0)                                               # current week
    ev(sql, uid, "donated", t=f"{b0} - interval '1 microsecond'")            # week -1
    ev(sql, uid, "thrown_out", "forgot", t=f"{b0} - interval '5 weeks'")      # oldest week
    ev(sql, uid, "used", t=f"{b0} - interval '5 weeks' - interval '1 microsecond'")  # excluded
    s = impact(client, user, "all")["last_6_weeks"]
    assert [(w["used"], w["donated"], w["wasted"]) for w in s] == [
        (0, 0, 1), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 1, 0), (1, 0, 0)]
    for w in s:
        assert w["saved"] == w["used"] + w["donated"]
    assert impact(client, user, "all")["saved"]["count"] == 3  # the excluded one still counts in totals


def _impact_in_session_tz(app, user, tz, rng="all", frozen_now=None):
    """GET /impact with every pooled connection's session TimeZone set to `tz` (pool checkout hook),
    and optionally the request's `now()` frozen to `frozen_now` (statement rewrite). Asserts the
    zone really was in effect, so the test can't pass vacuously."""
    from app.extensions import db
    from sqlalchemy import text

    def set_tz(dbapi_conn, rec, proxy):
        c = dbapi_conn.cursor()
        c.execute(f"SET TIME ZONE '{tz}'")
        c.close()

    def freeze(conn, cur, stmt, params, ctx, many):
        if frozen_now is not None and "now()" in stmt and not many and isinstance(params, dict):
            stmt = stmt.replace("now()", "CAST(%(frozen_now)s AS timestamptz)")
            params = dict(params, frozen_now=frozen_now)
        return stmt, params

    with app.app_context():
        db.session.remove()
        db.engine.dispose()
        sa_event.listen(db.engine, "checkout", set_tz)
        sa_event.listen(db.engine, "before_cursor_execute", freeze, retval=True)
        try:
            assert db.session.execute(text("SHOW timezone")).scalar() == tz
            db.session.remove()
            b = impact(app.test_client(), user, rng)
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", freeze)
            sa_event.remove(db.engine, "checkout", set_tz)
            db.session.remove()
            db.engine.dispose()
    return b


def test_last_6_weeks_utc_even_if_session_timezone_is_not(app, client, user, sql):
    """BE-10 (fixed in PR 2): a non-UTC session zone does not shift buckets (week dates stay
    Mondays, events land in the right bucket)."""
    uid = user["user"]["id"]
    for wk in range(6):
        ev(sql, uid, "used", t=f"time_bucket('1 week', now()) - interval '{wk} weeks' + interval '2 hours'")
    cur = _monday_utc(sql)
    b = _impact_in_session_tz(app, user, "America/Chicago")
    weeks = [date.fromisoformat(w["week"]) for w in b["last_6_weeks"]]
    assert weeks == [cur - timedelta(weeks=5 - i) for i in range(6)]
    assert [w["used"] for w in b["last_6_weeks"]] == [1] * 6
    assert [date.fromisoformat(w["week"]) for w in b["weekly"]] == weeks
    assert b == _impact_in_session_tz(app, user, "UTC")


# US DST changes: 2026-03-08 (spring forward) and 2026-11-01 (fall back), both Sundays.
_NOV4 = ("2026-11-04 12:00:00+00", ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26", "2026-11-02"])
_MAR11 = ("2026-03-11 12:00:00+00", ["2026-02-02", "2026-02-09", "2026-02-16", "2026-02-23", "2026-03-02", "2026-03-09"])
_NOV2 = ("2026-11-02 00:00:00+00", _NOV4[1])
_NOV1 = ("2026-11-01 23:59:59.999999+00", ["2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"])
# BE-10 part 2 (fixed in PR 2): Chicago-2026-03-11 and Auckland-2026-11-01T23 cross a spring-forward
# change inside the window and used to drop events in the oldest week's first hour.
_DST_CASES = [pytest.param(tz, f, m, id=f"{tz}-{f[:10]}{'T' + f[11:13] if f[11:13] != '12' else ''}")
              for tz in ("America/Chicago", "Pacific/Auckland", "Asia/Kolkata", "UTC")
              for f, m in (_NOV4, _MAR11, _NOV2, _NOV1)]


@pytest.mark.parametrize("tz,frozen,mondays", _DST_CASES)
def test_last_6_weeks_stable_across_dst_in_any_session_zone(app, client, user, sql, tz, frozen, mondays):
    """`now()` frozen just after a DST change, session zone non-UTC: the 6 weeks are the Monday
    00:00 UTC buckets, and events on both sides of the change (bucket start, +2 h, last microsecond
    of the week, and the Sunday-night local times around the switch) land in their own bucket
    with no zero gaps. `weekly` (range=all) carries the same Monday dates."""
    uid = user["user"]["id"]
    for i, m in enumerate(mondays):
        start = f"TIMESTAMPTZ '{m} 00:00:00+00'"
        ev(sql, uid, "used", t=start)                                                     # exactly Monday 00:00Z
        ev(sql, uid, "donated", t=f"{start} + interval '2 hours'")
        if start != f"TIMESTAMPTZ '{mondays[-1]} 00:00:00+00'":
            ev(sql, uid, "thrown_out", "forgot", t=f"{start} + interval '7 days' - interval '1 microsecond'")
    # one event just before the oldest bucket: outside the series
    ev(sql, uid, "used", t=f"TIMESTAMPTZ '{mondays[0]} 00:00:00+00' - interval '1 microsecond'")
    b = _impact_in_session_tz(app, user, tz, "all", frozen)
    s = b["last_6_weeks"]
    assert [w["week"] for w in s] == mondays
    assert all(date.fromisoformat(m).weekday() == 0 for m in mondays)
    assert [(w["used"], w["donated"]) for w in s] == [(1, 1)] * 6, s
    assert [w["wasted"] for w in s] == [1, 1, 1, 1, 1, 0], s
    assert all(w["saved"] == w["used"] + w["donated"] for w in s)
    weekly = {w["week"]: (w["saved"], w["wasted"]) for w in b["weekly"]}
    assert all(date.fromisoformat(k).weekday() == 0 for k in weekly), weekly
    for m in mondays[:-1]:
        assert weekly[m] == (2, 1)
    assert weekly[mondays[-1]] == (2, 0)
    # the extra event sits in the week before the series, still a Monday bucket, still counted in totals
    prev = (date.fromisoformat(mondays[0]) - timedelta(weeks=1)).isoformat()
    assert weekly[prev] == (1, 0)
    assert b["saved"]["count"] == 13 and b["wasted"]["count"] == 5


# ---- isolation ---------------------------------------------------------------------------------
def test_other_users_events_invisible_everywhere(client, user, user2, sql):
    uid2 = user2["user"]["id"]
    for o, r in (("used", None), ("donated", None), ("thrown_out", "forgot")):
        ev(sql, uid2, o, r, days=1)
        ev(sql, uid2, o, r, days=10)
    sql("INSERT INTO food_events (user_id, item_id, event_type, category, est_price) "
        "VALUES (:u, gen_random_uuid(), 'add', 'dairy', 99)", u=user["user"]["id"])
    for rng in ("week", "month", "all"):
        b = impact(client, user, rng)
        assert all(b[k]["count"] == 0 for k in KINDS)
        assert all(x["count"] == 0 for x in b["waste_reasons"])
        assert all(w["saved"] == 0 and w["wasted"] == 0 for w in b["last_6_weeks"])
        if b["previous"] is not None:
            assert all(b["previous"][k]["count"] == 0 for k in KINDS)


# ---- N+1: a fixed number of statements whatever the data ---------------------------------------
def _count_statements(app, fn):
    from app.extensions import db

    n = [0]

    def hook(*a):
        n[0] += 1

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", hook)
        try:
            fn()
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", hook)
    return n[0]


@pytest.mark.parametrize("rng", ["week", "month", "all"])
def test_impact_query_count_constant(app, client, user, sql, rng):
    empty = _count_statements(app, lambda: impact(client, user, rng))
    uid = user["user"]["id"]
    for i in range(60):
        o = ("used", "donated", "thrown_out")[i % 3]
        ev(sql, uid, o, REASONS[i % 4] if o == "thrown_out" else None, days=i * 0.9)
    full = _count_statements(app, lambda: impact(client, user, rng))
    assert full == empty, (empty, full)
    # API.md: 5 queries for week/month (incl. the `since` lookup), 4 for all; +1 for the auth user lookup
    assert full == (5 if rng != "all" else 4) + 1, full


def test_range_echoed(client, user):
    for rng in ("week", "month", "all"):
        assert impact(client, user, rng)["range"] == rng
    assert client.get("/impact", headers=user["headers"]).get_json()["range"] == "all"


@pytest.mark.parametrize("rng,days", [("week", 7), ("month", 30)])
def test_events_exactly_at_since_and_prev_since(app, client, user, sql, rng, days):
    """Pin the request's `now()` (the since query) to a fixed instant T so events can sit exactly on
    the edges: [T-2d, T-d) is previous, [T-d, ...] is current, before T-2d is neither."""
    from app.extensions import db

    T = sql("SELECT date_trunc('second', now()) - interval '1 hour' AS t")[0]["t"]
    uid = user["user"]["id"]
    at = lambda expr: f"CAST(:T AS timestamptz) {expr}"  # noqa: E731
    put = lambda o, expr, p, r=None: sql(_INS.format(t=at(expr)), u=uid, o=o, r=r, kg=1, p=p, c=1, T=T)  # noqa: E731
    put("used", f"- interval '{days} days'", 1.0)                                   # == since -> current
    put("used", f"- interval '{days} days' - interval '1 microsecond'", 2.0)        # previous
    put("donated", f"- interval '{2 * days} days'", 4.0)                            # == prev_since -> previous
    put("used", f"- interval '{2 * days} days' - interval '1 microsecond'", 8.0)    # neither

    def pin(conn, cur, stmt, params, ctx, many):
        if stmt.lstrip().startswith("SELECT now() - make_interval"):
            stmt = stmt.replace("now()", "CAST(%(pinned_t)s AS timestamptz)")
            params = dict(params, pinned_t=T)
        return stmt, params

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", pin, retval=True)
        try:
            b = impact(app.test_client(), user, rng)
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", pin)
    assert b["saved"]["count"] == 1 and approx(b["saved"]["money"], 1.0), b["saved"]
    p = b["previous"]
    assert p["saved"]["count"] == 2 and approx(p["saved"]["money"], 6.0), p["saved"]
    assert p["used"]["count"] == 1 and p["donated"]["count"] == 1


@pytest.mark.parametrize("rng", ["week", "month"])
@pytest.mark.parametrize("tz,frozen", [
    ("America/Chicago", "2026-03-11 12:00:00+00"),  # BE-10 part 2 (fixed): spring forward, window was N days - 1 h
    ("America/Chicago", "2026-11-04 12:00:00+00"),  # BE-10 part 2 (fixed): fall back, window was N days + 1 h
    ("America/Chicago", "2026-07-15 12:00:00+00"),
    ("Pacific/Auckland", "2026-10-01 12:00:00+00"),
])
def test_range_windows_do_not_depend_on_session_zone(app, client, user, sql, rng, tz, frozen):
    """Events 30 min inside/outside N x 24 h (and 2N x 24 h) of a frozen `now`: same answer in any
    session zone as in UTC."""
    uid = user["user"]["id"]
    days = {"week": 7, "month": 30}[rng]
    for h, o in ((days * 24 - 0.5, "used"), (days * 24 + 0.5, "donated"),
                 (2 * days * 24 - 0.5, "used"), (2 * days * 24 + 0.5, "donated")):
        ev(sql, uid, o, t=f"TIMESTAMPTZ '{frozen}' - make_interval(secs => {h * 3600})")
    local = _impact_in_session_tz(app, user, tz, rng, frozen)
    utc = _impact_in_session_tz(app, user, "UTC", rng, frozen)
    assert utc["used"]["count"] == 1 and utc["previous"]["donated"]["count"] == 1
    assert utc["previous"]["used"]["count"] == 1
    assert local == utc
