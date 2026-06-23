"""pipeline.py — orchestration de la veille (idempotente).

Enchaînement :
  1. Charger l'état (seen_ids / posted_ids).
  2. Scraper nukema pour chaque terme → consultations dédupliquées.
  3. Filtrer la pertinence (heuristique mots-clés).
  4. Ne garder que les NOUVEAUX (pas dans posted_ids).
  5. Pour chacun : récupérer le DCE (best-effort) + analyser via OpenRouter.
     L'analyse LLM peut re-déclasser un faux positif (pertinent=false).
  6. Sorties : digest Basecamp + Signal Twenty.
  7. Mettre à jour et persister l'état (posted_ids permanent).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .analyzer import Analysis, analyze
from .basecamp import BasecampPublisher
from .config import Config
from .dce import get_dce_text
from .relevance import filter_relevant
from .scraper import Consultation, NukemaScraper
from .signals import SignalPublisher
from .state import State, make_store

log = logging.getLogger("veille_marches")


@dataclass
class RunResult:
    seen: int = 0
    relevant: int = 0
    new: int = 0
    analyzed: list[tuple[Consultation, Analysis]] = field(default_factory=list)
    posted_via: str = "skip"
    signals_created: int = 0
    dry_run: bool = False


def run(
    cfg: Config,
    *,
    scraper: NukemaScraper | None = None,
    basecamp: BasecampPublisher | None = None,
    signals: SignalPublisher | None = None,
    dce_fetcher=None,
    analyze_caller=None,
) -> RunResult:
    scraper = scraper or NukemaScraper(timeout=cfg.request_timeout)
    basecamp = basecamp or BasecampPublisher(cfg)
    signals = signals or SignalPublisher(cfg)
    store = make_store(cfg)
    state: State = store.load()
    result = RunResult(dry_run=cfg.dry_run)

    # 2-3) scrape + filtre de pertinence
    consultations = scraper.search_terms(cfg.terms, size=cfg.max_results_per_term)
    result.seen = len(consultations)
    for c in consultations:
        state.mark_seen(c.stable_id)
    relevant = filter_relevant(consultations)
    result.relevant = len(relevant)
    log.info("scrape: %d consultations, %d pertinentes", result.seen, result.relevant)

    # 4) nouveaux uniquement
    new_items = [(c, v) for c, v in relevant if state.is_new(c.stable_id)]
    result.new = len(new_items)
    log.info("nouveaux (hors posted_ids): %d", result.new)

    # 5) DCE + analyse LLM
    analyzed: list[tuple[Consultation, Analysis]] = []
    for c, _verdict in new_items:
        dce = get_dce_text(c, fetcher=dce_fetcher, timeout=cfg.request_timeout)
        if not cfg.openrouter_api_key and analyze_caller is None:
            log.warning("OPENROUTER_API_KEY manquant — analyse sautée pour %s", c.stable_id)
            continue
        try:
            a = analyze(
                c, dce.text, dce.source,
                api_key=cfg.openrouter_api_key or "",
                model=cfg.openrouter_model,
                timeout=cfg.request_timeout,
                caller=analyze_caller,
            )
        except Exception as e:  # une analyse KO ne casse pas le lot
            log.warning("analyse KO pour %s: %s", c.stable_id, e)
            continue
        if not a.pertinent:
            log.info("re-déclassé par le LLM (non pertinent): %s", c.stable_id)
            continue
        analyzed.append((c, a))
    result.analyzed = analyzed
    log.info("analysés et pertinents: %d", len(analyzed))

    if cfg.dry_run:
        log.info("DRY-RUN — aucune sortie ni écriture d'état")
        return result

    # 6) sorties
    if analyzed:
        result.posted_via = basecamp.post(analyzed)
        log.info("Basecamp: %s", result.posted_via)
        for c, a in analyzed:
            try:
                if signals.create(c, a) is not None:
                    result.signals_created += 1
            except Exception as e:
                log.warning("Signal Twenty KO pour %s: %s", c.stable_id, e)
            state.mark_posted(c.stable_id)

    # 7) persistance
    state.finalize()
    store.save(state)
    log.info("état sauvegardé (posted_ids=%d, seen_ids=%d)", len(state.posted_ids), len(state.seen_ids))
    return result
