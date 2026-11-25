# job-agent — spécification (phase 1)

Statut : **à relire et valider avant tout code.** Rien n'est construit tant que ce document n'est pas validé.

## 1. Objectif

Chaque matin, sans intervention :
1. chercher des offres d'emploi correspondant aux critères de `config.yml` ;
2. supprimer les doublons et les offres déjà vues ;
3. les comparer au CV et leur donner un score de 0 à 100 avec une explication courte ;
4. envoyer sur Telegram un résumé des meilleures offres nouvelles.

Remplace l'appli JobTracker (Next.js + PocketBase) par quelque chose de petit, lisible et réparable.

## 2. Principes

- **Un seul programme Python, une base SQLite, un cron.** Pas de serveur web en phase 1.
- **Local d'abord** : le score est calculé par Ollama (LXC batcomputer). Le CV ne sort jamais du réseau.
- **Flux sortants autorisés uniquement** : API d'offres (Adzuna, Jooble, France Travail), Telegram, healthchecks.io. Rien d'autre.
- **Pas de lecture de HTML** de sites d'emploi (fragile, contraire à leurs conditions d'utilisation). API officielles seulement.
- **Aucun secret, aucun CV, aucune donnée personnelle dans le dépôt.** Secrets dans `.env`, CV dans `data/cv.txt`, base dans `data/jobs.db` : tous exclus par `.gitignore`.
- **Une panne d'une source ne bloque pas les autres** ; une panne d'Ollama ne bloque pas le résumé (offres envoyées sans score, signalées comme telles).
- Dépendances minimales : `requests`, `PyYAML`, `pytest`. SQLite et planification sont fournis par la bibliothèque standard et cron.

## 3. Chaîne de traitement

```
cron 07:00  ->  python -m jobagent run
  1. charger config.yml + .env
  2. pour chaque source activée : rechercher (par intitulé x lieu), normaliser en Offer
  3. dédoublonner : même URL, ou même (entreprise, intitulé, ville) normalisés
  4. ignorer les offres déjà en base
  5. pré-filtre sans IA : mots exclus, ancienneté maximale, durée/contrat si demandé
  6. scorer chaque offre retenue (Ollama) ; plafond de N offres par jour
  7. enregistrer en base (statut "nouvelle")
  8. envoyer le résumé Telegram (top K par score)
  9. ping healthchecks.io (succès ou échec)
```

### Offer (modèle commun)
`source`, `source_id`, `url`, `title`, `company`, `location`, `remote` (oui / non / inconnu), `contract` (CDI, CDD, freelance, stage, alternance, inconnu), `salary_text`, `published_at`, `description`, `first_seen_at`.

### Sources
| Source | Accès | Remarque |
|---|---|---|
| Adzuna | API officielle (clés gratuites) | pays `fr` |
| Jooble | API officielle (clé gratuite) | |
| France Travail | API officielle « Offres d'emploi » (OAuth2, identifiants gratuits) | à ajouter en second |

Chaque source = un module qui expose `search(query, location, radius_km) -> list[Offer]`. Ajouter une source ne change rien d'autre.

### Score
- Entrée : texte du CV (`data/cv.txt`) + offre (titre, entreprise, lieu, description tronquée).
- Sortie attendue du modèle : JSON `{"score": 0-100, "pourquoi": "2 phrases", "points_forts": [...], "manques": [...]}`.
- JSON invalide : une nouvelle tentative, puis offre enregistrée avec `score = NULL` et `erreur`.
- Un score n'est recalculé que si le CV change (empreinte du CV enregistrée avec le score).
- Le modèle est un réglage (`ollama.model`). Avant de figer le choix : comparer 2 ou 3 modèles sur 20 offres réelles (phase 1b).

### Résumé Telegram
Un message : date, nombre d'offres nouvelles, puis les K meilleures (par défaut 5) : score, intitulé, entreprise, ville, télétravail, contrat, lien, une phrase d'explication. Si rien de nouveau : message d'une ligne. Si une source est en panne : une ligne le dit.

## 4. Réglages (`config.yml`, versionné, sans secret)

Voir `config.example.yml`. Valeurs actuelles : tous types de contrat, télétravail indifférent. **Intitulés recherchés, lieu et rayon : à compléter par le propriétaire.**

## 5. Base de données (`data/jobs.db`)

- `offers` : un enregistrement par offre (champs de `Offer` + `score`, `pourquoi`, `cv_hash`, `statut`, `erreur`).
- `runs` : un enregistrement par exécution (début, fin, sources OK/KO, nombre d'offres trouvées, nouvelles, scorées, erreurs).
- Statuts d'une offre : `nouvelle`, `vue`, `intéressante`, `écartée`, `postulée`. Phase 1 : seul `nouvelle` est posé automatiquement ; les autres se changent à la main (commande `python -m jobagent statut <id> <statut>`).

## 6. Arborescence prévue

```
jobagent/          code (config, models, sources/, dedupe, filtre, scoring, store, notify, run)
tests/             pytest + fixtures (réponses d'API enregistrées, sans donnée personnelle)
data/              cv.txt, jobs.db   (ignoré par git)
config.example.yml  réglages d'exemple
.env.example        noms des variables, sans valeur
```

## 7. Tests

- Tests automatiques sur réponses d'API **enregistrées** : normalisation par source, dédoublonnage, pré-filtre, analyse du JSON du score (valide, invalide, absent), formatage du message Telegram.
- Appels réseau simulés : aucun test n'appelle une vraie API ni Ollama.
- Commande `python -m jobagent check` (à lancer chez le propriétaire) : vérifie la présence des variables (sans les afficher), l'accès à chaque source, à Ollama et à Telegram, et affiche OK/KO par élément.

## 8. Liste de contrôle du propriétaire (validation de fin de phase 1)

1. `check` affiche OK partout.
2. Un lancement à la main trouve des offres de chaque source activée.
3. Trois offres au hasard : lien valide, texte cohérent, pas de doublon.
4. Trois scores relus : le « pourquoi » est cohérent avec le CV.
5. Le résumé Telegram arrive, lisible, avec les bons liens.
6. Un second lancement immédiat ne renvoie aucune offre déjà vue.
7. Ollama éteint : le résumé arrive quand même, signalé « sans score ».
8. Le cron du matin s'exécute et healthchecks.io reçoit le signal.

## 9. Hors périmètre de la phase 1

Classement des mails, page web, candidature automatique, scraping de pages, application mobile. Prévus plus tard, un à la fois (phase 2 : import des 176 candidatures de JobTracker ; phase 3 : mails en lecture seule ; phase 4 : petite page de consultation).

## 10. Déploiement (chez le propriétaire, après validation)

Nouveau conteneur LXC (sans Docker), utilisateur dédié, `python3 -m venv`, `.env` en droits 600, cron quotidien, règle réseau limitée aux sorties listées au point 2. Détail fourni au moment du déploiement, pas avant.
