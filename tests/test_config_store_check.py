from types import SimpleNamespace

import pytest

from jobagent.check import run_checks
from jobagent.config import load_config, load_env
from jobagent.errors import ConfigError
from jobagent.models import Offer
from jobagent.store import Store
from tests.helpers import FakeResponse, base_cfg


def test_load_config_requires_intitules_and_lieux(tmp_path):
    p = tmp_path / "c.yml"
    p.write_text("recherche:\n  intitules: []\n  lieux: [Lens]\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)
    p.write_text("recherche:\n  intitules: [Technicien]\n  lieux: [Lens]\n  rayon_km: 50\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg["recherche"]["contrats"] == "tous" and cfg["sources"]["adzuna"] is True


def test_load_config_rejects_bad_values(tmp_path):
    p = tmp_path / "c.yml"
    p.write_text("recherche:\n  intitules: [a]\n  lieux: [b]\n  contrats: bizarre\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)


def test_load_env(tmp_path):
    p = tmp_path / ".env"
    p.write_text('# commentaire\nA=1\nB="deux"\n\nC = trois\n', encoding="utf-8")
    assert load_env(p) == {"A": "1", "B": "deux", "C": "trois"}
    assert load_env(tmp_path / "absent") == {}


def test_store_known_by_id_url_or_triplet():
    s = Store(":memory:")
    o = Offer("adzuna", "1", "https://x.test/o/1?a=b", "Technicien", "ACME", "Lens")
    s.add(o, "2026-11-25T07:00:00Z")
    assert s.is_known(o)
    assert s.is_known(Offer("jooble", "9", "https://x.test/o/1?z=y", "Autre", "Autre", "Ailleurs"))  # même URL
    assert s.is_known(Offer("jooble", "9", "https://z.test/9", "technicien", "acme", "LENS"))  # même triplet
    assert not s.is_known(Offer("jooble", "9", "https://z.test/9", "Autre", "ACME", "Lens"))


def test_store_statut():
    s = Store(":memory:")
    i = s.add(Offer("a", "1", "https://x.test/1", "T", "C", "L"), "2026-11-25T07:00:00Z")
    assert s.set_statut(i, "postulée") and s.get(i)["statut"] == "postulée"
    assert not s.set_statut(999, "vue")
    with pytest.raises(ValueError):
        s.set_statut(i, "nimporte")


def test_check_reports_ok_ko_without_secrets(tmp_path):
    cfg = base_cfg()
    cfg["sources"] = {"adzuna": True, "jooble": True}
    env = {"ADZUNA_APP_ID": "ID-SECRET-1", "ADZUNA_APP_KEY": "KEY-SECRET-2",
           "TELEGRAM_BOT_TOKEN": "TOKEN-SECRET-3", "TELEGRAM_CHAT_ID": "424242"}

    sources = {
        "adzuna": SimpleNamespace(NAME="adzuna", ENV=("ADZUNA_APP_ID", "ADZUNA_APP_KEY"),
                                  search=lambda *a, **k: []),
        "jooble": SimpleNamespace(NAME="jooble", ENV=("JOOBLE_API_KEY",), search=lambda *a, **k: []),
    }

    def fake_get(url, params=None, timeout=None):
        if "/api/tags" in url:
            return FakeResponse({"models": [{"name": "test-model:latest"}]})
        if "getMe" in url:
            return FakeResponse({"ok": True})
        return FakeResponse(status=404)

    results = {label: (ok, d) for label, ok, d in run_checks(cfg, env, tmp_path / "cv.txt", get=fake_get, sources=sources)}
    assert results["source adzuna"][0] is True
    assert results["source jooble"][0] is False and "JOOBLE_API_KEY" in results["source jooble"][1]
    assert results["Ollama"][0] is True and results["Telegram"][0] is True
    assert results["CV (data/cv.txt)"][0] is False
    assert "SECRET" not in str(results)
