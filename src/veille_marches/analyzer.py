"""analyzer.py — analyse d'une consultation via OpenRouter (JSON structuré).

Reproduit l'analyse de la spec :
  A) Nature du logiciel sur une échelle de 3 niveaux :
       1 = boîte aux lettres (réception/transmission)
       2 = gestion de dossiers avec workflow d'instruction
       3 = aide à l'instruction avec connaissance réglementaire intégrée
  B) Fonctionnalités clés : GNAU front office, SIG/cartographie, aide à la
     décision, IA/extraction, reprise de données, hébergement.
  C) Positionnement concurrentiel Kutsh : couvert / manquant / différenciation IA.

Pattern HTTP : cf. kutsh-crm/scripts/qualify_leads.py (OpenRouter + response_format
json_object, urllib stdlib).
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field

from .scraper import Consultation

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM = (
    "Tu es analyste avant-vente pour Kutsh, éditeur d'un logiciel SaaS d'aide à "
    "l'instruction des autorisations d'urbanisme (ADS/DAU), avec IA d'extraction "
    "et connaissance réglementaire (PLU). Tu analyses des consultations de marchés "
    "publics pour qualifier l'opportunité. Réponds STRICTEMENT en JSON."
)

PROMPT = """Analyse cette consultation de marché public.

Titre : {title}
Acheteur : {buyer}
Nature : {market}
Procédure : {procedure}
Date de clôture : {closing}

Texte technique disponible (source={source}) :
\"\"\"{text}\"\"\"

Produis un JSON STRICT :
{{
  "pertinent": <bool : le marché porte-t-il bien sur un logiciel/service de gestion
                ou d'instruction des autorisations d'urbanisme (et non des travaux,
                de la MOE construction, de l'AMO généraliste) ?>,
  "niveau": <1|2|3 : 1=boîte aux lettres, 2=workflow d'instruction,
             3=aide à l'instruction avec connaissance réglementaire>,
  "niveau_justification": <str, 1 phrase citant les indices du texte>,
  "fonctionnalites": {{
     "gnau_front_office": <bool|null>,
     "sig_cartographie": <bool|null>,
     "aide_decision_consultations": <bool|null>,
     "ia_extraction": <"OBLIGATOIRE"|"SOUHAITABLE"|"NON"|null>,
     "reprise_donnees": <bool|null>,
     "hebergement": <"SAAS"|"ON_PREMISE"|"INDIFFERENT"|null>
  }},
  "positionnement_kutsh": {{
     "couvert": <str : ce que Kutsh couvre déjà>,
     "manquant": <str : ce qui manque / nécessite une roadmap>,
     "differenciation_ia": <str : niveau de différenciation possible sur IA/aide à l'instruction>
  }},
  "resume": <str : 2-3 phrases de synthèse pour l'équipe>,
  "action_suggeree": <str : action concrète (analyser le DCE, go/no-go, contacter l'acheteur) + échéance>
}}"""


@dataclass
class Analysis:
    pertinent: bool
    niveau: int | None
    niveau_justification: str
    fonctionnalites: dict
    positionnement_kutsh: dict
    resume: str
    action_suggeree: str
    raw: dict = field(default_factory=dict)

    NIVEAU_LABELS = {
        1: "Boîte aux lettres (réception/transmission)",
        2: "Gestion de dossiers avec workflow d'instruction",
        3: "Aide à l'instruction avec connaissance réglementaire intégrée",
    }

    @property
    def niveau_label(self) -> str:
        return self.NIVEAU_LABELS.get(self.niveau or 0, "Indéterminé")


def _call_openrouter(api_key: str, model: str, messages: list[dict], timeout: int = 90) -> str:
    body = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": 900,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://kutsh.fr",
            "X-Title": "kutsh-veille-marches",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        data = json.loads(r.read())
    return (data["choices"][0]["message"]["content"] or "").strip()


def _parse_json(content: str) -> dict:
    content = re.sub(r"^```(?:json)?|```$", "", content.strip()).strip()
    return json.loads(content)


def analyze(
    consultation: Consultation,
    text: str,
    source: str,
    api_key: str,
    model: str = "openai/gpt-4o-mini",
    timeout: int = 90,
    caller=None,
) -> Analysis:
    """Analyse une consultation. `caller` injectable pour les tests (renvoie le JSON brut)."""
    prompt = PROMPT.format(
        title=consultation.title,
        buyer=consultation.buyer or "—",
        market=consultation.market or "—",
        procedure=consultation.procedure or "—",
        closing=consultation.closing_date or "—",
        source=source,
        text=(text or "")[:8000],
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    if caller is not None:
        content = caller(messages)
    else:
        content = _call_openrouter(api_key, model, messages, timeout=timeout)
    out = _parse_json(content)
    niveau = out.get("niveau")
    if isinstance(niveau, str) and niveau.isdigit():
        niveau = int(niveau)
    if niveau not in (1, 2, 3):
        niveau = None
    return Analysis(
        pertinent=bool(out.get("pertinent", True)),
        niveau=niveau,
        niveau_justification=out.get("niveau_justification") or "",
        fonctionnalites=out.get("fonctionnalites") or {},
        positionnement_kutsh=out.get("positionnement_kutsh") or {},
        resume=out.get("resume") or "",
        action_suggeree=out.get("action_suggeree") or "",
        raw=out,
    )
