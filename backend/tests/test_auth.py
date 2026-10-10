def test_signup_login(client):
    r = client.post("/auth/signup", json={"email": "a@x.com", "password": "pw12345678", "display_name": "A"})
    assert r.status_code == 201
    b = r.get_json()
    assert b["token"] and b["user"]["email"] == "a@x.com"
    assert "password" not in str(b["user"]).lower().replace("password_hash", "") or "password_hash" not in b["user"]
    assert "password_hash" not in b["user"]
    r = client.post("/auth/login", json={"email": "a@x.com", "password": "pw12345678"})
    assert r.status_code == 200 and r.get_json()["token"]


def test_signup_duplicate_email(client, signup):
    u = signup(email="dup@x.com")
    r = client.post("/auth/signup", json={"email": "DUP@x.com", "password": "pw12345678", "display_name": "B"})
    assert r.status_code in (400, 409)
    assert "code" in r.get_json()["error"]


def test_signup_bad_input(client):
    for body in [{}, {"email": "nope", "password": "pw12345678", "display_name": "A"},
                 {"email": "a@x.com", "display_name": "A"}]:
        r = client.post("/auth/signup", json=body)
        assert r.status_code == 400, body
        e = r.get_json()["error"]
        assert e["code"] and e["message"]


def test_login_wrong_password_and_unknown(client, signup):
    u = signup(email="l@x.com")
    assert client.post("/auth/login", json={"email": "l@x.com", "password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"email": "no@x.com", "password": "x"}).status_code == 401
    assert client.post("/auth/login", json={}).status_code == 400


def test_protected_requires_token(client):
    assert client.get("/health").status_code == 200
    for method, path in [("get", "/items"), ("post", "/items"), ("get", "/impact"), ("get", "/tips"),
                         ("post", "/recipes/suggest"), ("get", "/items/barcode/123")]:
        r = getattr(client, method)(path)
        assert r.status_code == 401, path
        assert r.get_json()["error"]["code"]


def test_invalid_token(client):
    r = client.get("/items", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
