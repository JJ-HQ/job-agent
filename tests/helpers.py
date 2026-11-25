import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, data=None, status=200):
        self._data, self.status_code = data, status

    def json(self):
        if self._data is None:
            raise ValueError("pas de JSON")
        return self._data


def base_cfg(**recherche):
    r = {"intitules": ["Technicien Support N2"], "lieux": ["VilleTest"], "rayon_km": 50,
         "contrats": "tous", "teletravail": "tous", "anciennete_max_jours": 14, "mots_exclus": []}
    r.update(recherche)
    return {
        "recherche": r,
        "sources": {"adzuna": True, "jooble": True},
        "scoring": {"ollama_url": "http://ollama.test:11434", "modele": "test-model", "offres_max_par_jour": 40},
        "resume": {"meilleures_offres": 5, "score_minimum": 50},
    }
