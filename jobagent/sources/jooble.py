"""Jooble : API officielle (https://jooble.org/api/about), clé gratuite.

La clé fait partie de l'URL : ne jamais afficher une URL ou une exception brute.
"""
import hashlib

import requests

from ..errors import SourceError
from ..models import Offer, detect_contract, detect_remote
from ..util import strip_html

NAME = "jooble"
ENV = ("JOOBLE_API_KEY",)
BASE = "https://jooble.org/api/"


def parse(data):
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise SourceError("réponse Jooble inattendue (pas de liste « jobs »)")
    offers = []
    for item in data["jobs"]:
        link, title = item.get("link"), strip_html(item.get("title"))
        if not link or not title:
            continue
        description = strip_html(item.get("snippet"))
        source_id = str(item.get("id") or hashlib.sha1(link.encode()).hexdigest()[:16])
        offers.append(
            Offer(
                source=NAME,
                source_id=source_id,
                url=link,
                title=title,
                company=strip_html(item.get("company")) or "Entreprise inconnue",
                location=strip_html(item.get("location")) or None,
                remote=detect_remote(title, description),
                contract=detect_contract(item.get("type"), title, description),
                salary_text=strip_html(item.get("salary")) or None,
                published_at=item.get("updated"),
                description=description,
            )
        )
    return offers


def search(query, location, radius_km, max_days, env, post=requests.post):
    payload = {"keywords": query, "location": location, "radius": str(radius_km), "page": "1"}
    try:
        resp = post(BASE + env["JOOBLE_API_KEY"], json=payload, timeout=30)
    except requests.RequestException as exc:
        raise SourceError(f"Jooble injoignable : {type(exc).__name__}") from None
    if resp.status_code != 200:
        raise SourceError(f"Jooble : HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        raise SourceError("Jooble : réponse non JSON") from None
    return parse(data)
