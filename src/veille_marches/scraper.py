"""scraper.py — récupération des consultations actives depuis nukema.

nukema (marches-publics.nukema.com) est une SPA Atexo/local-trust, mais l'app
Angular consomme une API JSON publique que l'on appelle **directement en HTTP**
(stdlib urllib) — aucun pilotage de navigateur n'est nécessaire pour la
recherche ni pour le détail des consultations. C'est nettement plus robuste que
de gratter le DOM (validé en étape 0).

Contrat d'API (rétro-ingénierie via Playwright network capture) :

  POST /core/v2/consultations/query
      body : { active, direction, email, includeIgnored, page, query, scope, size }
      → { content: [ {id}, ... ], totalElements, totalPages, ... }
      (la liste ne porte QUE les ids des consultations)

  POST /core/v2/consultations/query/<id>?merged=false
      même body
      → { id, title, description, buyer{reason}, closedBy, ref, internalRef,
          market (SERVICES|WORKS|SUPPLIES), procedure{label},
          attachments:[ {label, lien, type, taille, source}, ... ], ... }

Le champ `query` est une requête Solr ; on reproduit exactement la forme émise
par la SPA pour un terme libre.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

BASE = "https://marches-publics.nukema.com"
QUERY_PATH = "/core/v2/consultations/query"

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (kutsh-veille-marches)",
    "Origin": BASE,
    "Referer": f"{BASE}/",
}


@dataclass
class Consultation:
    """Vue normalisée d'une consultation nukema."""

    id: int
    ref: str
    title: str
    description: str
    buyer: str
    closing_date: str | None  # ISO-8601 ou None
    market: str  # SERVICES | WORKS | SUPPLIES | ""
    procedure: str
    url: str
    attachments: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def stable_id(self) -> str:
        """Identifiant idempotent pour seen_ids/posted_ids.

        On préfère la référence métier (`ref`) si présente, sinon l'id nukema.
        """
        return (self.ref or "").strip() or f"nukema:{self.id}"


def build_query(term: str) -> str:
    """Reproduit la requête Solr émise par la SPA pour un terme libre."""
    t = term.replace('"', "")
    return (
        f'*:* AND *:* AND *:* AND ( (  title:"{t}*"  OR  description:"{t}*"  '
        f'OR  lots.label:"{t}*"  ) ) AND   search.duplicate : true '
    )


def _payload(term: str, page: int = 0, size: int = 30) -> dict:
    return {
        "active": "published.at",
        "direction": "asc",
        "email": None,
        "includeIgnored": False,
        "page": page,
        "query": build_query(term),
        "scope": "ACTIVES",
        "size": size,
    }


class HttpPoster:
    """Transport HTTP par défaut (urllib). Injectable pour les tests."""

    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    def post(self, path: str, payload: dict) -> Any:
        req = urllib.request.Request(
            f"{BASE}{path}",
            data=json.dumps(payload).encode(),
            method="POST",
            headers=_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310
            return json.loads(r.read())


def _consultation_url(cid: int) -> str:
    # Lien profond vers la fiche de consultation dans la SPA.
    return f"{BASE}/#/consultation/{cid}"


def _normalize(detail: dict) -> Consultation:
    buyer = (detail.get("buyer") or {}).get("reason") or ""
    procedure = (detail.get("procedure") or {}).get("label") or ""
    market = detail.get("market")
    market = market if isinstance(market, str) else ""
    return Consultation(
        id=detail["id"],
        ref=detail.get("ref") or detail.get("internalRef") or "",
        title=_strip_highlight(detail.get("title") or ""),
        description=_strip_highlight(detail.get("description") or ""),
        buyer=buyer,
        closing_date=detail.get("closedBy"),
        market=market,
        procedure=procedure,
        url=_consultation_url(detail["id"]),
        attachments=detail.get("attachments") or [],
        raw=detail,
    )


def _strip_highlight(text: str) -> str:
    """nukema injecte des <b class="text-highlight"> autour des termes ; on nettoie."""
    import re

    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


class NukemaScraper:
    def __init__(self, poster: HttpPoster | None = None, timeout: int = 60):
        self.poster = poster or HttpPoster(timeout=timeout)

    def search_ids(self, term: str, size: int = 30) -> list[int]:
        resp = self.poster.post(QUERY_PATH, _payload(term, size=size))
        content = resp.get("content", []) if isinstance(resp, dict) else []
        return [c["id"] for c in content if isinstance(c, dict) and "id" in c]

    def fetch_detail(self, cid: int, term: str) -> Consultation:
        # le body doit rester cohérent avec la recherche (mêmes params)
        detail = self.poster.post(f"{QUERY_PATH}/{cid}?merged=false", _payload(term))
        return _normalize(detail)

    def search(self, term: str, size: int = 30) -> list[Consultation]:
        """Recherche + hydratation des détails pour un terme."""
        out: list[Consultation] = []
        for cid in self.search_ids(term, size=size):
            try:
                out.append(self.fetch_detail(cid, term))
            except urllib.error.HTTPError:
                # une consultation qui échoue ne casse pas le lot
                continue
        return out

    def search_terms(self, terms: list[str], size: int = 30) -> list[Consultation]:
        """Recherche multi-termes, dédupliquée par id nukema."""
        seen: dict[int, Consultation] = {}
        for term in terms:
            for c in self.search(term, size=size):
                seen.setdefault(c.id, c)
        return list(seen.values())
