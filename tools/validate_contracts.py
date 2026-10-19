#!/usr/bin/env python3
"""validate_contracts.py — контракты из TEAMS.md §5 как исполняемый код.

Запускается в Actions ПЕРЕД коммитом: битый контракт не попадает в дашборд,
а автор лида получает ошибку в CI, а не «потом разберёмся».
Выход 0 = ок, 1 = есть нарушения (пишет какие и по каким лидидам).
"""
import json, sys, pathlib, urllib.parse

REQUIRED = {"lead_id": str, "repo": str, "url": str, "first_seen_at": str, "lead_score": (int, float),
            "signals": dict, "fit_internal": (int, float), "manipulation_risk": (int, float),
            "score_explain": list, "triage": dict, "problem_statement": str}
SIGNALS = {"age_days": (int, float), "last_push_days_ago": (int, float), "stars_in_window": int,
           "stars_per_day_recent": (int, float), "acceleration": (int, float),
           "self_star_share": (int, float), "ring_share": (int, float)}
CHECKS = {"license", "scorecard", "readme_claims_reproduced", "sandbox_run"}
errs, warn = [], []


def validate(doc):
    leads = doc.get("leads", [])
    rank = {l.get("lead_id"): i for i, l in enumerate(sorted(leads, key=lambda x: -x.get("lead_score", 0)))}
    if doc.get("schema") not in (None, "radar/leads.v1"):
        errs.append(f"schema: ожидается radar/leads.v1, получено {doc.get('schema')!r}")
    if not leads:
        warn.append("0 лидов: либо окно пустое, либо ingest сломался - не молчать, а алертить")
    for l in leads:
        lid = l.get("lead_id", "?")
        for k, t in REQUIRED.items():
            if k not in l: errs.append(f"{lid}: нет обязательного поля {k}")
            elif not isinstance(l[k], t): errs.append(f"{lid}: {k} должен быть {t}, а не {type(l[k]).__name__}")
        for k, t in SIGNALS.items():
            v = (l.get("signals") or {}).get(k)
            if v is None: errs.append(f"{lid}: signals.{k} отсутствует")
            elif not isinstance(v, t): errs.append(f"{lid}: signals.{k} тип {type(v).__name__}")
        if not l.get("score_explain") or len(l["score_explain"]) < 3:
            errs.append(f"{lid}: score_explain должен иметь ≥3 пункта - иначе скор необъясним")
        u = urllib.parse.urlparse(l.get("url", ""))
        if u.scheme != "https" or not u.netloc.endswith("github.com"):
            errs.append(f"{lid}: url обязан быть https-ссылкой на github (evidence)")
        for fld, lo, hi in (("lead_score", 0, 10), ("fit_internal", 0, 1), ("manipulation_risk", 0, 1)):
            if isinstance(l.get(fld), (int, float)) and not lo <= l[fld] <= hi:
                errs.append(f"{lid}: {fld}={l[fld]} вне диапазона [{lo};{hi}]")
        tr = l.get("triage") or {}
        missing = CHECKS - set(tr.get("checks") or {})
        if missing: errs.append(f"{lid}: в триаже нет полей {sorted(missing)}")
        if not tr.get("sla_deadline"): errs.append(f"{lid}: нет sla_deadline - SLA никто не выполнит")
        if not l.get("license") and tr.get("verdict") in ("adopt", "pilot"):
            errs.append(f"{lid}: adopt/pilot без лицензии - жёсткая отсечка из §1")
        # накрученный репо не имеет права попадать в первую десятку выдачи - иначе весь радар обнуляется
        if l.get("manipulation_risk", 0) >= 0.35 and rank.get(lid, 99) < 10:
            errs.append(f"{lid}: M={l['manipulation_risk']} на {rank[lid]+1}-м месте - фильтр накрутки не сработал")


def main():
    paths = sys.argv[1:] or ["mvp/data/leads.json"]
    for p in paths:
        errs.clear(); warn.clear()
        f = pathlib.Path(p)
        if not f.exists(): errs.append(f"файл не найден: {p}"); continue
        validate(json.loads(f.read_text(encoding="utf-8")))
        n = len(json.loads(f.read_text(encoding="utf-8")).get("leads", []))
        for w in warn: print(f"WARN  {p}: {w}")
        for e in errs[:40]: print(f"FAIL  {p}: {e}")
        print(("PASS  " if not errs else "FAIL  ") + f"{p}: {n} лидов, нарушений {len(errs)}")
    return 1 if errs else 0


sys.exit(main())
