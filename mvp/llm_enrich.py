#!/usr/bin/env python3
"""Единственное место в системе, где живёт модель. Детерминизм (числа, скор, дедуп) ей не отдаём.

Три задачи, где LLM экономит недели ручной работы:
  1) classify: README+topics -> PS-xx, доменные теги, тип проекта (для fit_internal вместо ключевых слов);
  2) summary : 5 строк «что решает / чем / для кого / ограничения» для карточки Т2;
  3) brief   : «куда применить у нас» 3 пункта для Т3.
Всё кэшируется по sha256(README + model + prompt_ver): повторный вызов за тот же репо = 0 токенов.
"""
import argparse, hashlib, json, os, pathlib, re, sys, urllib.request

CACHE = pathlib.Path(os.environ.get("RADAR_LLM_CACHE", ".llm_cache"))
ENDPOINTS = {
    "github": ("https://models.github.ai/inference/chat/completions",
               os.environ.get("GITHUB_TOKEN"), "openai/gpt-4.1-mini"),
    "openai": ("https://api.openai.com/v1/chat/completions",
               os.environ.get("OPENAI_API_KEY"), os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")),
}
PROMPT_VER = "v1"
SYS = ("Ты - аналитик open-source. Отвечай строго JSON без пояснений. Не выдумывай: если факта нет в тексте, пиши null.")
USR = """Репозиторий: {repo}
Описание: {desc}
Topics: {topics}
README (первые 3000 символов):
{readme}

Верни JSON: {{"ps":"PS-infer|PS-data|PS-web|PS-ml|PS-infra|PS-sec|PS-dev|PS-doc|PS-unknown",
"tags":["не более 5, строчные"],"what":"что решает, 1 предложение","by_what":"на чём реализовано",
"for_whom":"кому полезно","limits":"ограничения/чего нет","apply":["3 конкретных сценария применения внутри продуктовой команды"]}}"""


def client():
    """Порядок выбора: (1) любой OpenAI-совместимый эндпоинт, (2) OpenAI, (3) GitHub Models - он закрыт, см. retired()."""
    base = os.environ.get("RADAR_LLM_BASE", "").rstrip("/")
    key = os.environ.get("RADAR_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if base and key:
        return "custom", f"{base}/chat/completions", key, os.environ.get("RADAR_MODEL", "openai/gpt-4.1-mini")
    for name in ("openai", "github"):
        url, k, model = ENDPOINTS[name]
        if k: return name, url, k, os.environ.get("RADAR_MODEL", model)
    return None


def retired(url, key):
    """GitHub Models закрыт 2026-07-30 (docs.github.com/en/github-models). С тех пор models.github.ai
    отвечает `200 text/plain OK` на ЛЮБОЙ путь и токен - выглядит как успех, а это муляж.
    Проверяем одним запросом, чтобы не жечь 25 вызовов и не маскировать проблему."""
    if "models.github.ai" not in url:
        return False
    hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
           "X-GitHub-Api-Version": "2022-11-28"}
    body = json.dumps({"model": "openai/gpt-4.1-mini", "max_tokens": 1,
                       "messages": [{"role": "user", "content": "ping"}]}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=hdr), timeout=30) as r:
            ct, raw = r.headers.get("Content-Type", ""), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        ct = (e.headers.get("Content-Type", "") if e.headers else "")
        raw = (e.read() or b"").decode("utf-8", "replace")
    except Exception as e:
        return False                                   # сеть/таймаут - это не про «закрыт», пусть решит основной цикл
    return "text/plain" in ct or raw.strip() in ("OK", "")


def call(url, key, model, prompt, readme, repo, desc, topics):
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 700,
                       "messages": [{"role": "system", "content": SYS},
                                    {"role": "user", "content": prompt.format(repo=repo, desc=desc, topics=topics, readme=readme[:3000])}]}).encode()
    hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if "models.github.ai" in url:                    # без этого заголовка Models отвечает не JSON
        hdr["X-GitHub-Api-Version"] = "2022-11-28"
    req = urllib.request.Request(url, data=body, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, raw = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, raw = e.code, (e.read() or b"").decode("utf-8", "replace")
    if not raw.strip():
        raise RuntimeError(f"пустой ответ (HTTP {status}) - проверь, что GitHub Models включён для репо")
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"HTTP {status}, ответ не JSON: {raw[:160]!r}")
    if status >= 400:
        raise RuntimeError(f"HTTP {status} от модели: {raw[:160]!r}")
    txt = d["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise RuntimeError(f"модель ответила не JSON: {txt[:120]!r}")
    return json.loads(m.group(0))


def main():
    here = pathlib.Path(__file__).resolve().parent
    dflt = next((str(x) for x in (here.parent / "data/leads.json", here / "data/leads.json") if x.exists()), str(here / "data/leads.json"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="i", default=dflt)
    ap.add_argument("--out", default=None)
    ap.add_argument("--max", type=int, default=25)
    ap.add_argument("--strict", action="store_true", help="падать при сбоях модели; по умолчанию - нет, LLM не блокирует выдачу")
    a = ap.parse_args()
    src = pathlib.Path(a.i); doc = json.loads(src.read_text(encoding="utf-8"))
    cli = client()
    if not cli:
        print("нет GITHUB_TOKEN/OPENAI_API_KEY - пропускаю LLM-шаг (детерминированная часть уже готова)", file=sys.stderr)
        return 0
    name, url, key, model = cli
    if retired(url, key):
        print("::warning::GitHub Models закрыт 2026-07-30: models.github.ai отвечает 200 text/plain на любой путь. "
              "LLM-обогащение отключено, детерминированная часть (числа, скор, дедуп) от этого не зависит. "
              "Чтобы вернуть обогащение: secrets RADAR_LLM_BASE + RADAR_API_KEY (Groq/OpenRouter/Azure Foundry/OpenAI).",
              file=sys.stderr)
        return 0
    CACHE.mkdir(exist_ok=True)
    done = hits = 0
    errors = []
    for l in doc["leads"][:a.max]:
        if l.get("llm"): hits += 1; continue
        try:
            readme = urllib.request.urlopen(urllib.request.Request(
                f"https://raw.githubusercontent.com/{l['repo']}/HEAD/README.md",
                headers={"User-Agent": "radar"}), timeout=20).read().decode("utf-8", "ignore")
        except Exception:
            readme = l.get("description") or ""
        h = hashlib.sha256(f"{PROMPT_VER}|{model}|{l['repo']}|{readme}".encode()).hexdigest()[:24]
        try:                                                    # ни один вызов модели не роняет конвейер:
            cf = CACHE / f"{h}.json"                            # числа уже посчитаны без LLM
            if cf.exists():
                obj = json.loads(cf.read_text())
            else:
                obj = call(url, key, model, USR, readme, l["repo"], l.get("description") or "", " ".join(l.get("topics") or []))
                if obj: cf.write_text(json.dumps(obj, ensure_ascii=False))
                done += 1
            if not obj:
                errors.append(f"{l['repo']}: модель вернула пустой/непарсимый ответ")
                continue
            obj["model"], obj["prompt_ver"] = model, PROMPT_VER
            l["llm"] = obj
            if obj.get("ps") and obj["ps"] != l.get("problem_statement"):
                l["problem_statement"] = obj["ps"]; l["fit_internal"] = round(max(l.get("fit_internal", 0), 0.45), 2)
        except Exception as e:
            errors.append(f"{l['repo']}: {type(e).__name__}: {str(e)[:120]}")
    src.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"LLM[{name}/{model}]: новых вызовов {done}, из кэша {hits}, заполнено {sum(1 for l in doc['leads'] if l.get('llm'))}/{len(doc['leads'])}")
    if errors:
        # LLM не имеет права валить конвейер: числа уже посчитаны без неё. Но и молчать нельзя.
        print(f"::warning::LLM-шаг дал сбой на {len(errors)} репо, выдача не заблокирована. Пример: {errors[0]}", file=sys.stderr)
    if a.strict and errors:
        return 1
    return 0


sys.exit(main())
