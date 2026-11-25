import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .util import norm

REMOTE_RE = re.compile(r"t[ée]l[ée]travail|remote|[àa] distance", re.I)
CONTRACT_PATTERNS = (
    ("alternance", re.compile(r"alternance|apprentissage|contrat pro", re.I)),
    ("stage", re.compile(r"\bstage\b|stagiaire|internship", re.I)),
    ("freelance", re.compile(r"freelance|ind[ée]pendant|auto-?entrepreneur", re.I)),
    ("intérim", re.compile(r"int[ée]rim", re.I)),
    ("CDD", re.compile(r"\bCDD\b|dur[ée]e d[ée]termin[ée]e|fixed[- ]term", re.I)),
    ("CDI", re.compile(r"\bCDI\b|dur[ée]e ind[ée]termin[ée]e|permanent", re.I)),
)


@dataclass
class Offer:
    source: str
    source_id: str
    url: str
    title: str
    company: str = "Entreprise inconnue"
    location: str | None = None
    remote: str = "inconnu"        # oui | inconnu (jamais « non » : on ne peut pas le déduire)
    contract: str = "inconnu"      # CDI | CDD | intérim | freelance | stage | alternance | inconnu
    salary_text: str | None = None
    published_at: str | None = None
    description: str | None = None


def detect_remote(*texts):
    return "oui" if any(REMOTE_RE.search(t or "") for t in texts) else "inconnu"


def detect_contract(*texts):
    blob = " ".join(t or "" for t in texts)
    for label, pattern in CONTRACT_PATTERNS:
        if pattern.search(blob):
            return label
    return "inconnu"


def dedupe_key(offer):
    """Même entreprise + même intitulé + même ville = même offre, quelle que soit la source."""
    return "|".join(norm(x) for x in (offer.company, offer.title, offer.location))


def url_key(url):
    parts = urlsplit((url or "").strip())
    return f"{parts.netloc}{parts.path}".lower().rstrip("/")
