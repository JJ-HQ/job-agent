import pytest

from jobagent.errors import SourceError
from jobagent.sources import adzuna, jooble
from tests.helpers import FakeResponse, fixture


def test_adzuna_parse():
    offers = adzuna.parse(fixture("adzuna.json"))
    assert len(offers) == 2  # l'offre sans lien est ignorée
    a, b = offers
    assert a.title == "Technicien Support N2 H/F"  # HTML retiré
    assert (a.company, a.location) == ("Exemple Informatique", "Lens, Pas-de-Calais")
    assert a.contract == "CDI" and a.remote == "oui"
    assert a.salary_text == "28000-32000 €/an"
    assert b.contract == "CDD"
    assert b.salary_text is None  # salaire estimé par le site : non repris


def test_adzuna_bad_payload():
    with pytest.raises(SourceError):
        adzuna.parse({"erreur": "x"})


def test_adzuna_search_http_error_has_no_secret():
    env = {"ADZUNA_APP_ID": "id-secret-123", "ADZUNA_APP_KEY": "key-secret-456"}
    with pytest.raises(SourceError) as exc:
        adzuna.search("q", "ville", 50, 14, env, get=lambda *a, **k: FakeResponse(status=401))
    assert "401" in str(exc.value) and "secret" not in str(exc.value)


def test_adzuna_search_passes_radius_and_age():
    seen = {}

    def fake_get(url, params, timeout):
        seen.update(params)
        return FakeResponse(fixture("adzuna.json"))

    adzuna.search("technicien", "Lens", 50, 14, {"ADZUNA_APP_ID": "i", "ADZUNA_APP_KEY": "k"}, get=fake_get)
    assert seen["distance"] == 50 and seen["max_days_old"] == 14 and seen["where"] == "Lens"


def test_jooble_parse():
    offers = jooble.parse(fixture("jooble.json"))
    assert len(offers) == 2
    a, b = offers
    assert a.source_id == "998877"
    assert "&amp;" not in a.description and "<b>" not in a.description
    assert a.remote == "oui" and a.contract == "alternance"
    assert b.salary_text == "30 000 €"


def test_jooble_search_key_in_url_not_in_error():
    def boom(url, json, timeout):
        return FakeResponse(status=403)

    with pytest.raises(SourceError) as exc:
        jooble.search("q", "ville", 50, 14, {"JOOBLE_API_KEY": "cle-jooble-secrete"}, post=boom)
    assert "cle-jooble-secrete" not in str(exc.value)
