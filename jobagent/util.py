import html
import re
import unicodedata
from datetime import datetime, timezone

# Variables qui contiennent des secrets : leurs valeurs ne doivent jamais apparaître
# dans un journal, un message d'erreur ou un message Telegram.
SECRET_NAMES = (
    "ADZUNA_APP_ID",
    "ADZUNA_APP_KEY",
    "JOOBLE_API_KEY",
    "FRANCE_TRAVAIL_CLIENT_ID",
    "FRANCE_TRAVAIL_CLIENT_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "HEALTHCHECK_URL",
)


def norm(text):
    """Minuscules, sans accents ni ponctuation, espaces réduits (pour comparer)."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def secrets_from(env):
    return [env[n] for n in SECRET_NAMES if env.get(n)]


def redact(text, secrets):
    """Remplace toute valeur secrète présente dans `text` par ***."""
    text = str(text)
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return text


def parse_dt(value):
    """Lit une date ISO (avec ou sans fraction/fuseau) ; None si illisible."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
