"""Multi-audience requests (feat/requests-audiences). Contract: docs/API.md "Request board".

POST /requests {text, audiences: {friends: bool, group_ids: [uuid]}}: at least one audience; the note is
stored once plus one join row per group audience; visibility is the union of the audiences; fulfil is
unchanged (one fulfilment, then 409 request_closed). A group you are not in is 404, nothing written.

World:
  alice   author of most requests; owner of G and K
  bob     accepted friend of alice, in no group
  carol   pending friend request -> alice only
  dave    stranger; owner of H
  erin    member of G, not a friend
  frank   accepted friend of alice AND member of G
  gina    former member of G (joined, then left)
  hank    member of K only
"""
import json
import uuid

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import text

from app.extensions import db
from conftest import _signup

MISSING = str(uuid.uuid4())


class W:
    def __init__(self, client):
        self.c = client

    def req(self, who, method, path, **kw):
        return getattr(self.c, method)(path, headers=who["headers"], **kw)

    def get(self, who, path):
        return self.req(who, "get", path)

    def post(self, who, path, body=None):
        return self.req(who, "post", path, json=body if body is not None else {})

    def delete(self, who, path):
        return self.req(who, "delete", path)

    def create(self, who, text_, friends=False, groups=(), expect=201):
        r = self.post(who, "/requests", {"text": text_, "audiences": {
            "friends": friends, "group_ids": [g["id"] for g in groups]}})
        assert r.status_code == expect, r.get_data(as_text=True)
        return r.get_json().get("request") if expect == 201 else r

    def board(self, who):
        r = self.get(who, "/requests")
        assert r.status_code == 200, r.get_data(as_text=True)
        return r.get_json()["requests"]

    def texts(self, who):
        return sorted(x["text"] for x in self.board(who))


@pytest.fixture
def w(client):
    w = W(client)
    for n in ("alice", "bob", "carol", "dave", "erin", "frank", "gina", "hank"):
        setattr(w, n, _signup(client, name=n.capitalize()))
    for friend in (w.bob, w.frank):
        assert w.post(w.alice, "/friends", {"email": friend["email"]}).status_code == 201
        assert w.post(friend, f"/friends/{w.alice['user']['id']}/accept").status_code == 200
    assert w.post(w.carol, "/friends", {"email": w.alice["email"]}).status_code == 201
    w.G = w.post(w.alice, "/groups", {"name": "Flat G"}).get_json()["group"]
    w.K = w.post(w.alice, "/groups", {"name": "Secret K"}).get_json()["group"]
    w.H = w.post(w.dave, "/groups", {"name": "Club H"}).get_json()["group"]
    for who, grp in ((w.erin, w.G), (w.frank, w.G), (w.gina, w.G), (w.hank, w.K)):
        assert w.post(who, "/groups/join", {"invite_code": grp["invite_code"]}).status_code == 200
    assert w.post(w.gina, f"/groups/{w.G['id']}/leave").status_code == 200
    return w


def err(r, status, code=None):
    assert r.status_code == status, (r.status_code, r.get_data(as_text=True))
    body = r.get_json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}, body
    if code:
        assert body["error"]["code"] == code, body
    return body


def _aud_table(sql):
    """The join table added by 0006 (any table with a request_id FK to requests)."""
    rows = sql("""SELECT DISTINCT c.relname AS t FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                  WHERE k.contype='f' AND k.confrelid = 'requests'::regclass""")
    names = [r["t"] for r in rows]
    assert len(names) == 1, names
    return names[0]


def _counts(sql):
    t = _aud_table(sql)
    return (sql("SELECT count(*) AS n FROM requests")[0]["n"], sql(f"SELECT count(*) AS n FROM {t}")[0]["n"])


# ------------------------------------------------------------------------------------------ validation

@pytest.mark.parametrize("body", [
    {"text": "eggs", "audiences": {}},
    {"text": "eggs", "audiences": {"friends": False, "group_ids": []}},
    {"text": "eggs", "audiences": {"friends": False}},
    {"text": "eggs", "audiences": {"group_ids": []}},
    {"text": "eggs", "audiences": None},
    {"text": "eggs", "audiences": []},
    {"text": "eggs", "audiences": "friends"},
    {"text": "eggs", "audiences": {"friends": "yes", "group_ids": []}},     # not a bool
    {"text": "eggs", "audiences": {"friends": 1, "group_ids": []}},
    {"text": "eggs", "audiences": {"friends": True, "group_ids": "G"}},     # not a list
    {"text": "eggs", "audiences": {"friends": True, "group_ids": None}},    # API.md: null group_ids is 400
    {"text": "eggs", "audiences": {"friends": True, "group_ids": [None]}},
    {"text": "eggs", "audiences": {"friends": True}, "group_id": None},     # both shapes at once
    {"text": "eggs", "audiences": {"friends": None, "group_ids": []}},
    {"text": "eggs", "audiences": {"friends": False, "group_ids": ["not-a-uuid"]}},
    {"text": "eggs", "audiences": {"friends": False, "group_ids": [123]}},
    {"text": "", "audiences": {"friends": True, "group_ids": []}},
    {"text": "   ", "audiences": {"friends": True, "group_ids": []}},
    {"text": "x" * 281, "audiences": {"friends": True, "group_ids": []}},
    {"text": 5, "audiences": {"friends": True, "group_ids": []}},
    {"audiences": {"friends": True, "group_ids": []}},
])
def test_create_validation_400_nothing_written(w, sql, body):
    err(w.post(w.alice, "/requests", body), 400, "validation_error")
    assert _counts(sql) == (0, 0)


def test_duplicate_group_ids_are_deduplicated(w, sql):
    """API.md: group_ids is deduplicated (any spelling of the same UUID), first-seen order kept."""
    q = w.create(w.alice, "eggs", groups=[w.G, w.K, w.G])
    t = _aud_table(sql)
    rows = sql(f"SELECT kind, group_id FROM {t}")
    assert sorted(str(r["group_id"]) for r in rows) == sorted([w.G["id"], w.K["id"]])
    r = w.post(w.alice, "/requests", {"text": "eggs2", "audiences": {
        "friends": False, "group_ids": [w.G["id"], w.G["id"].upper(), "{" + w.G["id"] + "}"]}})
    assert r.status_code == 201, r.get_data(as_text=True)
    assert [g["id"] for g in r.get_json()["request"]["audiences"]["groups"]] == [w.G["id"]]
    assert sql(f"SELECT count(*) AS n FROM {t} WHERE request_id=:r", r=r.get_json()["request"]["id"])[0]["n"] == 1
    assert q["audiences"]["hidden_count"] == 0


def test_both_audiences_and_group_id_400(w, sql):
    err(w.post(w.alice, "/requests", {"text": "x", "group_id": w.G["id"],
                                      "audiences": {"friends": True, "group_ids": []}}), 400, "validation_error")
    assert _counts(sql) == (0, 0)


def test_friends_true_with_zero_friends_is_allowed(w):
    q = w.create(w.hank, "anyone?", friends=True)
    assert q["audiences"] == {"friends": True, "groups": [], "hidden_count": 0}
    assert w.texts(w.hank) == ["anyone?"]
    for who in (w.alice, w.bob, w.erin):
        assert w.texts(who) == []


# ------------------------------------------------------------------------------- legacy group_id body

def test_legacy_body_without_audiences_is_friends(w, sql):
    for body in ({"text": "old"}, {"text": "old2", "group_id": None}):
        r = w.post(w.alice, "/requests", body)
        assert r.status_code == 201, r.get_data(as_text=True)
        assert r.get_json()["request"]["audiences"] == {"friends": True, "groups": [], "hidden_count": 0}
    assert w.texts(w.bob) == ["old", "old2"] and w.texts(w.erin) == []


def test_legacy_group_id_is_that_group_with_old_errors(w, sql):
    r = w.post(w.alice, "/requests", {"text": "old g", "group_id": w.G["id"]})
    assert r.status_code == 201
    q = r.get_json()["request"]
    assert q["audiences"] == {"friends": False, "groups": [{"id": w.G["id"], "name": "Flat G"}], "hidden_count": 0}
    assert q["group_id"] == w.G["id"] and q["group_name"] == "Flat G"
    assert w.texts(w.erin) == ["old g"] and w.texts(w.bob) == []
    before = _counts(sql)
    err(w.post(w.alice, "/requests", {"text": "x", "group_id": w.H["id"]}), 403, "forbidden")
    err(w.post(w.alice, "/requests", {"text": "x", "group_id": MISSING}), 404, "not_found")
    err(w.post(w.alice, "/requests", {"text": "x", "group_id": "junk"}), 400, "validation_error")
    err(w.post(w.gina, "/requests", {"text": "x", "group_id": w.G["id"]}), 403, "forbidden")
    assert _counts(sql) == before


def test_text_bounds(w):
    assert w.create(w.alice, "x" * 280, friends=True)["text"] == "x" * 280
    assert w.create(w.alice, "  y  ", friends=True)["text"] == "y"


@pytest.mark.parametrize("which", ["H", "MISSING", "gina_G"])
def test_group_not_member_or_unknown_is_404_nothing_written(w, sql, which):
    """A group you are not in (or that does not exist, or that you left) is 404, even next to valid audiences."""
    gid = {"H": w.H["id"], "MISSING": MISSING, "gina_G": w.G["id"]}[which]
    who = w.gina if which == "gina_G" else w.alice
    for aud in ({"friends": False, "group_ids": [gid]},
                {"friends": True, "group_ids": [gid]},
                {"friends": True, "group_ids": [w.K["id"], gid] if who is w.alice else [gid]}):
        err(w.post(who, "/requests", {"text": "eggs", "audiences": aud}), 404, "not_found")
    assert _counts(sql) == (0, 0)


def test_valid_create_writes_one_note_and_one_row_per_group(w, sql):
    q = w.create(w.alice, "eggs", friends=True, groups=[w.G, w.K])
    t = _aud_table(sql)
    assert sql("SELECT count(*) AS n FROM requests")[0]["n"] == 1
    rows = sql(f"SELECT * FROM {t}")
    assert all(str(r["request_id"]) == q["id"] for r in rows)
    gids = {str(r["group_id"]) for r in rows if r.get("group_id") is not None}
    assert gids == {w.G["id"], w.K["id"]}
    assert q["status"] == "open" and q["author_id"] == w.alice["user"]["id"]


# ------------------------------------------------------------------------------------------ visibility

def test_visibility_matrix_friends_only(w):
    w.create(w.alice, "f-only", friends=True)
    for who in (w.alice, w.bob, w.frank):
        assert w.texts(who) == ["f-only"], who["user"]["display_name"]
    for who in (w.carol, w.dave, w.erin, w.gina, w.hank):
        assert w.texts(who) == [], who["user"]["display_name"]


def test_visibility_matrix_group_only(w):
    w.create(w.alice, "g-only", groups=[w.G])
    for who in (w.alice, w.erin, w.frank):
        assert w.texts(who) == ["g-only"], who["user"]["display_name"]
    for who in (w.bob, w.carol, w.dave, w.gina, w.hank):
        assert w.texts(who) == [], who["user"]["display_name"]


def test_visibility_matrix_union(w):
    w.create(w.alice, "both", friends=True, groups=[w.G, w.K])
    for who in (w.alice, w.bob, w.erin, w.frank, w.hank):
        assert w.texts(who) == ["both"], who["user"]["display_name"]   # exactly once each
    for who in (w.carol, w.dave, w.gina):
        assert w.texts(who) == [], who["user"]["display_name"]


def test_friend_and_member_sees_request_once(w):
    """frank is a friend AND in G; alice is in G and K: no duplicates however many paths match."""
    w.create(w.alice, "multi", friends=True, groups=[w.G, w.K])
    w.create(w.alice, "two-groups", groups=[w.G, w.K])
    for who in (w.frank, w.alice):
        ids = [x["id"] for x in w.board(who)]
        assert len(ids) == len(set(ids)) == 2, w.board(who)


def test_pending_friend_accepted_later_sees_it_unfriend_revokes(w):
    w.create(w.alice, "f", friends=True)
    assert w.texts(w.carol) == []
    assert w.post(w.alice, f"/friends/{w.carol['user']['id']}/accept").status_code == 200
    assert w.texts(w.carol) == ["f"]
    assert w.delete(w.bob, f"/friends/{w.alice['user']['id']}").status_code == 204
    assert w.texts(w.bob) == []


def test_member_joining_later_sees_it_leaving_revokes(w):
    w.create(w.alice, "g", groups=[w.G])
    assert w.texts(w.bob) == []
    assert w.post(w.bob, "/groups/join", {"invite_code": w.G["invite_code"]}).status_code == 200
    assert w.texts(w.bob) == ["g"]
    assert w.post(w.erin, f"/groups/{w.G['id']}/leave").status_code == 200
    assert w.texts(w.erin) == []


def test_other_authors_requests_reach_me_through_any_path(w):
    """Reverse direction: erin's group request reaches alice/frank; bob's friends request reaches alice only."""
    w.create(w.erin, "from erin", groups=[w.G])
    w.create(w.bob, "from bob", friends=True)
    assert w.texts(w.alice) == ["from bob", "from erin"]
    assert w.texts(w.frank) == ["from erin"]
    assert w.texts(w.hank) == []


def test_fulfil_invisible_is_404_for_everyone_outside_audience(w):
    q = w.create(w.alice, "both", friends=True, groups=[w.G])
    for who in (w.carol, w.dave, w.gina, w.hank):
        err(w.post(who, f"/requests/{q['id']}/fulfil"), 404, "not_found")
        err(w.delete(who, f"/requests/{q['id']}"), 404, "not_found")
    err(w.post(w.bob, f"/requests/{MISSING}/fulfil"), 404, "not_found")
    err(w.post(w.bob, "/requests/not-a-uuid/fulfil"), 404, "not_found")
    assert w.board(w.alice)[0]["status"] == "open"


# ------------------------------------------------------------------------------------- audience exposure

def _secret_leaks(resp_json, *secrets):
    blob = json.dumps(resp_json)
    return [s for s in secrets if s in blob]


def test_get_never_names_groups_caller_is_not_in(w):
    w.create(w.alice, "both", friends=True, groups=[w.G, w.K])
    # bob: friend, in no group -> neither G nor K is named
    assert _secret_leaks(w.get(w.bob, "/requests").get_json(), "Flat G", "Secret K") == []
    # erin: in G only -> may see G, never K
    assert _secret_leaks(w.get(w.erin, "/requests").get_json(), "Secret K") == []
    # hank: in K only -> never G
    assert _secret_leaks(w.get(w.hank, "/requests").get_json(), "Flat G") == []


def test_get_never_exposes_ids_of_groups_caller_is_not_in(w):
    w.create(w.alice, "both", friends=True, groups=[w.G, w.K])
    assert _secret_leaks(w.get(w.bob, "/requests").get_json(), w.G["id"], w.K["id"]) == []
    assert _secret_leaks(w.get(w.erin, "/requests").get_json(), w.K["id"]) == []


def test_fulfil_and_cancel_responses_do_not_leak_foreign_groups(w):
    q = w.create(w.alice, "both", friends=True, groups=[w.G, w.K])
    r = w.post(w.bob, f"/requests/{q['id']}/fulfil")
    assert r.status_code == 200
    assert _secret_leaks(r.get_json(), "Flat G", "Secret K", w.G["id"], w.K["id"]) == []
    q2 = w.create(w.erin, "erin g", groups=[w.G])
    # alice (in G) can see erin's request; cancelling is author-only -> 403 with no leak either way
    err(w.delete(w.alice, f"/requests/{q2['id']}"), 403, "forbidden")


def test_author_sees_all_own_audiences(w):
    q = w.create(w.alice, "both", friends=True, groups=[w.G, w.K])
    mine = w.board(w.alice)[0]
    assert mine["id"] == q["id"]
    blob = json.dumps(mine)
    assert "Flat G" in blob and "Secret K" in blob


def test_source_types(w):
    w.create(w.alice, "both", friends=True, groups=[w.G])
    assert w.board(w.alice)[0]["source"]["type"] == "me"
    assert w.board(w.bob)[0]["source"] == {"type": "friend", "name": "Alice"}
    assert w.board(w.erin)[0]["source"] == {"type": "group", "name": "Flat G"}
    assert w.board(w.frank)[0]["source"]["type"] in ("friend", "group")


def _view(w, who, text_):
    return next(x for x in w.board(who) if x["text"] == text_)


def test_audiences_field_filtered_per_caller(w):
    w.create(w.alice, "all3", friends=True, groups=[w.K, w.G])
    G, K = {"id": w.G["id"], "name": "Flat G"}, {"id": w.K["id"], "name": "Secret K"}
    exp = {
        "alice": ({"friends": True, "groups": [G, K], "hidden_count": 0}, None, None),  # sorted by name
        "bob": ({"friends": True, "groups": [], "hidden_count": 2}, None, None),
        "erin": ({"friends": False, "groups": [G], "hidden_count": 2}, G["id"], "Flat G"),
        "frank": ({"friends": True, "groups": [G], "hidden_count": 1}, G["id"], "Flat G"),
        "hank": ({"friends": False, "groups": [K], "hidden_count": 2}, K["id"], "Secret K"),
    }
    for name, (aud, gid, gname) in exp.items():
        v = _view(w, getattr(w, name), "all3")
        assert v["audiences"] == aud, (name, v["audiences"])
        if name != "alice":
            assert (v["group_id"], v["group_name"]) == (gid, gname), (name, v)
    a = _view(w, w.alice, "all3")
    assert (a["group_id"], a["group_name"]) == (G["id"], "Flat G")   # deprecated: first of audiences.groups
    assert _view(w, w.frank, "all3")["source"] == {"type": "group", "name": "Flat G"}
    assert _view(w, w.hank, "all3")["source"] == {"type": "group", "name": "Secret K"}


def test_group_sort_is_case_insensitive(w, client):
    a = w.post(w.alice, "/groups", {"name": "apple"}).get_json()["group"]
    b = w.post(w.alice, "/groups", {"name": "Banana"}).get_json()["group"]
    q = w.create(w.alice, "s", groups=[b, a])
    assert [x["name"] for x in q["audiences"]["groups"]] == ["apple", "Banana"]


def test_board_order_newest_first_then_id(w, sql):
    for t in ("one", "two", "three"):
        w.create(w.alice, t, friends=True, groups=[w.G])
    assert [x["text"] for x in w.board(w.frank)] == ["three", "two", "one"]
    sql("UPDATE requests SET created_at = '2026-01-01T00:00:00Z'")
    ids = [x["id"] for x in w.board(w.frank)]
    assert ids == sorted(ids), ids     # equal created_at -> id order, stable


# ----------------------------------------------------------------------------------------------- fulfil

def test_fulfil_once_then_409_and_gone_from_every_board(w):
    q = w.create(w.alice, "both", friends=True, groups=[w.G, w.K])
    err(w.post(w.alice, f"/requests/{q['id']}/fulfil"), 403, "forbidden")
    r = w.post(w.erin, f"/requests/{q['id']}/fulfil")
    assert r.status_code == 200, r.get_data(as_text=True)
    f = r.get_json()["request"]
    assert f["status"] == "fulfilled" and f["fulfilled_by"] == w.erin["user"]["id"]
    for who in (w.bob, w.frank, w.hank, w.erin):
        err(w.post(who, f"/requests/{q['id']}/fulfil"), 409, "request_closed")
    for who in (w.alice, w.bob, w.erin, w.frank, w.hank):
        assert w.board(who) == []


def test_cancel_removes_from_every_board(w):
    q = w.create(w.alice, "both", friends=True, groups=[w.G, w.K])
    err(w.delete(w.bob, f"/requests/{q['id']}"), 403, "forbidden")
    assert w.delete(w.alice, f"/requests/{q['id']}").status_code == 200
    for who in (w.alice, w.bob, w.erin, w.frank, w.hank):
        assert w.board(who) == []
    err(w.post(w.bob, f"/requests/{q['id']}/fulfil"), 409, "request_closed")


# ------------------------------------------------------------------------------------------ leaving

def test_leaving_removes_only_that_audience(w, sql):
    q = w.create(w.frank, "frank both", friends=True, groups=[w.G])   # frank: friend of alice, in G
    t = _aud_table(sql)
    assert w.texts(w.erin) == ["frank both"] and w.texts(w.alice) == ["frank both"]
    assert w.post(w.frank, f"/groups/{w.G['id']}/leave").status_code == 200
    assert w.texts(w.erin) == []                 # G audience gone
    assert w.texts(w.alice) == ["frank both"]    # still a friend
    assert w.texts(w.frank) == ["frank both"]    # still open for the author
    assert w.board(w.frank)[0]["status"] == "open"
    assert sql(f"SELECT count(*) AS n FROM {t} WHERE group_id=:g", g=w.G["id"])[0]["n"] == 0
    assert sql("SELECT status FROM requests WHERE id=:i", i=q["id"])[0]["status"] == "open"


def test_leaving_one_of_two_groups_keeps_the_other(w, sql):
    # erin joins K too, then posts to G+K, then leaves G
    assert w.post(w.erin, "/groups/join", {"invite_code": w.K["invite_code"]}).status_code == 200
    w.create(w.erin, "erin gk", groups=[w.G, w.K])
    assert w.texts(w.frank) == ["erin gk"] and w.texts(w.hank) == ["erin gk"]
    assert w.post(w.erin, f"/groups/{w.G['id']}/leave").status_code == 200
    assert w.texts(w.frank) == []
    assert w.texts(w.hank) == ["erin gk"]
    assert w.texts(w.alice) == ["erin gk"]   # alice is in K as well
    assert _secret_leaks(w.get(w.hank, "/requests").get_json(), "Flat G", w.G["id"]) == []


def test_leaving_last_audience_closes_request(w, sql):
    q = w.create(w.erin, "erin g", groups=[w.G])
    assert w.post(w.erin, f"/groups/{w.G['id']}/leave").status_code == 200
    for who in (w.alice, w.frank, w.erin):
        assert w.board(who) == []
    assert sql("SELECT status FROM requests WHERE id=:i", i=q["id"])[0]["status"] == "cancelled"
    # closed, so nobody can act on it
    assert w.post(w.alice, f"/requests/{q['id']}/fulfil").status_code in (404, 409)


def test_leaving_does_not_touch_other_members_requests(w):
    w.create(w.alice, "alice g", groups=[w.G])
    w.create(w.frank, "frank g", groups=[w.G])
    assert w.post(w.erin, f"/groups/{w.G['id']}/leave").status_code == 200
    assert w.texts(w.frank) == ["alice g", "frank g"]
    assert w.texts(w.alice) == ["alice g", "frank g"]
    assert w.texts(w.erin) == []


def test_leaving_does_not_reopen_or_touch_closed_requests(w, sql):
    q = w.create(w.frank, "done", friends=True, groups=[w.G])
    assert w.post(w.erin, f"/requests/{q['id']}/fulfil").status_code == 200
    assert w.post(w.frank, f"/groups/{w.G['id']}/leave").status_code == 200
    row = sql("SELECT status, fulfilled_by FROM requests WHERE id=:i", i=q["id"])[0]
    assert row["status"] == "fulfilled" and str(row["fulfilled_by"]) == w.erin["user"]["id"]


def test_owner_leaving_keeps_friends_audience(w):
    w.create(w.alice, "alice both", friends=True, groups=[w.G])
    assert w.post(w.alice, f"/groups/{w.G['id']}/leave").status_code == 200
    assert w.texts(w.bob) == ["alice both"]
    assert w.texts(w.erin) == []


# ------------------------------------------------------------------------------------- account delete

def test_delete_author_removes_requests_and_join_rows(w, sql):
    w.create(w.alice, "a1", friends=True, groups=[w.G, w.K])
    w.create(w.alice, "a2", groups=[w.K])
    w.create(w.erin, "e1", groups=[w.G])
    t = _aud_table(sql)
    assert w.delete(w.alice, "/auth/me").status_code == 204
    left = sql(f"SELECT r.text FROM {t} a JOIN requests r ON r.id = a.request_id")
    assert [x["text"] for x in left] == ["e1"]
    assert sql(f"SELECT count(*) AS n FROM {t} a LEFT JOIN requests r ON r.id=a.request_id "
               "WHERE r.id IS NULL")[0]["n"] == 0
    assert w.texts(w.erin) == ["e1"] and w.texts(w.frank) == ["e1"]


def test_delete_member_keeps_others_requests_visible(w):
    w.create(w.alice, "a g", groups=[w.G])
    assert w.delete(w.erin, "/auth/me").status_code == 204
    assert w.texts(w.frank) == ["a g"]


def test_delete_fulfiller_reopens_request_with_audiences_intact(w, sql):
    q = w.create(w.alice, "a", friends=True, groups=[w.G])
    assert w.post(w.erin, f"/requests/{q['id']}/fulfil").status_code == 200
    assert w.delete(w.erin, "/auth/me").status_code == 204
    assert w.texts(w.bob) == ["a"] and w.texts(w.frank) == ["a"]


# --------------------------------------------------------------------------------------------- N+1

def _count_queries(app, fn):
    seen = []

    def hook(conn, cur, stmt, params, ctx, many):
        seen.append(stmt)

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", hook)
    try:
        r = fn()
    finally:
        with app.app_context():
            sa_event.remove(db.engine, "before_cursor_execute", hook)
    return r, seen


def test_board_query_count_constant(app, w):
    w.create(w.alice, "seed", friends=True, groups=[w.G])
    r, small = _count_queries(app, lambda: w.get(w.frank, "/requests"))
    assert r.status_code == 200 and len(r.get_json()["requests"]) == 1
    for i in range(12):
        w.create(w.alice, f"a{i}", friends=bool(i % 2), groups=[w.G, w.K][: 1 + i % 2])
        w.create(w.erin, f"e{i}", groups=[w.G])
        w.create(w.bob, f"b{i}", friends=True)
    r, big = _count_queries(app, lambda: w.get(w.frank, "/requests"))
    assert r.status_code == 200 and len(r.get_json()["requests"]) == 1 + 12 * 2
    assert len(big) == len(small) == 5, (len(small), len(big), big)   # API.md / builder: 5 total
    # author view (every audience named) is constant too
    _, a1 = _count_queries(app, lambda: w.get(w.alice, "/requests"))
    for i in range(10):
        w.create(w.alice, f"more{i}", friends=True, groups=[w.G, w.K])
    _, a2 = _count_queries(app, lambda: w.get(w.alice, "/requests"))
    assert len(a1) == len(a2) == 5, (len(a1), len(a2))


# ------------------------------------------------------------------------------------------ rollback

@pytest.mark.parametrize("target", ["join", "requests"])
def test_create_is_atomic_on_failure(app, w, sql, target):
    t = _aud_table(sql)
    prefix = f"INSERT INTO {t}".upper() if target == "join" else "INSERT INTO REQUESTS"

    def boom(conn, cur, stmt, params, ctx, many):
        if stmt.lstrip().upper().startswith(prefix):
            raise RuntimeError("boom")

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", boom)
        try:
            app.config["PROPAGATE_EXCEPTIONS"] = False
            r = app.test_client().post("/requests", headers=w.alice["headers"], json={
                "text": "eggs", "audiences": {"friends": True, "group_ids": [w.G["id"], w.K["id"]]}})
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", boom)
            app.config.pop("PROPAGATE_EXCEPTIONS", None)
    err(r, 500, "internal_error")
    assert _counts(sql) == (0, 0)
    assert w.board(w.alice) == []
    # the app recovers: the next create works
    w.create(w.alice, "eggs", friends=True, groups=[w.G])
    assert _counts(sql)[0] == 1


# ------------------------------------------------------------------------------------------ races

@pytest.mark.parametrize("k", [2, 4])
def test_concurrent_fulfil_exactly_one_wins(app, w, sql, k):
    import threading

    q = w.create(w.alice, "race", friends=True, groups=[w.G])
    fulfillers = [w.bob, w.erin, w.frank, w.bob][:k]
    barrier = threading.Barrier(k, timeout=10)
    lock, hits = threading.Lock(), {"n": 0}

    def hold(conn, cur, stmt, params, ctx, many):
        s = stmt.lstrip().upper()
        if s.startswith("SELECT") and "FROM REQUESTS" in s and "FOR UPDATE" in s:
            with lock:
                hits["n"] += 1
                mine = hits["n"] <= k
            if mine:
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass

    out = []

    def run(who):
        r = app.test_client().post(f"/requests/{q['id']}/fulfil", headers=who["headers"])
        out.append((r.status_code, (r.get_json() or {}).get("error", {}).get("code")))

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", hold)
    try:
        ts = [threading.Thread(target=run, args=(u,)) for u in fulfillers]
        for t in ts:
            t.start()
        for t in ts:
            t.join(30)
    finally:
        with app.app_context():
            sa_event.remove(db.engine, "before_cursor_execute", hold)
    assert sorted(out) == [(200, None)] + [(409, "request_closed")] * (k - 1), out
    row = sql("SELECT status, fulfilled_by FROM requests WHERE id=:i", i=q["id"])[0]
    assert row["status"] == "fulfilled" and row["fulfilled_by"] is not None


def test_too_many_group_ids_400(w, sql):
    ids = [str(uuid.uuid4()) for _ in range(51)]
    err(w.post(w.alice, "/requests", {"text": "x", "audiences": {"friends": True, "group_ids": ids}}),
        400, "validation_error")
    assert _counts(sql) == (0, 0)


def test_delete_me_rolls_back_audience_cleanup_on_failure(app, w, sql):
    q = w.create(w.alice, "keep", friends=True, groups=[w.G])
    t = _aud_table(sql)

    def boom(conn, cur, stmt, params, ctx, many):
        if stmt.lstrip().upper().startswith("DELETE FROM USERS"):
            raise RuntimeError("boom")

    with app.app_context():
        sa_event.listen(db.engine, "before_cursor_execute", boom)
        try:
            app.config["PROPAGATE_EXCEPTIONS"] = False
            r = app.test_client().delete("/auth/me", headers=w.alice["headers"])
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", boom)
            app.config.pop("PROPAGATE_EXCEPTIONS", None)
    err(r, 500, "internal_error")
    assert sql(f"SELECT count(*) AS n FROM {t} WHERE request_id=:r", r=q["id"])[0]["n"] == 2
    assert w.texts(w.bob) == ["keep"] and w.texts(w.erin) == ["keep"]


def test_former_member_still_sees_through_friends(w):
    """gina left G; once she is alice's friend she sees a friends+G request via friends only."""
    w.create(w.alice, "fg", friends=True, groups=[w.G])
    assert w.texts(w.gina) == []
    assert w.post(w.gina, "/friends", {"email": w.alice["email"]}).status_code == 201
    assert w.post(w.alice, f"/friends/{w.gina['user']['id']}/accept").status_code == 200
    v = w.board(w.gina)
    assert len(v) == 1 and v[0]["audiences"] == {"friends": True, "groups": [], "hidden_count": 1}
    assert v[0]["source"] == {"type": "friend", "name": "Alice"} and v[0]["group_id"] is None
    assert _secret_leaks(w.get(w.gina, "/requests").get_json(), "Flat G", w.G["id"]) == []
    # a G-only request stays invisible to her
    q = w.create(w.alice, "g only", groups=[w.G])
    err(w.post(w.gina, f"/requests/{q['id']}/fulfil"), 404, "not_found")
