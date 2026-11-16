"""Etapa 3: detecção de momentos (sinais baratos, sem LLM).

Sinais combinados por janela de tempo:
  - audio:    pico de volume (grito, risada, explosão) — RMS por janela, z-score
  - chat:     explosão de mensagens no live chat replay + peso extra para "kkkk", "😂", "LUL"
  - keywords: palavras de reação na transcrição ("mano", "não acredito", "caraca"...)
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np

from .config import write_json

SR = 16000

LAUGH_RE = re.compile(r"(k{3,}|(ha){2,}|(rs){2,}|😂|🤣|lul|kekw|omegalul)", re.I)
REACTION_WORDS = [
    "mano", "caraca", "caramba", "não acredito", "nao acredito", "meu deus", "socorro",
    "que isso", "olha isso", "mds", "nossa", "puts", "eita", "vish", "morri", "ridículo",
    "não não não", "corre", "pega ele", "bugou", "bug",
]


def zscore(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x
    sd = x.std()
    return (x - x.mean()) / sd if sd > 1e-9 else np.zeros_like(x)


def media_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def audio_energy(path: Path, window_s: float) -> np.ndarray:
    """RMS em dB por janela, lendo o áudio em streaming (funciona com lives de horas)."""
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        stdout=subprocess.PIPE,
    )
    n = int(SR * window_s)
    vals = []
    assert proc.stdout
    while True:
        buf = proc.stdout.read(n * 2)
        if not buf:
            break
        a = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(a * a)) if a.size else 0.0
        vals.append(20 * np.log10(rms + 1e-6))
    proc.wait()
    return np.array(vals, dtype=np.float32)


def load_chat(vdir: Path) -> list[tuple[float, str]]:
    """Lê o live chat replay do yt-dlp (source.live_chat.json, JSONL)."""
    files = list(vdir.glob("*.live_chat.json"))
    msgs: list[tuple[float, str]] = []
    if not files:
        return msgs
    for line in files[0].read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            obj = json.loads(line)
            r = obj["replayChatItemAction"]
            t = int(r["videoOffsetTimeMsec"]) / 1000.0
            for act in r.get("actions", []):
                item = act.get("addChatItemAction", {}).get("item", {})
                rend = item.get("liveChatTextMessageRenderer")
                if not rend:
                    continue
                text = "".join(
                    run.get("text") or run.get("emoji", {}).get("shortcuts", [""])[0]
                    for run in rend.get("message", {}).get("runs", [])
                )
                msgs.append((t, text))
        except (KeyError, ValueError, IndexError):
            continue
    return msgs


def chat_signal(msgs: list[tuple[float, str]], n_windows: int, window_s: float) -> np.ndarray:
    sig = np.zeros(n_windows, dtype=np.float32)
    for t, text in msgs:
        i = int(t / window_s)
        if 0 <= i < n_windows:
            sig[i] += 1.0 + (2.0 if LAUGH_RE.search(text) else 0.0)
    # chat reage com atraso de ~3-8s; suaviza e "puxa" para trás
    kernel = np.ones(5, dtype=np.float32) / 5
    sig = np.convolve(sig, kernel, mode="same")
    shift = int(4 / window_s)
    return np.concatenate([sig[shift:], np.zeros(shift, dtype=np.float32)])[:n_windows]


def keyword_signal(transcript: list[dict], n_windows: int, window_s: float) -> np.ndarray:
    sig = np.zeros(n_windows, dtype=np.float32)
    for s in transcript:
        low = s["text"].lower()
        hits = sum(low.count(w) for w in REACTION_WORDS) + 2 * len(LAUGH_RE.findall(low))
        if hits:
            i0, i1 = int(s["start"] / window_s), int(s["end"] / window_s) + 1
            sig[max(i0, 0):min(i1, n_windows)] += hits
    return sig


def find_candidates(vdir: Path, transcript: list[dict], cfg: dict) -> list[dict]:
    dcfg = cfg.get("detect", {})
    w = float(dcfg.get("window_s", 1.0))
    weights = dcfg.get("weights", {"audio": 0.35, "chat": 0.45, "keywords": 0.20})
    src = vdir / "source.mp4"
    duration = media_duration(src)

    audio = audio_energy(src, w)
    n = len(audio)
    # volume relativo à vizinhança (60s): um grito numa parte calma vale mais
    local = np.convolve(audio, np.ones(60) / 60, mode="same") if n > 60 else np.full(n, audio.mean())
    signals = {"audio": zscore(audio - local)}

    msgs = load_chat(vdir)
    if msgs:
        signals["chat"] = zscore(chat_signal(msgs, n, w))
    if transcript:
        signals["keywords"] = zscore(keyword_signal(transcript, n, w))

    total_w = sum(weights.get(k, 0) for k in signals) or 1.0
    score = sum(signals[k] * weights.get(k, 0) for k in signals) / total_w
    score = np.convolve(score, np.ones(3) / 3, mode="same")

    pre, post = float(dcfg.get("pre_roll_s", 20)), float(dcfg.get("post_roll_s", 10))
    min_len, max_len = float(dcfg.get("min_clip_s", 15)), float(dcfg.get("max_clip_s", 59))
    top_n = int(dcfg.get("top_n", 15))

    # non-maximum suppression: pega o maior pico, bloqueia a vizinhança, repete
    order = np.argsort(score)[::-1]
    taken = np.zeros(n, dtype=bool)
    cands = []
    for i in order:
        if len(cands) >= top_n or score[i] <= 0.5:
            break
        if taken[i]:
            continue
        t = i * w
        start, end = max(0.0, t - pre), min(duration, t + post)
        if end - start < min_len:
            end = min(duration, start + min_len)
        end = min(end, start + max_len)
        lo, hi = int(start / w), int(end / w) + 1
        taken[max(lo - int(pre / w), 0):hi] = True
        cands.append({
            "peak": round(t, 2), "start": round(start, 2), "end": round(end, 2),
            "score": round(float(score[i]), 3),
            "signals": {k: round(float(v[i]), 2) for k, v in signals.items()},
        })
    cands.sort(key=lambda c: c["start"])
    write_json(vdir / "candidates.json", cands)
    return cands
