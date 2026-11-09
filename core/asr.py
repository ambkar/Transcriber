"""Распознавание речи: Whisper (mlx-whisper) по отрезкам из диаризации."""
import gc

from . import config

MAX_CHUNK = 28.0      # секунд (окно Whisper = 30)
MERGE_GAP = 0.8       # склеиваем реплики одного спикера, если пауза меньше
MIN_CHUNK = 0.3

HALLUCINATIONS = ("dimatorzok", "продолжение следует", "редактор субтитров",
                  "корректор а.кулакова", "субтитры подогнал")

import re

TERMINAL = re.compile(r'[.!?…]["»)]*\s')


def _words(t):
    return re.findall(r"\w+", t.lower())


def repair_turns(turns):
    turns = [dict(t) for t in turns]
    changed = True
    while changed:
        changed = False
        for i in range(1, len(turns) - 1):
            t = turns[i]
            if (len(t["text"].split()) <= 3
                    and turns[i - 1]["speaker"] == turns[i + 1]["speaker"] != t["speaker"]):
                del turns[i]
                changed = True
                break

    def merge(ts):
        out = []
        for t in ts:
            if out and out[-1]["speaker"] == t["speaker"]:
                out[-1]["text"] += " " + t["text"]
            else:
                out.append(dict(t))
        return out

    turns = merge(turns)
    for i in range(1, len(turns)):
        txt = turns[i]["text"].lstrip()
        if not txt or not txt[0].islower():
            continue
        m = TERMINAL.search(txt + " ")
        frag = txt[:m.end()].strip() if m else txt
        if len(frag.split()) > 8:
            continue
        rest = txt[len(frag):].strip() if m else ""
        prev = turns[i - 1]
        tail = " ".join(_words(prev["text"])[-15:])
        if " ".join(_words(frag)) not in tail:
            prev["text"] = prev["text"].rstrip() + " " + frag
        turns[i]["text"] = rest
    return merge([t for t in turns if t["text"].strip()])

def make_chunks(segments, duration):
    """segments: [(start, end, raw_speaker)] -> [{start, end, speaker(1..N)}]."""
    order, merged = {}, []
    for start, end, spk in sorted(segments, key=lambda s: s[0]):
        start, end = max(0.0, start), min(duration, end)
        if end - start < MIN_CHUNK:
            continue
        num = order.setdefault(spk, len(order) + 1)
        last = merged[-1] if merged else None
        if (last and last["speaker"] == num and start - last["end"] <= MERGE_GAP
                and end - last["start"] <= MAX_CHUNK):
            last["end"] = max(last["end"], end)
        else:
            merged.append({"start": start, "end": end, "speaker": num})

    chunks = []
    for c in merged:
        length = c["end"] - c["start"]
        if length <= MAX_CHUNK:
            chunks.append(c)
            continue
        parts = int(length // MAX_CHUNK) + 1
        step = length / parts
        for i in range(parts):
            chunks.append({"start": c["start"] + i * step,
                           "end": c["start"] + (i + 1) * step,
                           "speaker": c["speaker"]})
    return chunks


def _is_hallucination(text):
    low = text.lower()
    return any(h in low for h in HALLUCINATIONS)


def transcribe(job, audio, chunks, model_dir, glossary, duration):
    """Возвращает реплики [{start, speaker, text}] (соседние реплики спикера склеены)."""
    import mlx_whisper

    prompt = None
    if glossary.strip():
        prompt = "Термины и названия: " + ", ".join(
            t.strip() for t in glossary.replace("\n", ",").split(",") if t.strip()) + "."

    turns = []
    for i, c in enumerate(chunks):
        job.check()
        a = max(0.0, c["start"] - 0.1)
        b = min(duration, c["end"] + 0.3)
        piece = audio[int(a * config.SR):int(b * config.SR)]
        result = mlx_whisper.transcribe(
            piece, path_or_hf_repo=str(model_dir), language="ru",
            initial_prompt=prompt, condition_on_previous_text=False, verbose=None)
        text = (result.get("text") or "").strip()
        if text and not _is_hallucination(text):
            if turns and turns[-1]["speaker"] == c["speaker"]:
                turns[-1]["text"] += " " + text
            else:
                turns.append({"start": c["start"], "speaker": c["speaker"], "text": text})
        done = c["end"]
        job.progress("Распознаём речь", done / max(duration, 1),
                     f"{_fmt(done)} из {_fmt(duration)}")
    return turns


def _fmt(t):
    t = int(t)
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def release():
    """Освобождает память перед загрузкой LLM."""
    try:
        from mlx_whisper.transcribe import ModelHolder
        ModelHolder.model = None
        ModelHolder.model_path = None
    except Exception:
        pass
    gc.collect()
    try:
        import mlx.core as mx
        try:
            mx.clear_cache()
        except AttributeError:
            mx.metal.clear_cache()
    except Exception:
        pass
