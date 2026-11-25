# job-agent

Recherche d'offres d'emploi quotidienne, score par rapport au CV (Ollama local), résumé Telegram.
Spécification : `SPEC.md`. Règle du dépôt : jamais de clé, de CV, de base de données ni de `config.yml` personnel dans Git (voir `.gitignore`).

## Installation (sur la machine qui fait tourner l'agent)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.yml config.yml      # puis compléter lieux et modèle
cp .env.example .env && chmod 600 .env  # puis renseigner les clés (jamais dans Git)
mkdir -p data && cp /chemin/vers/cv.txt data/cv.txt   # CV en texte brut
```

## Commandes

| Commande | Rôle |
|---|---|
| `python -m jobagent check` | vérifie réglages, CV, chaque source, Ollama, Telegram (OK/KO, aucun secret affiché) |
| `python -m jobagent run` | recherche, score, résumé Telegram (c'est ce que lance le cron) |
| `python -m jobagent sources` | pour chaque source : activée ? clé présente (oui/NON) ? dernier succès, dernière erreur |
| `python -m jobagent liste -n 20` | dernières offres enregistrées, avec score et statut |
| `python -m jobagent statut ID postulée` | change le statut d'une offre (nouvelle, vue, intéressante, écartée, postulée) |

## Ajouter un site qui utilise une clé d'API

1. Créer le module dans `jobagent/sources/` (modèle : `adzuna.py`) avec `NAME`, `ENV` (noms des variables) et `search(...)`.
2. L'ajouter dans `jobagent/sources/__init__.py` et dans `config.example.yml`.
3. Ajouter les noms de variables dans `.env.example` et dans `SECRET_NAMES` de `jobagent/util.py`.
4. Mettre la valeur dans `.env`, puis `python -m jobagent sources` confirme la présence de la clé et garde la trace des succès et erreurs.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Les tests utilisent des réponses d'API fictives, aucun accès réseau. Les premiers essais réels (vraies clés, Ollama, Telegram) se font avec `check`.
