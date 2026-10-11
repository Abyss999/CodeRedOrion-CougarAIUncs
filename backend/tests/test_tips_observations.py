"""GET /tips (feat/requests-audiences): every tip is a one-line factual observation drawn from the
caller's own events. No imperative advice, single line, short, numbers that match the seeded data,
never another user's data. Contract: docs/API.md "Recipes, impact, tips"."""
import re

import pytest

from conftest import iso_in

MAX_LEN = 100
# Imperative / advisory wording. Word-boundary, case-insensitive. "used"/"added"/"kept" etc. stay legal.
ADVICE = re.compile(
    r"\b(try|should|shouldn't|remember|don't|do not|consider|make sure|be sure|keep|buy|plan|use them|"
    r"use it|check|avoid|store|freeze|put|move|need to|must|ought|let's|why not|tip:|start|add)\b",
    re.IGNORECASE)


def _tips(client, who):
    r = client.get("/tips", headers=who["headers"])
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert set(body) == {"tips"} and isinstance(body["tips"], list)
    for t in body["tips"]:
        assert isinstance(t, dict) and isinstance(t.get("code"), str) and isinstance(t.get("message"), str), t
    return body["tips"]


def _throw(client, who, make_item, name, category, reason, n, price=3.5):
    for _ in range(n):
        it = make_item(who, name=name, category=category, est_price=price)
        r = client.post(f"/items/{it['id']}/remove", json={"outcome": "thrown_out", "waste_reason": reason},
                        headers=who["headers"])
        assert r.status_code == 200, r.get_data(as_text=True)


def _use(client, who, make_item, name, category, n):
    for _ in range(n):
        it = make_item(who, name=name, category=category)
        assert client.post(f"/items/{it['id']}/remove", json={"outcome": "used"},
                           headers=who["headers"]).status_code == 200


def _assert_style(tips):
    for t in tips:
        m = t["message"]
        assert m == m.strip() and m, t
        assert "\n" not in m and "\r" not in m, t
        assert len(m) <= MAX_LEN, (len(m), m)
        hit = ADVICE.search(m)
        assert hit is None, f"advice wording {hit.group(0)!r} in {m!r}"


def _ints(s):
    return [int(x) for x in re.findall(r"(?<![\d.])\d+(?![\d.])", s.replace(",", ""))]


@pytest.fixture
def seeded(client, user, make_item):
    """user: Spinach thrown out 5x (forgot), Milk 2x (expired), Bread used 4x, Yogurt expiring tomorrow."""
    _throw(client, user, make_item, "Spinach", "produce_leafy", "forgot", 5, price=2.0)
    _throw(client, user, make_item, "Milk", "dairy", "expired", 2, price=3.5)
    _use(client, user, make_item, "Bread", "bakery", 4)
    make_item(user, name="Yogurt", category="dairy", predicted_expiry=iso_in(1))
    return user


def test_seeded_tips_are_factual_one_liners(client, seeded):
    tips = _tips(client, seeded)
    assert tips, "expected observations for seeded data"
    _assert_style(tips)


def test_seeded_numbers_match_events(client, seeded):
    tips = _tips(client, seeded)
    blob = " | ".join(t["message"] for t in tips)
    # every integer quoted must be a true fact about the seed, or a window length the contract names
    # 5 spinach, 2 milk, 7 thrown total, 4 used, 1 expiring; 2-day expiry window; 30/90-day windows
    truthful = {5, 2, 7, 4, 1, 30, 90}
    bad = [n for n in _ints(blob) if n not in truthful]
    assert not bad, f"numbers {bad} do not match the seeded events: {blob}"
    by = {t["code"]: t["message"] for t in tips}
    assert "Spinach" in by["top_wasted_item"] and "5 times" in by["top_wasted_item"], by
    assert by["top_reason_forgot"].startswith("5 of the 7 "), by
    assert "$10.00" in by["top_wasted_category"] and "5 items" in by["top_wasted_category"], by
    assert "4 items" in by["saved_recent"], by
    assert "Yogurt" in by["expiring_soon"], by
    assert "Milk" not in blob and "Bread" not in blob, blob   # runner-ups / used items are not named


def test_window_excludes_old_events_and_follows_restore(client, user, make_item, sql):
    """Events outside the tip window do not count; undoing a removal removes it from the tips."""
    _throw(client, user, make_item, "Spinach", "produce_leafy", "forgot", 3)
    # hypertable: a row cannot move chunks by UPDATE, so copy it back in time and drop the original
    sql("CREATE TEMP TABLE _old AS SELECT * FROM food_events WHERE event_type='remove'; "
        "DELETE FROM food_events WHERE event_type='remove'; "
        "UPDATE _old SET time = time - interval '120 days', id = gen_random_uuid(); "
        "INSERT INTO food_events SELECT * FROM _old; DROP TABLE _old")
    tips = _tips(client, user)
    assert [t["code"] for t in tips] == ["getting_started"], tips
    it = make_item(user, name="Kale", category="produce_leafy")
    assert client.post(f"/items/{it['id']}/remove", json={"outcome": "thrown_out", "waste_reason": "expired"},
                       headers=user["headers"]).status_code == 200
    assert "Kale" in " ".join(t["message"] for t in _tips(client, user))
    assert client.post(f"/items/{it['id']}/restore", headers=user["headers"]).status_code == 200
    assert "Kale" not in " ".join(t["message"] for t in _tips(client, user))


def test_counts_track_the_data(client, user, make_item):
    _throw(client, user, make_item, "Spinach", "produce_leafy", "forgot", 3)
    first = " ".join(t["message"] for t in _tips(client, user))
    _throw(client, user, make_item, "Spinach", "produce_leafy", "forgot", 3)
    second = " ".join(t["message"] for t in _tips(client, user))
    assert first != second, "tips did not change when the counts did"
    if "3" in first:
        assert "6" in second, (first, second)


def test_other_users_events_never_show(client, user, user2, make_item):
    _throw(client, user2, make_item, "Durian", "produce_hardy", "didnt_like", 7, price=9.99)
    make_item(user2, name="Kimchi", category="other", predicted_expiry=iso_in(1))
    _throw(client, user, make_item, "Spinach", "produce_leafy", "forgot", 2, price=2.0)
    tips = _tips(client, user)
    _assert_style(tips)
    blob = " ".join(t["message"] for t in tips).lower()
    for leak in ("durian", "kimchi", "didn't like", "didnt", "hardy", "9.99", "69.93"):
        assert leak not in blob, (leak, blob)
    assert 7 not in _ints(blob), blob


def test_empty_state(client, user):
    tips = _tips(client, user)
    _assert_style(tips)
    assert len(tips) <= 1, tips
    for t in tips:  # an empty-state line is allowed, but it may not invent data
        assert not _ints(t["message"]) or set(_ints(t["message"])) <= {0, 30, 90}, t


def test_only_used_or_donated_no_waste_lines(client, user, make_item):
    _use(client, user, make_item, "Bread", "bakery", 3)
    tips = _tips(client, user)
    _assert_style(tips)
    blob = " ".join(t["message"] for t in tips).lower()
    assert "thrown" not in blob and "wasted" not in blob or "0" in blob, blob


def test_every_reason_produces_a_factual_line(client, signup, make_item):
    for reason in ("expired", "forgot", "didnt_like", "other"):
        u = signup()
        _throw(client, u, make_item, "Spinach", "produce_leafy", reason, 2)
        tips = _tips(client, u)
        assert tips, reason
        _assert_style(tips)


def test_expiring_soon_is_an_observation(client, user, make_item):
    make_item(user, name="Yogurt", category="dairy", predicted_expiry=iso_in(1))
    make_item(user, name="Ham", category="meat", predicted_expiry=iso_in(0))
    make_item(user, name="Rice", category="pantry_dry", predicted_expiry=iso_in(30))
    tips = _tips(client, user)
    _assert_style(tips)
    blob = " ".join(t["message"] for t in tips)
    assert "Rice" not in blob
    if "Yogurt" in blob or "Ham" in blob:
        assert 2 in _ints(blob), blob


def test_long_item_names_stay_one_short_line(client, user, make_item):
    long = "Organic Free-Range Extra Large Brown Eggs From The Farm Down The Road"
    _throw(client, user, make_item, long, "eggs", "forgot", 3)
    make_item(user, name=long + " (2)", category="eggs", predicted_expiry=iso_in(1))
    tips = _tips(client, user)
    _assert_style(tips)
    assert long not in " ".join(t["message"] for t in tips)   # API.md: names trimmed to 30 chars


def test_many_long_names_in_lists_stay_short(client, user, make_item):
    for i in range(6):
        make_item(user, name=f"Very Long Artisanal Sourdough Loaf Number {i}", category="bakery",
                  predicted_expiry=iso_in(1))
        make_item(user, name=f"Extremely Old Forgotten Casserole Dish {i}", category="leftovers",
                  predicted_expiry=iso_in(-3))
    tips = _tips(client, user)
    _assert_style(tips)
    by = {t["code"]: t["message"] for t in tips}
    for code in ("expiring_soon", "past_expiry"):   # shown names + "and N more" account for all 6
        m = re.search(r"^(.*) and (\d+) more (?:expire|are)", by[code])
        assert m, by[code]
        assert len(m.group(1).split(", ")) + int(m.group(2)) == 6, by[code]
        assert len(m.group(1).split(", ")) <= 3
    assert [t["code"] for t in tips][:2] == ["past_expiry", "expiring_soon"]


def test_item_name_grouping_is_case_insensitive(client, user, make_item):
    _throw(client, user, make_item, "spinach", "produce_leafy", "forgot", 2)
    _throw(client, user, make_item, "SPINACH", "produce_leafy", "forgot", 1)
    _throw(client, user, make_item, "Kale", "produce_leafy", "forgot", 2)
    by = {t["code"]: t["message"] for t in _tips(client, user)}
    assert "3 times" in by["top_wasted_item"] and "spinach" in by["top_wasted_item"].lower(), by


def test_ties_break_alphabetically(client, user, make_item):
    _throw(client, user, make_item, "Zucchini", "produce_hardy", "other", 2)
    _throw(client, user, make_item, "Apple", "produce_hardy", "expired", 1)
    _throw(client, user, make_item, "Banana", "dairy", "expired", 1)
    by = {t["code"]: t["message"] for t in _tips(client, user)}
    # item: Zucchini 2 wins on count; reason: expired 2 vs other 2 -> expired; category: hardy 3 wins
    assert by["top_wasted_item"].startswith("Zucchini"), by
    assert "top_reason_expired" in by and "top_reason_other" not in by, by
    assert by["top_wasted_category"].startswith("Hardy produce"), by


def test_item_tie_by_name(client, signup, make_item):
    u = signup()
    _throw(client, u, make_item, "Pear", "dairy", "forgot", 1)
    _throw(client, u, make_item, "Apple", "meat", "forgot", 1)
    by = {t["code"]: t["message"] for t in _tips(client, u)}
    assert by["top_wasted_item"].startswith("Apple"), by
    assert by["top_wasted_category"].startswith("Dairy"), by   # dairy < meat


def test_code_order_matches_contract(client, seeded, make_item):
    make_item(seeded, name="Ham", category="meat", predicted_expiry=iso_in(-1))
    codes = [t["code"] for t in _tips(client, seeded)]
    assert codes == ["past_expiry", "expiring_soon", "top_wasted_item", "top_reason_forgot",
                     "top_wasted_category", "saved_recent"], codes


def test_empty_state_code_and_message(client, user, make_item):
    make_item(user, name="Rice", category="pantry_dry", predicted_expiry=iso_in(30))
    tips = _tips(client, user)
    assert [t["code"] for t in tips] == ["getting_started"], tips
    assert "30 days" in tips[0]["message"]


def _backdate_removes(sql, days):
    sql("CREATE TEMP TABLE _old AS SELECT * FROM food_events WHERE event_type='remove' AND time > now() - interval '1 hour'; "
        "DELETE FROM food_events WHERE event_type='remove' AND time > now() - interval '1 hour'; "
        f"UPDATE _old SET time = time - interval '{days} days', id = gen_random_uuid(); "
        "INSERT INTO food_events SELECT * FROM _old; DROP TABLE _old")


def test_window_boundary_30_days(client, user, make_item, sql):
    _throw(client, user, make_item, "Inside", "dairy", "forgot", 2)
    _backdate_removes(sql, 29)
    _throw(client, user, make_item, "Outside", "meat", "expired", 5)
    _backdate_removes(sql, 31)
    by = {t["code"]: t["message"] for t in _tips(client, user)}
    blob = " ".join(by.values())
    assert "Inside" in by["top_wasted_item"] and "Outside" not in blob, by
    assert "top_reason_forgot" in by and "top_reason_expired" not in by, by
    assert by["top_wasted_category"].startswith("Dairy"), by


@pytest.mark.parametrize("n, word", [(1, "once"), (2, "twice"), (3, "3 times")])
def test_plurals_times(client, user, make_item, n, word):
    _throw(client, user, make_item, "Kale", "produce_leafy", "forgot", n)
    by = {t["code"]: t["message"] for t in _tips(client, user)}
    assert by["top_wasted_item"] == f"Kale went in the bin {word} in the last 30 days.", by
    cat = by["top_wasted_category"]
    assert (": 1 item," in cat) if n == 1 else (f": {n} items," in cat), cat
    if n == 1:
        assert by["top_reason_forgot"] == "The one item you threw out in the last 30 days was forgotten.", by
    else:
        assert by["top_reason_forgot"] == f"{n} of the {n} items you threw out in the last 30 days were forgotten.", by


def test_plurals_reason_split_and_saved(client, user, make_item):
    _throw(client, user, make_item, "Kale", "produce_leafy", "forgot", 1)
    _throw(client, user, make_item, "Milk", "dairy", "expired", 2)
    _use(client, user, make_item, "Bread", "bakery", 1)
    by = {t["code"]: t["message"] for t in _tips(client, user)}
    assert by["top_reason_expired"] == "2 of the 3 items you threw out in the last 30 days had expired.", by
    assert by["saved_recent"] == "You used or donated 1 item in the last 30 days.", by


def test_expiry_plurals_and_today_boundary(client, user, make_item):
    make_item(user, name="Ham", category="meat", predicted_expiry=iso_in(-1))
    make_item(user, name="Yogurt", category="dairy", predicted_expiry=iso_in(0))    # today -> soon, not past
    make_item(user, name="Milk", category="dairy", predicted_expiry=iso_in(2))      # edge of 2-day window
    make_item(user, name="Rice", category="pantry_dry", predicted_expiry=iso_in(3)) # outside
    by = {t["code"]: t["message"] for t in _tips(client, user)}
    assert by["past_expiry"] == "Ham is past the expiry date and still logged as in stock.", by
    assert by["expiring_soon"] == "Yogurt and Milk expire within 2 days.", by


def test_expiry_singular_and_plural_past(client, user, make_item):
    make_item(user, name="Milk", category="dairy", predicted_expiry=iso_in(1))
    make_item(user, name="Ham", category="meat", predicted_expiry=iso_in(-1))
    make_item(user, name="Eggs", category="eggs", predicted_expiry=iso_in(-2))
    by = {t["code"]: t["message"] for t in _tips(client, user)}
    assert by["expiring_soon"] == "Milk expires within 2 days.", by
    assert by["past_expiry"] == "Eggs and Ham are past the expiry date and still logged as in stock.", by
