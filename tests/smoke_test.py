"""Teste de ponta a ponta sem internet: gera uma "live" sintética e roda detect → rank → render.

  python tests/smoke_test.py
Cria um vídeo de 3 min com dois picos (barulho alto + chat com kkkk + falas de reação) em 50s e 130s
e verifica se o pipeline acha esses picos e gera cortes 1080x1920.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("ANTHROPIC_API_KEY", None)  # força ranking por sinais (sem custo)

from clipper.__main__ import process  # noqa: E402
from clipper.config import data_dir  # noqa: E402
from clipper.review import all_clips, gallery  # noqa: E402

PEAKS = (50, 130)


def make_video(path: Path, dur: int = 180) -> None:
    vol = "+".join(f"between(t,{p},{p+3})*12" for p in PEAKS)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={dur}",
        "-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.02:duration={dur}:sample_rate=44100",
        "-af", f"volume='1+{vol}':eval=frame",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path),
    ], check=True)


def make_transcript(dur: int = 180) -> list[dict]:
    segs = []
    for t in range(0, dur, 6):
        hot = any(p - 3 <= t <= p + 6 for p in PEAKS)
        text = "MANO NÃO ACREDITO KKKKK caraca" if hot else "vamos lá pessoal pegar o carro"
        ws = text.split()
        step = 5.0 / len(ws)
        words = [{"start": t + i * step, "end": t + (i + 1) * step, "word": w} for i, w in enumerate(ws)]
        segs.append({"start": t, "end": t + 5, "text": text, "words": words})
    return segs


def make_chat(path: Path, dur: int = 180) -> None:
    lines = []
    for t in range(0, dur * 1000, 2000):
        n = 1
        if any(p * 1000 + 2000 <= t <= p * 1000 + 9000 for p in PEAKS):
            n = 15
        for k in range(n):
            text = "KKKKKKK" if n > 1 else "salve"
            lines.append(json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": str(t + k), "actions": [
                {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {"message": {"runs": [{"text": text}]}}}}}
            ]}}))
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="clipper_smoke_"))
    cfg = {
        "data_dir": str(work / "data"),
        "detect": {"top_n": 5, "pre_roll_s": 12, "post_roll_s": 8, "min_clip_s": 15, "max_clip_s": 30},
        "llm": {"enabled": False, "keep_top": 2},
        "render": {"crf": 30},
    }
    root = data_dir(cfg)
    vdir = root / "videos" / "synthetic"
    vdir.mkdir(parents=True)
    make_video(vdir / "source.mp4")
    (vdir / "transcript.json").write_text(json.dumps(make_transcript()), encoding="utf-8")
    make_chat(vdir / "source.live_chat.json")
    (vdir / "meta.json").write_text(json.dumps({
        "video_id": "synthetic", "title": "Live teste GTA 6", "credit": "@teste", "authorization": "teste",
        "url": None}), encoding="utf-8")

    clips = process(vdir, cfg, root, skip_transcribe=True)
    assert len(clips) == 2, clips
    metas = [m for _, m in all_clips(root)]
    for m in metas:
        assert any(m["start"] <= p <= m["end"] for p in PEAKS), f"corte fora dos picos: {m['start']}-{m['end']}"
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
         "-of", "json", str(clips[0] / "clip.mp4")], check=True, capture_output=True, text=True).stdout)
    assert (probe["streams"][0]["width"], probe["streams"][0]["height"]) == (1080, 1920), probe
    print("OK:", [(m["start"], m["end"]) for m in metas])
    print("Galeria:", gallery(root))
    print("Primeiro corte:", clips[0] / "clip.mp4")


if __name__ == "__main__":
    main()
