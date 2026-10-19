#!/usr/bin/env python3
"""Порог срабатывания: не «у нас 200 новых репо», а «есть то, что стоит посмотреть сегодня»."""
import json, os, pathlib, sys, urllib.request
d = json.loads(pathlib.Path(os.environ.get("LEADS", "data/leads.json")).read_text(encoding="utf-8"))
from datetime import datetime, timezone
gen = d.get("generated_at")
age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(gen.replace("Z", "+00:00"))).total_seconds() / 3600 if gen else 9e9
if age_h > float(os.environ.get("RADAR_MAX_AGE_H", "4")):
    print(f"::error::снимку {age_h:.1f} ч - в канал это не отправляем, иначе люди будут триажировать вчерашний список", file=sys.stderr)
    raise SystemExit(1)
import datetime as _dt
SENT = pathlib.Path(os.environ.get("RADAR_SENT", "data/sent.json"))
sent = json.loads(SENT.read_text(encoding="utf-8")) if SENT.exists() else {}
top = [l for l in d["leads"] if l["lead_score"] >= float(os.environ.get("MIN_SCORE", "1.0"))
       and l["manipulation_risk"] < 0.35 and l.get("license")][:5]
# cron каждые 30 минут = 48 прогонов в сутки. Без фильтра канал получал бы 48 сообщений в день
# с одними и теми же репозиториями. В канал идёт только то, чего раньше не было.
fresh = [l for l in top if l["repo"] not in sent]
if not top:
    print("порог не пройден - молчим (шум в канал = смерть процесса)"); raise SystemExit(0)
if not fresh:
    print(f"новых нет: все {len(top)} кандидатов уже приходили в канал ({', '.join(l['repo'] for l in top)[:140]})")
    raise SystemExit(0)
top = fresh
msg = "RADAR: %d кандидата(ов)\n" % len(top) + "\n".join(
  f"- {l['repo']}  {l['stars']}★  +{l['signals']['stars_per_day_recent']:.0f}/сут  fit {l['fit_internal']} -> {l['problem_statement']}\n  {l['url']}"
  for l in top)
print(msg)
import time
t, c = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
if not c:      # Telegram Variables требуют права Actions:write на запись - читаем chat id из файла в репо
    for cand in (pathlib.Path("data/telegram.json"), pathlib.Path(__file__).resolve().parent / "data/telegram.json"):
        if cand.exists():
            c = str(json.loads(cand.read_text(encoding="utf-8")).get("chat_id") or "")
            if c: print(f"chat id взят из {cand}"); break
if "--test" in sys.argv:                              # python3 notify.py --test  (после настройки)
    msg = "RADAR на связи: тестовое сообщение."
if not t:
    print("TELEGRAM_BOT_TOKEN не задан -> печать без отправки (в Actions: gh secret set TELEGRAM_BOT_TOKEN)")
elif not c:
    # chat id можно не гуглить: бот отдаёт последние входящие; нужен id чата, где вы написали боту
    d = json.load(urllib.request.urlopen(f"https://api.telegram.org/bot{t}/getUpdates", timeout=25))
    ids = sorted({u["message"]["chat"]["id"] for u in d.get("result", []) if u.get("message")})
    print("chat id не задан. варианты:", ids or "пусто - напишите боту /start, затем повторите")
    print(f"  gh variable set TELEGRAM_CHAT_ID --body {ids[0] if ids else '<id>'}")
if t and c:
    body = json.dumps({"chat_id": c, "text": msg, "disable_web_page_preview": True}).encode()
    for attempt in range(3):                            # 429 у Telegram бывает на ровном месте
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(
                f"https://api.telegram.org/bot{t}/sendMessage", data=body,
                headers={"Content-Type": "application/json"}), timeout=25))
            print("-> отправлено, message_id:", r.get("result", {}).get("message_id"))
            now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
            for l in top: sent[l["repo"]] = now
            cut = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)).isoformat()
            SENT.parent.mkdir(parents=True, exist_ok=True)
            SENT.write_text(json.dumps({k: v for k, v in sent.items() if v > cut},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"помечено отправленными: {len(top)} (в {SENT} итого: {len(sent)})")
            break
        except urllib.error.HTTPError as e:
            wait = int(e.headers.get("retry-after", 2)) if e.code == 429 else 2
            print(f"  ! telegram {e.code}, повтор через {wait}с (попытка {attempt+1}/3)", file=sys.stderr); time.sleep(wait)
    else:
        print("  ! не отправлено - сообщение осталось в логе, CI из-за этого не падает", file=sys.stderr)
