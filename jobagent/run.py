import logging
import time
from datetime import timedelta

from . import notify, scoring
from .filtre import dedupe, prefilter
from .sources import SOURCES
from .util import iso, redact, secrets_from, utcnow

log = logging.getLogger("jobagent")
CONSECUTIVE_FAILURES_STOP = 3  # Ollama éteint : on n'attend pas 40 délais d'attente


def collect(cfg, env, store, sources, secrets, now, sleep):
    """Interroge chaque source activée. Retourne (offres, erreurs par source)."""
    r = cfg["recherche"]
    found, errors = [], {}
    for name, enabled in cfg["sources"].items():
        if not enabled or name not in sources:
            continue
        module = sources[name]
        missing = [v for v in module.ENV if not env.get(v)]
        if missing:
            errors[name] = "clé manquante : " + ", ".join(missing)
            store.source_error(name, errors[name], iso(now))
            continue
        count, successes, first_error = 0, 0, None
        for query in r["intitules"]:
            for place in r["lieux"]:
                try:
                    offers = module.search(query, place, r["rayon_km"], r["anciennete_max_jours"], env)
                    found.extend(offers)
                    count += len(offers)
                    successes += 1
                except Exception as exc:  # une requête en échec ne bloque pas les autres
                    first_error = first_error or redact(exc, secrets)
                    log.warning("%s : %s", name, redact(exc, secrets))
                sleep(1)
        if successes:
            store.source_ok(name, count, iso(now))
            if first_error:
                errors[name] = "partiel : " + first_error
        else:
            errors[name] = first_error or "aucune requête exécutée"
            store.source_error(name, errors[name], iso(now))
    return found, errors


def run(cfg, env, store, *, sources=None, score_fn=None, send_fn=None, ping_fn=None,
        cv_text=None, now=None, sleep=time.sleep):
    now = now or utcnow()
    started = iso(now)
    sources = SOURCES if sources is None else sources
    secrets = secrets_from(env)
    notes = []

    # 1-5 : recherche, doublons, pré-filtre, offres déjà vues
    found, errors = collect(cfg, env, store, sources, secrets, now, sleep)
    candidates = prefilter(dedupe(found), cfg["recherche"], now)
    new_offers = [o for o in candidates if not store.is_known(o)]
    new_ids = [store.add(o, started) for o in new_offers]

    # 6 : score (offres nouvelles du jour + offres récentes jamais scorées), plafonné
    scored = 0
    if not cv_text:
        notes.append("CV absent (data/cv.txt) : offres envoyées sans score")
    elif score_fn is None:
        notes.append("Scoring non configuré : offres envoyées sans score")
    else:
        h = scoring.cv_hash(cv_text)
        since = iso(now - timedelta(days=cfg["recherche"]["anciennete_max_jours"]))
        failures = 0
        for row in store.to_score(h, cfg["scoring"]["offres_max_par_jour"], since):
            try:
                store.set_score(row["id"], score_fn(row, cv_text), h)
                scored += 1
                failures = 0
            except Exception as exc:
                store.set_error(row["id"], redact(exc, secrets))
                failures += 1
                if failures >= CONSECUTIVE_FAILURES_STOP:
                    notes.append(f"Scoring interrompu : {redact(exc, secrets)}")
                    break

    # 7-8 : résumé
    rows = store.get_many(new_ids)
    text = notify.format_summary(
        now.strftime("%d/%m/%Y"), rows,
        cfg["resume"]["meilleures_offres"], cfg["resume"]["score_minimum"], errors, notes,
    )
    sent = True
    try:
        if send_fn is None:
            raise RuntimeError("Telegram non configuré")
        send_fn(text)
    except Exception as exc:
        sent = False
        notes.append(f"Résumé non envoyé : {redact(exc, secrets)}")
        log.error("Résumé non envoyé : %s", redact(exc, secrets))

    ok = sent and any(
        s in cfg["sources"] and cfg["sources"][s] and (s not in errors or errors[s].startswith("partiel"))
        for s in sources
    )
    store.record_run(started, iso(utcnow()), ok, len(found), len(new_ids), scored,
                     {"erreurs": errors, "notes": notes})
    if ping_fn:
        ping_fn(ok)
    return {"ok": ok, "found": len(found), "new": len(new_ids), "scored": scored,
            "errors": errors, "notes": notes, "summary": text}
