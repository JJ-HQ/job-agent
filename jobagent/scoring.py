"""Score CV / offre avec un modèle local (Ollama). Le CV ne quitte pas le réseau."""
import hashlib
import json
import re

import requests

from .errors import ScoreError

CV_MAX = 6000
DESC_MAX = 3000


def cv_hash(cv_text):
    return hashlib.sha256(cv_text.encode("utf-8")).hexdigest()[:16]


def build_prompt(cv_text, offer):
    return f"""Tu évalues l'adéquation entre un CV et une offre d'emploi.
Réponds UNIQUEMENT par un objet JSON, sans texte autour, avec exactement ces clés :
{{"score": <entier 0-100>, "pourquoi": "<2 phrases maximum>", "points_forts": ["..."], "manques": ["..."]}}

Barème : 0-30 hors sujet ou très éloigné ; 31-50 faible ; 51-70 correct, des écarts notables ;
71-85 bon ; 86-100 excellent. Base-toi uniquement sur le CV et l'offre, n'invente rien.
Si la description de l'offre est trop courte pour juger, note prudemment et dis-le dans « pourquoi ».

=== CV ===
{cv_text[:CV_MAX]}

=== OFFRE ===
Intitulé : {offer['title']}
Entreprise : {offer['company']}
Lieu : {offer['location'] or 'non précisé'}
Contrat : {offer['contract']}
Télétravail : {offer['remote']}
Description : {(offer['description'] or 'aucune')[:DESC_MAX]}
"""


def parse_score(text):
    """Extrait et valide le JSON du modèle. Lève ScoreError s'il est inexploitable."""
    candidate = (text or "").strip()
    try:
        data = json.loads(candidate)
    except ValueError:
        match = re.search(r"\{.*\}", candidate, re.S)
        if not match:
            raise ScoreError("réponse du modèle sans JSON") from None
        try:
            data = json.loads(match.group(0))
        except ValueError:
            raise ScoreError("JSON du modèle invalide") from None
    if not isinstance(data, dict):
        raise ScoreError("JSON du modèle inattendu")
    try:
        score = int(round(float(data["score"])))
    except (KeyError, TypeError, ValueError):
        raise ScoreError("score absent ou non numérique") from None
    if not 0 <= score <= 100:
        raise ScoreError(f"score hors limites : {score}")
    pourquoi = data.get("pourquoi")
    if not isinstance(pourquoi, str) or not pourquoi.strip():
        raise ScoreError("explication absente")

    def as_list(value):
        return [str(v) for v in value][:6] if isinstance(value, list) else []

    return {
        "score": score,
        "pourquoi": pourquoi.strip(),
        "points_forts": as_list(data.get("points_forts")),
        "manques": as_list(data.get("manques")),
    }


def ollama_chat(url, model, prompt, post=requests.post, timeout=240):
    try:
        resp = post(
            url.rstrip("/") + "/api/chat",
            json={
                "model": model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1},
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ScoreError(f"Ollama injoignable : {type(exc).__name__}") from None
    if resp.status_code != 200:
        raise ScoreError(f"Ollama : HTTP {resp.status_code}")
    try:
        return resp.json()["message"]["content"]
    except (ValueError, KeyError, TypeError):
        raise ScoreError("réponse Ollama inattendue") from None


def score_offer(offer, cv_text, scoring_cfg, chat=ollama_chat):
    """Un essai, puis un second si la réponse est un JSON invalide."""
    if not scoring_cfg.get("modele"):
        raise ScoreError("scoring.modele non renseigné dans config.yml")
    prompt = build_prompt(cv_text, offer)
    last = None
    for _ in range(2):
        raw = chat(scoring_cfg["ollama_url"], scoring_cfg["modele"], prompt)
        try:
            return parse_score(raw)
        except ScoreError as exc:
            last = exc
    raise last
