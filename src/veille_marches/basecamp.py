"""basecamp.py — publication du digest de veille sur Basecamp.

Deux voies (cf. spec), choisies dans cet ordre de simplicité/robustesse :

  1) Campfire via lines_url signée (RECOMMANDÉE, sans OAuth) :
     POST {content: html} sur BASECAMP_CHATBOT_LINES_URL. Même mécanisme que
     kutsh-crm/scripts/qualify_leads.py. Robuste, zéro gestion de token.

  2) API Basecamp (message riche dans le projet Veille) si BASECAMP_ACCESS_TOKEN
     + BASECAMP_ACCOUNT_ID sont fournis :
     POST /buckets/<project>/message_boards/<board>/messages.json
     (nécessite de résoudre l'id du message board du projet).

Le CLI Basecamp (qui ne rend pas les tableaux markdown) n'est PAS utilisé : on
poste du HTML directement via l'API HTTP. On évite donc les tableaux markdown.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .analyzer import Analysis
from .config import Config
from .scraper import Consultation

USER_AGENT = "kutsh-veille-marches (joel.gombin@gmail.com)"


def _http(url: str, *, method: str, headers: dict, body: bytes | None = None, timeout: int = 60):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return r.status, r.read()


def urgent(consultation: Consultation) -> bool:
    """URGENCE si clôture < 7 jours."""
    import datetime as dt

    if not consultation.closing_date:
        return False
    try:
        d = dt.datetime.fromisoformat(consultation.closing_date.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (d.date() - dt.date.today()).days < 7


def _feat_line(label: str, value) -> str:
    if value is None:
        value = "non précisé"
    elif value is True:
        value = "oui"
    elif value is False:
        value = "non"
    return f"<li>{label} : {value}</li>"


def render_item_html(consultation: Consultation, analysis: Analysis) -> str:
    """HTML d'un marché (réutilisé en digest Campfire ET en message API)."""
    c, a = consultation, analysis
    flag = "🚨 URGENCE — " if urgent(c) else ""
    f = a.fonctionnalites or {}
    pos = a.positionnement_kutsh or {}
    feats = "".join(
        [
            _feat_line("GNAU front office", f.get("gnau_front_office")),
            _feat_line("SIG / cartographie", f.get("sig_cartographie")),
            _feat_line("Aide à la décision (consultations)", f.get("aide_decision_consultations")),
            _feat_line("IA / extraction", f.get("ia_extraction")),
            _feat_line("Reprise de données", f.get("reprise_donnees")),
            _feat_line("Hébergement", f.get("hebergement")),
        ]
    )
    return (
        f"<div><strong>{flag}{c.buyer or 'Acheteur inconnu'}</strong> — {c.title}<br>"
        f"Réf. {c.ref or c.id} · clôture {c.closing_date or '—'} · nature {c.market or '—'}<br>"
        f"<a href=\"{c.url}\">Voir la consultation</a></div>"
        f"<p><strong>Nature du logiciel (niveau {a.niveau or '?'}/3)</strong> : "
        f"{a.niveau_label}.<br><em>{a.niveau_justification}</em></p>"
        f"<p><strong>Fonctionnalités clés</strong></p><ul>{feats}</ul>"
        f"<p><strong>Positionnement Kutsh</strong><br>"
        f"Couvert : {pos.get('couvert', '—')}<br>"
        f"Manquant : {pos.get('manquant', '—')}<br>"
        f"Différenciation IA : {pos.get('differenciation_ia', '—')}</p>"
        f"<p><strong>Synthèse</strong> : {a.resume}<br>"
        f"<strong>Action suggérée</strong> : {a.action_suggeree}</p>"
    )


def render_digest_html(items: list[tuple[Consultation, Analysis]]) -> str:
    n = len(items)
    parts = [f"<h3>📋 Veille marchés publics — {n} nouveau(x) marché(s) pertinent(s)</h3>"]
    for c, a in items:
        parts.append(render_item_html(c, a))
        parts.append("<hr>")
    return "".join(parts)


class BasecampPublisher:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def post(self, items: list[tuple[Consultation, Analysis]]) -> str:
        """Publie le digest. Retourne la voie effectivement utilisée."""
        if not items:
            return "skip:empty"
        html = render_digest_html(items)
        # Voie 1 : Campfire (simple, sans token) — préférée.
        if self.cfg.basecamp_via_campfire:
            self._post_campfire(html)
            return "campfire"
        # Voie 2 : API Basecamp (message riche).
        if self.cfg.basecamp_via_api:
            self._post_message(items, html)
            return "api"
        return "skip:no-credentials"

    def _post_campfire(self, html: str) -> None:
        assert self.cfg.basecamp_chatbot_lines_url is not None  # garanti par basecamp_via_campfire
        body = json.dumps({"content": html}).encode()
        _http(
            self.cfg.basecamp_chatbot_lines_url,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            body=body,
            timeout=self.cfg.request_timeout,
        )

    def _api_base(self) -> str:
        return f"https://3.basecampapi.com/{self.cfg.basecamp_account_id}"

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.cfg.basecamp_access_token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }

    def _message_board_id(self) -> str:
        """Résout l'id du message board du projet via le dock."""
        url = f"{self._api_base()}/projects/{self.cfg.basecamp_project_id}.json"
        _, body = _http(url, method="GET", headers=self._auth_headers(), timeout=self.cfg.request_timeout)
        project = json.loads(body)
        for tool in project.get("dock", []):
            if tool.get("name") == "message_board":
                return str(tool["id"])
        raise RuntimeError("message_board introuvable dans le dock du projet")

    def _post_message(self, items: list[tuple[Consultation, Analysis]], html: str) -> None:
        board = self._message_board_id()
        first = items[0][0]
        subject = (
            f"Marchés publics — {len(items)} nouveau(x) "
            f"(dont {first.buyer or first.title[:40]})"
        )
        url = (
            f"{self._api_base()}/buckets/{self.cfg.basecamp_project_id}"
            f"/message_boards/{board}/messages.json"
        )
        body = json.dumps({"subject": subject, "content": html, "status": "active"}).encode()
        _http(url, method="POST", headers=self._auth_headers(), body=body, timeout=self.cfg.request_timeout)
