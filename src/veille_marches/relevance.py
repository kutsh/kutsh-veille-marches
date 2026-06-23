"""relevance.py — filtre de pertinence métier (cf. spec).

Pertinent = cœur de métier Kutsh (logiciels/SaaS de gestion des autorisations
d'urbanisme : DAU/ADS/PC/DP/DIA, GNAU, instruction, dématérialisation urbanisme).

Exclus = travaux, maîtrise d'œuvre construction, AMO généraliste où « urbanisme »
n'est qu'incident.

Le filtre est volontairement conservateur en pré-tri (heuristique mots-clés sur
titre+description), puis l'analyse LLM (analyzer.py) tranche les cas limites.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .scraper import Consultation

# Signaux positifs : logiciel/service d'instruction & dématérialisation urbanisme.
POSITIVE = [
    "autorisation d'urbanisme",
    "autorisations d'urbanisme",
    "droit des sols",
    "instruction",
    "gnau",
    "guichet numérique",
    "dématérialisation",
    "permis de construire",
    "déclaration préalable",
    "logiciel d'urbanisme",
    "logiciel urbanisme",
    "logiciel d'instruction",
    "gestion des dossiers d'urbanisme",
    "dossiers d'urbanisme",
    "ads ",
    " dau",
    "saas",
    "sve",  # saisine par voie électronique
    "déclaration d'intention d'aliéner",
    "dia",
    "déclaration préalable",
    "numérisation des dossiers d'urbanisme",
]

# Signaux d'exclusion forts : marchés de travaux / MOE / construction physique.
NEGATIVE = [
    "maîtrise d'œuvre",
    "maitrise d'oeuvre",
    "conception réalisation",
    "conception-réalisation",
    "construction d'",
    "construction de",
    "logements",
    "rénovation",
    "réhabilitation",
    "contrôle technique",
    "paysagiste",
    "voirie",
    "réseaux",
    "bâtiment",
    "vrd",
    "espaces verts",
    "démolition",
    "assainissement",
]

# Le marché de NATURE « travaux » est rarement dans le périmètre Kutsh (logiciel).
EXCLUDED_MARKETS = {"WORKS"}


@dataclass
class RelevanceVerdict:
    relevant: bool
    score: int
    reasons: list[str]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def score(consultation: Consultation) -> RelevanceVerdict:
    hay = _norm(f"{consultation.title} {consultation.description}")
    reasons: list[str] = []
    pos = [kw for kw in POSITIVE if kw in hay]
    neg = [kw for kw in NEGATIVE if kw in hay]

    s = len(pos) * 2 - len(neg)
    if pos:
        reasons.append("mots-clés métier: " + ", ".join(sorted(set(pos))[:6]))
    if neg:
        reasons.append("signaux travaux/MOE: " + ", ".join(sorted(set(neg))[:6]))

    if consultation.market in EXCLUDED_MARKETS:
        s -= 2
        reasons.append(f"nature marché={consultation.market}")

    # Pertinent si on a au moins un signal métier net ET un score positif.
    relevant = bool(pos) and s >= 1
    return RelevanceVerdict(relevant=relevant, score=s, reasons=reasons)


def filter_relevant(consultations: list[Consultation]) -> list[tuple[Consultation, RelevanceVerdict]]:
    out = []
    for c in consultations:
        v = score(c)
        if v.relevant:
            out.append((c, v))
    return out
