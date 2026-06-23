# kutsh-veille-marches

Veille automatisée des marchés publics pour Kutsh. Remplace l'ancienne routine
launchd (Mac + `claude --print` + `gstack browse` + CLI `basecamp`) par un
service **serveur-natif**, sans dépendance Claude/CLI, conçu pour tourner en
tâche planifiée **Coolify**.

Pipeline hebdomadaire :

1. **Scrape** `marches-publics.nukema.com` (consultations actives).
2. **Filtre** de pertinence sur le cœur de métier Kutsh (gestion/instruction des
   autorisations d'urbanisme : ADS/DAU/PC/DP/DIA, GNAU, dématérialisation).
3. **DCE** (best-effort) : récupère et extrait le texte du CCTP.
4. **Analyse** via OpenRouter : échelle 3 niveaux + fonctionnalités clés +
   positionnement concurrentiel Kutsh.
5. **Sorties** : digest **Basecamp** (projet Veille, ID 46486516) + **Signal
   `MARCHE_PUBLIC`** dans le CRM **Twenty**.
6. **État idempotent** (`seen_ids` / `posted_ids` / `last_run`) sur **S3** ou un
   volume local — un marché déjà posté n'est jamais reposté.

## Comment ça scrape nukema (important)

nukema est une SPA Atexo/local-trust, mais l'app Angular consomme une **API JSON
publique** que l'on appelle **directement en HTTP** (urllib, stdlib) — pas besoin
de piloter un navigateur pour la recherche ni le détail :

- `POST /core/v2/consultations/query` → liste des ids (requête Solr sur le terme) ;
- `POST /core/v2/consultations/query/<id>?merged=false` → détail complet
  (titre, acheteur, `closedBy`, `ref`, `description` riche, `attachments[]`…).

C'est nettement plus robuste qu'un scraping DOM. Playwright reste embarqué comme
**repli** (amorçage de session, tentative de téléchargement des DCE).

### Limite connue — téléchargement des DCE

Le lien `/attachments?uuid=…` de nukema renvoie le **shell de la SPA** (HTML), pas
le binaire : le téléchargement réel passe par la plateforme source (megalis,
marches-securises, AWS-achat…) qui exige généralement une **inscription/login**.
Le service tente le téléchargement (HTTP puis session Playwright) ; s'il n'obtient
pas de fichier exploitable (zip/docx/pdf), il **bascule sur le champ `description`**
de l'API nukema (~900–1800 caractères) comme matière d'analyse. **La veille reste
pleinement utile sans DCE** (scrape + filtre + analyse + post). Les PDF ne sont pas
extraits nativement (pas de dépendance lourde) ; les `.docx` le sont via `zipfile`.

## Lancer en local

```bash
uv venv -p 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"
playwright install chromium          # repli navigateur (optionnel pour le scrape API)

# Dry-run : scrape + filtre + analyse, sans rien poster ni écrire d'état
OPENROUTER_API_KEY=… python -m veille_marches --dry-run -v

# Run réel (nécessite les variables d'env, cf. .env.example)
python -m veille_marches
```

Tests (mockés, aucun réseau) :

```bash
pytest -q
ruff check src tests
```

## Variables d'environnement

| Variable | Requis | Rôle |
|---|---|---|
| `OPENROUTER_API_KEY` | oui | Clé OpenRouter (analyse LLM) |
| `VEILLE_MODEL` | non | Modèle (défaut `openai/gpt-4o-mini`) |
| `TWENTY_API_KEY` | oui* | Clé API Twenty (création des Signaux) |
| `TWENTY_BASE_URL` | non | Défaut `https://twenty.kutsh.fr` |
| `BASECAMP_CHATBOT_LINES_URL` | oui** | Campfire lines_url signée (voie simple) |
| `BASECAMP_ACCESS_TOKEN` / `BASECAMP_ACCOUNT_ID` | oui** | API Basecamp (voie message riche) |
| `BASECAMP_PROJECT_ID` | non | Défaut `46486516` (projet Veille) |
| `S3_BUCKET`, `S3_ENDPOINT`, `S3_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_STATE_KEY` | non*** | État sur S3 (`DECI_S3_*` acceptés en repli) |
| `STATE_FILE` | non*** | État sur fichier (défaut `/data/veille-marches-state.json`) |
| `VEILLE_TERMS` | non | Termes (séparés par `;`) |
| `VEILLE_MAX_RESULTS` | non | Résultats max/terme (défaut 30) |
| `VEILLE_DRY_RUN` | non | `true` = ne poste rien |

\* Sans `TWENTY_API_KEY`, l'étape Signal est sautée sans bloquer le reste.
\** Au moins une des deux voies Basecamp ; la voie Campfire est préférée si les deux sont présentes.
\*** Si `S3_BUCKET` + creds présents → S3 ; sinon fichier `STATE_FILE` (monter un volume Coolify sur `/data`).

### Basecamp — quelle voie choisir ?

- **Campfire (`BASECAMP_CHATBOT_LINES_URL`)** : recommandée. Aucun OAuth, juste un
  `POST {content: html}` sur une URL signée. Même mécanisme que `kutsh-crm`.
  Idéal pour un digest hebdo.
- **API (`BASECAMP_ACCESS_TOKEN` + `BASECAMP_ACCOUNT_ID`)** : poste un vrai
  *message* dans le message board du projet Veille (sujet + corps HTML). Plus
  riche, mais nécessite un token OAuth valide.

Le CLI `basecamp` (qui ne rend pas les tableaux markdown) n'est **pas** utilisé :
on poste du HTML via l'API HTTP, sans tableaux markdown.

## Déploiement Coolify

1. **Type de ressource** : « Dockerfile » (ce repo contient un `Dockerfile`).
2. **Variables d'environnement** : renseigner celles du tableau ci-dessus.
3. **Volume persistant** (si pas de S3) : monter un volume sur `/data`.
4. **Tâche planifiée (Scheduled Task)** Coolify :
   - **Commande** : `python -m veille_marches`
   - **Cadence (cron)** : `0 8 * * 1` → **chaque lundi à 8h00** (Europe/Paris)
   - C'est une exécution *one-shot* : le conteneur démarre, exécute la veille,
     puis s'arrête. Coolify le relance selon le cron.

Le conteneur n'embarque pas de scheduler interne : la planification est déléguée
à Coolify (une seule source de vérité).

## Architecture des modules (`src/veille_marches/`)

- `config.py` — configuration 12-factor depuis l'env.
- `scraper.py` — appels API nukema (HTTP direct), normalisation `Consultation`.
- `relevance.py` — pré-filtre heuristique (mots-clés métier / exclusions travaux).
- `dce.py` — téléchargement best-effort + extraction CCTP (docx/zip, stdlib).
- `analyzer.py` — analyse OpenRouter (3 niveaux + fonctionnalités + positionnement).
- `state.py` — état idempotent (S3 SigV4 stdlib **ou** fichier atomique).
- `basecamp.py` — publication digest (Campfire ou API), rendu HTML.
- `signals.py` — Signal `MARCHE_PUBLIC` dans Twenty (via `crm_client` partagé).
- `browser.py` — repli Playwright (session/cookies, fetch DCE).
- `pipeline.py` — orchestration idempotente.
- `__main__.py` — CLI / entrypoint.
