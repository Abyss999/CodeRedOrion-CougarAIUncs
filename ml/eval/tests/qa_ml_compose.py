"""QA (ML) for the opt-in compose `ml` service and OCR_BACKEND=off (branch feat/ml-compose-service).

Run from the repo root:
  .venv-ml/bin/python -m pytest ml/eval/tests/qa_ml_compose.py -q -o python_files="test_*.py qa_*.py"

Never builds or starts a container. `docker compose config` (parse only) runs in a temp project dir whose
.env is a copy of .env.example, so the real .env is never read or printed. Optional deps (PyYAML, requests,
docker) skip their tests when missing.
"""
import ast
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap

import pytest
from PIL import Image

from conftest import REPO_ROOT

ML = os.path.join(REPO_ROOT, "ml")
COMPOSE = os.path.join(REPO_ROOT, "docker-compose.yml")
DOCKERFILE = os.path.join(ML, "serve", "Dockerfile")
ENV_EXAMPLE = os.path.join(REPO_ROOT, ".env.example")

ML_ENV = {"DETECTOR_BACKEND": "yolo", "YOLO_WEIGHTS": "/models/detector.pt",
          "FRESHNESS_WEIGHTS": "/models/freshness.pt", "YOLO_DEVICE": "${YOLO_DEVICE:-cpu}",
          "OCR_BACKEND": "off", "YOLO_CONFIG_DIR": "/tmp/ultralytics"}


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _png():
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 30, 30)).save(b, "PNG")
    return b.getvalue()


def _service_block(name):
    """Text of one top-level service (2-space indent) in docker-compose.yml, without PyYAML."""
    lines, out, on = _read(COMPOSE).splitlines(), [], False
    for ln in lines:
        if re.match(rf"^  {name}:\s*$", ln):
            on = True
            continue
        if on and (re.match(r"^  \S", ln) or re.match(r"^\S", ln)):
            break
        if on:
            out.append(ln)
    assert out, f"service {name} not found"
    return "\n".join(out)


def _strip_comments(s):
    return "\n".join(l for l in s.splitlines() if not l.strip().startswith("#"))


# ---------------------------------------------------------------- compose (text level, no deps)
def test_ml_block_profile_no_ports_ro_volume():
    b = _strip_comments(_service_block("ml"))
    assert re.search(r'profiles:\s*\["ml"\]', b)
    for key in ("ports:", "expose:", "network_mode:", "privileged:", "env_file:"):
        assert key not in b, f"ml must not set {key}"
    # ML-70 fix: long-syntax bind, read-only, never creates a missing host folder
    assert re.search(r"-\s*type:\s*bind\s*$", b, re.M)
    assert re.search(r"^\s+source:\s*\$\{ML_MODELS_DIR:-\.\./mldata/models/current\}\s*$", b, re.M)
    assert re.search(r"^\s+target:\s*/models\s*$", b, re.M) and re.search(r"^\s+read_only:\s*true\s*$", b, re.M)
    assert re.search(r"^\s+bind:\s*\n\s+create_host_path:\s*false\s*$", b, re.M)
    for k, v in ML_ENV.items():
        assert re.search(rf'^\s+{k}:\s*"?{re.escape(v)}"?\s*$', b, re.M), k


def test_ocr_off_is_quoted_so_yaml_keeps_a_string():
    # Unquoted `off` is a YAML 1.1 boolean (False); compose would then pass "false" and serve FakeOCR.
    assert re.search(r'OCR_BACKEND:\s*"off"', _service_block("ml"))


def test_default_services_have_no_profile_and_loopback_ports():
    for svc in ("db", "api"):
        b = _strip_comments(_service_block(svc))
        assert "profiles:" not in b
        for port in re.findall(r'^\s+-\s*"([^"]+)"\s*$', b.split("ports:")[1], re.M)[:1] if "ports:" in b else []:
            assert port.startswith("127.0.0.1:"), port
    assert "ML_SERVICE_URL" not in _service_block("api")    # comes from .env only


def test_build_context_and_dockerfile_exist():
    b = _service_block("ml")
    assert re.search(r"context:\s*\./ml\s*$", b, re.M) and re.search(r"dockerfile:\s*serve/Dockerfile\s*$", b, re.M)
    assert os.path.isfile(DOCKERFILE)


# ---------------------------------------------------------------- compose (PyYAML, if installed)
def test_compose_yaml_structure():
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load(_read(COMPOSE))
    s = d["services"]
    assert set(s) == {"db", "api", "ml"}
    ml = s["ml"]
    assert ml["profiles"] == ["ml"] and "ports" not in ml and "expose" not in ml
    assert ml["environment"] == ML_ENV and ml["environment"]["OCR_BACKEND"] == "off"
    assert ml["volumes"] == [{"type": "bind", "source": "${ML_MODELS_DIR:-../mldata/models/current}", "target": "/models",
                              "read_only": True, "bind": {"create_host_path": False}}]
    assert ml["build"] == {"context": "./ml", "dockerfile": "serve/Dockerfile"}
    assert all("profiles" not in s[k] for k in ("db", "api"))
    for k in ("db", "api"):
        assert all(str(p).startswith("127.0.0.1:") for p in s[k].get("ports", []))


# ---------------------------------------------------------------- docker compose config (parse only)
def _compose_config(tmp_path, *args):
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not installed")
    shutil.copy(ENV_EXAMPLE, tmp_path / ".env")   # never the real .env
    cmd = ["docker", "compose", "-f", COMPOSE, "--project-directory", str(tmp_path),
           "--env-file", str(tmp_path / ".env"), "-p", "qa_dummy", *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0 and "is not a docker command" in r.stderr:
        pytest.skip("docker compose plugin missing")
    assert r.returncode == 0, r.stderr[-500:]
    return r.stdout


def test_compose_config_default_up_excludes_ml(tmp_path):
    assert sorted(_compose_config(tmp_path, "config", "--services").split()) == ["api", "db"]
    assert sorted(_compose_config(tmp_path, "--profile", "ml", "config", "--services").split()) == ["api", "db", "ml"]


def test_compose_config_ml_resolved_with_empty_env_example_values(tmp_path):
    d = json.loads(_compose_config(tmp_path, "--profile", "ml", "config", "--format", "json"))
    ml = d["services"]["ml"]
    assert "ports" not in ml and "expose" not in ml
    env = ml["environment"]
    assert env["YOLO_DEVICE"] == "cpu"           # `YOLO_DEVICE=` in .env.example -> default via `:-`
    assert env["OCR_BACKEND"] == "off"
    (vol,) = ml["volumes"]
    assert vol["type"] == "bind" and vol["target"] == "/models" and vol["read_only"] is True
    assert vol["source"].endswith(os.path.join("mldata", "models", "current"))   # `ML_MODELS_DIR=` -> default
    assert vol["bind"] == {"create_host_path": False}                              # ML-70 fix survives normalisation
    assert ml["build"]["context"].endswith(os.sep + "ml") and ml["build"]["dockerfile"] == "serve/Dockerfile"


# ---------------------------------------------------------------- Dockerfile: the image has every module it imports
def _copied():
    df = _read(DOCKERFILE)
    files, dirs = set(), set()
    for m in re.finditer(r"^COPY\s+(.+?)\s+(/app/\S*)\s*$", df, re.M):
        srcs = m.group(1).split()
        for s in srcs:
            if s.endswith("/"):
                dirs.add(s.rstrip("/"))
            elif not s.endswith(".txt"):
                files.add(s)
    return files, dirs


def _in_image(relpath, files, dirs):
    return relpath in files or any(relpath.startswith(d + "/") for d in dirs)


def _local_imports(path):
    tree = ast.parse(_read(path))
    pkg = os.path.relpath(os.path.dirname(path), ML).replace(os.sep, ".")
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            if n.level:
                base = pkg.rsplit(".", n.level - 1)[0] if n.level > 1 else pkg
                mods.add(f"{base}.{n.module}" if n.module else base)
            elif n.module:
                mods.add(n.module)
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    return {m for m in mods if m.split(".")[0] in ("yolo", "ocr", "serve")}


def test_dockerfile_copies_every_local_module_the_service_imports():
    files, dirs = _copied()
    assert {"serve", "ocr"} <= dirs and "yolo/infer.py" in files and "yolo/taxonomy.py" in files
    todo = [p for p in ("serve/app.py", "serve/wsgi.py", "serve/backends.py", "serve/categories.py",
                        "yolo/infer.py", "ocr/receipt_pipeline.py")]
    seen = set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        assert _in_image(rel, files, dirs), f"{rel} imported but not copied into the image"
        for mod in _local_imports(os.path.join(ML, rel)):
            parts = mod.split(".")
            cand = ["/".join(parts) + ".py", "/".join(parts) + "/__init__.py"]
            hit = [c for c in cand if os.path.isfile(os.path.join(ML, c))]
            if not hit and len(parts) > 1:   # `from yolo import taxonomy`
                hit = [c for c in ("/".join(parts[:-1]) + ".py", "/".join(parts[:-1]) + "/__init__.py")
                       if os.path.isfile(os.path.join(ML, c))]
            assert hit, f"{rel}: cannot resolve {mod}"
            todo.extend(hit)
    assert "yolo/infer.py" in seen and "yolo/taxonomy.py" in seen


def test_dockerfile_cmd_binds_inside_container_only_and_ultralytics_pinned():
    df = _read(DOCKERFILE)
    assert '"0.0.0.0:8000"' in df and "serve.wsgi:app" in df      # fine: compose publishes no port
    assert re.search(r"^ultralytics==\S+$", _read(os.path.join(ML, "serve", "requirements.txt")), re.M)


def test_dockerfile_base_python_can_install_pins():
    """ML-72: the pytorch/pytorch:2.5.1 base had Python 3.11; numpy==2.5.4 needs >=3.12, so the image never built."""
    df = _read(DOCKERFILE)
    m = re.search(r"^FROM\s+python:(\d+)\.(\d+)(?:\.\d+)?-slim\s*$", df, re.M)
    assert m and (int(m.group(1)), int(m.group(2))) >= (3, 12), "base image must be Python >= 3.12"
    assert not re.search(r"^FROM\s+pytorch/pytorch", df, re.M) and len(re.findall(r"^FROM ", df, re.M)) == 1
    req = _read(os.path.join(ML, "serve", "requirements.txt"))
    assert re.search(r"^numpy==2\.\d+\.\d+$", req, re.M)
    assert not re.search(r"^torch(vision)?\b", req, re.M)               # torch only from the TORCH_INDEX layer
    assert re.search(r"^ARG TORCH_INDEX=https://download\.pytorch\.org/whl/cpu\s*$", df, re.M)
    t = re.search(r"^RUN pip install .*--index-url \$\{?TORCH_INDEX\}?.*$", df, re.M)
    assert t and "torch==2.9.1" in t.group(0) and "torchvision==0.24.1" in t.group(0)
    assert df.index(t.group(0)) < df.index("pip install --no-cache-dir -r /tmp/req.txt")   # torch first, then ultralytics
    assert re.search(r"apt-get install .*\blibgl1\b.*\blibglib2\.0-0\b", df)          # OpenCV runtime libs
    assert "rm -rf /var/lib/apt/lists" in df


def test_simulated_image_layout_boots_with_compose_env(tmp_path):
    """Lay out /app exactly as the Dockerfile COPYs it and import the wsgi app with the compose env.
    Weights point at a missing path (as when ML_MODELS_DIR is empty): /health is still 200, /ocr 503, and
    /detect fails with the contract's 500 inference_failed (the backend then falls back to Gemini)."""
    files, dirs = _copied()
    app_dir = tmp_path / "app"
    for f in files:
        os.makedirs(app_dir / os.path.dirname(f), exist_ok=True)
        shutil.copy(os.path.join(ML, f), app_dir / f)
    for d in dirs:
        shutil.copytree(os.path.join(ML, d), app_dir / d, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    script = textwrap.dedent(f"""
        import io, json, sys
        sys.path.insert(0, {str(app_dir)!r})
        from serve.wsgi import app
        import yolo.infer
        from PIL import Image
        def png():
            b = io.BytesIO(); Image.new("RGB", (32, 32)).save(b, "PNG"); return b.getvalue()
        c = app.test_client()
        h = c.get("/health")
        o = c.post("/ocr", data={{"image": (io.BytesIO(png()), "r.png")}}, content_type="multipart/form-data")
        d = c.post("/detect", data={{"image": (io.BytesIO(png()), "p.png")}}, content_type="multipart/form-data")
        print(json.dumps([h.status_code, h.json, o.status_code, o.json, d.status_code, d.json,
                          [m for m in sys.modules if m.startswith(("yolo", "ocr", "serve"))]]))
    """)
    env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "PYTHONPATH")}
    env.update({k: v for k, v in ML_ENV.items() if not v.startswith("$")}, YOLO_DEVICE="cpu",
               YOLO_WEIGHTS=str(tmp_path / "missing" / "detector.pt"),
               FRESHNESS_WEIGHTS=str(tmp_path / "missing" / "freshness.pt"))
    r = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, cwd=tmp_path,
                       env=env, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    hs, h, os_, o, ds, dj, mods = json.loads(r.stdout.strip().splitlines()[-1])
    assert hs == 200 and h == {"status": "ok", "detector": "YoloDetector", "ocr": "off"}
    assert os_ == 503 and o == {"error": {"code": "ocr_not_configured", "message": o["error"]["message"]}}
    assert ds == 500 and dj["error"]["code"] == "inference_failed"
    assert all(m.split(".")[0] in ("yolo", "ocr", "serve") for m in mods)


# ---------------------------------------------------------------- ml/serve OCR_BACKEND
@pytest.fixture
def serve():
    if ML not in sys.path:
        sys.path.insert(0, ML)
    from serve import app as app_mod, backends
    return app_mod, backends


@pytest.mark.parametrize("val,expect", [(None, "FakeOCR"), ("fake", "FakeOCR"), ("glm", "GlmOcr"), ("off", None)])
def test_ocr_from_env_values(serve, monkeypatch, val, expect):
    _, b = serve
    if val is None:
        monkeypatch.delenv("OCR_BACKEND", raising=False)
    else:
        monkeypatch.setenv("OCR_BACKEND", val)
    o = b.ocr_from_env()
    assert (o is None) if expect is None else type(o).__name__ == expect


def test_ocr_backend_normalised_and_typos_rejected(serve, monkeypatch):
    """ML-71 fix: case/space-insensitive; anything else raises instead of silently serving FakeOCR's canned receipt."""
    _, b = serve
    for v, want in (("Off", None), (" off ", None), ("OFF", None), (" Glm", "GlmOcr"), ("FAKE", "FakeOCR")):
        monkeypatch.setenv("OCR_BACKEND", v)
        o = b.ocr_from_env()
        assert (o is None) if want is None else type(o).__name__ == want, v
    for v in ("none", "false", "0", "disabled", "of", ""):
        monkeypatch.setenv("OCR_BACKEND", v)
        with pytest.raises(ValueError):
            b.ocr_from_env()


def test_bad_ocr_backend_stops_the_wsgi_app_import(tmp_path):
    """gunicorn imports serve.wsgi, which builds the app at import: a typo must stop the worker, never serve /ocr."""
    env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "PYTHONPATH")}
    env.update(OCR_BACKEND="none", DETECTOR_BACKEND="fake")
    r = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {ML!r}); import serve.wsgi"],
                       capture_output=True, text=True, cwd=tmp_path, env=env, timeout=60)
    assert r.returncode != 0 and "OCR_BACKEND must be fake, glm or off" in r.stderr


def _post(c, path, data=None):
    return c.post(path, data={"image": (io.BytesIO(data if data is not None else _png()), "x.png")},
                  content_type="multipart/form-data")


def test_ocr_off_contract(serve, monkeypatch):
    app_mod, b = serve
    monkeypatch.setenv("OCR_BACKEND", "off")
    c = app_mod.create_app(b.FakeDetector(), ocr=None, structure_with_gemini=False).test_client()
    r = _post(c, "/ocr")
    assert r.status_code == 503 and r.is_json
    assert set(r.json) == {"error"} and set(r.json["error"]) == {"code", "message"}
    assert r.json["error"]["code"] == "ocr_not_configured" and r.json["error"]["message"]
    assert "lines" not in r.json and "GV 2% MILK" not in r.get_data(as_text=True)
    # 503 even without / with a bad image: nothing is parsed
    assert c.post("/ocr").status_code == 503
    assert _post(c, "/ocr", b"not an image").status_code == 503
    assert c.get("/health").json == {"status": "ok", "detector": "FakeDetector", "ocr": "off"}
    d = _post(c, "/detect")
    assert d.status_code == 200 and d.json["candidates"]
    assert _post(c, "/detect", b"junk").status_code == 400          # detect errors unchanged


def test_explicit_ocr_injection_wins_over_off(serve, monkeypatch):
    app_mod, b = serve
    monkeypatch.setenv("OCR_BACKEND", "off")
    c = app_mod.create_app(b.FakeDetector(), b.FakeOCR(), structure_with_gemini=False).test_client()
    assert _post(c, "/ocr").status_code == 200 and c.get("/health").json["ocr"] == "FakeOCR"


def test_default_unset_still_fake(serve, monkeypatch):
    app_mod, b = serve
    monkeypatch.delenv("OCR_BACKEND", raising=False)
    c = app_mod.create_app(b.FakeDetector(), structure_with_gemini=False).test_client()
    r = _post(c, "/ocr")
    assert r.status_code == 200 and r.json["lines"] and c.get("/health").json["ocr"] == "FakeOCR"


# ---------------------------------------------------------------- backend side: 503 from /ocr -> MLUnavailable (-> 502)
def test_backend_client_maps_ocr_503_to_ml_unavailable(serve, monkeypatch):
    requests = pytest.importorskip("requests")
    flask = pytest.importorskip("flask")
    app_mod, b = serve
    spec = importlib.util.spec_from_file_location(
        "qa_backend_ml", os.path.join(REPO_ROOT, "backend", "app", "services", "ml.py"))
    bml = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bml)

    monkeypatch.setenv("OCR_BACKEND", "off")
    ml_client = app_mod.create_app(b.FakeDetector(), structure_with_gemini=False).test_client()

    def fake_post(url, files=None, data=None, timeout=None):
        path = url.split("http://ml:8000", 1)[1]
        name, payload, mime = files["image"]
        r = ml_client.post(path, data={**(data or {}), "image": (io.BytesIO(payload), name)},
                           content_type="multipart/form-data")
        resp = requests.Response()
        resp.status_code, resp._content, resp.url = r.status_code, r.get_data(), url
        resp.headers["Content-Type"] = r.content_type
        return resp

    monkeypatch.setattr(bml.requests, "post", fake_post)
    backend = flask.Flask("qa_backend")
    backend.config["ML_SERVICE_URL"] = "http://ml:8000"
    with backend.app_context():
        with pytest.raises(bml.MLUnavailable):
            bml.ocr(_png(), "r.png", "image/png")
        assert bml.detect(_png(), "p.png", "image/png", "fridge")       # /detect still works through the client
    errors = _read(os.path.join(REPO_ROOT, "backend", "app", "errors.py"))
    assert re.search(r'def upstream_unavailable.*\n\s+return ApiError\(502, "upstream_unavailable"', errors)
    items = _read(os.path.join(REPO_ROOT, "backend", "app", "routes", "items.py"))
    assert re.search(r"body = ml\.ocr\(.*\)\n\s+except ml\.MLUnavailable as e:\n\s+raise upstream_unavailable", items)


# ---------------------------------------------------------------- docs / env
def test_env_example_ml_keys_are_placeholders():
    env = _read(ENV_EXAMPLE)
    for k in ("ML_MODELS_DIR", "YOLO_DEVICE", "ML_SERVICE_URL"):
        assert re.search(rf"^{k}=\s*$", env, re.M), f"{k} must be present and empty"
    assert "http://ml:8000" in env and "--profile ml" in env


def test_docs_cover_profile_env_and_ocr_off():
    ml_md, setup = _read(os.path.join(REPO_ROOT, "docs", "ML.md")), _read(os.path.join(REPO_ROOT, "docs", "SETUP.md"))
    assert "docker compose --profile ml up -d --build" in ml_md and "docker compose --profile ml up -d --build" in setup
    assert "Plain `docker compose up -d` leaves `ml` off" in setup
    assert "OCR_BACKEND=fake|glm|off" in ml_md and "503 `ocr_not_configured`" in ml_md
    for k in ("ML_MODELS_DIR", "YOLO_DEVICE", "ML_SERVICE_URL"):
        assert k in setup and k in ml_md
    for k in ("DETECTOR_BACKEND", "YOLO_WEIGHTS", "FRESHNESS_WEIGHTS", "OCR_BACKEND"):
        assert k in ml_md
    assert "no host port" in ml_md.lower() or "publishes no host port" in ml_md
    assert "YOLO_CONFIG_DIR" in ml_md and "absolute `ML_MODELS_DIR`" in ml_md
    assert "TORCH_INDEX" in ml_md                                     # ML-72: GPU build arg documented
