# RADAR — система раннего обнаружения и проверки GitHub-репозиториев

**Как это работает без сервера:** GitHub Actions по cron каждые 30 мин качает почасовые дампы
событий (data.gharchive.org), считает звёздную динамику, заворачивает вердикты в `data/leads.json`,
GitHub Pages отдаёт `index.html`. LLM-шаг (GitHub Models по токену задачи) дополняет карточку
классификацией и 5 строками «что решает» — с кэшем, поэтому каждый репо читается моделью один раз.

    make run     # локально: инжест -> дашборд -> проверка контракта
    make demo    # открыть собранный дашборд на http://localhost:8080/index.html

## Настройка (15 минут, один раз)

1. Создать **публичный** репозиторий, `git push` этого каталога.
2. Settings → Pages → Source: **GitHub Actions**.
3. Settings → Actions → General → Workflow permissions: **Read and write permissions** (иначе `git push` из cron не пройдёт).
4. Проверить: `gh workflow run radar-ingest` → через пару минут обновится `data/leads.json`, а сайт — `https://<user>.github.io/<repo>/`.
5. Опционально: `gh secret set TELEGRAM_BOT_TOKEN`, `gh variable set TELEGRAM_CHAT_ID` (дайджест),
   `gh secret set OPENAI_API_KEY` (если захотим модель вне каталога GitHub Models).

Документы процесса: `docs/TEAMS.md` (команды и ритуалы), `docs/METRICS.md` (метрики и формула),
`docs/RED_TEAM.md` (право вето и rubric), `docs/BACKLOG.csv` (71 задача), `docs/HOW_IT_RUNS.md` (архитектура).
