#!/usr/bin/env python3
"""build_dashboard.py - собирает dashboard.html из data/leads.json (всё инлайном, 0 зависимостей).

Статика = бесплатно хостится на GitHub Pages / Cloudflare Pages / Vercel.
Данные обновляет не браузер, а cron в Actions: браузер только читает leads.json.
"""
import json, os, pathlib

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

import sys
from datetime import datetime, timezone
MAX_AGE_H = float(os.environ.get("RADAR_MAX_AGE_H", "4"))
HERE = pathlib.Path(__file__).resolve().parent
DATA_PATH = data_dir() / "leads.json"
DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
try:
    age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(DATA["generated_at"].replace("Z", "+00:00"))).total_seconds() / 3600
except Exception:
    age_h = 9e9
STALE = age_h > MAX_AGE_H
if STALE:
    print(f"::error::снимку {age_h:.1f} ч - публикация выглядела бы свежей, а это не так. "
          f"Инжест падал. (порог RADAR_MAX_AGE_H={MAX_AGE_H}ч)", file=sys.stderr)
DATA.setdefault("window", {}).update(DATA.pop("totals", {}))   # сводка за okno -> в DATA.window
TPL = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RADAR · очередь репозиториев</title>
<style>
:root{--bg:#0b0e13;--pan:#12171f;--pan2:#0f141b;--tx:#e6edf3;--dim:#8b98a8;--ac:#4da3ff;--ok:#2ea043;--wn:#d29922;--bd:#30363d;--no:#f85149}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
header{padding:14px 20px;border-bottom:1px solid var(--bd);background:linear-gradient(180deg,#0f141b,#0b0e13);position:sticky;top:0;z-index:5}
h1{margin:0;font-size:17px;letter-spacing:.3px}h1 b{color:var(--ac)}
.sub{color:var(--dim);font-size:12px;margin-top:3px}
.stats{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.st{background:var(--pan);border:1px solid var(--bd);border-radius:8px;padding:6px 10px;font-size:12px}
.st b{display:block;font-size:16px;color:var(--tx)}.st span{color:var(--dim)}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 20px;border-bottom:1px solid var(--bd);background:var(--pan2);position:sticky;top:0;z-index:4}
.chip{border:1px solid var(--bd);background:var(--pan);color:var(--dim);border-radius:999px;padding:5px 11px;font-size:12px;cursor:pointer}
.chip.on{border-color:var(--ac);color:var(--tx);background:#16202e}
input[type=search]{background:var(--pan);border:1px solid var(--bd);color:var(--tx);border-radius:8px;padding:6px 10px;min-width:200px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{position:sticky;top:0;background:var(--pan2);color:var(--dim);font-weight:600;text-align:right;padding:8px 10px;border-bottom:1px solid var(--bd);cursor:pointer;white-space:nowrap}
th:nth-child(-n+2){text-align:left}td{padding:8px 10px;border-bottom:1px solid #161c24;text-align:right;vertical-align:top}
td:nth-child(-n+2){text-align:left}tbody tr:hover{background:#0f151d;cursor:pointer}
.rp{font-weight:600}.rp a{color:var(--tx);text-decoration:none}.rp a:hover{color:var(--ac)}
.desc{color:var(--dim);font-size:11.5px;max-width:420px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.num{font-variant-numeric:tabular-nums}.sc{font-weight:700}.badge{display:inline-block;border-radius:5px;padding:1px 6px;font-size:11px;border:1px solid var(--bd);color:var(--dim)}
.v{display:inline-block;border-radius:5px;padding:1px 7px;font-size:11px;font-weight:600;border:1px solid}
.needs_review{color:var(--dim)}.adopt{color:var(--ok);border-color:#1f4d2c;background:#0f2417}.pilot{color:#7cc4ff;border-color:#1e3f66;background:#0f1f33}
.watch{color:var(--wn);border-color:#4d3f14;background:#231d0b}.reject{color:var(--no);border-color:#4d1f1c;background:#210f0e}
.m1{color:var(--no);font-weight:700}.m0{color:var(--dim)}
aside{position:fixed;top:0;right:-560px;width:min(560px,96vw);height:100vh;background:#0d1117;border-left:1px solid var(--bd);transition:right .18s;overflow:auto;padding:18px 20px;z-index:9}
aside.open{right:0}aside h2{margin:0 0 4px;font-size:15px}aside h3{margin:18px 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--dim)}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:12.5px}.kv i{font-style:normal;color:var(--dim)}
pre{white-space:pre-wrap;background:#0f141b;border:1px solid var(--bd);border-radius:8px;padding:9px;font-size:11.5px;color:#c9d5e2;margin:0}
.btns{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px}button{background:var(--pan);border:1px solid var(--bd);color:var(--tx);border-radius:8px;padding:7px 12px;font-size:12.5px;cursor:pointer}
button:hover{border-color:var(--ac)}textarea{width:100%;background:#0f141b;color:var(--tx);border:1px solid var(--bd);border-radius:8px;padding:8px;min-height:64px;font:inherit;font-size:12.5px;margin-top:8px}
.x{float:right;background:none;border:0;color:var(--dim);font-size:20px;padding:0 4px}.chk{font-size:12px;color:var(--dim);margin:3px 0}
.foot{color:var(--dim);font-size:11.5px;padding:14px 20px;border-top:1px solid var(--bd);margin-top:18px}
.hide{display:none}@media(max-width:900px){.desc,th.hide,td.hide{display:none}}
</style></head><body>
<header><h1><b>RADAR</b> · очередь репозиториев и вердикты</h1>
<div class="sub">Снимок: <b id="gen"></b> · окно наблюдения: <span id="win"></span> · обновление каждые 30 мин из GH Archive (cron в GitHub Actions). Сервер не нужен. · <a href="day.html">за сутки</a> · <a href="catalog.html">каталог (копится)</a></div>
<div class="stats" id="stats"></div></header>
<div class="bar"><span class="chip on" data-f="all">все</span><span class="chip" data-f="needs_review">нужен триаж</span>
<span class="chip" data-f="adopt">adopt</span><span class="chip" data-f="pilot">pilot</span><span class="chip" data-f="watch">watch</span>
<span class="chip" data-f="reject">reject</span><span class="chip" data-f="risk">риск накрутки</span>
<input type="search" id="q" placeholder="фильтр: имя, описание, PS…"><span class="sub" id="cnt"></span>
<span style="margin-left:auto" class="sub">сортировка: <b id="sk"></b></span></div>
<table><thead><tr>
<th data-s="lead_score">Скор</th><th data-s="repo">Репозиторий</th>
<th class="hide" data-s="stars">★ всего</th><th data-s="stars_in_window">звёзд<br>в окне</th>
<th data-s="stars_per_day_recent">темп<br>зв/сут</th><th data-s="acceleration">разгон<br>x</th>
<th class="hide" data-s="age_days">возраст<br>дн</th><th class="hide" data-s="last_push_days_ago">пуш<br>дн назад</th>
<th data-s="fit_internal">fit → PS</th><th class="hide" data-s="manipulation_risk">накрут<br>ка M</th>
<th class="hide" data-s="license">лицензия</th><th data-s="verdict">вердикт</th></tr></thead><tbody id="tb"></tbody></table>
<div class="foot">Как читать: <b>темп</b> и <b>разгон</b> — опережающие сигналы (сколько звёзд в час и во сколько раз быстрее штатного темпа за жизнь репо). <b>Накрутка M</b> — доля звёзд от «колец» (аккаунты, наставившие ≥4 разных репо в окне) и само-звёзд; M≥0.35 = красный флаг, в Top не пускаем. <b>fit</b> — совпадение с нашей онтологией задач, пока по ключевым словам, дальше — LLM-классификация README. Вердикты хранятся локально в браузере (localStorage): в проде это таблица triage в Postgres + журнал решений в git.</div>
<aside id="drawer"></aside>
<script>
const DATA=__DATA__, LS="radar.triage.v1";
let store={};try{store=JSON.parse(localStorage.getItem(LS)||"{}")}catch(e){}
const VZ={needs_review:"нужен триаж",adopt:"adopt",pilot:"pilot",watch:"watch",reject:"reject"};
const sig=(l,k)=>k in l.signals?l.signals[k]:(l.triage.verdict||"");
let filt="all",q="",sk="lead_score",dir=-1;
function val(l,k){if(k==="verdict")return (store[l.lead_id]||{}).verdict||"needs_review";if(k==="fit_internal")return l.fit_internal;if(k in l)return l[k];return sig(l,k)??0}
function draw(){const rows=DATA.leads.filter(l=>{const v=(store[l.lead_id]||{}).verdict||"needs_review";
 if(filt==="risk"){if(!(l.manipulation_risk>=.15))return false}
 else if(filt!=="all"&&v!==filt)return false;
 if(q&&!(l.repo+" "+(l.description||"")+" "+l.problem_statement).toLowerCase().includes(q))return false;return true})
 .sort((a,b)=>{const A=val(a,sk),B=val(b,sk);return (typeof A=="string"?String(A).localeCompare(String(B)):A-B)*dir});
 document.getElementById("cnt").textContent=rows.length+" из "+DATA.leads.length;
 document.getElementById("tb").innerHTML=rows.map(l=>{const v=(store[l.lead_id]||{}).verdict||"needs_review",s=l.signals;
 return `<tr data-id="${l.lead_id}"><td class="sc num">${l.lead_score.toFixed(2)}</td>
<td><div class="rp"><a href="${l.url}" target="_blank" onclick="event.stopPropagation()">${l.repo}</a></div>
<div class="desc">${(l.description||"—").replace(/</g,"&lt;")}</div></td>
<td class="hide num">${l.stars.toLocaleString("ru")}</td><td class="num">${s.stars_in_window}</td>
<td class="num">${Math.round(s.stars_per_day_recent).toLocaleString("ru")}</td>
<td class="num">${s.acceleration>=10?Math.round(s.acceleration):s.acceleration.toFixed(1)}</td>
<td class="hide num">${s.age_days.toFixed(0)}</td><td class="hide num">${s.last_push_days_ago}</td>
<td class="num">${l.fit_internal.toFixed(2)} <span class="badge">${l.problem_statement}</span></td>
<td class="hide num ${l.manipulation_risk>=.35?"m1":"m0"}">${l.manipulation_risk.toFixed(2)}</td>
<td class="hide">${l.license||"<span class=m1>нет</span>"}</td>
<td><span class="v ${v}">${VZ[v]}</span></td></tr>`}).join("")}
function open(id){const l=DATA.leads.find(x=>x.lead_id===id);if(!l)return;const st=store[id]||{};
 document.getElementById("drawer").innerHTML=`<button class="x" onclick="cl()">×</button>
<h2>${l.repo}</h2><div class="sub">${l.url}</div>
<h3>Почему в очереди (объяснение скора)</h3><pre>${l.score_explain.join("\\n")}</pre>
<h3>Карточка</h3><div class="kv"><i>звёзды / форки</i><span>${l.stars} / ${l.forks}</span>
<i>открытых issues</i><span>${l.open_issues}</span><i>язык</i><span>${l.language||"—"}</span>
<i>лицензия</i><span>${l.license||"ОТСУТСТВУЕТ → auto-reject"}</span><i>размер кода</i><span>${(l.size_kb/1024).toFixed(1)} МБ</span>
<i>topics</i><span>${l.topics.join(", ")||"—"}</span><i>описание</i><span>${(l.description||"—").replace(/</g,"&lt;")}</span></div>
<h3>Триаж Т2 (SLA 15 мин, досье 4 ч)</h3>
${Object.entries(l.triage.checks).map(([k,v])=>`<div class="chk">▢ ${k}: <b>${v}</b></div>`).join("")}
<div class="chk">срок вердикта: <b>${l.triage.sla_deadline}</b> · владелец: ${l.triage.owner}</div>
<h3>Вердикт</h3><div class="btns">${Object.keys(VZ).map(v=>`<button onclick="setV('${id}','${v}')">${VZ[v]}</button>`).join("")}</div>
<textarea id="note" placeholder="обоснование (обязательно для adopt/reject): что проверяли, чего не хватает">${st.note||""}</textarea>
<h3>Куда применить (Т3)</h3><div class="sub">fit=${l.fit_internal} → ${l.problem_statement}. В проде здесь 5 строк LLM-брифа: что решает / что заменяет / цена внедрения / 3 сценария / риск.</div>`;
 document.getElementById("drawer").classList.add("open")}
window.cl=()=>document.getElementById("drawer").classList.remove("open");
window.setV=(id,v)=>{store[id]={...(store[id]||{}),verdict:v,ts:new Date().toISOString()};
 localStorage.setItem(LS,JSON.stringify(store));draw();open(id)};
document.getElementById("q").oninput=e=>{q=e.target.value.toLowerCase();draw()};
document.querySelectorAll(".chip").forEach(c=>c.onclick=()=>{document.querySelectorAll(".chip").forEach(x=>x.classList.remove("on"));c.classList.add("on");filt=c.dataset.f;draw()});
document.querySelectorAll("th").forEach(t=>t.onclick=()=>{const k=t.dataset.s;if(!k)return;dir=(sk===k?-dir:((k==="repo"||k==="license"||k==="verdict")?1:-1));sk=k;document.getElementById("sk").textContent=k;draw()});
document.getElementById("tb").onclick=e=>{const tr=e.target.closest("tr");if(tr)open(tr.dataset.id)};
document.getElementById("gen").textContent=DATA.generated_at;
const w=DATA.window;document.getElementById("win").textContent=`${w.from} → ${w.to} UTC (${w.hours} ч, ${w.watch_events} WatchEvent, ${w.ring_accounts} «кольцевых» акк.)`;
document.getElementById("stats").innerHTML=[["лидов в очереди",DATA.leads.length],["ждут триажа",DATA.leads.filter(l=>!store[l.lead_id]||!store[l.lead_id].verdict).length],
["с M≥0.35",DATA.leads.filter(l=>l.manipulation_risk>=.35).length],["без лицензии",DATA.leads.filter(l=>!l.license).length],
["уникальных репо в окне",w.repos],["источник","GH Archive + REST, "+w.api_calls+" вызовов"]].map(([a,b])=>`<div class="st"><b>${b}</b><span>${a}</span></div>`).join("");
draw();
</script></body></html>"""

out = TPL.replace("__DATA__", json.dumps(DATA, ensure_ascii=False)).replace(
    "<header>", "<div style=\"background:#5a1e1e;color:#ffd7d7;padding:8px 20px;font-size:13px;border-bottom:1px solid #f85149\">"    f"\u26a0 \u0421\u041d\u0418\u041c\u041e\u041a \u0423\u0421\u0422\u0410\u0420\u0415\u041b: {age_h:.1f} \u0447 - \u0438\u043d\u0436\u0435\u0441 \u043d\u0435 \u043e\u0431\u043d\u043e\u0432\u0438\u043b \u0434\u0430\u043d\u043d\u044b\u0435. "
    "\u041d\u0438\u0436\u0435 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 \u0445\u043e\u0440\u043e\u0448\u0438\u0439 \u0441\u043d\u0438\u043c\u043e\u043a.</div><header>") if STALE else TPL.replace("__DATA__", json.dumps(DATA, ensure_ascii=False))
OUT_PATH = DATA_PATH.parent.parent / "dashboard.html"   # рядом с data/: корень в deploy/, mvp/ в исходной раскладке
OUT_PATH.write_text(out, encoding="utf-8")
if STALE and "--allow-stale" not in sys.argv:
    sys.exit(3)   # CI: красный. Локально: python3 mvp/build_dashboard.py --allow-stale
print(f"{OUT_PATH}: {len(out)/1024:.0f} КБ, лидов: {len(DATA['leads'])}")
