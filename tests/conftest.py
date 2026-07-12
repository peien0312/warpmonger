"""Site test harness: real Flask app against a POS-schema fixture DB.

The POS fixture is built by the sibling repo's venv (schema stays truthful
to the source; see make_pos_fixture.py). Env must be set before app import.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="abbeys-test-")
_POS_DB = os.path.join(_TMP, "pos.db")
_ROOT = Path(__file__).resolve().parents[1]
_POS_PY = _ROOT.parent / "warpmonger-pos" / "venv" / "bin" / "python"

subprocess.run([str(_POS_PY), str(_ROOT / "tests" / "make_pos_fixture.py"),
                _POS_DB], check=True, capture_output=True)

os.environ["POS_DB"] = _POS_DB
os.environ["MEMBERS_DB"] = os.path.join(_TMP, "members.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("STOREFRONT_API_KEY", "")   # checkout API calls disabled

sys.path.insert(0, str(_ROOT))

import pytest  # noqa: E402

import memberdb  # noqa: E402
memberdb.init()

from app import app as flask_app  # noqa: E402


@pytest.fixture(scope="session")
def app():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()
