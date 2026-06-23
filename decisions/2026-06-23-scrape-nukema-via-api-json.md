## Decision: Scraper nukema via son API JSON interne (HTTP direct/urllib), pas via DOM Playwright

## Context: Étape 0 « make-or-break » du service de veille marchés publics. La spec
indiquait que nukema est une SPA Atexo/local-trust (JS) et suggérait Playwright +
extraction DOM. En inspectant le trafic réseau de la SPA (Playwright network
capture), j'ai découvert une API JSON publique non authentifiée :
`POST /core/v2/consultations/query` (liste d'ids, requête Solr) puis
`POST /core/v2/consultations/query/<id>?merged=false` (détail complet : titre,
acheteur, closedBy, ref, description riche, attachments). Ces appels fonctionnent
en `urllib` pur, sans navigateur ni cookies.

## Alternatives considered:
- (A) Piloter Playwright + parser le DOM rendu (suggestion initiale de la spec).
- (B) Appeler directement l'API JSON en HTTP (urllib stdlib). ← retenu
- (C) Hybride : Playwright pour amorcer une session puis appeler l'API.

## Reasoning: (B) est nettement plus robuste et léger : pas de fragilité aux
changements de CSS/markup, pas de timing de rendu, pas de chromium en RAM pour le
chemin nominal, données structurées propres (champs typés). L'API a renvoyé des
résultats réels et stables pour les 3 termes de la spec. Playwright est conservé
(module `browser.py`) uniquement en repli : amorçage de session si anti-bot un
jour, et tentative de téléchargement des DCE.

## Trade-offs accepted:
- L'API est interne/non documentée : elle peut changer sans préavis (forme de la
  requête Solr, chemins). Mitigation : le contrat est isolé dans `scraper.py` et
  couvert par des tests sur fixtures ; un repli Playwright existe.
- Le téléchargement des DCE reste non fiable sans login (le lien `/attachments`
  renvoie le shell SPA) → on bascule sur le champ `description` de l'API. La v1
  livre donc scrape + filtre + analyse (sur description ou docx accessible) +
  post, et documente la limite DCE.
