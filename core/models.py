"""Реестр моделей и их скачивание в папку Models (без авторизации)."""
import tarfile
from urllib.parse import quote

import requests

from . import config
from .jobs import Cancelled

GH = "https://github.com/k2-fsa/sherpa-onnx/releases/download"

ASSETS = {
    "diar_seg": {
        "label": "Сегментация спикеров (pyannote 3.0)", "kind": "tar", "dir": "diarization",
        "url": f"{GH}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
    },
    "diar_emb": {
        "label": "Эмбеддинги голоса (TitaNet small)", "kind": "file", "dir": "diarization",
        "url": f"{GH}/speaker-recongition-models/nemo_en_titanet_small.onnx",
        "filename": "nemo_en_titanet_small.onnx",
    },
    "asr_turbo_q4": {
        "label": "Whisper large-v3-turbo (q4)", "kind": "hf",
        "repo": "mlx-community/whisper-large-v3-turbo-q4", "dir": "asr/whisper-large-v3-turbo-q4",
    },
    "asr_turbo": {
        "label": "Whisper large-v3-turbo", "kind": "hf",
        "repo": "mlx-community/whisper-large-v3-turbo", "dir": "asr/whisper-large-v3-turbo",
    },
    "llm_4b": {
        "label": "Qwen3-4B (4-bit)", "kind": "hf",
        "repo": "Qwen/Qwen3-4B-MLX-4bit", "dir": "llm/Qwen3-4B-MLX-4bit",
    },
    "llm_14b": {
        "label": "Qwen3-14B (4-bit)", "kind": "hf",
        "repo": "Qwen/Qwen3-14B-MLX-4bit", "dir": "llm/Qwen3-14B-MLX-4bit",
    },
    "llm_32b": {
        "label": "Qwen3-32B (4-bit)", "kind": "hf",
        "repo": "Qwen/Qwen3-32B-MLX-4bit", "dir": "llm/Qwen3-32B-MLX-4bit",
    },
}

PROFILES = {
    "light": {"title": "Лёгкий", "asr": "asr_turbo_q4", "llm": "llm_4b",
              "size_gb": 2.7, "ram": "8–16 ГБ",
              "desc": "Быстро и компактно. Анализ текста проще, имена и договорённости могут пропускаться."},
    "optimal": {"title": "Оптимальный", "asr": "asr_turbo", "llm": "llm_14b",
                "size_gb": 9.5, "ram": "16 ГБ",
                "desc": "Рекомендуется. Баланс качества и скорости для MacBook с 16 ГБ."},
    "powerful": {"title": "Мощный", "asr": "asr_turbo", "llm": "llm_32b",
                 "size_gb": 19.0, "ram": "24 ГБ",
                 "desc": "Лучший анализ текста. Нужен Mac с 24 ГБ памяти и больше."},
}


def profile_assets(profile_id):
    p = PROFILES[profile_id]
    return ["diar_seg", "diar_emb", p["asr"], p["llm"]]


def asset_dir(asset_id):
    return config.MODELS / ASSETS[asset_id]["dir"]


def diar_paths():
    d = config.MODELS / "diarization"
    return (d / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx",
            d / ASSETS["diar_emb"]["filename"])


def _marker(asset_id):
    return config.MODELS / ".markers" / asset_id


def is_ready(asset_id):
    return _marker(asset_id).exists()


def profile_ready(profile_id):
    return all(is_ready(a) for a in profile_assets(profile_id))


def profiles_info():
    return [{"id": pid, **p, "ready": profile_ready(pid)} for pid, p in PROFILES.items()]


# ---------- скачивание ----------

def _hf_files(repo):
    r = requests.get(f"https://huggingface.co/api/models/{repo}",
                     params={"blobs": "true"}, timeout=30)
    r.raise_for_status()
    out = []
    for s in r.json().get("siblings", []):
        name = s["rfilename"]
        if name == ".gitattributes":
            continue
        size = s.get("size") or (s.get("lfs") or {}).get("size") or 0
        out.append((f"https://huggingface.co/{repo}/resolve/main/{quote(name)}", name, int(size)))
    return out


def _head_size(url):
    try:
        r = requests.head(url, allow_redirects=True, timeout=30)
        return int(r.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def _plan(asset):
    d = config.MODELS / asset["dir"]
    if asset["kind"] == "hf":
        return [(u, d / name, size) for u, name, size in _hf_files(asset["repo"])]
    if asset["kind"] == "file":
        return [(asset["url"], d / asset["filename"], _head_size(asset["url"]))]
    name = asset["url"].rsplit("/", 1)[1]
    return [(asset["url"], d / name, _head_size(asset["url"]))]


class _Tracker:
    def __init__(self, job, total):
        self.job, self.total, self.done, self.label = job, total, 0, ""

    def add(self, n):
        self.done += n
        frac = self.done / self.total if self.total else None
        if self.total:
            detail = f"{_fmt(self.done)} / {_fmt(self.total)}"
        else:
            detail = _fmt(self.done)
        self.job.progress(f"Скачивание модели: {self.label}", frac, detail)


def _fmt(n):
    return f"{n / 1e9:.2f} ГБ" if n >= 1e9 else f"{n / 1e6:.0f} МБ"


def download_file(url, dest, tracker, check):
    """Скачивание с докачкой (.part)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have:
        tracker.add(have)
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, stream=True, headers=headers, timeout=60,
                      allow_redirects=True) as r:
        if r.status_code == 416:
            part.replace(dest)
            return
        r.raise_for_status()
        if have and r.status_code != 206:
            tracker.add(-have)
            have = 0
        with open(part, "ab" if have else "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                check()
                if chunk:
                    f.write(chunk)
                    tracker.add(len(chunk))
    part.replace(dest)


def _extract_tar(archive, dest_dir):
    with tarfile.open(archive) as tf:
        try:
            tf.extractall(dest_dir, filter="data")
        except TypeError:
            tf.extractall(dest_dir)
    archive.unlink(missing_ok=True)


def ensure_profile(job, profile_id):
    """Скачивает недостающие файлы профиля. Если всё уже есть, ничего не делает."""
    missing = [a for a in profile_assets(profile_id) if not is_ready(a)]
    if not missing:
        return
    job.progress("Скачивание модели", None, "Проверяем размер файлов...")
    plan, total = [], 0
    for a in missing:
        job.check()
        files = _plan(ASSETS[a])
        plan.append((a, files))
        total += sum(s for _, _, s in files)

    tracker = _Tracker(job, total)
    for a, files in plan:
        tracker.label = ASSETS[a]["label"]
        for url, dest, size in files:
            if dest.exists() and size and dest.stat().st_size == size:
                tracker.add(size)
                continue
            download_file(url, dest, tracker, job.check)
        if ASSETS[a]["kind"] == "tar":
            _, dest, _ = files[0]
            if dest.exists():
                _extract_tar(dest, dest.parent)
        _marker(a).write_text("ok")
