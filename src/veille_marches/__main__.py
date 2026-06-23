"""Entrypoint : `python -m veille_marches`.

Options :
  --dry-run        ne poste rien, n'écrit pas l'état (override VEILLE_DRY_RUN)
  --term TERM      remplace les termes de recherche (répétable)
  --max N          nombre max de résultats par terme
  -v / --verbose   logs DEBUG
"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import Config
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="veille-marches", description="Veille marchés publics Kutsh")
    ap.add_argument("--dry-run", action="store_true", help="ne poste rien, n'écrit pas l'état")
    ap.add_argument("--term", action="append", dest="terms", help="terme de recherche (répétable)")
    ap.add_argument("--max", type=int, default=None, help="résultats max par terme")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = Config()
    if args.dry_run:
        cfg.dry_run = True
    if args.terms:
        cfg.terms = args.terms
    if args.max is not None:
        cfg.max_results_per_term = args.max

    log = logging.getLogger("veille_marches")
    log.info(
        "démarrage (termes=%s, dry_run=%s, état=%s, basecamp=%s)",
        cfg.terms,
        cfg.dry_run,
        "S3" if cfg.use_s3 else cfg.state_file,
        "api" if cfg.basecamp_via_api else ("campfire" if cfg.basecamp_via_campfire else "aucun"),
    )
    result = run(cfg)
    log.info(
        "terminé: vus=%d pertinents=%d nouveaux=%d analysés=%d basecamp=%s signaux=%d",
        result.seen,
        result.relevant,
        result.new,
        len(result.analyzed),
        result.posted_via,
        result.signals_created,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
