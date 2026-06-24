import json

from veille_marches.basecamp import BasecampPublisher
from veille_marches.config import Config
from veille_marches.pipeline import run
from veille_marches.scraper import NukemaScraper
from veille_marches.signals import SignalPublisher


class FakeTwenty:
    def __init__(self):
        self.created = []
        self.signals = []
        self.collectivites = []

    def find_one(self, obj, field, value):
        return None  # force la création de la collectivité acheteuse

    def create(self, obj, data):
        self.collectivites.append(data)
        return {"id": f"col{len(self.collectivites)}"}

    def create_signal(self, name, type_signal, statut="NOUVEAU", action_suggeree=None, **fields):
        self.created.append(name)
        self.signals.append({"name": name, **fields})
        return {"id": f"sig{len(self.created)}"}


def _llm(messages):
    return json.dumps({
        "pertinent": True, "niveau": 2, "niveau_justification": "workflow",
        "fonctionnalites": {}, "positionnement_kutsh": {},
        "resume": "ok", "action_suggeree": "go/no-go",
    })


def _cfg(tmp_path, monkeypatch):
    cfg = Config()
    cfg.state_file = str(tmp_path / "state.json")
    cfg.s3_bucket = None
    cfg.openrouter_api_key = "fake"
    cfg.twenty_api_key = "fake"
    cfg.basecamp_chatbot_lines_url = "https://example.test/lines"
    cfg.terms = ["x"]
    return cfg


def test_full_pipeline_posts_only_relevant_new(fake_poster, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    posts = []
    monkeypatch.setattr("veille_marches.basecamp._http",
                        lambda url, **k: (posts.append(url), (201, b"{}"))[1])
    fake_twenty = FakeTwenty()
    res = run(
        cfg,
        scraper=NukemaScraper(poster=fake_poster),
        basecamp=BasecampPublisher(cfg),
        signals=SignalPublisher(cfg, client=fake_twenty),
        dce_fetcher=lambda url: b"<!doctype html>",  # force fallback description
        analyze_caller=_llm,
    )
    # 3 vus, 1 pertinent (Rennes), 1 nouveau, 1 analysé/posté
    assert res.seen == 3
    assert res.relevant == 1
    assert res.new == 1
    assert len(res.analyzed) == 1
    assert res.posted_via == "campfire"
    assert res.signals_created == 1
    assert len(posts) == 1
    assert fake_twenty.created  # signal créé
    assert fake_twenty.collectivites  # collectivité acheteuse créée
    assert fake_twenty.signals[-1].get("collectiviteId")  # signal relié à la collectivité (1dhk)


def test_idempotent_no_repost(fake_poster, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    monkeypatch.setattr("veille_marches.basecamp._http", lambda url, **k: (201, b"{}"))
    common = dict(
        scraper=NukemaScraper(poster=fake_poster),
        dce_fetcher=lambda url: b"<!doctype html>",
        analyze_caller=_llm,
    )
    r1 = run(cfg, basecamp=BasecampPublisher(cfg), signals=SignalPublisher(cfg, client=FakeTwenty()), **common)
    assert r1.new == 1
    # second run : Rennes est désormais dans posted_ids → plus de nouveau
    r2 = run(cfg, basecamp=BasecampPublisher(cfg), signals=SignalPublisher(cfg, client=FakeTwenty()), **common)
    assert r2.new == 0
    assert len(r2.analyzed) == 0
    assert r2.posted_via == "skip"


def test_dry_run_writes_nothing(fake_poster, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    cfg.dry_run = True
    res = run(
        cfg,
        scraper=NukemaScraper(poster=fake_poster),
        dce_fetcher=lambda url: b"<!doctype html>",
        analyze_caller=_llm,
    )
    assert res.dry_run is True
    import os
    assert not os.path.exists(cfg.state_file)  # rien persisté
