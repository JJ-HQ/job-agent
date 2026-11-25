import pytest

from jobagent import scoring
from jobagent.errors import ScoreError

CFG = {"ollama_url": "http://ollama.test", "modele": "m", "offres_max_par_jour": 10}
ROW = {"title": "Technicien N2", "company": "ACME", "location": "Lens", "contract": "CDI",
       "remote": "oui", "description": "Support."}
GOOD = '{"score": 82, "pourquoi": "Bon profil.", "points_forts": ["AD"], "manques": ["ITIL"]}'


def test_parse_valid():
    r = scoring.parse_score(GOOD)
    assert r["score"] == 82 and r["points_forts"] == ["AD"]


def test_parse_json_with_text_around():
    assert scoring.parse_score("Voici : " + GOOD + " fin")["score"] == 82


@pytest.mark.parametrize("raw", [
    "", "pas de json", "[1,2]", '{"score": "abc", "pourquoi": "x"}',
    '{"score": 140, "pourquoi": "x"}', '{"score": 50}', '{"score": 50, "pourquoi": "  "}',
])
def test_parse_invalid(raw):
    with pytest.raises(ScoreError):
        scoring.parse_score(raw)


def test_score_offer_retries_once_on_bad_json():
    answers = iter(["n'importe quoi", GOOD])
    assert scoring.score_offer(ROW, "cv", CFG, chat=lambda *a: next(answers))["score"] == 82


def test_score_offer_gives_up_after_two_bad_answers():
    with pytest.raises(ScoreError):
        scoring.score_offer(ROW, "cv", CFG, chat=lambda *a: "rien")


def test_score_offer_requires_model():
    with pytest.raises(ScoreError):
        scoring.score_offer(ROW, "cv", {**CFG, "modele": ""}, chat=lambda *a: GOOD)


def test_prompt_truncates_long_inputs():
    p = scoring.build_prompt("c" * 20000, {**ROW, "description": "d" * 20000})
    assert len(p) < scoring.CV_MAX + scoring.DESC_MAX + 1500


def test_cv_hash_changes_with_cv():
    assert scoring.cv_hash("a") != scoring.cv_hash("b") and scoring.cv_hash("a") == scoring.cv_hash("a")


def test_prompt_includes_profile_and_asks_short_answer():
    p = scoring.build_prompt("cv", ROW, "technicien support N1/N2, pas de management")
    assert "technicien support N1/N2" in p and "25 mots" in p and "points_forts" not in p
    assert "Poste recherché" not in scoring.build_prompt("cv", ROW)


def test_score_without_lists_is_valid():
    r = scoring.parse_score('{"score": 70, "pourquoi": "ok"}')
    assert r["points_forts"] == [] and r["manques"] == []


def test_hash_changes_with_profile():
    assert scoring.cv_hash("cv", "a") != scoring.cv_hash("cv", "b")
    assert scoring.cv_hash("cv", "") == scoring.cv_hash("cv")
