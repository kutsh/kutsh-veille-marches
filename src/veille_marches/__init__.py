"""kutsh-veille-marches — veille des marchés publics urbanisme pour Kutsh.

Service serveur-natif (Coolify) qui remplace l'ancienne routine launchd :
scrape nukema → filtre pertinence → analyse DCE (OpenRouter) → poste sur
Basecamp + crée un Signal Twenty, en idempotent (état S3/volume).
"""
__version__ = "0.1.0"
