"""Запуск: python app.py"""
import subprocess
import threading
import webbrowser
from pathlib import Path


import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel


from core import config, jobs, media, models
from scenarios import meeting, video


HOST, PORT = "127.0.0.1", 8000


config.ensure_dirs()
media.clean_work_dir()


app = FastAPI(title="Транскрибатор")
app.mount("/static", StaticFiles(directory=config.BASE / "static"), name="static")
templates = Jinja2Templates(directory=str(config.BASE / "templates"))



class StartRequest(BaseModel):
    scenario: str            # video | meeting
    source_type: str         # url | file
    source: str
    profile: str
    speakers: int = 0        # 0 = автоопределение
    glossary: str = ""



@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html",
                                      {"profiles": models.profiles_info()})



@app.post("/api/pick-file")
def pick_file():
    return {"path": media.pick_file_dialog()}



@app.post("/api/start")
def start(req: StartRequest):
    if req.scenario not in ("video", "meeting"):
        raise HTTPException(400, "Неизвестный сценарий")
    if req.profile not in models.PROFILES:
        raise HTTPException(400, "Неизвестный профиль модели")
    if req.scenario == "meeting" and req.source_type != "file":
        raise HTTPException(400, "Для созвона нужен файл записи")
    source = req.source.strip()
    if not source:
        raise HTTPException(400, "Укажите ссылку или файл")
    if req.source_type == "file":
        if not Path(source).expanduser().is_file():
            raise HTTPException(400, "Файл не найден: " + source)
    elif not source.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "Ссылка должна начинаться с http:// или https://")


    params = req.model_dump()
    params["source"] = source
    params["speakers"] = max(0, min(int(params["speakers"]), 10))
    runner = video.run if req.scenario == "video" else meeting.run
    try:
        jobs.start(runner, params)
    except jobs.Busy:
        raise HTTPException(409, "Уже выполняется другая задача")
    return {"ok": True}



@app.get("/api/status")
def status():
    return jobs.snapshot()



@app.post("/api/cancel")
def cancel():
    jobs.cancel()
    return {"ok": True}



@app.post("/api/reset")
def reset():
    jobs.reset()
    return {"ok": True}



def _docx_path() -> Path:
    path = jobs.result_docx_path()
    if not path or not Path(path).is_file():
        raise HTTPException(404, "Файл не найден")
    return Path(path)



@app.post("/api/reveal")
def reveal():
    subprocess.run(["open", "-R", str(_docx_path())], check=False)
    return {"ok": True}



@app.get("/api/download")
def download():
    path = _docx_path()
    return FileResponse(path, filename=path.name)



if __name__ == "__main__":
    threading.Timer(1.2, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
