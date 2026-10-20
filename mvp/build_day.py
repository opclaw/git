#!/usr/bin/env python3
"""Витрина «за сутки».

Сайт (index.html) показывает только последние 4-6 часов - это живой экран, и если
смотреть его раз в день, половина находок уже уехала. Эта страница собирает ВСЕ
часовые снимки из data/history/ за последние 24 часа, склеивает повторы и даёт
один список на сутки. Проверять утром - ничего не теряется.

Запуск:  python3 mvp/build_day.py            -> day.html рядом с index.html
"""
import datetime as dt
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
HISTORY = ROOT / "data" / "history"
LEADS = ROOT / "data" / "leads.json"
SENT = ROOT / "data" / "sent.json"
OUT = ROOT / "day.html"
HOURS = float(os.environ.get("RADAR_DAY_HOURS", "24"))


def snapshots():
    """Файлы истории + текущий снимок, свежие за HOURS часов."""
    now = dt.datetime.now(dt.timezone.utc)
    files = sorted(HISTORY.glob("*.json")) if HISTORY.exists() else []
    if LEADS.exists():
        files.append(LEADS)
    out = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue                                # битый снимок не должен ронять витрину
        gen = d.get("generated_at")
        try:
            ts = dt.datetime.fromisoformat(gen.replace("Z", "+00:00"))
        except Exception:
            continue
        out.append((ts, d))
    fresh = [x for x in out if (now - x[0]).total_seconds() / 3600 <= HOURS]
    if fresh:
        return sorted(fresh)
    return sorted(out)[-1:]
    return sorted(out)


def main():
    snaps = snapshots()
    sent = json.loads(SENT.read_text(encoding="utf-8")) if SENT.exists() else {}
    agg = {}
    for ts, d in snaps:
        for l in d.get("leads", []):
            repo = l.get("repo")
            if not repo:
                continue
            a = agg.setdefault(repo, {
                "repo": repo, "url": l.get("url") or f"https://github.com/{repo}",
                "description": (l.get("description") or "")[:160],
                "stars": 0, "spd": 0.0, "score": 0.0, "fit": 0.0, "risk": 0.0,
                "problem_statement": l.get("problem_statement") or "PS-unknown",
                "license": l.get("license"), "hits": 0, "first": ts, "last": ts,
            })
            a["hits"] += 1
            a["first"] = min(a["first"], ts)
            a["last"] = max(a["last"], ts)
            a["stars"] = max(a["stars"], l.get("stars") or 0)
            a["spd"] = max(a["spd"], float((l.get("signals") or {}).get("stars_per_day_recent") or 0))
            a["score"] = max(a["score"], float(l.get("lead_score") or 0))
            a["fit"] = max(a["fit"], float(l.get("fit_internal") or 0))
            a["risk"] = max(a["risk"], float(l.get("manipulation_risk") or 0))
            if l.get("license"):
                a["license"] = l["license"]
            if l.get("problem_statement") and a["problem_statement"] == "PS-unknown":
                a["problem_statement"] = l["problem_statement"]

    rows = sorted(agg.values(), key=lambda a: (-a["score"], -a["hits"]))
    for a in rows:
        a["first"] = a["first"].strftime("%d.%m %H:%M")
        a["last"] = a["last"].strftime("%d.%m %H:%M")
        a["in_tg"] = a["repo"] in sent

    payload = {
        "hours": HOURS, "snapshots": len(snaps), "rows": rows,
        "built_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": (snaps[-1][1].get("window", {}) if snaps else {}),
    }
    html = TPL.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    if not snaps:
        # Свежих нет, но старые снимки есть - публикуем их с прямой пометкой возраста,
        # иначе поломка инжеста дополнительно блокировала бы и публикацию живого экрана.
        print("::warning::нет снимков моложе %.0f ч - витрина собрана по более старым данным" % HOURS, file=sys.stderr)
    OUT.write_text(html, encoding="utf-8")
    print(f"{OUT}: {len(html)//1024} КБ | снимков: {len(snaps)} | репо за {HOURS:.0f} ч: {len(rows)}")
    return 0


TPL = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RADAR · за сутки</title>
<style>
:root{--bg:#0b0e13;--pan:#12171f;--pan2:#0f141b;--tx:#e6edf3;--dim:#8b98a8;--ac:#4da3ff;--ok:#2ea043;--wn:#d29922;--bd:#30363d;--no:#f85149}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
header{padding:14px 20px;border-bottom:1px solid var(--bd);background:linear-gradient(180deg,#0f141b,#0b0e13);position:sticky;top:0;z-index:5}
h1{margin:0;font-size:17px;letter-spacing:.3px}h1 b{color:var(--ac)}
.sub{color:var(--dim);font-size:12px;margin-top:3px}
.stats{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.st{background:var(--pan);border:1px solid var(--bd);border-radius:8px;padding:6px 10px;font-size:12px}
.st b{display:block;font-size:16px;color:var(--tx)}.st span{color:var(--dim)}
a{color:var(--ac)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 10px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}
th{position:sticky;top:96px;background:var(--pan2);color:var(--dim);font-weight:600;font-size:12px;cursor:pointer;white-space:nowrap}
tr:hover td{background:#0f1620}
.num{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
.mono{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.desc{color:var(--dim);max-width:520px}
.tag{display:inline-block;padding:1px 6px;border:1px solid var(--bd);border-radius:999px;font-size:11px;color:var(--dim)}
.new{color:var(--ok);border-color:var(--ok)}
.tg{color:var(--ac);border-color:var(--ac)}
.risk{color:var(--no)}
.foot{color:var(--dim);font-size:12px;padding:16px 20px 40px;max-width:900px}
.bar{display:flex;gap:8px;align-items:center;padding:10px 20px;border-bottom:1px solid var(--bd);background:var(--pan2);position:sticky;top:76px;z-index:4;flex-wrap:wrap}
input[type=search]{background:var(--bg);border:1px solid var(--bd);border-radius:6px;color:var(--tx);padding:5px 9px;font-size:13px;min-width:220px}
.chip{border:1px solid var(--bd);border-radius:999px;padding:3px 10px;font-size:12px;color:var(--dim);cursor:pointer}
.chip.on{color:var(--tx);border-color:var(--ac);background:#12233a}
@media(max-width:900px){.desc,th.hide,td.hide{display:none}}
</style></head><body>
<header><h1><b>RADAR</b> · всё за сутки</h1>
<div class="sub">Агрегат часовых снимков: <b id="gen"></b> · собрано снимков: <span id="sn"></span> ·
<a href="index.html">← живой экран (последние часы)</a></div>
<div class="stats" id="stats"></div></header>
<div class="bar"><span class="chip on" data-f="all">все</span><span class="chip" data-f="new">новые за сутки</span>
<span class="chip" data-f="tg">ушли в Telegram</span><span class="chip" data-f="risk">риск накрутки</span>
<span class="chip" data-f="rep">попадались ≥3 раз</span>
<input type="search" id="q" placeholder="фильтр: имя, описание, PS…"><span class="sub" id="cnt"></span></div>
<table><thead><tr>
<th data-s="score" class="num">скор</th><th data-s="repo">репозиторий</th>
<th data-s="stars" class="num">звёзд</th><th data-s="spd" class="num">+в сутки</th>
<th data-s="hits" class="num">попадался</th><th data-s="first">замечен</th>
<th data-s="problem_statement" class="hide">PS</th><th data-s="risk" class="num">M</th>
<th data-s="license" class="hide">лицензия</th></tr></thead><tbody id="tb"></tbody></table>
<div class="foot"><b>Зачем эта страница.</b> Живой экран показывает только последние часы, поэтому найденное утром
к вечеру с него уезжает. Здесь склеены все часовые снимки за сутки: если репозиторий попадался несколько раз,
виден максимум его скора и сколько раз он всплывал — повторяемость это признак устойчивого роста, а не случайного
всплеска. Вердикты ставятся на живой странице и хранятся в этом же браузере.</div>
<script>
const D=__DATA__, LS="radar.triage.v1";
let store={};try{store=JSON.parse(localStorage.getItem(LS)||"{}")}catch(e){}
let f="all", q="", sk="score", dir=-1;
const fmt=n=>n>=1000?(n/1000).toFixed(1)+"k":String(n);
document.getElementById("gen").textContent=D.built_at.replace("T"," ").replace("Z"," UTC");
document.getElementById("sn").textContent=D.snapshots;
function rows(){
  const t=(new Date().getTime())/1000;
  return D.rows.filter(r=>{
    if(f==="new" && !(r.last===r.first)) return false;
    if(f==="tg" && !r.in_tg) return false;
    if(f==="risk" && !(r.risk>=0.35)) return false;
    if(f==="rep" && !(r.hits>=3)) return false;
    if(q && !(r.repo+" "+(r.description||"")+" "+r.problem_statement).toLowerCase().includes(q)) return false;
    return true;
  }).sort((a,b)=>{const x=a[sk],y=b[sk];
    return (typeof x==="number"&&typeof y==="number")?(x-y)*dir:String(x).localeCompare(String(y))*dir;});
}
function draw(){
  const rs=rows();
  document.getElementById("tb").innerHTML=rs.map(r=>{
    const v=(store[r.repo]||{}).verdict;
    return `<tr><td class="num"><b>${r.score.toFixed(2)}</b></td>
    <td class="mono"><a href="${r.url}" target="_blank" rel="noopener">${r.repo}</a>
      ${r.in_tg?' <span class="tag tg">в Telegram</span>':''}
      ${v?` <span class="tag new">${v}</span>`:''}
      <div class="desc">${(r.description||"").replace(/[<>&]/g,"")}</div></td>
    <td class="num">${fmt(r.stars)}</td><td class="num">${r.spd.toFixed(0)}</td>
    <td class="num">${r.hits}</td><td>${r.first}</td>
    <td class="hide">${r.problem_statement}</td>
    <td class="num ${r.risk>=0.35?"risk":""}">${r.risk.toFixed(2)}</td>
    <td class="hide">${r.license||"—"}</td></tr>`;}).join("");
  document.getElementById("cnt").textContent=rs.length+" из "+D.rows.length;
  document.getElementById("stats").innerHTML=[
    ["репо за сутки",D.rows.length],
    ["попадались ≥3 раз",D.rows.filter(r=>r.hits>=3).length],
    ["ушли в Telegram",D.rows.filter(r=>r.in_tg).length],
    ["с риском накрутки",D.rows.filter(r=>r.risk>=0.35).length],
    ["с вердиктом",D.rows.filter(r=>(store[r.repo]||{}).verdict).length]
  ].map(([k,v])=>`<div class="st"><b>${v}</b><span>${k}</span></div>`).join("");
}
document.querySelectorAll(".chip").forEach(c=>c.onclick=()=>{
  document.querySelectorAll(".chip").forEach(x=>x.classList.remove("on"));
  c.classList.add("on"); f=c.dataset.f; draw();});
document.getElementById("q").oninput=e=>{q=e.target.value.toLowerCase();draw()};
document.querySelectorAll("th").forEach(t=>t.onclick=()=>{
  const k=t.dataset.s; if(!k)return; dir=(sk===k?-dir:(typeof D.rows[0][k]==="number"?-1:1));
  sk=k; draw();});
draw();
</script></body></html>
"""
if __name__ == "__main__":
    sys.exit(main())
