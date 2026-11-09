"""Общие шаги обоих сценариев: подготовка расшифровки и сохранение результата."""
from pathlib import Path


import soundfile as sf


from . import asr, config, diarize, docx_export, media, models



def fmt_time(t):
    t = int(t)
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"



def speaker_label(num, names):
    name = names.get(num)
    return f"Спикер {num} ({name})" if name else f"Спикер {num}"



def prepare(job):
    """Модели -> аудио -> спикеры -> текст. Возвращает {title, turns}."""
    p = job.params
    profile = models.PROFILES[p["profile"]]


    models.ensure_profile(job, p["profile"])
    job.check()


    wav = config.WORK / f"{job.id}_audio.wav"
    if p["source_type"] == "url":
        raw, title = media.download_audio(job, p["source"])
        job.progress("Готовим аудио", None, "Извлекаем звук...")
        media.extract_audio(raw, wav)
        raw.unlink(missing_ok=True)
    else:
        src = Path(p["source"]).expanduser()
        title = src.stem
        job.progress("Готовим аудио", None, "Извлекаем звук...")
        media.extract_audio(src, wav)
    job.check()


    audio, sr = sf.read(str(wav), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    duration = len(audio) / sr


    segments = diarize.run(job, audio, p["speakers"])
    chunks = asr.make_chunks(segments, duration)
    if not chunks:
        raise RuntimeError("В записи не обнаружена речь")


    turns = asr.transcribe(job, audio, chunks, models.asset_dir(profile["asr"]),
                           p.get("glossary", ""), duration)
    asr.release()
    turns = asr.repair_turns(turns)
    if not turns:
        raise RuntimeError("Не удалось распознать речь")
    return {"title": title, "turns": turns, "profile": profile}



def lines(turns, names):
    return [f"[{fmt_time(t['start'])}] {speaker_label(t['speaker'], names)}: {t['text']}"
            for t in turns]



def transcript_rows(turns, names):
    return [{"time": fmt_time(t["start"]), "speaker": speaker_label(t["speaker"], names),
             "text": t["text"]} for t in turns]



def save_docx(job, scenario, title, summary, rows):
    job.finalize()
    path = media.unique_path(config.FINAL, media.sanitize(title), ".docx")
    docx_export.build(path, scenario, title, summary, rows)
    return str(path)
