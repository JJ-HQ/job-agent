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


def test_nettoyer_discards_offers_outside_title_rules(tmp_path, monkeypatch, capsys):
    from jobagent.__main__ import main
    cfg = tmp_path / "c.yml"
    cfg.write_text('recherche:\n  intitules: [a]\n  lieux: [b]\n  titre_exclu: ["immobilier"]\n', encoding="utf-8")
    monkeypatch.setenv("JOBAGENT_DATA", str(tmp_path / "data"))
    s = Store(tmp_path / "data" / "jobs.db")
    bad = s.add(Offer("a", "1", "https://x.test/1", "Commercial immobilier", "C", "L"), "2026-11-25T07:00:00Z")
    good = s.add(Offer("a", "2", "https://x.test/2", "Technicien support", "C", "L"), "2026-11-25T07:00:00Z")
    s.close()
    assert main(["--config", str(cfg), "--env", str(tmp_path / ".env"), "nettoyer"]) == 0
    assert "1 offre(s) écartée(s)" in capsys.readouterr().out
    s = Store(tmp_path / "data" / "jobs.db")
    assert s.get(bad)["statut"] == "écartée" and s.get(good)["statut"] == "nouvelle"


def test_since_ignores_discarded_offers():
    s = Store(":memory:")
    a = s.add(Offer("a", "1", "https://x.test/1", "T1", "C1", "L"), "2026-11-25T07:00:00Z")
    b = s.add(Offer("a", "2", "https://x.test/2", "T2", "C2", "L"), "2026-11-25T07:00:00Z")
    s.set_statut(a, "écartée")
    assert [r["id"] for r in s.since("2026-11-24T00:00:00Z")] == [b]
