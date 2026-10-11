"""Test-only WSGI entry for tests/test_gunicorn_gthread.py (not collected: no `test_` prefix).

Builds the real app against TEST_DATABASE_URL with test config and a stubbed, slow Gemini. It never
creates, drops or migrates anything: the pytest `app` fixture has already built the schema (under the
session advisory lock) before the test starts this under gunicorn, and the test stops gunicorn before
it returns. Refuses to start unless the test set FWR_GTHREAD_QA=1.
"""
import os
import time

if os.environ.get("FWR_GTHREAD_QA") != "1":  # pragma: no cover
    raise RuntimeError("tests/gthread_wsgi.py is test-only (FWR_GTHREAD_QA=1 not set)")

_DB = os.environ["TEST_DATABASE_URL"]
os.environ["DATABASE_URL"] = _DB  # create_app's load_dotenv() must not pick the dev DB
os.environ["ML_SERVICE_URL"] = ""

from app import create_app  # noqa: E402
from app.services import gemini  # noqa: E402

SLOW_S = float(os.environ.get("FWR_GTHREAD_SLOW_S", "3"))


def _slow_generate(contents, schema_hint, response_schema=None, purpose="generate", list_key=None,
                   timeout_s=None, retry=True):
    """Stands in for the Gemini round trip: blocks this request's thread, never touches the network."""
    time.sleep(SLOW_S)
    return [{"name": "Apples", "category": "produce_hardy", "quantity": 2, "unit": "piece"}]


gemini._generate = _slow_generate

app = create_app({
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": _DB,
    "JWT_SECRET": os.environ["FWR_GTHREAD_JWT_SECRET"],
    "GEMINI_API_KEY": "stub-not-a-key",
    "GEMINI_MODEL": "stub-model",
    "ML_SERVICE_URL": "",
})
