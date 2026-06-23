from veille_marches.scraper import NukemaScraper, build_query


def test_build_query_shape():
    q = build_query("autorisations d'urbanisme")
    assert 'title:"autorisations d\'urbanisme*"' in q
    assert "search.duplicate : true" in q


def test_build_query_strips_quotes():
    # le terme utilisateur ne doit pas injecter de guillemets dans la requête Solr
    q = build_query('a "b" c')
    assert 'title:"a b c*"' in q


def test_search_hydrates_details(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    res = s.search("autorisations d'urbanisme")
    assert len(res) == 3
    rennes = next(c for c in res if c.id == 3007885)
    assert rennes.title == "Numérisation des dossiers d'urbanisme de Rennes Métropole"
    assert rennes.buyer.startswith("RENNES METROPOLE")
    assert rennes.market == "SERVICES"
    assert rennes.closing_date == "2026-07-30T10:00:00Z"
    # highlight html stripped
    assert "<b" not in rennes.description


def test_stable_id_prefers_ref(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    rennes = next(c for c in s.search("x") if c.id == 3007885)
    assert rennes.stable_id == "235366"


def test_search_terms_dedup(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    res = s.search_terms(["t1", "t2"])
    assert len(res) == 3  # dédup par id malgré 2 termes
