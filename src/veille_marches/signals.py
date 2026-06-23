"""signals.py — création des Signaux MARCHE_PUBLIC dans Twenty.

Réutilise le client partagé `crm_client.TwentyClient` (cf. spec : NE PAS dupliquer
un client Twenty). On s'appuie sur `create_signal(name, type_signal,
action_suggeree, statut, **fields)`.

Non bloquant : si TWENTY_API_KEY est absent ou le CRM indisponible, on log et on
continue (la veille Basecamp reste prioritaire).
"""
from __future__ import annotations

from .analyzer import Analysis
from .config import Config
from .scraper import Consultation

try:  # le client partagé est packagé ; import paresseux pour les tests
    from crm_client import TwentyClient  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - dépend de l'install
    TwentyClient = None  # type: ignore[assignment]


def signal_name(consultation: Consultation) -> str:
    buyer = consultation.buyer or "Acheteur inconnu"
    short = consultation.title[:60]
    return f"{buyer} — {short}"


class SignalPublisher:
    def __init__(self, cfg: Config, client=None):
        self.cfg = cfg
        self._client = client

    @property
    def available(self) -> bool:
        return bool(self.cfg.twenty_api_key) and (self._client is not None or TwentyClient is not None)

    def _get_client(self):
        if self._client is not None:
            return self._client
        if TwentyClient is None:
            raise RuntimeError("crm_client indisponible (kutsh-crm non installé)")
        self._client = TwentyClient(
            api_key=self.cfg.twenty_api_key, base_url=self.cfg.twenty_base_url
        )
        return self._client

    def create(self, consultation: Consultation, analysis: Analysis) -> dict | None:
        """Crée un Signal MARCHE_PUBLIC. Retourne le record ou None si indisponible."""
        if not self.available:
            return None
        client = self._get_client()
        return client.create_signal(
            name=signal_name(consultation),
            type_signal="MARCHE_PUBLIC",
            statut="NOUVEAU",
            action_suggeree=analysis.action_suggeree
            or f"Analyser le DCE / décider go-no-go (clôture {consultation.closing_date or '—'})",
        )
