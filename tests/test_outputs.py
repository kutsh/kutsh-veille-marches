import datetime as dt

from veille_marches.analyzer import Analysis
from veille_marches.basecamp import BasecampPublisher, render_digest_html, urgent
from veille_marches.config import Config
from veille_marches.scraper import NukemaScraper
from veille_marches.signals import SignalPublisher


def _analysis():
    return Analysis(
        pertinent=True, niveau=3, niveau_justification="x",
        fonctionnalites={"ia_extraction": "OBLIGATOIRE", "gnau_front_office": True},
        positionnement_kutsh={"couvert": "c", "manquant": "m", "differenciation_ia": "d"},
        resume="r", action_suggeree="a",
    )


def test_urgent_flag(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    c = next(x for x in s.search("x") if x.id == 3007885)
    c.closing_date = (dt.date.today() + dt.timedelta(days=3)).isoformat() + "T10:00:00Z"
    assert urgent(c) is True
    c.closing_date = (dt.date.today() + dt.timedelta(days=30)).isoformat() + "T10:00:00Z"
    assert urgent(c) is False


def test_digest_html_contains_levels(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    c = next(x for x in s.search("x") if x.id == 3007885)
    html = render_digest_html([(c, _analysis())])
    assert "niveau 3/3" in html
    assert "Aide à l'instruction" in html
    assert "OBLIGATOIRE" in html
    assert "Positionnement Kutsh" in html


def test_basecamp_uses_campfire_when_configured(fake_poster, monkeypatch):
    s = NukemaScraper(poster=fake_poster)
    c = next(x for x in s.search("x") if x.id == 3007885)
    cfg = Config()
    cfg.basecamp_chatbot_lines_url = "https://example.test/lines"
    posted = {}

    def fake_http(url, *, method, headers, body=None, timeout=60):
        posted["url"] = url
        posted["body"] = body
        return 201, b"{}"

    monkeypatch.setattr("veille_marches.basecamp._http", fake_http)
    via = BasecampPublisher(cfg).post([(c, _analysis())])
    assert via == "campfire"
    assert posted["url"] == "https://example.test/lines"


def test_basecamp_skips_without_credentials(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    c = next(x for x in s.search("x") if x.id == 3007885)
    cfg = Config()
    cfg.basecamp_chatbot_lines_url = None
    cfg.basecamp_access_token = None
    assert BasecampPublisher(cfg).post([(c, _analysis())]) == "skip:no-credentials"


class FakeTwenty:
    def __init__(self):
        self.created = []

    def create_signal(self, name, type_signal, statut="NOUVEAU", action_suggeree=None):
        rec = {"id": "sig1", "name": name, "typeSignal": type_signal,
               "statut": statut, "actionSuggeree": action_suggeree}
        self.created.append(rec)
        return rec


def test_signal_publisher_creates_signal(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    c = next(x for x in s.search("x") if x.id == 3007885)
    cfg = Config()
    cfg.twenty_api_key = "k"
    fake = FakeTwenty()
    pub = SignalPublisher(cfg, client=fake)
    rec = pub.create(c, _analysis())
    assert rec["typeSignal"] == "MARCHE_PUBLIC"
    assert rec["statut"] == "NOUVEAU"
    assert fake.created[0]["name"].startswith("RENNES METROPOLE")


def test_signal_unavailable_without_key(fake_poster):
    cfg = Config()
    cfg.twenty_api_key = None
    pub = SignalPublisher(cfg, client=FakeTwenty())
    assert pub.available is False
    s = NukemaScraper(poster=fake_poster)
    c = next(x for x in s.search("x") if x.id == 3007885)
    assert pub.create(c, _analysis()) is None
