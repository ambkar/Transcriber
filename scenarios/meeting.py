"""Сценарий «Созвон»: саммари и расшифровка по спикерам."""
from core import media, models, pipeline
from core.llm import LLM, detect_names, summarize



def run(job):
    try:
        ctx = pipeline.prepare(job)
        title, turns = ctx["title"], ctx["turns"]


        job.progress("Загружаем модель анализа", None, "Это может занять минуту")
        llm = LLM(models.asset_dir(ctx["profile"]["llm"]))
        try:
            job.progress("Анализируем текст", 0.0, "Определяем имена спикеров")
            names = detect_names(llm, turns)
            lines = pipeline.lines(turns, names)
            summary = summarize(job, llm, lines, "рабочий созвон")
        finally:
            llm.release()


        rows = pipeline.transcript_rows(turns, names)
        docx_path = pipeline.save_docx(job, "meeting", title, summary, rows)
        return {"scenario": "meeting", "title": title, "summary": summary,
                "transcript": rows, "docx_path": docx_path}
    finally:
        media.cleanup(job.id)
