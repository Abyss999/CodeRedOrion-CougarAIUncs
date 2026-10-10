def _tips(r):
    b = r.get_json()
    return b["tips"] if isinstance(b, dict) else b


def test_tips_zero_data(client, user):
    r = client.get("/tips", headers=user["headers"])
    assert r.status_code == 200
    assert isinstance(_tips(r), list)


def test_tips_forgot_pattern(client, user, make_item):
    for _ in range(3):
        it = make_item(user, name="Spinach", category="produce_leafy")
        r = client.post(f"/items/{it['id']}/remove", json={"outcome": "thrown_out", "waste_reason": "forgot"},
                        headers=user["headers"])
        assert r.status_code == 200
    tips = _tips(client.get("/tips", headers=user["headers"]))
    assert tips, "expected at least one tip for a repeated 'forgot' pattern"
    blob = str(tips).lower()
    assert "spinach" in blob or "produce_leafy" in blob or "forgot" in blob


def test_tips_scoped_to_user(client, user, user2, make_item):
    for _ in range(3):
        it = make_item(user2, name="Spinach", category="produce_leafy")
        client.post(f"/items/{it['id']}/remove", json={"outcome": "thrown_out", "waste_reason": "forgot"}, headers=user2["headers"])
    assert "spinach" not in str(_tips(client.get("/tips", headers=user["headers"]))).lower()
