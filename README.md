# Транскрибатор (локальное веб-приложение)

Расшифровка видео по ссылке (YouTube/Rutube) или из файла, а также расшифровка рабочих созвонов.
Всё работает локально на Mac с Apple Silicon. Модели скачиваются без авторизации при первом использовании.

## Установка

```bash
brew install ffmpeg deno          # deno нужен yt-dlp для YouTube
cd transcriber
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Запуск

```bash
python app.py
```

Откроется браузер на http://127.0.0.1:8000

## Папки

- `Models/` модели (скачиваются один раз, дальше берутся оттуда)
- `Work/` временное аудио (удаляется после создания итогового файла)
- `Final/` итоговые DOCX с названием видео

## Профили моделей

| Профиль | Распознавание речи | Анализ текста | Скачать | Память |
|---|---|---|---|---|
| Лёгкий | Whisper large-v3-turbo (q4) | Qwen3-4B 4-bit | ~2,7 ГБ | 8-16 ГБ |
| Оптимальный | Whisper large-v3-turbo | Qwen3-14B 4-bit | ~9,5 ГБ | 16 ГБ |
| Мощный | Whisper large-v3-turbo | Qwen3-32B 4-bit | ~19 ГБ | 24 ГБ |

Разделение спикеров во всех профилях: pyannote segmentation 3.0 + TitaNet small (sherpa-onnx).

## После установки

Когда всё заработает, зафиксируйте версии: `pip freeze > requirements.txt`
