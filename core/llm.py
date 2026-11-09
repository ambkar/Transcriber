"""LLM (mlx-lm): имена спикеров и саммари."""
import gc
import json
import re


SYSTEM = ("Ты аккуратный русскоязычный ассистент-аналитик. Отвечай по-русски, "
          "строго по тексту расшифровки, ничего не выдумывай. Названия, термины "
          "и аббревиатуры сохраняй как в тексте.")
CHUNK_CHARS = 12000



class LLM:
    def __init__(self, model_dir):
        from mlx_lm import load
        self.model, self.tokenizer = load(str(model_dir))


    def ask(self, user, max_tokens=1500):
        from mlx_lm import generate
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user}]
        try:
            prompt = self.tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=False, enable_thinking=False)
        except TypeError:
            prompt = self.tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=False)
        out = generate(self.model, self.tokenizer, prompt=prompt,
                       max_tokens=max_tokens, verbose=False)
        return strip_think(out)


    def release(self):
        self.model = self.tokenizer = None
        gc.collect()
        try:
            import mlx.core as mx
            try:
                mx.clear_cache()
            except AttributeError:
                mx.metal.clear_cache()
        except Exception:
            pass



def strip_think(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.replace("<think>", "").strip()



def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    raw = m.group(0)
    for candidate in (raw, re.sub(r",\s*([}\]])", r"\1", raw)):
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else {}
        except Exception:
            continue
    return {}



def chunk_lines(lines, max_chars=CHUNK_CHARS):
    chunks, cur, size = [], [], 0
    for line in lines:
        if cur and size + len(line) > max_chars:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks



class Steps:
    def __init__(self, job, total):
        self.job, self.total, self.i = job, max(total, 1), 0


    def step(self, text):
        self.job.check()
        self.job.progress("Анализируем текст", min(self.i / self.total, 0.98),
                          f"{text} ({self.i + 1} из {self.total})")
        self.i += 1



def resolve_names(mentions, speakers):
    votes = {}
    for m in mentions or []:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name") or "").strip()
        try:
            said = int(m.get("said_by"))
        except (TypeError, ValueError):
            continue
        kind = str(m.get("kind", "")).lower()
        if not name or said not in speakers:
            continue
        if kind.startswith("self"):
            owner = said
        elif kind.startswith("addr") and len(speakers) == 2:
            owner = [s for s in speakers if s != said][0]
        else:
            continue
        key = name.split()[0].lower()
        votes.setdefault(owner, {}).setdefault(key, []).append(name)
    names = {}
    for spk, groups in votes.items():
        key, variants = max(groups.items(), key=lambda kv: len(kv[1]))
        best = max(variants, key=len)
        if 2 <= len(best) <= 60:
            names[spk] = (best, len(variants))
    seen = {}
    for spk, (name, n) in sorted(names.items(), key=lambda kv: -kv[1][1]):
        seen.setdefault(name.lower(), spk)
    return {spk: names[spk][0] for spk in names if seen[names[spk][0].lower()] == spk}



def detect_names(llm, turns):
    words = {}
    for t in turns:
        words[t["speaker"]] = words.get(t["speaker"], 0) + len(t["text"].split())
    total = sum(words.values()) or 1
    speakers = sorted(k for k, v in words.items() if v / total >= 0.05)
    head, size = [], 0
    for t in turns:
        if t["speaker"] not in speakers:
            continue
        line = f"Спикер {t['speaker']}: {t['text']}"
        if size + len(line) > 9000:
            break
        head.append(line)
        size += len(line)
    prompt = (
        "Ниже начало расшифровки с метками «Спикер N». Найди упоминания имён участников "
        "разговора. Для каждого упоминания укажи: name (имя), said_by (номер спикера, который "
        "его произнёс), kind: «self», если спикер называет СВОЁ имя (меня зовут…, я…), "
        "или «addressed», если спикер называет имя СОБЕСЕДНИКА (обращение «привет, Лилит», "
        "«наш гость Лилит», представление гостя). Не включай людей, не участвующих в разговоре.\\n"
        'Верни ТОЛЬКО JSON: {"mentions": [{"name": "...", "said_by": 1, "kind": "addressed"}]}\\n\\n'
        + "\\n".join(head))
    data = parse_json(llm.ask(prompt, max_tokens=500))
    return resolve_names(data.get("mentions"), speakers)



def summarize(job, llm, lines, kind, steps=None):
    """Саммари по частям: сначала конспекты кусков, потом объединение."""
    chunks = chunk_lines(lines)
    steps = steps or Steps(job, len(chunks) + 1)
    notes = []
    for ch in chunks:
        steps.step("Конспект части")
        notes.append(llm.ask(
            f"Это фрагмент расшифровки ({kind}). Составь краткий конспект фрагмента: "
            "5–10 пунктов списком, каждый с новой строки через «- ». "
            "Только факты, цифры и решения из текста. "
            "Реплики ведущего или интервьюера — это вопросы, а не факты: не считай "
            "утверждение верным, пока собеседник его не подтвердил; если он возразил, "
            "так и напиши.\n\n" + ch, max_tokens=700))
    steps.step("Итоговое саммари")
    joined = "\n\n".join(notes)
    while len(joined) > 14000:
        groups = chunk_lines(joined.split("\n"), 10000)
        joined = "\n\n".join(llm.ask(
            "Сократи и объедини конспекты, сохрани важные факты, цифры и решения. "
            "Формат: пункты через «- ».\n\n" + g, max_tokens=700) for g in groups)
    return llm.ask(
        f"На основе конспектов частей ({kind}) напиши итоговое саммари: "
        "сначала абзац из 3–5 предложений о чём это, затем строка «Ключевые пункты:» "
        "и 5–10 пунктов списком через «- ».\n\n" + joined, max_tokens=900)
