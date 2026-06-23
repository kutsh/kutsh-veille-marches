import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def query_resp():
    return json.loads((FIX / "nukema_query.json").read_text())


@pytest.fixture
def details():
    return json.loads((FIX / "nukema_details.json").read_text())


@pytest.fixture
def cctp_docx_bytes():
    return (FIX / "cctp_sample.docx").read_bytes()


class FakePoster:
    """Imite scraper.HttpPoster en servant les fixtures (pas de réseau)."""

    def __init__(self, query_resp, details):
        self.query_resp = query_resp
        self.details = details

    def post(self, path, payload):
        if path.endswith("/consultations/query"):
            return self.query_resp
        # /consultations/query/<id>?merged=false
        cid = path.rsplit("/", 1)[1].split("?")[0]
        return self.details[cid]


@pytest.fixture
def fake_poster(query_resp, details):
    return FakePoster(query_resp, details)
