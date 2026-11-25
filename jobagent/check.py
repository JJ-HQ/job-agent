"""Vérification de l'installation. N'affiche jamais une valeur secrète."""
from pathlib import Path

import requests

from .sources import SOURCES
from .util import redact, secrets_from


def run_checks(cfg, env, cv_path, get=requests.get, sources=None):
    """Retourne une liste de (libellé, ok, détail)."""
    sources = SOURCES if sources is None else sources
    secrets = secrets_from(env)
    results = []

    def add(label, ok, detail=""):
        results.append((label, ok, redact(detail, secrets)))

    r = cfg["recherche"]
    add("réglages (config.yml)", True, f"{len(r['intitules'])} intitulé(s), {len(r['lieux'])} lieu(x), {r['rayon_km']} km")

    cv = Path(cv_path)
    add("CV (data/cv.txt)", cv.exists() and cv.stat().st_size > 200,
        "présent" if cv.exists() else "absent : les offres seront envoyées sans score")

    for name, enabled in cfg["sources"].items():
        if not enabled or name not in sources:
            continue
        module = sources[name]
        missing = [v for v in module.ENV if not env.get(v)]
        if missing:
            add(f"source {name}", False, "clé manquante : " + ", ".join(missing))
            continue
        try:
            offers = module.search(r["intitules"][0], r["lieux"][0], r["rayon_km"], r["anciennete_max_jours"], env)
            add(f"source {name}", True, f"{len(offers)} offre(s) pour « {r['intitules'][0]} »")
        except Exception as exc:
            add(f"source {name}", False, str(exc))

    model = cfg["scoring"]["modele"]
    try:
        resp = get(cfg["scoring"]["ollama_url"].rstrip("/") + "/api/tags", timeout=15)
        names = [m.get("name", "") for m in resp.json().get("models", [])] if resp.status_code == 200 else []
        if resp.status_code != 200:
            add("Ollama", False, f"HTTP {resp.status_code}")
        elif not model:
            add("Ollama", False, "joignable, mais scoring.modele est vide : modèles installés : " + ", ".join(names))
        elif not any(n == model or n.startswith(model + ":") for n in names):
            add("Ollama", False, f"joignable, mais modèle « {model} » absent")
        else:
            add("Ollama", True, f"modèle « {model} » disponible")
    except Exception as exc:
        add("Ollama", False, f"injoignable : {type(exc).__name__}")

    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token or not env.get("TELEGRAM_CHAT_ID"):
        add("Telegram", False, "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant")
    else:
        try:
            resp = get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
            add("Telegram", resp.status_code == 200, "bot joignable" if resp.status_code == 200 else f"HTTP {resp.status_code}")
        except Exception as exc:
            add("Telegram", False, f"injoignable : {type(exc).__name__}")

    add("healthchecks.io", bool(env.get("HEALTHCHECK_URL")),
        "URL renseignée" if env.get("HEALTHCHECK_URL") else "HEALTHCHECK_URL absent (facultatif)")
    return results
