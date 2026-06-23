from veille_marches.relevance import filter_relevant, score
from veille_marches.scraper import NukemaScraper


def test_relevant_urbanisme_software(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    rennes = next(c for c in s.search("x") if c.id == 3007885)
    v = score(rennes)
    assert v.relevant is True
    assert v.score >= 1


def test_excludes_construction_works(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    logements = next(c for c in s.search("x") if c.id == 2997303)
    v = score(logements)
    assert v.relevant is False  # WORKS + signaux travaux


def test_excludes_controle_technique(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    ct = next(c for c in s.search("x") if c.id == 2987466)
    assert score(ct).relevant is False


def test_filter_keeps_only_relevant(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    res = filter_relevant(s.search("x"))
    assert [c.id for c, _ in res] == [3007885]
