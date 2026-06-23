# syntax=docker/dockerfile:1
# Image de la veille marchés publics Kutsh — conçue pour une tâche planifiée Coolify.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# uv pour une install rapide et reproductible
RUN pip install --no-cache-dir uv

# Dépendances d'abord (cache de couche)
COPY pyproject.toml README.md ./
COPY src ./src

# Installe le paquet + ses dépendances (dont kutsh-crm via git et playwright).
# git nécessaire pour la dépendance "kutsh-crm @ git+https://…".
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && uv pip install --system --no-cache . \
    && apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Chromium + ses dépendances système (le scrape API n'en a pas besoin, mais le
# repli navigateur / tentative de téléchargement DCE l'utilise).
RUN playwright install --with-deps chromium

# Volume pour l'état si l'on n'utilise pas S3 (monter un volume Coolify sur /data).
VOLUME ["/data"]

# Exécution unique (la planification est gérée par Coolify, pas par un cron interne).
ENTRYPOINT ["python", "-m", "veille_marches"]
