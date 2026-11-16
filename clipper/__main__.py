"""CLI: python -m clipper <comando>

  run                 ingest → transcribe → detect → rank → render (+ gera review.html)
  process <dir>       roda as etapas 2-4 num vídeo já baixado (data/videos/<id>)
  add-local <arquivo> --title T --credit C --auth A   registra um VOD local autorizado
  review              lista pendentes e gera data/review.html
  approve <id> [--title T] / reject <id>
  publish [--dry-run] publica aprovados (respeita daily_limit)
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .config import data_dir, load_config, read_json
from .detect import find_candidates
from .ingest import ingest, register_local
from .publish_youtube import publish
from .rank_llm import rank
from .render import render_clip
from .review import all_clips, gallery, set_status


def process(vdir: Path, cfg: dict, root: Path, skip_transcribe: bool = False) -> list[Path]:
    meta = read_json(vdir / "meta.json") or {"video_id": vdir.name, "title": vdir.name, "credit": "?"}
    transcript: list[dict] = []
    if not skip_transcribe:
        from .transcribe import transcribe
        print(f"[transcribe] {vdir.name}")
        transcript = transcribe(vdir, cfg)
    else:
        transcript = read_json(vdir / "transcript.json", [])
    print(f"[detect] {vdir.name}")
    cands = find_candidates(vdir, transcript, cfg)
    print(f"[detect] {len(cands)} candidatos")
    picked = rank(vdir, cands, transcript, meta, cfg)
    print(f"[rank] {len(picked)} selecionados")
    out = []
    for c in picked:
        cdir = render_clip(vdir, c, transcript, meta, cfg, root)
        print(f"[render] {cdir.name}  {c['start']:.0f}-{c['end']:.0f}s  {c.get('title','')}")
        out.append(cdir)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(prog="clipper")
    ap.add_argument("--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    p = sub.add_parser("process"); p.add_argument("vdir"); p.add_argument("--skip-transcribe", action="store_true")
    p = sub.add_parser("add-local"); p.add_argument("file"); p.add_argument("--title", required=True)
    p.add_argument("--credit", required=True); p.add_argument("--auth", required=True)
    sub.add_parser("review")
    p = sub.add_parser("approve"); p.add_argument("clip_id"); p.add_argument("--title")
    p = sub.add_parser("reject"); p.add_argument("clip_id")
    p = sub.add_parser("publish"); p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg = load_config(a.config)
    root = data_dir(cfg)

    if a.cmd == "run":
        for vdir in ingest(cfg, root):
            process(vdir, cfg, root)
        print(f"Revisar: {gallery(root)}")
    elif a.cmd == "process":
        process(Path(a.vdir), cfg, root, a.skip_transcribe)
        print(f"Revisar: {gallery(root)}")
    elif a.cmd == "add-local":
        vdir = register_local(Path(a.file), root, a.title, a.credit, a.auth)
        print(f"Registrado em {vdir}. Rode: python -m clipper process {vdir}")
    elif a.cmd == "review":
        for cdir, m in all_clips(root, "pending"):
            print(f"{cdir.name}  [{m.get('score')}/{m.get('llm_score')}]  {m.get('title')}")
        print(f"Galeria: {gallery(root)}")
    elif a.cmd == "approve":
        set_status(root, a.clip_id, "approved", a.title)
    elif a.cmd == "reject":
        set_status(root, a.clip_id, "rejected")
    elif a.cmd == "publish":
        publish(root, cfg, a.dry_run)


if __name__ == "__main__":
    main()
