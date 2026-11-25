from datetime import datetime, timezone

from jobagent.filtre import dedupe, prefilter
from jobagent.models import Offer
from jobagent.sources import adzuna, jooble
from tests.helpers import base_cfg, fixture

NOW = datetime(2026, 11, 25, 7, 0, tzinfo=timezone.utc)


def offer(**kw):
    d = dict(source="adzuna", source_id="1", url="https://x.test/1?utm=a", title="Technicien support",
             company="ACME", location="Lens", published_at="2026-11-24T08:00:00Z")
    d.update(kw)
    return Offer(**d)


def test_dedupe_same_company_title_city_across_sources():
    offers = adzuna.parse(fixture("adzuna.json")) + jooble.parse(fixture("jooble.json"))
    out = dedupe(offers)
    # « Technicien Support N2 H/F » / « Exemple Informatique » / Lens : même offre sur Adzuna et Jooble ?
    # Les lieux diffèrent (« Lens, Pas-de-Calais » vs « Lens ») : volontairement NON fusionnées.
    assert len(out) == len(offers)


def test_dedupe_same_url_ignoring_tracking():
    a = offer(source_id="1", url="https://x.test/o/1?utm=a")
    b = offer(source_id="2", url="https://x.test/o/1?utm=zzz", title="Autre titre")
    assert len(dedupe([a, b])) == 1


def test_dedupe_same_triplet_with_accents_and_case():
    a = offer(source_id="1", url="https://x.test/1", company="Société Été", title="Technicien Support")
    b = offer(source_id="2", url="https://y.test/2", company="societe ete", title="technicien  support")
    assert len(dedupe([a, b])) == 1


def test_prefilter_age():
    old = offer(published_at="2026-10-01T00:00:00Z")
    unknown = offer(source_id="2", published_at=None, url="https://x.test/2", title="B")
    kept = prefilter([old, unknown], base_cfg()["recherche"], NOW)
    assert kept == [unknown]  # date inconnue : on garde


def test_prefilter_excluded_words_whole_word_only():
    r = base_cfg(mots_exclus=["stage"])["recherche"]
    bad = offer(title="Stage technicien", url="https://x.test/a")
    ok = offer(source_id="2", title="Technicien stagnation réseau", url="https://x.test/b")
    assert prefilter([bad, ok], r, NOW) == [ok]


def test_prefilter_contract_keeps_unknown():
    r = base_cfg(contrats="CDI")["recherche"]
    cdi = offer(contract="CDI", url="https://x.test/a")
    cdd = offer(source_id="2", contract="CDD", url="https://x.test/b", title="b")
    inconnu = offer(source_id="3", contract="inconnu", url="https://x.test/c", title="c")
    assert prefilter([cdi, cdd, inconnu], r, NOW) == [cdi, inconnu]


def test_prefilter_remote_modes():
    oui = offer(remote="oui", url="https://x.test/a")
    inc = offer(source_id="2", remote="inconnu", url="https://x.test/b", title="b")
    assert prefilter([oui, inc], base_cfg(teletravail="tous")["recherche"], NOW) == [oui, inc]
    assert prefilter([oui, inc], base_cfg(teletravail="oui")["recherche"], NOW) == [oui]
    assert prefilter([oui, inc], base_cfg(teletravail="non")["recherche"], NOW) == [inc]


def test_title_rules_exclude_and_require():
    from jobagent.filtre import title_ok
    r = base_cfg(titre_exclu=["commercial", "immobilier", "responsable"],
                 titre_requis=["technicien", "support", "informatique", "it"])["recherche"]
    assert title_ok("Technicien support informatique N2 H/F", r)
    assert title_ok("Techniciennes de proximité - support", r)           # début de mot
    assert not title_ok("Support commercial immobilier", r)               # exclu l'emporte
    assert not title_ok("Responsable support informatique", r)
    assert not title_ok("Agent d'accueil", r)                             # aucun mot requis
    assert not title_ok("Chargé de projet digital", r)                    # « it » = mot entier : pas dans « digital »
    assert title_ok("Technicien IT", r)


def test_title_rules_empty_means_no_filter():
    from jobagent.filtre import title_ok
    assert title_ok("N'importe quoi", base_cfg()["recherche"])


def test_prefilter_applies_title_rules():
    r = base_cfg(titre_exclu=["immobilier"])["recherche"]
    bad = offer(title="Conseiller support immobilier", url="https://x.test/a")
    ok = offer(source_id="2", title="Technicien support", url="https://x.test/b")
    assert prefilter([bad, ok], r, NOW) == [ok]
