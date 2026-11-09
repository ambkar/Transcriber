"""Сборка итогового DOCX."""
from docx import Document


EMPTY = "В записи не найдено."



def _add_text_block(doc, text):
    if not text:
        doc.add_paragraph(EMPTY)
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(("- ", "• ", "* ")):
            doc.add_paragraph(line[2:].strip(), style="List Bullet")
        else:
            doc.add_paragraph(line)



def build(path, scenario, title, summary, transcript):
    """transcript: [{time, speaker (с именем), text}]."""
    doc = Document()
    doc.add_heading(title, 0)


    n = 1
    doc.add_heading(f"{n}) Саммари", 1)
    _add_text_block(doc, summary)


    n += 1
    doc.add_heading(f"{n}) Расшифровка", 1)
    for t in transcript:
        p = doc.add_paragraph()
        p.add_run(f"[{t['time']}] {t['speaker']}: ").bold = True
        p.add_run(t["text"])


    doc.save(str(path))
