"""browser.py — repli Playwright (optionnel).

Le cœur du scraping appelle l'API JSON de nukema en HTTP direct (urllib) — voir
scraper.py. Ce module n'est utilisé que si l'on veut :
  - amorcer une session navigateur (cookies/anti-bot) avant les appels API ;
  - tenter le téléchargement des DCE via les cookies de la session SPA.

Téléchargement DCE : validé en étape 0 comme NON fiable sans login (nukema
renvoie le shell SPA, le binaire vit derrière la plateforme source). On expose
néanmoins un fetcher branchable sur dce.get_dce_text(fetcher=…) ; il retourne
des bytes ou lève, et dce.py bascule alors sur la description.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator

from .scraper import BASE


@contextlib.contextmanager
def browser_fetcher(headless: bool = True) -> Iterator:
    """Context manager → callable(url) -> bytes, partageant les cookies de la SPA."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="fr-FR")
        page = ctx.new_page()
        # amorce la session (cookies)
        page.goto(f"{BASE}/#/search?tokens=urbanisme&fromMenu=true",
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        def fetch(url: str) -> bytes:
            resp = ctx.request.get(url, headers={"Referer": f"{BASE}/"})
            return resp.body()

        try:
            yield fetch
        finally:
            browser.close()
