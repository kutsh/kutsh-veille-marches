#!/usr/bin/env python3
"""scripts/run.py — point d'entrée alternatif (équivalent à `python -m veille_marches`).

Utile pour une commande Coolify explicite ou un lancement local sans installer
le paquet. Ajoute src/ au path puis délègue à veille_marches.__main__.main.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from veille_marches.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
