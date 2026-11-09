"""Одна фоновая задача + состояние для интерфейса."""
import threading
import traceback
import uuid


class Busy(Exception):
    pass


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, params):
        self.id = uuid.uuid4().hex[:8]
        self.params = params
        self.status = "running"      # running | done | error | cancelled
        self.label = "Запуск..."
        self.fraction = 0.0          # None = неопределённый прогресс
        self.detail = ""
        self.finalizing = False
        self.result = None
        self.error = None
        self.cancel_flag = threading.Event()

    def progress(self, label, fraction=None, detail=""):
        self.label = label
        self.fraction = None if fraction is None else max(0.0, min(1.0, float(fraction)))
        self.detail = detail

    def finalize(self):
        self.finalizing = True
        self.label = "Готовим итоговый файл. Еще немного."
        self.fraction = None
        self.detail = ""

    def check(self):
        if self.cancel_flag.is_set():
            raise Cancelled()


_lock = threading.Lock()
_current = None


def start(runner, params):
    global _current
    with _lock:
        if _current is not None and _current.status == "running":
            raise Busy()
        job = Job(params)
        _current = job
    threading.Thread(target=_run, args=(runner, job), daemon=True).start()


def _run(runner, job):
    try:
        job.result = runner(job)
        job.status = "done"
    except Cancelled:
        job.status = "cancelled"
    except Exception as e:
        traceback.print_exc()
        job.status = "error"
        job.error = f"{type(e).__name__}: {e}"


def snapshot():
    j = _current
    if j is None:
        return {"status": "idle"}
    data = {"status": j.status, "label": j.label, "fraction": j.fraction,
            "detail": j.detail, "finalizing": j.finalizing}
    if j.status == "done":
        data["result"] = j.result
    if j.status == "error":
        data["error"] = j.error
    return data


def cancel():
    if _current is not None and _current.status == "running":
        _current.cancel_flag.set()


def reset():
    global _current
    with _lock:
        if _current is not None and _current.status != "running":
            _current = None


def result_docx_path():
    if _current is not None and _current.status == "done" and _current.result:
        return _current.result.get("docx_path")
    return None
