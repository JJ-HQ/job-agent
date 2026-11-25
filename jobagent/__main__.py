import argparse
import functools
import logging
import os
import sys
from pathlib import Path

from . import notify, scoring
from .check import run_checks
from .config import load_config, load_env
from .errors import ConfigError
from .run import run
from .sources import SOURCES
from .store import STATUTS, Store

ROOT = Path.cwd()


def _paths(args):
    data = Path(os.environ.get("JOBAGENT_DATA", ROOT / "data"))
    return Path(args.config), Path(args.env), data / "jobs.db", data / "cv.txt"


def _load(args):
    config_path, env_path, db_path, cv_path = _paths(args)
    env = {**load_env(env_path), **{k: v for k, v in os.environ.items() if k.isupper()}}
    return load_config(config_path), env, db_path, cv_path


def cmd_run(args):
    cfg, env, db_path, cv_path = _load(args)
    store = Store(db_path)
    cv = cv_path.read_text(encoding="utf-8") if cv_path.exists() else ""
    score_fn = functools.partial(scoring.score_offer, scoring_cfg=cfg["scoring"]) if cfg["scoring"]["modele"] else None
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    send_fn = functools.partial(notify.send_telegram, token, chat) if token and chat else None
    hc = env.get("HEALTHCHECK_URL")
    ping_fn = functools.partial(notify.ping_healthcheck, hc) if hc else None
    try:
        result = run(cfg, env, store, score_fn=score_fn, send_fn=send_fn, ping_fn=ping_fn, cv_text=cv)
    except Exception:
        if ping_fn:
            ping_fn(False)
        raise
    print(result["summary"])
    print(f"\n[{result['found']} trouvée(s), {result['new']} nouvelle(s), {result['scored']} scorée(s)]")
    return 0 if result["ok"] else 1


def cmd_check(args):
    cfg, env, _, cv_path = _load(args)
    results = run_checks(cfg, env, cv_path)
    for label, ok, detail in results:
        print(f"{'OK ' if ok else 'KO '} {label}" + (f" — {detail}" if detail else ""))
    required_ko = [r for r in results if not r[1] and not r[0].startswith("healthchecks")]
    return 1 if required_ko else 0


def cmd_sources(args):
    cfg, env, db_path, _ = _load(args)
    status = Store(db_path).sources_status()
    print(f"{'source':<16}{'activée':<9}{'clé':<8}{'dernier succès':<22}{'dernière erreur'}")
    for name, enabled in cfg["sources"].items():
        module = SOURCES.get(name)
        key = "—" if not module else ("oui" if all(env.get(v) for v in module.ENV) else "NON")
        s = status.get(name, {})
        ok_at = f"{s['last_ok_at']} ({s['last_count']})" if s.get("last_ok_at") else "—"
        err = f"{s['last_error_at']} {s['last_error']}" if s.get("last_error_at") else "—"
        print(f"{name:<16}{'oui' if enabled else 'non':<9}{key:<8}{ok_at:<22}{err}")
    return 0


def cmd_statut(args):
    _, _, db_path, _ = _load(args)
    try:
        found = Store(db_path).set_statut(args.id, args.statut)
    except ValueError as exc:
        print(exc)
        return 2
    print("Statut mis à jour." if found else "Offre introuvable.")
    return 0 if found else 1


def cmd_liste(args):
    _, _, db_path, _ = _load(args)
    for r in Store(db_path).latest(args.n):
        score = "—" if r["score"] is None else r["score"]
        print(f"#{r['id']:<5}{str(score):>4}  {r['statut']:<12}{r['title']} — {r['company']} ({r['location'] or '?'})")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="jobagent")
    parser.add_argument("--config", default="config.yml")
    parser.add_argument("--env", default=".env")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="recherche, score, résumé Telegram").set_defaults(fn=cmd_run)
    sub.add_parser("check", help="vérifie l'installation").set_defaults(fn=cmd_check)
    sub.add_parser("sources", help="état et clés des sources").set_defaults(fn=cmd_sources)
    p = sub.add_parser("statut", help="change le statut d'une offre")
    p.add_argument("id", type=int)
    p.add_argument("statut", choices=STATUTS)
    p.set_defaults(fn=cmd_statut)
    p = sub.add_parser("liste", help="dernières offres enregistrées")
    p.add_argument("-n", type=int, default=15)
    p.set_defaults(fn=cmd_liste)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return args.fn(args)
    except ConfigError as exc:
        print(f"Configuration : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
