from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MODELS = BASE / "Models"
WORK = BASE / "Work"
FINAL = BASE / "Final"
SR = 16000


def ensure_dirs():
    for d in (MODELS, WORK, FINAL, MODELS / ".markers"):
        d.mkdir(parents=True, exist_ok=True)
