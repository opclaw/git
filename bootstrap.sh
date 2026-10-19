#!/usr/bin/env bash
# Первый запуск RADAR: проверки -> git -> что нажать в веб-интерфейсе.
set -e
echo "== 0. если gh нет, шаги a-c делаются в браузере =="
echo "== 1. python =="; python3 -V
echo "== 2. инжест (реальные данные) =="; python3 mvp/ingest.py --hours 8 --top 24
echo "== 3. LLM-шаг (без ключа пропустится) =="; python3 mvp/llm_enrich.py || true
echo "== 4. дашборд =="; python3 mvp/build_dashboard.py && cp dashboard.html index.html
echo "== 5. контракт =="; python3 tools/validate_contracts.py data/leads.json
if [ -d .git ]; then echo "== 6. git уже инициализирован - пропускаю =="; else
  git init -q
  git config user.name  >/dev/null 2>&1 || git config user.name  "radar-bot"     # без identity commit падает
  git config user.email >/dev/null 2>&1 || git config user.email "radar@local"
  git add -A && git commit -qm "radar: MVP" && echo "== 6. локальный коммит готов, можно push =="
fi
echo
echo "Дальше руками (2 минуты):"
echo "  a) gh repo create radar --public --source=. --push        # или git push на созданный вручную репо"
echo "  b) Settings -> Pages -> Source: GitHub Actions"
echo "  c) gh workflow run radar-ingest   ->  через 1-2 мин сайт отдаст обновлённый data/leads.json"
