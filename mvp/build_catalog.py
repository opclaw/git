#!/usr/bin/env python3
"""Каталог - то, что не забывается.

Живой экран показывает 4-6 часов, витрина «за сутки» - 24 часа, и карточка уезжает.
Каталог копит: одна строка на репозиторий, первый и последний раз замечен, максимум
скора, сколько раз попадался. Строки не удаляются никогда - поэтому «что-то пропало»
перестаёт быть правдой.

Состояние лежит в data/catalog.json и коммитится тем же шагом, что и снимок:
история изменений = git log, никакой базы данных не нужно.

Запуск:  python3 mvp/build_catalog.py    -> data/catalog.json + catalog.html
"""
import datetime as dt
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
HISTORY = DATA / "history"
LEADS = DATA / "leads.json"
SENT = DATA / "sent.json"
CAT = DATA / "catalog.json"
OUT = ROOT / "catalog.html"
KEEP_DAYS = int(__import__("os").environ.get("RADAR_KEEP_DAYS", "7"))   # ротация часовых снимков


def load_json(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts):
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def row(l, now):
    """Строка каталога из карточки лида."""
    s = l.get("signals") or {}
    return {
        "repo": l.get("repo"),
        "url": l.get("url") or f"https://github.com/{l.get('repo','')}",
        "description": (l.get("description") or "")[:200],
        "stars": l.get("stars") or 0,
        "spd": float(s.get("stars_per_day_recent") or 0),
        "score": float(l.get("lead_score") or 0),
        "fit": float(l.get("fit_internal") or 0),
        "risk": float(l.get("manipulation_risk") or 0),
        "ps": l.get("problem_statement") or "PS-unknown",
        "license": l.get("license"),
        "language": l.get("language") or "",
        "first_seen": iso(now), "last_seen": iso(now), "hits": 1,
    }


def merge(old, new, now):
    """Сливаем новое наблюдение с已有的 строкой: максимумы растут, nothing не удаляется."""
    o = dict(old)
    for k in ("stars", "spd", "score", "fit", "risk"):
        o[k] = max(float(old.get(k) or 0), float(new.get(k) or 0))
    o["hits"] = int(old.get("hits") or 0) + 1
    o["last_seen"] = iso(now)
    for k in ("description", "license", "language", "url"):
        if new.get(k):
            o[k] = new[k]
    if new.get("ps") and (o.get("ps") in (None, "", "PS-unknown")):
        o["ps"] = new["ps"]
    return o


def status(r, now):
    last = parse(r.get("last_seen") or "")
    first = parse(r.get("first_seen") or "")
    if not last:
        return "unknown"
    age = (now - last).total_seconds() / 3600
    if age <= 24:
        return "new" if first and (now - first).total_seconds() / 3600 <= 24 else "active"
    return "cooled"


def rotate_history():
    """Часовые снимки нужны лишь для витрины «за сутки»: старше KEEP_DAYS удаляем,
    иначе репозиторий растёт на ~1.2 МБ в сутки и через год станет неклонируемым."""
    if not HISTORY.exists():
        return 0
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=KEEP_DAYS)
    removed = 0
    for f in HISTORY.glob("*.json"):
        ts = f.stat().st_mtime
        if dt.datetime.fromtimestamp(ts, dt.timezone.utc) < cut:
            f.unlink(); removed += 1
    return removed


def main():
    now = dt.datetime.now(dt.timezone.utc)
    catalog = load_json(CAT, {})
    sent = load_json(SENT, {})
    leads_doc = load_json(LEADS, {})
    fresh = leads_doc.get("leads") or []
    if not fresh:
        print("::error::нет data/leads.json - каталог обновлять не из чего", file=sys.stderr)
        return 1

    # первичное наполнение: если каталог пуст, вычитываем сохранённые снимки
    seeded = 0
    if not catalog and HISTORY.exists():
        for f in sorted(HISTORY.glob("*.json")):
            d = load_json(f, {})
            ts = parse(d.get("generated_at") or "") or now
            for l in d.get("leads", []):
                if not l.get("repo"):
                    continue
                r = row(l, ts)
                catalog[l["repo"]] = merge(catalog[l["repo"]], r, ts) if l["repo"] in catalog else r
                seeded += 1

    new_today = 0
    for l in fresh:
        repo = l.get("repo")
        if not repo:
            continue
        r = row(l, now)
        if repo in catalog:
            catalog[repo] = merge(catalog[repo], r, now)
        else:
            catalog[repo] = r
            new_today += 1

    for repo, r in catalog.items():
        r["in_tg"] = repo in sent
        r["status"] = status(r, now)

    rows = sorted(catalog.values(), key=lambda r: (-(r.get("score") or 0), -(r.get("hits") or 0)))
    CAT.parent.mkdir(parents=True, exist_ok=True)
    CAT.write_text(json.dumps(catalog, ensure_ascii=False, indent=0), encoding="utf-8")

    payload = {
        "built_at": iso(now), "total": len(rows), "new_today": new_today,
        "seeded": seeded, "keep_days": KEEP_DAYS, "rows": rows,
    }
    OUT.write_text(TPL.replace("__DATA__", json.dumps(payload, ensure_ascii=False)), encoding="utf-8")
    removed = rotate_history()
    print(f"{OUT}: {len(OUT.read_text(encoding='utf-8'))//1024} КБ | в каталоге: {len(rows)} "
          f"(+{new_today} новых, из архива {seeded}) | снимков удалено: {removed}")
    return 0


TPL = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RADAR · каталог</title>
<style>
:root{--bg:#0b0e13;--pan:#12171f;--pan2:#0f141b;--tx:#e6edf3;--dim:#8b98a8;--ac:#4da3ff;--ok:#2ea043;--wn:#d29922;--bd:#30363d;--no:#f85149}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
header{padding:14px 20px;border-bottom:1px solid var(--bd);background:linear-gradient(180deg,#0f141b,#0b0e13);position:sticky;top:0;z-index:5}
h1{margin:0;font-size:17px;letter-spacing:.3px}h1 b{color:var(--ac)}
.sub{color:var(--dim);font-size:12px;margin-top:3px}
.stats{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.st{background:var(--pan);border:1px solid var(--bd);border-radius:8px;padding:6px 10px;font-size:12px}
.st b{display:block;font-size:16px;color:var(--tx)}.st span{color:var(--dim)}
a{color:var(--ac)}table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 10px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}
th{position:sticky;top:112px;background:var(--pan2);color:var(--dim);font-weight:600;font-size:12px;cursor:pointer;white-space:nowrap}
tr:hover td{background:#0f1620}
.num{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
.mono{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.desc{color:var(--dim);max-width:520px}
.tag{display:inline-block;padding:1px 6px;border:1px solid var(--bd);border-radius:999px;font-size:11px;color:var(--dim)}
.t-new{color:var(--ok);border-color:var(--ok)}.t-act{color:var(--ac);border-color:var(--ac)}
.t-cool{color:var(--dim)}.tg{color:var(--ac);border-color:var(--ac)}.risk{color:var(--no)}
.foot{color:var(--dim);font-size:12px;padding:16px 20px 40px;max-width:900px}
.bar{display:flex;gap:8px;align-items:center;padding:10px 20px;border-bottom:1px solid var(--bd);background:var(--pan2);position:sticky;top:76px;z-index:4;flex-wrap:wrap}
input[type=search]{background:var(--bg);border:1px solid var(--bd);border-radius:6px;color:var(--tx);padding:5px 9px;font-size:13px;min-width:220px}
.chip{border:1px solid var(--bd);border-radius:999px;padding:3px 10px;font-size:12px;color:var(--dim);cursor:pointer}
.chip.on{color:var(--tx);border-color:var(--ac);background:#12233a}
@media(max-width:900px){.desc,th.hide,td.hide{display:none}}
</style></head><body>
<header><h1><b>RADAR</b> · каталог (копится, не удаляется)</h1>
<div class="sub">Собрано: <b id="gen"></b> · <a href="index.html">живой экран</a> ·
<a href="day.html">за сутки</a></div>
<div class="stats" id="stats"></div></header>
<div class="bar"><span class="chip on" data-f="all">всё</span><span class="chip" data-f="new">новые за сутки</span>
<span class="chip" data-f="active">активные</span><span class="chip" data-f="cooled">остывшие</span>
<span class="chip" data-f="tg">в Telegram</span><span class="chip" data-f="rep">попадались ≥3 раз</span>
<span class="chip" data-f="risk">риск накрутки</span>
<input type="search" id="q" placeholder="поиск: имя, описание, язык, PS…"><span class="sub" id="cnt"></span></div>
<table><thead><tr>
<th data-s="score" class="num">скор</th><th data-s="repo">репозиторий</th>
<th data-s="stars" class="num">звёзд</th><th data-s="spd" class="num">+в сутки</th>
<th data-s="hits" class="num">раз</th><th data-s="first_seen">замечен</th><th data-s="last_seen">последний раз</th>
<th data-s="ps" class="hide">PS</th><th data-s="risk" class="num">M</th>
<th data-s="license" class="hide">лицензия</th></tr></thead><tbody id="tb"></tbody></table>
<div class="foot"><b>Чем это отличается от живого экрана.</b> Живой экран показывает последние часы,
витрина «за сутки» - сутки. Оттуда карточки уезжают. Здесь строка остаётся навсегда: видно, когда
репозиторий замечен впервые, когда попадался последний раз и сколько раз вообще всплывал.
Статусы: <span class="tag t-new">новый</span> - замечен впервые за сутки,
<span class="tag t-act">активный</span> - попадался за сутки, <span class="tag t-cool">остыл</span> - не видели больше суток.
Вердикты ставятся на живом экране и хранятся в этом браузере.</div>
<script>
const D=__DATA__, LS="radar.triage.v1";
let store={};try{store=JSON.parse(localStorage.getItem(LS)||"{}")}catch(e){}
let f="all", q="", sk="score", dir=-1;
const fmt=n=>n>=1000?(n/1000).toFixed(1)+"k":String(n);
const dshort=t=>(t||"").slice(5,16).replace("T"," ");
document.getElementById("gen").textContent=D.built_at.replace("T"," ").replace("Z"," UTC");
const ST={new:["новый","t-new"],active:["активный","t-act"],cooled:["остыл","t-cool"],unknown:["—",""]};
function rows(){
  return D.rows.filter(r=>{
    if(f!=="all"&&f!=="new"&&f!=="active"&&f!=="cooled"&&f!=="tg"&&f!=="rep"&&f!=="risk")return true;
    if(f==="new"&&r.status!=="new")return false;
    if(f==="active"&&r.status!=="active")return false;
    if(f==="cooled"&&r.status!=="cooled")return false;
    if(f==="tg"&&!r.in_tg)return false;
    if(f==="rep"&&!(r.hits>=3))return false;
    if(f==="risk"&&!(r.risk>=0.35))return false;
    if(q&&!(r.repo+" "+(r.description||"")+" "+r.ps+" "+(r.language||"")).toLowerCase().includes(q))return false;
    return true;
  }).sort((a,b)=>{const x=a[sk],y=b[sk];
    return (typeof x==="number"&&typeof y==="number")?(x-y)*dir:String(x).localeCompare(String(y))*dir;});
}
function draw(){
  const rs=rows();
  document.getElementById("tb").innerHTML=rs.map(r=>{
    const v=(store[r.repo]||{}).verdict, st=ST[r.status]||ST.unknown;
    return `<tr><td class="num"><b>${(r.score||0).toFixed(2)}</b></td>
    <td class="mono"><a href="${r.url}" target="_blank" rel="noopener">${r.repo}</a>
      <span class="tag ${st[1]}">${st[0]}</span>
      ${r.in_tg?' <span class="tag tg">в Telegram</span>':''}
      ${v?` <span class="tag t-new">${v}</span>`:''}
      <div class="desc">${(r.description||"").replace(/[<>&]/g,"")}</div></td>
    <td class="num">${fmt(r.stars||0)}</td><td class="num">${(r.spd||0).toFixed(0)}</td>
    <td class="num">${r.hits}</td><td>${dshort(r.first_seen)}</td><td>${dshort(r.last_seen)}</td>
    <td class="hide">${r.ps||""}</td>
    <td class="num ${(r.risk||0)>=0.35?"risk":""}">${(r.risk||0).toFixed(2)}</td>
    <td class="hide">${r.license||"—"}</td></tr>`;}).join("");
  document.getElementById("cnt").textContent=rs.length+" из "+D.rows.length;
  document.getElementById("stats").innerHTML=[
    ["в каталоге",D.rows.length],["новых за сутки",D.new_today],
    ["активных",D.rows.filter(r=>r.status==="active").length],
    ["остывших",D.rows.filter(r=>r.status==="cooled").length],
    ["попадались ≥3 раз",D.rows.filter(r=>r.hits>=3).length],
    ["с вердиктом",D.rows.filter(r=>(store[r.repo]||{}).verdict).length]
  ].map(([k,v])=>`<div class="st"><b>${v}</b><span>${k}</span></div>`).join("");
}
document.querySelectorAll(".chip").forEach(c=>c.onclick=()=>{
  document.querySelectorAll(".chip").forEach(x=>x.classList.remove("on"));
  c.classList.add("on"); f=c.dataset.f; draw();});
document.getElementById("q").oninput=e=>{q=e.target.value.toLowerCase();draw()};
document.querySelectorAll("th").forEach(t=>t.onclick=()=>{
  const k=t.dataset.s; if(!k)return; dir=(sk===k?-dir:(typeof D.rows[0][k]==="number"?-1:1)); sk=k; draw();});
draw();
</script></body></html>
"""
if __name__ == "__main__":
    sys.exit(main())
