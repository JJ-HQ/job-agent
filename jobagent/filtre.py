from datetime import timedelta

from .models import dedupe_key, url_key
from .util import norm, parse_dt


def dedupe(offers):
    """Supprime les doublons du lot (même URL, ou même entreprise/intitulé/ville). Garde la 1re."""
    seen_urls, seen_keys, out = set(), set(), []
    for offer in offers:
        uk, dk = url_key(offer.url), dedupe_key(offer)
        if uk in seen_urls or dk in seen_keys:
            continue
        seen_urls.add(uk)
        seen_keys.add(dk)
        out.append(offer)
    return out


def _word_in(word, text):
    """Mot court (<= 3 lettres) : mot entier. Sinon : début de mot (technicien -> techniciens, technicienne)."""
    return f" {word} " in text if len(word) <= 3 else f" {word}" in text


def title_ok(title, recherche):
    """Règles sur le titre : aucun mot de `titre_exclu`, et au moins un mot de `titre_requis` (si défini)."""
    t = " " + norm(title) + " "
    excluded = [norm(w) for w in recherche.get("titre_exclu", []) if norm(w)]
    if any(_word_in(w, t) for w in excluded):
        return False
    required = [norm(w) for w in recherche.get("titre_requis", []) if norm(w)]
    return not required or any(_word_in(w, t) for w in required)


def prefilter(offers, recherche, now):
    """Tri sans IA : ancienneté, mots exclus, contrat, télétravail."""
    excluded = [norm(w) for w in recherche["mots_exclus"] if norm(w)]
    limit = now - timedelta(days=recherche["anciennete_max_jours"])
    kept = []
    for o in offers:
        published = parse_dt(o.published_at)
        if published and published < limit:
            continue
        if not title_ok(o.title, recherche):
            continue
        blob = " " + norm(f"{o.title} {o.description or ''}") + " "
        if any(f" {w} " in blob for w in excluded):
            continue
        if recherche["contrats"] != "tous" and o.contract not in ("inconnu", recherche["contrats"]):
            continue
        if recherche["teletravail"] == "oui" and o.remote != "oui":
            continue
        if recherche["teletravail"] == "non" and o.remote == "oui":
            continue
        kept.append(o)
    return kept
