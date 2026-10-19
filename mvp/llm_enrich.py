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
    for name in ("openai", "github"):                      # приоритет: платной ключ, иначе бесплатный GitHub Models
        url, key, model = ENDPOINTS[name]
        if key: return name, url, key, os.environ.get("RADAR_MODEL", model)
    return None


def call(url, key, model, prompt, readme, repo, desc, topics):
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 700,
                       "messages": [{"role": "system", "content": SYS},
                                    {"role": "user", "content": prompt.format(repo=repo, desc=desc, topics=topics, readme=readme[:3000])}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        txt = json.load(r)["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0)) if m else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--in", dest="i", default="data/leads.json")
    ap.add_argument("--out", default=None); ap.add_argument("--max", type=int, default=25); a = ap.parse_args()
    src = pathlib.Path(a.i); doc = json.loads(src.read_text(encoding="utf-8"))
    cli = client()
    if not cli:
        print("нет GITHUB_TOKEN/OPENAI_API_KEY - пропускаю LLM-шаг (детерминированная часть уже готова)", file=sys.stderr)
        return 0
    name, url, key, model = cli
    CACHE.mkdir(exist_ok=True)
    done = hits = 0
    for l in doc["leads"][:a.max]:
        if l.get("llm"): hits += 1; continue
        try:
            readme = urllib.request.urlopen(urllib.request.Request(
                f"https://raw.githubusercontent.com/{l['repo']}/HEAD/README.md",
                headers={"User-Agent": "radar"}), timeout=20).read().decode("utf-8", "ignore")
        except Exception:
            readme = l.get("description") or ""
        h = hashlib.sha256(f"{PROMPT_VER}|{model}|{l['repo']}|{readme}".encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            obj = json.loads(cf.read_text())
        else:
            obj = call(url, key, model, USR, readme, l["repo"], l.get("description") or "", " ".join(l.get("topics") or []))
            if obj: cf.write_text(json.dumps(obj, ensure_ascii=False))
            done += 1
        if not obj: continue
        obj["model"], obj["prompt_ver"] = model, PROMPT_VER
        l["llm"] = obj
        if obj.get("ps") and obj["ps"] != l.get("problem_statement"):
            l["problem_statement"] = obj["ps"]; l["fit_internal"] = round(max(l.get("fit_internal", 0), 0.45), 2)
    src.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"LLM[{name}/{model}]: новых вызовов {done}, из кэша {hits} - стоимость ~{done*1500/1e6:.4f}M токенов")
    return 0


sys.exit(main())
