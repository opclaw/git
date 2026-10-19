# RADAR MVP. Только python3, зависимостей нет.
.PHONY: ingest llm build check demo run

ingest:
	python3 mvp/ingest.py --hours 8 --top 24

llm:
	python3 mvp/llm_enrich.py

build:
	python3 mvp/build_dashboard.py
	cp dashboard.html index.html

check:
	python3 tools/validate_contracts.py data/leads.json

run: ingest build check
	@echo "готово; открыть deploy/index.html"

demo: build
	@echo "локальный сервер: python3 -m http.server 8080  (затем index.html)"
