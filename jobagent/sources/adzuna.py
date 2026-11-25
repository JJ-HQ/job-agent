"""Adzuna : API officielle (https://developer.adzuna.com), clés gratuites."""
import requests

from ..errors import SourceError
from ..models import Offer, detect_contract, detect_remote
from ..util import strip_html

NAME = "adzuna"
ENV = ("ADZUNA_APP_ID", "ADZUNA_APP_KEY")
URL = "https://api.adzuna.com/v1/api/jobs/fr/search/1"
CONTRACT_MAP = {"permanent": "CDI", "contract": "CDD"}


def _salary(item):
    lo, hi = item.get("salary_min"), item.get("salary_max")
    if not lo and not hi:
        return None
    if str(item.get("salary_is_predicted")) == "1":
        return None  # estimation du site, pas un salaire annoncé
    if lo and hi and int(lo) != int(hi):
        return f"{int(lo)}-{int(hi)} €/an"
    return f"{int(lo or hi)} €/an"


def parse(data):
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise SourceError("réponse Adzuna inattendue (pas de liste « results »)")
    offers = []
    for item in data["results"]:
        if not item.get("redirect_url") or not item.get("title"):
            continue
        title = strip_html(item["title"])
        description = strip_html(item.get("description"))
        contract = CONTRACT_MAP.get(item.get("contract_type") or "") or detect_contract(title, description)
        offers.append(
            Offer(
                source=NAME,
                source_id=str(item.get("id") or item["redirect_url"]),
                url=item["redirect_url"],
                title=title,
                company=(item.get("company") or {}).get("display_name") or "Entreprise inconnue",
                location=(item.get("location") or {}).get("display_name"),
                remote=detect_remote(title, description),
                contract=contract,
                salary_text=_salary(item),
                published_at=item.get("created"),
                description=description,
            )
        )
    return offers


def search(query, location, radius_km, max_days, env, get=requests.get):
    params = {
        "app_id": env["ADZUNA_APP_ID"],
        "app_key": env["ADZUNA_APP_KEY"],
        "what": query,
        "where": location,
        "distance": radius_km,
        "max_days_old": max_days,
        "results_per_page": 50,
        "sort_by": "date",
        "content-type": "application/json",
    }
    try:
        resp = get(URL, params=params, timeout=30)
    except requests.RequestException as exc:
        raise SourceError(f"Adzuna injoignable : {type(exc).__name__}") from None
    if resp.status_code != 200:
        raise SourceError(f"Adzuna : HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        raise SourceError("Adzuna : réponse non JSON") from None
    return parse(data)
