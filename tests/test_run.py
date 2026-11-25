from datetime import datetime, timezone

import requests

from jobagent.errors import ScoreError, SourceError
from jobagent.run import run
from jobagent.sources import adzuna, jooble
from jobagent.store import Store
from tests.helpers import base_cfg, fixture

NOW = datetime(2026, 11, 25, 7, 0, tzinfo=timezone.utc)
ENV = {"ADZUNA_APP_ID": "ID-ADZUNA-1", "ADZUNA_APP_KEY": "KEY-ADZUNA-2", "JOOBLE_API_KEY": "KEY-JOOBLE-3"}
CV = "CV de test " * 40


class FakeSource:
    def __init__(self, name, env, offers=None, error=None):
        self.NAME, self.ENV, self._offers, self._error = name, env, offers or [], error
        self.calls = 0

    def search(self, query, location, radius_km, max_days, env):
        self.calls += 1
        if self._error:
            raise self._error
        return list(self._offers)


def fakes(**kw):
    return {
        "adzuna": FakeSource("adzuna", adzuna.ENV, adzuna.parse(fixture("adzuna.json")), kw.get("adz_err")),
        "jooble": FakeSource("jooble", jooble.ENV, jooble.parse(fixture("jooble.json")), kw.get("joo_err")),
    }


def score_ok(row, cv):
    return {"score": 80 if "N2" in row["title"] else 40, "pourquoi": "Test.", "points_forts": [], "manques": []}


def go(store, sources, score_fn=score_ok, cv=CV, env=ENV, cfg=None, now=NOW):
    sent, pings = [], []
    result = run(cfg or base_cfg(), env, store, sources=sources, score_fn=score_fn, send_fn=sent.append,
                 ping_fn=pings.append, cv_text=cv, now=now, sleep=lambda s: None)
    return result, sent, pings


def test_full_run_then_second_run_finds_nothing_new():
    store = Store(":memory:")
    result, sent, pings = go(store, fakes())
    assert result["ok"] and result["new"] == 4 and result["scored"] == 4 and pings == [True]
    assert len(sent) == 1 and "4 nouvelle(s)" in sent[0] and "80/100" in sent[0]
    result2, sent2, _ = go(store, fakes())  # critère 6 de la liste de contrôle
    assert result2["new"] == 0 and "0 nouvelle" in sent2[0]


def test_one_source_down_does_not_block_the_other():
    store = Store(":memory:")
    result, sent, pings = go(store, fakes(joo_err=SourceError("Jooble : HTTP 500")))
    assert result["ok"] and result["new"] == 2 and pings == [True]
    assert "jooble : Jooble : HTTP 500" in sent[0]
    assert store.sources_status()["jooble"]["last_error"] == "Jooble : HTTP 500"
    assert store.sources_status()["adzuna"]["last_count"] == 2


def test_all_sources_down_pings_failure():
    store = Store(":memory:")
    result, sent, pings = go(store, fakes(adz_err=SourceError("x"), joo_err=SourceError("y")))
    assert not result["ok"] and pings == [False] and len(sent) == 1


def test_missing_key_is_reported_and_recorded():
    store = Store(":memory:")
    env = {k: v for k, v in ENV.items() if k != "JOOBLE_API_KEY"}
    result, sent, _ = go(store, fakes(), env=env)
    assert "clé manquante : JOOBLE_API_KEY" in sent[0]
    assert "clé manquante" in store.sources_status()["jooble"]["last_error"]


def test_ollama_down_still_sends_summary_unscored_and_stops_early():
    store = Store(":memory:")
    calls = []

    def down(row, cv):
        calls.append(row["id"])
        raise ScoreError("Ollama injoignable : ConnectionError")

    result, sent, pings = go(store, fakes(), score_fn=down)  # critère 7
    assert result["scored"] == 0 and len(calls) == 3  # arrêt après 3 échecs d'affilée
    assert "sans score" in sent[0] and "Scoring interrompu" in sent[0] and pings == [True]


def test_unscored_offers_are_retried_next_day():
    store = Store(":memory:")
    go(store, fakes(), score_fn=lambda r, c: (_ for _ in ()).throw(ScoreError("x")))
    result, _, _ = go(store, fakes(), now=datetime(2026, 11, 26, 7, 0, tzinfo=timezone.utc))
    assert result["new"] == 0 and result["scored"] == 4


def test_cv_change_triggers_rescoring_only_then():
    store = Store(":memory:")
    go(store, fakes())
    assert go(store, fakes())[0]["scored"] == 0
    assert go(store, fakes(), cv=CV + " nouvelle expérience")[0]["scored"] == 4


def test_daily_cap_on_scoring():
    store = Store(":memory:")
    cfg = base_cfg()
    cfg["scoring"]["offres_max_par_jour"] = 2
    assert go(store, fakes(), cfg=cfg)[0]["scored"] == 2


def test_no_cv_sends_unscored_with_warning():
    store = Store(":memory:")
    result, sent, _ = go(store, fakes(), cv="")
    assert result["scored"] == 0 and "CV absent" in sent[0]


def test_secret_never_appears_in_summary_or_db():
    store = Store(":memory:")
    leak = SourceError("échec sur https://jooble.org/api/KEY-JOOBLE-3 et KEY-ADZUNA-2")
    result, sent, _ = go(store, fakes(joo_err=leak, adz_err=leak))
    blob = sent[0] + str(store.sources_status()) + str(result)
    for secret in ("KEY-JOOBLE-3", "KEY-ADZUNA-2", "ID-ADZUNA-1"):
        assert secret not in blob


def test_send_failure_is_reported_and_run_not_ok():
    store = Store(":memory:")

    def broken(text):
        raise RuntimeError("Telegram : HTTP 400")

    result = run(base_cfg(), ENV, store, sources=fakes(), score_fn=score_ok, send_fn=broken,
                 cv_text=CV, now=NOW, sleep=lambda s: None)
    assert not result["ok"] and any("non envoyé" in n for n in result["notes"])
