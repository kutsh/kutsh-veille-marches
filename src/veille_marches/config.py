"""config.py — configuration centralisée depuis l'environnement.

Toutes les options du service de veille sont pilotées par variables
d'environnement (12-factor) pour s'exécuter sans modification en conteneur
Coolify. Aucune valeur secrète n'est codée en dur.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# Termes de recherche (cf. spec métier). Surclassables via VEILLE_TERMS
# (séparés par des « ; »).
DEFAULT_TERMS = [
    "autorisations d'urbanisme",
    "droit des sols",
    "logiciel gestion dossiers",
]

# Projet Basecamp « Veille »
BASECAMP_PROJECT_ID = "46486516"


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [t.strip() for t in raw.split(";") if t.strip()]


@dataclass
class Config:
    # --- recherche ---
    terms: list[str] = field(default_factory=lambda: _env_list("VEILLE_TERMS", DEFAULT_TERMS))
    max_results_per_term: int = int(os.environ.get("VEILLE_MAX_RESULTS", "30"))

    # --- OpenRouter (analyse) ---
    openrouter_api_key: str | None = os.environ.get("OPENROUTER_API_KEY")
    openrouter_model: str = os.environ.get("VEILLE_MODEL", "openai/gpt-4o-mini")

    # --- Twenty (CRM) ---
    twenty_api_key: str | None = os.environ.get("TWENTY_API_KEY")
    twenty_base_url: str | None = os.environ.get("TWENTY_BASE_URL")

    # --- Basecamp ---
    # Voie 1 (simple, recommandée) : Campfire via lines_url signée (POST {content})
    basecamp_chatbot_lines_url: str | None = os.environ.get("BASECAMP_CHATBOT_LINES_URL")
    # Voie 2 (riche) : API Basecamp avec token OAuth
    basecamp_access_token: str | None = os.environ.get("BASECAMP_ACCESS_TOKEN")
    basecamp_account_id: str | None = os.environ.get("BASECAMP_ACCOUNT_ID")
    basecamp_project_id: str = os.environ.get("BASECAMP_PROJECT_ID", BASECAMP_PROJECT_ID)

    # --- État (S3 ou fichier sur volume) ---
    # Si S3_BUCKET est présent → état sur S3 ; sinon fichier local STATE_FILE.
    s3_bucket: str | None = os.environ.get("S3_BUCKET")
    s3_endpoint: str | None = os.environ.get("S3_ENDPOINT")
    s3_region: str = os.environ.get("S3_REGION", "eu-central")
    s3_access_key: str | None = os.environ.get("S3_ACCESS_KEY") or os.environ.get("DECI_S3_ACCESS_KEY")
    s3_secret_key: str | None = os.environ.get("S3_SECRET_KEY") or os.environ.get("DECI_S3_SECRET_KEY")
    s3_key: str = os.environ.get("S3_STATE_KEY", "veille-marches/state.json")
    state_file: str = os.environ.get("STATE_FILE", "/data/veille-marches-state.json")

    # --- divers ---
    dry_run: bool = os.environ.get("VEILLE_DRY_RUN", "").lower() in ("1", "true", "yes")
    request_timeout: int = int(os.environ.get("VEILLE_TIMEOUT", "60"))

    @property
    def use_s3(self) -> bool:
        return bool(self.s3_bucket and self.s3_access_key and self.s3_secret_key)

    @property
    def basecamp_via_api(self) -> bool:
        return bool(self.basecamp_access_token and self.basecamp_account_id)

    @property
    def basecamp_via_campfire(self) -> bool:
        return bool(self.basecamp_chatbot_lines_url)
