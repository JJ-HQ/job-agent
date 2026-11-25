from jobagent import notify
from jobagent.util import norm, redact


def row(i, score, **kw):
    d = dict(id=i, title=f"Technicien {i}", company="ACME", location="Lens", remote="oui", contract="CDI",
             salary_text=None, pourquoi="Bon profil.", url=f"https://x.test/{i}", score=score)
    d.update(kw)
    return d


def test_select_orders_by_score_then_fills_with_unscored():
    rows = [row(1, 60), row(2, 90), row(3, 20), row(4, None), row(5, None)]
    chosen = notify.select_for_summary(rows, 3, 50)
    assert [r["id"] for r in chosen] == [2, 1, 4]  # 20 < seuil exclu ; sans score en complément


def test_summary_mentions_unscored_and_errors():
    text = notify.format_summary("25/11/2026", [row(1, None, pourquoi=None)], 5, 50,
                                 {"jooble": "HTTP 500"}, ["CV absent"])
    assert "sans score" in text and "jooble : HTTP 500" in text and "CV absent" in text
    assert "https://x.test/1" in text


def test_summary_no_new_offer_is_one_short_message():
    text = notify.format_summary("25/11/2026", [], 5, 50, {}, [])
    assert "0 nouvelle" in text and "\n" not in text


def test_summary_stays_under_telegram_limit():
    rows = [row(i, 90, pourquoi="x" * 600) for i in range(30)]
    assert len(notify.format_summary("d", rows, 30, 0, {}, [])) <= notify.TELEGRAM_MAX


def test_healthcheck_never_raises():
    import requests

    def boom(url, timeout):
        raise requests.ConnectionError("x")

    notify.ping_healthcheck("https://hc.test/abc", True, get=boom)


def test_healthcheck_fail_url():
    seen = []
    notify.ping_healthcheck("https://hc.test/abc/", False, get=lambda u, timeout: seen.append(u))
    assert seen == ["https://hc.test/abc/fail"]


def test_redact_and_norm():
    assert redact("url https://j.test/api/CLE-SECRETE-9 fin", ["CLE-SECRETE-9"]) == "url https://j.test/api/*** fin"
    assert redact("abc", ["ab"]) == "abc"  # secrets trop courts ignorés
    assert norm("  Société   Été ! ") == "societe ete"
