#!/usr/bin/env python3
"""RADAR · ingest v0.2 — детект из GH Archive, без сервера и без БД.

Ядро идеи: GitHub закрывает /repos/{o}/{r}/stargazers за авторизацией (401 без токена),
зато data.gharchive.org отдаёт почасовые JSON-lines с WatchEvent бесплатно, ~9 МБ/час.
Оттуда мы берём САМЫЙ важный сигнал - кто и как быстро ставит звёзды, - и там же
бесплатно считаем признак накрутки (само-звёзды и «кольца» аккаунтов).

Запуск:   python3 ingest.py [--hours 6]
Прод:     этот же файл запускается GitHub Actions по cron: '*/30 * * * *',
          результат коммитится в /data/leads.json, Pages его отдаёт статикой.
"""
import argparse, collections, gzip, io, json, math, os, pathlib, re, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

ARCHIVE = "https://data.gharchive.org/{stamp}.json.gz"
API = "https://api.github.com"
UA = {"User-Agent": "radar-v0", "Accept": "application/vnd.github+json"}
TOK = os.environ.get("GITHUB_TOKEN")
if TOK: UA["Authorization"] = f"Bearer {TOK}"


def data_dir(create=False):
    """Каталог данных: <корень>/data, если он есть (раскладка deploy/), иначе <папка_скрипта>/data (radar/mvp).
    Одно правило на обе раскладки - иначе пути разъезжаются при сборке."""
    here = pathlib.Path(__file__).resolve().parent
    for cand in (here.parent / "data", here / "data"):
        if cand.is_dir():
            return cand
    tgt = here / "data"
    if create:
        tgt.mkdir(parents=True, exist_ok=True)
    return tgt


QUOTA = {"core": None, "search": None}

def http(url, binary=False, timeout=60):
    """Один выход в API. Заодно читаем x-ratelimit-remaining - по нему решаем, каким способом брать метаданные."""
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        k = "search" if "/search/" in url else "core"
        rem = r.headers.get("x-ratelimit-remaining")
        if rem is not None:
            QUOTA[k] = int(rem)
        return r.read() if binary else json.load(r)


def cache_path():
    return data_dir(create=True) / "cache.json"


def fetch_metas(repos):
    """Метаданные репо с тремя уровнями: кэш -> REST по одному -> Search API батчем по 5 (отдельная квота!).
    Без этого инжест встанет на первом же 403 rate limit, а лимит без токена = 60 запросов/час."""
    cp = cache_path()
    cache = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}
    if QUOTA["core"] is None:                     # /rate_limit НЕ тратит квоту - cheaper than a 403
        try:
            http(f"{API}/rate_limit")
        except Exception:
            pass
    got = {r: cache[r] for r in repos if r in cache}
    need = [r for r in repos if r not in got]
    calls = 0
    if need and (QUOTA["core"] is None or QUOTA["core"] > len(need)):
        for r in list(need):
            try:
                m = http(f"{API}/repos/{r}"); calls += 1
            except Exception as e:
                print(f"  ! REST {r}: {e}", file=sys.stderr); break
            got[r] = m; cache[r] = m; need.remove(r)
            if (QUOTA["core"] or 0) < 3:
                break
    if need:                                             # батч через search: repo:a/b repo:c/d ... до 5 в запросе
        print(f"  REST-квоты мало ({QUOTA['core']}), добиваю через Search API батчами по 5 (квота {QUOTA['search']})")
        for i in range(0, len(need), 5):
            ch = need[i:i+5]
            try:
                q = " ".join("repo:" + r for r in ch)
                d = http(f"{API}/search/repositories?" + urllib.parse.urlencode({"q": q, "per_page": 30}))
                calls += 1
            except Exception as e:
                print(f"  ! search batch: {e}", file=sys.stderr); break
            for it in d.get("items", []):
                if it.get("full_name") in ch:
                    got[it["full_name"]] = it; cache[it["full_name"]] = it
    cp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return got, calls


def recent_hours(n):
    """Архив отстаёт на ~1 час и хранит последние ~3 суток -> идём назад от текущего часа."""
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    out, i = [], 0
    while len(out) < n and i < 30:
        t = now - timedelta(hours=i); i += 1
        out.append(t.strftime("%Y-%m-%d-%H"))
    return out


def scan(hours):
    """Один проход по потоку: никаких файлов на диск, только счётчики."""
    stars = collections.Counter(); events = collections.defaultdict(list)
    actor_repos = collections.defaultdict(set); selfs = collections.Counter()
    for stamp in hours:
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(http(ARCHIVE.format(stamp=stamp), binary=True)))
        except Exception as e:
            print(f"  ! {stamp}: {e}", file=sys.stderr); continue
        n = 0
        for line in raw:
            b = line.strip()
            if b'{"type":"WatchEvent"' not in b[:80] and b'"WatchEvent"' not in b[:200]:
                continue
            try: e = json.loads(b)
            except Exception: continue
            if e.get("type") != "WatchEvent": continue
            repo = (e.get("repo") or {}).get("name"); actor = (e.get("actor") or {}).get("login")
            if not repo or not actor: continue
            stars[repo] += 1; n += 1
            actor_repos[actor].add(repo)
            if "/" in repo and repo.split("/")[0].lower() == (actor or "").lower():
                selfs[repo] += 1
            ts = e.get("created_at")
            if ts: events[repo].append(ts)
        print(f"  {stamp}: WatchEvent {n}")
    return stars, events, actor_repos, selfs


# PS-xx онтология Т3. Здесь детерминированный v0 (12 строк). В проде - 1 вызов LLM
# (GitHub Models / OpenAI) на классификацию README -> PS + теги + fit. Кэш по sha README.
PS = {
 "PS-infer": (["llm","inference","agent","vllm","rag","embed","prompt","mcp","gpt","finetun","diffusion","transcribe","voice","image","video","ocr"], 1.0),
 "PS-data":  (["database","sql","duckdb","pandas","etl","pipeline","analytic","vector","parquet","clickhouse","query"], 0.9),
 "PS-web":   (["react","next","vue","ui","framework","frontend","css","component","vite","site","web","html"], 0.8),
 "PS-ml":    (["train","pytorch","tensorflow","jax","cuda","model","dataset","benchmark","ml","ai"], 0.9),
 "PS-infra": (["deploy","kubernetes","docker","terraform","proxy","self-host","devops","ci","serverless","cloud"], 0.8),
 "PS-sec":   (["security","vulnerab","auth","crypto","scan","sbom","audit","firewall","encrypt"], 0.9),
 "PS-dev":   (["cli","developer","tool","productivity","terminal","sdk","debug","ide","test","lint"], 0.7),
 "PS-doc":   (["docs","documentation","notebook","tutorial","knowledge","wiki","learn","course"], 0.6),
}


def fit(desc, name, topics):
    text = " ".join(filter(None, [desc or "", name, " ".join(topics or [])])).lower()
    scored = sorted(((sum(1 for k in kw if k in text) * w, ps) for ps, (kw, w) in PS.items()), reverse=True)
    hits, ps = scored[0]
    return (0.0 if hits == 0 else min(1.0, round(0.3 + 0.22 * hits, 2))), (ps if hits else "PS-unknown")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--hours", type=int, default=6)
    ap.add_argument("--top", type=int, default=14); a = ap.parse_args()
    now = datetime.now(timezone.utc)
    hours = recent_hours(a.hours)
    print(f"GH Archive, {len(hours)} часов: {hours[-1]} .. {hours[0]}")
    stars, events, actor_repos, selfs = scan(hours)
    print(f"всего WatchEvent: {sum(stars.values())} | уникальных репо: {len(stars)} | аккаунтов: {len(actor_repos)}")
    if not stars:
        print("пусто - сеть недоступна"); return

    # «кольцо» = аккаунт, наставивший звёзд на >=4 разных репо в этом окне. Считаем долю таких
    # в каждом репо: это бесплатный proxy-индикатор накрутки (в проде - графовая модель).
    ring = {ac for ac, rs in actor_repos.items() if len(rs) >= 4}
    window_h = max(1.0, len(hours) * 1.0)

    cands = []
    for repo, cnt in stars.most_common(400):
        if cnt < 3: continue
        ts = sorted(events.get(repo, []))
        span_h = 0.0
        if len(ts) >= 2:
            t0 = datetime.fromisoformat(ts[0].replace("Z", "+00:00")); t1 = datetime.fromisoformat(ts[-1].replace("Z", "+00:00"))
            span_h = max(0.02, (t1 - t0).total_seconds() / 3600)
        rate = cnt / max(0.5, span_h) * 24
        ring_share = sum(1 for ac in ring if repo in actor_repos[ac]) / cnt
        cands.append(dict(repo=repo, n=cnt, span_h=round(span_h, 1), rate=round(rate, 1),
                          self_share=round(selfs.get(repo, 0) / cnt, 2), ring_share=round(ring_share, 2),
                          first=ts[0] if ts else None, last=ts[-1] if ts else None))
    cands.sort(key=lambda c: (-c["n"], -c["rate"]))
    cands = cands[:a.top * 3]

    cands = cands[:a.top]
    metas, api_calls = fetch_metas([c["repo"] for c in cands])
    print(f"метаданные получены по {len(metas)} из {len(cands)} кандидатам (вызовов API: {api_calls})")
    leads = []
    for c in cands:
        meta = metas.get(c["repo"])
        if not meta:
            print(f"  ! {c['repo']}: нет метаданных (квота) - лид переносится, а не угадывается", file=sys.stderr)
            continue
        created = datetime.fromisoformat(meta["created_at"].replace("Z", "+00:00"))
        age_d = max(0.5, (now - created).total_seconds() / 86400)
        total = meta.get("stargazers_count", 0)
        lifetime_daily = total / age_d
        accel = c["rate"] / max(0.5, lifetime_daily)
        pushed = (now - datetime.fromisoformat(meta["pushed_at"].replace("Z", "+00:00"))).days
        f, ps = fit(meta.get("description"), c["repo"], meta.get("topics"))
        # V - ускорение хвоста против штатного темпа; N - «новое»; C - живость; A - доверие автора
        V = math.log1p(max(0.0, accel)) * (1.0 if age_d <= 60 else 0.6)
        N = 1.0 if age_d <= 45 else (0.6 if age_d <= 180 else 0.2)
        C = 0.0 if pushed > 30 else (0.5 if pushed > 7 else 1.0)
        A = min(1.0, 0.4 + (0.2 if meta["owner"].get("type") == "Organization" else 0)
                + (0.25 if meta.get("forks_count", 0) / max(1, total) > 0.05 else 0))
        M = round(min(1.0, 0.55 * c["ring_share"] + 0.45 * c["self_share"]), 2)
        score = max(0.0, 0.30 * V * 3 + 0.20 * N + 0.10 * C + 0.10 * A + 0.30 * f * 2.5 - 0.40 * M * 3
                    - (0.3 if not meta.get("license") else 0))
        leads.append({
            "lead_id": f"L-{now:%Y%m%d}-{len(leads)+1:02d}", "repo": c["repo"], "url": meta["html_url"],
            "first_seen_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "channel": "gh_archive_watch",
            "stars": total, "forks": meta.get("forks_count", 0), "open_issues": meta.get("open_issues_count", 0),
            "language": meta.get("language"), "license": (meta.get("license") or {}).get("spdx_id"),
            "archived": meta.get("archived"), "size_kb": meta.get("size"),
            "description": meta.get("description"), "topics": (meta.get("topics") or [])[:6],
            "signals": {"age_days": round(age_d, 1), "last_push_days_ago": pushed,
                        "stars_in_window": c["n"], "window_h": c["span_h"],
                        "stars_per_day_recent": c["rate"], "lifetime_stars_per_day": round(lifetime_daily, 2),
                        "acceleration": round(accel, 1), "self_star_share": c["self_share"],
                        "ring_share": c["ring_share"]},
            "fit_internal": f, "problem_statement": ps, "manipulation_risk": M,
            "lead_score": round(score, 2),
            "score_explain": [f"V={V:.2f}: хвост {c['rate']} зв/сут против штатных {lifetime_daily:.1f} (x{accel:.0f})",
                              f"N={N:.1f}: репо {age_d:.0f} дн от роду",
                              f"C={C:.1f}: пуш {pushed} дн назад", f"fit={f} -> {ps}",
                              f"M={M}: self-star {c['self_share']}, кольца {c['ring_share']}"],
            "triage": {"verdict": "needs_review", "owner": "Т2", "sla_deadline":
                       (now + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "checks": {"license": "ok" if meta.get("license") else "MISSING->auto-reject",
                                  "scorecard": "not_run", "readme_claims_reproduced": "not_run",
                                  "sandbox_run": "not_run"}}})
    leads.sort(key=lambda x: -x["lead_score"])
    payload = {"schema": "radar/leads.v1", "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "window": {"hours": len(hours), "from": hours[-1], "to": hours[0],
                          "watch_events": sum(stars.values()), "repos": len(stars),
                          "actors": len(actor_repos), "ring_accounts": len(ring),
                          "api_calls": api_calls, "authenticated": bool(TOK)},
               "leads": leads}
    dd = data_dir(create=True)
    (dd / "leads.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{dd}/leads.json | лидов: {len(leads)} | звёзд в окне: {sum(stars.values())} | «кольца»: {len(ring)} акк. | API: {api_calls}")
    for l in leads[:8]:
        s = l["signals"]
        print(f"  {l['lead_score']:>5} | {l['repo'][:38]:<38} | {l['stars']:>6}★ | {s['stars_in_window']:>3} зв/{s['window_h']:.0f}ч "
              f"| x{s['acceleration']:>4.0f} | {l['problem_statement']:<10} | M={l['manipulation_risk']}")


main()
