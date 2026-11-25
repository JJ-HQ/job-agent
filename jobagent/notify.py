import requests

TELEGRAM_MAX = 4000  # limite Telegram : 4096 caractères


def select_for_summary(rows, k, score_min):
    """Meilleures offres scorées (>= seuil), puis offres sans score pour compléter."""
    scored = sorted(
        (r for r in rows if r["score"] is not None and r["score"] >= score_min),
        key=lambda r: -r["score"],
    )[:k]
    unscored = [r for r in rows if r["score"] is None][: max(0, k - len(scored))]
    return scored + unscored


def _line(index, r):
    bits = [r["title"], r["company"]]
    if r["location"]:
        bits[-1] += f" ({r['location']})"
    extra = []
    if r["remote"] == "oui":
        extra.append("télétravail")
    if r["contract"] != "inconnu":
        extra.append(r["contract"])
    if r["salary_text"]:
        extra.append(r["salary_text"])
    head = f"{r['score']}/100" if r["score"] is not None else "sans score"
    text = f"{index}. {head} · {' — '.join(bits)}"
    if extra:
        text += " · " + " · ".join(extra)
    if r["pourquoi"]:
        text += f"\n   {r['pourquoi']}"
    return text + f"\n   {r['url']}"


def format_summary(date_text, new_rows, k, score_min, errors, notes):
    chosen = select_for_summary(new_rows, k, score_min)
    lines = [f"Offres du {date_text} : {len(new_rows)} nouvelle(s)."]
    for note in notes:
        lines.append(f"⚠ {note}")
    for source, message in errors.items():
        lines.append(f"⚠ {source} : {message}")
    if not new_rows:
        return "\n".join(lines)
    if not chosen:
        lines.append(f"Aucune offre au-dessus de {score_min}/100 aujourd'hui.")
        return "\n".join(lines)
    blocks = [_line(i, r) for i, r in enumerate(chosen, 1)]
    text = "\n".join(lines) + "\n\n" + "\n\n".join(blocks)
    while len(text) > TELEGRAM_MAX and len(blocks) > 1:
        blocks.pop()
        text = "\n".join(lines) + "\n\n" + "\n\n".join(blocks)
    return text[:TELEGRAM_MAX]


def send_telegram(token, chat_id, text, post=requests.post):
    try:
        resp = post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Telegram injoignable : {type(exc).__name__}") from None
    if resp.status_code != 200:
        detail = ""
        try:
            detail = str(resp.json().get("description", ""))[:120]
        except (ValueError, AttributeError):
            pass
        raise RuntimeError(f"Telegram : HTTP {resp.status_code}" + (f" ({detail})" if detail else ""))


def ping_healthcheck(url, ok, get=requests.get):
    """Signal healthchecks.io : succès, ou /fail en cas d'échec. Ne lève jamais d'exception."""
    try:
        get(url if ok else url.rstrip("/") + "/fail", timeout=15)
    except requests.RequestException:
        pass
