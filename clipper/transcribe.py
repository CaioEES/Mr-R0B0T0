"""Etapa 2: transcrição com timestamps por palavra (faster-whisper)."""
from __future__ import annotations

from pathlib import Path

from .config import read_json, write_json


def transcribe(vdir: Path, cfg: dict) -> list[dict]:
    out = vdir / "transcript.json"
    cached = read_json(out)
    if cached is not None:
        return cached

    from faster_whisper import WhisperModel  # import tardio: pesado

    tcfg = cfg.get("transcribe", {})
    model = WhisperModel(
        tcfg.get("model", "small"),
        device=tcfg.get("device", "auto"),
        compute_type=tcfg.get("compute_type", "int8"),
    )
    segments, _info = model.transcribe(
        str(vdir / "source.mp4"),
        language=tcfg.get("language", "pt"),
        word_timestamps=True,
        vad_filter=True,
    )
    result = []
    for s in segments:
        result.append({
            "start": s.start, "end": s.end, "text": s.text.strip(),
            "words": [{"start": w.start, "end": w.end, "word": w.word.strip()} for w in (s.words or [])],
        })
    write_json(out, result)
    return result


def text_between(transcript: list[dict], start: float, end: float) -> str:
    return " ".join(s["text"] for s in transcript if s["end"] > start and s["start"] < end)


def words_between(transcript: list[dict], start: float, end: float) -> list[dict]:
    words = []
    for s in transcript:
        if s["end"] <= start or s["start"] >= end:
            continue
        for w in s.get("words") or []:
            if w["start"] >= start and w["end"] <= end:
                words.append(w)
    return words
