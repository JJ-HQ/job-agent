import copy
from pathlib import Path

import yaml

from .errors import ConfigError

DEFAULTS = {
    "recherche": {
        "intitules": [],
        "lieux": [],
        "rayon_km": 30,
        "contrats": "tous",
        "teletravail": "tous",
        "anciennete_max_jours": 14,
        "mots_exclus": [],
    },
    "sources": {"adzuna": True, "jooble": False, "france_travail": False},
    "scoring": {
        "ollama_url": "http://localhost:11434",
        "modele": "",
        "offres_max_par_jour": 40,
        "profil_recherche": "",
    },
    "resume": {"meilleures_offres": 5, "score_minimum": 50},
}

CONTRATS = {"tous", "CDI", "CDD", "intérim", "freelance", "stage", "alternance"}
TELETRAVAIL = {"tous", "oui", "non"}


def _merge(base, extra):
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_env(path):
    """Lit un fichier .env (CLE=valeur). Ne modifie pas l'environnement et n'affiche rien."""
    env = {}
    p = Path(path)
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[key.strip()] = value
    return env


def load_config(path):
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Fichier de réglages introuvable : {p} (copier config.example.yml)")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yml illisible : {exc}") from exc
    cfg = _merge(copy.deepcopy(DEFAULTS), raw)
    validate(cfg)
    return cfg


def validate(cfg):
    r = cfg["recherche"]
    if not r["intitules"]:
        raise ConfigError("recherche.intitules est vide")
    if not r["lieux"]:
        raise ConfigError("recherche.lieux est vide")
    if not isinstance(r["rayon_km"], int) or r["rayon_km"] <= 0:
        raise ConfigError("recherche.rayon_km doit être un entier positif")
    if r["contrats"] not in CONTRATS:
        raise ConfigError(f"recherche.contrats doit être parmi {sorted(CONTRATS)}")
    if r["teletravail"] not in TELETRAVAIL:
        raise ConfigError(f"recherche.teletravail doit être parmi {sorted(TELETRAVAIL)}")
    if cfg["scoring"]["offres_max_par_jour"] < 1:
        raise ConfigError("scoring.offres_max_par_jour doit être >= 1")
