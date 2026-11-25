import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .models import dedupe_key, url_key

STATUTS = ("nouvelle", "vue", "intéressante", "écartée", "postulée")

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL, source_id TEXT NOT NULL,
    url TEXT NOT NULL, url_key TEXT NOT NULL, dedupe_key TEXT NOT NULL,
    title TEXT NOT NULL, company TEXT, location TEXT,
    remote TEXT, contract TEXT, salary_text TEXT, published_at TEXT, description TEXT,
    first_seen_at TEXT NOT NULL,
    score INTEGER, pourquoi TEXT, details_json TEXT, cv_hash TEXT,
    statut TEXT NOT NULL DEFAULT 'nouvelle', erreur TEXT,
    UNIQUE (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_offers_url ON offers (url_key);
CREATE INDEX IF NOT EXISTS idx_offers_dedupe ON offers (dedupe_key);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, ok INTEGER,
    found INTEGER, new INTEGER, scored INTEGER, notes_json TEXT
);
CREATE TABLE IF NOT EXISTS source_status (
    source TEXT PRIMARY KEY, last_ok_at TEXT, last_count INTEGER,
    last_error_at TEXT, last_error TEXT
);
"""


class Store:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # --- offres ---------------------------------------------------------
    def is_known(self, offer):
        row = self.db.execute(
            "SELECT 1 FROM offers WHERE (source=? AND source_id=?) OR url_key=? OR dedupe_key=? LIMIT 1",
            (offer.source, offer.source_id, url_key(offer.url), dedupe_key(offer)),
        ).fetchone()
        return row is not None

    def add(self, offer, seen_at):
        d = asdict(offer)
        cur = self.db.execute(
            """INSERT INTO offers (source, source_id, url, url_key, dedupe_key, title, company, location,
               remote, contract, salary_text, published_at, description, first_seen_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["source"], d["source_id"], d["url"], url_key(d["url"]), dedupe_key(offer), d["title"],
             d["company"], d["location"], d["remote"], d["contract"], d["salary_text"],
             d["published_at"], d["description"], seen_at),
        )
        self.db.commit()
        return cur.lastrowid

    def get(self, offer_id):
        row = self.db.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
        return dict(row) if row else None

    def get_many(self, ids):
        return [self.get(i) for i in ids]

    def to_score(self, cv_hash, limit, since):
        rows = self.db.execute(
            """SELECT * FROM offers WHERE statut='nouvelle' AND first_seen_at >= ?
               AND (score IS NULL OR cv_hash IS NOT ?) ORDER BY first_seen_at DESC, id DESC LIMIT ?""",
            (since, cv_hash, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def set_score(self, offer_id, result, cv_hash):
        details = {"points_forts": result.get("points_forts", []), "manques": result.get("manques", [])}
        self.db.execute(
            "UPDATE offers SET score=?, pourquoi=?, details_json=?, cv_hash=?, erreur=NULL WHERE id=?",
            (result["score"], result["pourquoi"], json.dumps(details, ensure_ascii=False), cv_hash, offer_id),
        )
        self.db.commit()

    def set_error(self, offer_id, message):
        self.db.execute("UPDATE offers SET erreur=? WHERE id=?", (message[:300], offer_id))
        self.db.commit()

    def set_statut(self, offer_id, statut):
        if statut not in STATUTS:
            raise ValueError(f"statut inconnu : {statut} (attendu : {', '.join(STATUTS)})")
        cur = self.db.execute("UPDATE offers SET statut=? WHERE id=?", (statut, offer_id))
        self.db.commit()
        return cur.rowcount == 1

    def since(self, iso_date):
        rows = self.db.execute(
            "SELECT * FROM offers WHERE first_seen_at >= ? ORDER BY first_seen_at DESC, id DESC", (iso_date,)
        ).fetchall()
        return [dict(r) for r in rows]

    def latest(self, n):
        rows = self.db.execute(
            "SELECT * FROM offers ORDER BY first_seen_at DESC, id DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- exécutions et sources ------------------------------------------
    def record_run(self, started, finished, ok, found, new, scored, notes):
        self.db.execute(
            "INSERT INTO runs (started_at, finished_at, ok, found, new, scored, notes_json) VALUES (?,?,?,?,?,?,?)",
            (started, finished, int(ok), found, new, scored, json.dumps(notes, ensure_ascii=False)),
        )
        self.db.commit()

    def source_ok(self, source, count, at):
        self.db.execute(
            """INSERT INTO source_status (source, last_ok_at, last_count) VALUES (?,?,?)
               ON CONFLICT(source) DO UPDATE SET last_ok_at=excluded.last_ok_at, last_count=excluded.last_count""",
            (source, at, count),
        )
        self.db.commit()

    def source_error(self, source, message, at):
        self.db.execute(
            """INSERT INTO source_status (source, last_error_at, last_error) VALUES (?,?,?)
               ON CONFLICT(source) DO UPDATE SET last_error_at=excluded.last_error_at, last_error=excluded.last_error""",
            (source, at, message[:300]),
        )
        self.db.commit()

    def sources_status(self):
        return {r["source"]: dict(r) for r in self.db.execute("SELECT * FROM source_status")}
