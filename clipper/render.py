"""Etapa 4: gera o corte vertical 9:16 com fundo desfocado e legenda queimada (ASS)."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .config import write_json
from .transcribe import words_between


def _ts(t: float) -> str:
    t = max(t, 0.0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(words: list[dict], clip_start: float, hook: str, rcfg: dict, duration: float) -> str:
    W, H = rcfg.get("width", 1080), rcfg.get("height", 1920)
    font, size = rcfg.get("font", "DejaVu Sans"), rcfg.get("font_size", 78)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,520,1",
        f"Style: Hook,{font},{int(size*0.9)},&H0000F0FF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,8,60,60,260,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if hook:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(min(2.5, duration))},Hook,,0,0,0,,{_esc(hook.upper())}")
    # blocos de até 3 palavras, estilo "caption de Shorts"
    chunk: list[dict] = []
    for w in words + [None]:  # type: ignore[list-item]
        if w is not None:
            chunk.append(w)
        if chunk and (w is None or len(chunk) == 3 or w["word"].endswith((".", "!", "?", ","))):
            s, e = chunk[0]["start"] - clip_start, chunk[-1]["end"] - clip_start
            text = _esc(" ".join(x["word"] for x in chunk).upper())
            lines.append(f"Dialogue: 0,{_ts(s)},{_ts(max(e, s + 0.3))},Cap,,0,0,0,,{text}")
            chunk = []
    return "\n".join(lines) + "\n"


def render_clip(vdir: Path, clip: dict, transcript: list[dict], meta: dict, cfg: dict, root: Path) -> Path:
    rcfg = cfg.get("render", {})
    W, H = rcfg.get("width", 1080), rcfg.get("height", 1920)
    start, end = float(clip["start"]), float(clip["end"])
    dur = end - start
    cid = hashlib.sha1(f"{meta['video_id']}:{start:.2f}:{end:.2f}".encode()).hexdigest()[:10]
    cdir = root / "clips" / f"{meta['video_id']}_{cid}"
    out = cdir / "clip.mp4"
    if out.exists():
        return cdir
    cdir.mkdir(parents=True, exist_ok=True)

    ass = cdir / "captions.ass"
    ass.write_text(build_ass(words_between(transcript, start, end), start, clip.get("hook", ""), rcfg, dur),
                   encoding="utf-8")

    vf = (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:5,eq=brightness=-0.08[bgb];"
        f"[fg]scale={W}:-2[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,ass='{ass.as_posix()}'[v]"
    )
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-i", str(vdir / "source.mp4"), "-t", f"{dur:.2f}",
        "-filter_complex", vf, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(rcfg.get("crf", 20)), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-movflags", "+faststart", str(out),
    ]
    subprocess.run(cmd, check=True)

    hashtags = " ".join(clip.get("hashtags") or [])
    write_json(cdir / "clip.json", {
        "status": "pending",
        "video_id": meta["video_id"], "source_url": meta.get("url"), "source_title": meta.get("title"),
        "credit": meta.get("credit"), "authorization": meta.get("authorization"),
        "start": start, "end": end, "score": clip.get("score"), "llm_score": clip.get("llm_score"),
        "reason": clip.get("reason"), "title": clip.get("title", ""), "hook": clip.get("hook", ""),
        "description": f"Corte da live de {meta.get('credit')}. Original: {meta.get('url') or '-'}\n{hashtags}",
        "hashtags": clip.get("hashtags", []),
    })
    return cdir
