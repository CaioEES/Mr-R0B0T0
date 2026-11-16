"""Etapa 1: descobre e baixa VODs novos dos canais autorizados (yt-dlp)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import write_json


def list_recent(url: str, limit: int) -> list[dict]:
    """Lista os vídeos mais recentes de um canal sem baixar."""
    out = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--playlist-end", str(limit), "-J", url],
        check=True, capture_output=True, text=True,
    ).stdout
    data = json.loads(out)
    entries = data.get("entries") or [data]
    return [{"id": e["id"], "url": e.get("url") or e.get("webpage_url"), "title": e.get("title")} for e in entries if e]


def download(video_url: str, dest: Path, max_height: int, with_chat: bool) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp", video_url,
        "-f", f"bv*[height<={max_height}]+ba/b[height<={max_height}]",
        "--merge-output-format", "mp4",
        "-o", str(dest / "source.%(ext)s"),
        "--write-info-json", "--no-playlist",
    ]
    if with_chat:
        # live_chat vira "legenda" no yt-dlp (YouTube lives); falha silenciosa se não houver
        cmd += ["--write-subs", "--sub-langs", "live_chat"]
    subprocess.run(cmd, check=True)
    return dest / "source.mp4"


def ingest(cfg: dict, root: Path) -> list[Path]:
    """Baixa vídeos novos. Retorna diretórios de vídeos baixados nesta rodada."""
    icfg = cfg.get("ingest", {})
    new_dirs = []
    for ch in cfg.get("channels", []):
        try:
            recent = list_recent(ch["url"], ch.get("max_videos", 2))
        except subprocess.CalledProcessError as e:
            print(f"[ingest] falha listando {ch['name']}: {e.stderr[:300] if e.stderr else e}")
            continue
        for v in recent:
            vdir = root / "videos" / v["id"]
            if (vdir / "source.mp4").exists():
                continue
            url = v["url"] if str(v["url"]).startswith("http") else f"https://www.youtube.com/watch?v={v['id']}"
            print(f"[ingest] baixando {v['title']!r} de {ch['name']}")
            try:
                download(url, vdir, icfg.get("max_height", 1080), icfg.get("download_chat", True))
            except subprocess.CalledProcessError as e:
                print(f"[ingest] falha no download {v['id']}: {e}")
                continue
            write_json(vdir / "meta.json", {
                "video_id": v["id"], "title": v["title"], "url": url,
                "channel": ch["name"], "credit": ch.get("credit", ch["name"]),
                "authorization": ch["authorization"],
            })
            new_dirs.append(vdir)
    return new_dirs


def register_local(video_path: Path, root: Path, title: str, credit: str, authorization: str) -> Path:
    """Registra um arquivo local (ex.: VOD que o streamer te enviou) como se fosse baixado."""
    vid = video_path.stem.replace(" ", "_")[:40]
    vdir = root / "videos" / vid
    vdir.mkdir(parents=True, exist_ok=True)
    target = vdir / "source.mp4"
    if not target.exists():
        target.symlink_to(video_path.resolve())
    write_json(vdir / "meta.json", {
        "video_id": vid, "title": title, "url": None, "channel": credit,
        "credit": credit, "authorization": authorization,
    })
    return vdir
