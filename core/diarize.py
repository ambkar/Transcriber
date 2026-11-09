"""Разделение спикеров: sherpa-onnx (pyannote segmentation + TitaNet)."""
from . import models

AUTO_THRESHOLD = 0.75   # больше значение = меньше спикеров
MIN_SHARE = 0.05        # спикеры с долей речи < 5% считаются шумом


def merge_minor(segments):
    if not segments:
        return segments
    talk = {}
    for s, e, spk in segments:
        talk[spk] = talk.get(spk, 0.0) + (e - s)
    total = sum(talk.values()) or 1.0
    major = {k for k, v in talk.items() if v / total >= MIN_SHARE}
    if not major or len(major) == len(talk):
        return segments
    majors = [x for x in segments if x[2] in major]

    def gap(m, s, e):
        return max(m[0] - e, s - m[1], 0.0)

    return [x if x[2] in major else (x[0], x[1], min(majors, key=lambda m: gap(m, x[0], x[1]))[2])
            for x in segments]

def run(job, audio, num_speakers):
    """Возвращает список (start, end, speaker_id). num_speakers=0 - автоопределение."""
    import sherpa_onnx

    seg_path, emb_path = models.diar_paths()
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(seg_path)),
            num_threads=4),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(emb_path), num_threads=4),
                clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers if num_speakers > 0 else -1,
            threshold=AUTO_THRESHOLD),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise RuntimeError("Неверная конфигурация диаризации (проверьте файлы в Models/diarization)")
    sd = sherpa_onnx.OfflineSpeakerDiarization(config)

    def callback(done, total):
        job.progress("Определяем спикеров", done / max(total, 1),
                     f"{done} из {total}")
        return 1 if job.cancel_flag.is_set() else 0

    job.progress("Определяем спикеров", 0.0)
    try:
        result = sd.process(audio, callback=callback).sort_by_start_time()
    except TypeError:
        result = sd.process(audio).sort_by_start_time()
    job.check()
    segments = [(r.start, r.end, r.speaker) for r in result]
    if num_speakers <= 0:
        segments = merge_minor(segments)
    return segments
