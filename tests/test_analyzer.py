import json

from veille_marches.analyzer import analyze
from veille_marches.scraper import NukemaScraper


def _fake_llm(payload: dict):
    def caller(messages):
        # vérifie que le prompt embarque bien le texte technique
        assert "Texte technique" in messages[1]["content"]
        return json.dumps(payload)

    return caller


def test_analyze_parses_structured_json(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    rennes = next(c for c in s.search("x") if c.id == 3007885)
    payload = {
        "pertinent": True,
        "niveau": 3,
        "niveau_justification": "aide à l'instruction + connaissance réglementaire",
        "fonctionnalites": {
            "gnau_front_office": True,
            "sig_cartographie": True,
            "aide_decision_consultations": True,
            "ia_extraction": "OBLIGATOIRE",
            "reprise_donnees": True,
            "hebergement": "SAAS",
        },
        "positionnement_kutsh": {"couvert": "ADS+IA", "manquant": "rien", "differenciation_ia": "fort"},
        "resume": "Opportunité forte.",
        "action_suggeree": "Go/no-go avant clôture",
    }
    a = analyze(rennes, "texte cctp", "cctp", api_key="x", caller=_fake_llm(payload))
    assert a.pertinent is True
    assert a.niveau == 3
    assert a.niveau_label.startswith("Aide à l'instruction")
    assert a.fonctionnalites["ia_extraction"] == "OBLIGATOIRE"


def test_analyze_can_declass(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    rennes = next(c for c in s.search("x") if c.id == 3007885)
    a = analyze(rennes, "t", "description", api_key="x",
                caller=lambda m: json.dumps({"pertinent": False, "niveau": 1}))
    assert a.pertinent is False


def test_analyze_normalizes_bad_niveau(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    rennes = next(c for c in s.search("x") if c.id == 3007885)
    a = analyze(rennes, "t", "x", api_key="x",
                caller=lambda m: json.dumps({"pertinent": True, "niveau": 9}))
    assert a.niveau is None
