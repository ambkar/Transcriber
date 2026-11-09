"""Работа с файлами: ссылка, ffmpeg, диалог выбора файла, Finder."""
import re
import subprocess

from . import config
from .jobs import Cancelled

_INVALID = re.compile(r'[\\/:*?"<>|\n\r\t]+')


def sanitize(name, maxlen=120):
    name = _INVALID.sub(" ", name or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:maxlen].strip() or "Расшифровка"


def unique_path(folder, name, ext):
    path = folder / f"{name}{ext}"
    i = 2
    while path.exists():
        path = folder / f"{name} ({i}){ext}"
        i += 1
    return path


def normalize_url(url):
    url = url.strip()
    m = re.search(r"rutube\.ru/(?:play/embed|video)/([0-9a-f]{32})", url)
    return f"https://rutube.ru/video/{m.group(1)}/" if m else url


def pick_file_dialog():
    """Системный диалог macOS. Возвращает путь или пустую строку."""
    script = ('tell application "System Events"\n'
              "activate\n"
              'set f to choose file with prompt "Выберите видео или аудио"\n'
              "return POSIX path of f\n"
              "end tell")
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def clean_work_dir():
    for p in config.WORK.glob("*"):
        if p.is_file():
            p.unlink(missing_ok=True)


def cleanup(job_id):
    for p in config.WORK.glob(f"{job_id}_*"):
        p.unlink(missing_ok=True)


def extract_audio(src, dst):
    """Из любого видео/аудио делает wav 16 кГц моно. Исходный файл не трогает."""
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                        "-vn", "-ac", "1", "-ar", str(config.SR), str(dst)],
                       check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg не найден. Установите: brew install ffmpeg")
    except subprocess.CalledProcessError as e:
        raise RuntimeError("ffmpeg не смог обработать файл: " + (e.stderr or "")[-300:])


def download_audio(job, url):
    """Скачивает звук по ссылке. Возвращает (путь к файлу, название ролика)."""
    import yt_dlp

    url = normalize_url(url)
    template = str(config.WORK / f"{job.id}_raw.%(ext)s")

    def hook(d):
        job.check()
        if d.get("status") != "downloading":
            return
        done = d.get("downloaded_bytes") or 0
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if total:
            job.progress("Скачивание по ссылке", done / total,
                         f"{done / 1e6:.1f} / {total / 1e6:.1f} МБ")
        elif d.get("fragment_count"):
            idx = d.get("fragment_index") or 0
            job.progress("Скачивание по ссылке", idx / d["fragment_count"],
                         f"фрагмент {idx} из {d['fragment_count']}")
        else:
            job.progress("Скачивание по ссылке", None, f"{done / 1e6:.1f} МБ")

    base = {"format": "bestaudio/best", "outtmpl": template, "noplaylist": True,
            "quiet": True, "no_warnings": True, "retries": 5,
            "fragment_retries": 5, "progress_hooks": [hook]}
    yt_args = {"youtube": {"player_client": ["default", "web_safari"],
                           "player_js_version": ["actual"]}}
    attempts = [{}, {"extractor_args": yt_args},
                {"cookiesfrombrowser": ("chrome",), "extractor_args": yt_args}]

    last_error = None
    for extra in attempts:
        job.progress("Скачивание по ссылке", 0.0, "Подключаемся...")
        try:
            with yt_dlp.YoutubeDL({**base, **extra}) as ydl:
                info = ydl.extract_info(url, download=True)
            files = [p for p in config.WORK.glob(f"{job.id}_raw.*")
                     if not p.name.endswith(".part")]
            if files:
                return files[0], (info or {}).get("title") or "Видео"
        except Exception as e:
            if job.cancel_flag.is_set():
                raise Cancelled()
            last_error = e
            for p in config.WORK.glob(f"{job.id}_raw.*"):
                p.unlink(missing_ok=True)
    raise RuntimeError(f"Не удалось скачать видео: {last_error}. "
                       "Проверьте, что установлен deno (brew install deno) и обновлён yt-dlp.")
