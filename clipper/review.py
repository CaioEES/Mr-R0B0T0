"""Etapa 5: fila de revisão humana (o "controle de qualidade" da linha)."""
from __future__ import annotations

import html
from pathlib import Path

from .config import read_json, write_json


def all_clips(root: Path, status: str | None = None) -> list[tuple[Path, dict]]:
    out = []
    for cdir in sorted((root / "clips").iterdir()):
        meta = read_json(cdir / "clip.json")
        if meta and (status is None or meta.get("status") == status):
            out.append((cdir, meta))
    return out


def set_status(root: Path, clip_id: str, status: str, title: str | None = None) -> None:
    cdir = root / "clips" / clip_id
    meta = read_json(cdir / "clip.json")
    if meta is None:
        raise SystemExit(f"Corte não encontrado: {clip_id}")
    meta["status"] = status
    if title:
        meta["title"] = title
    write_json(cdir / "clip.json", meta)
    print(f"{clip_id}: {status}")


def gallery(root: Path) -> Path:
    """Gera data/review.html: abre no navegador, assiste e copia o comando de aprovar/rejeitar."""
    cards = []
    for cdir, m in all_clips(root, "pending"):
        cid = cdir.name
        cards.append(f"""
<div class="card">
  <video src="clips/{cid}/clip.mp4" controls preload="metadata"></video>
  <h3>{html.escape(m.get('title',''))}</h3>
  <p class="meta">{html.escape(str(m.get('credit')))} · {m['start']:.0f}s–{m['end']:.0f}s ·
     score {m.get('score')} · IA {m.get('llm_score')}</p>
  <p class="why">{html.escape(m.get('reason') or '')}</p>
  <code>python -m clipper approve {cid}</code>
  <code>python -m clipper reject {cid}</code>
</div>""")
    page = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Fila de cortes</title>
<style>
body{{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}}
.card{{background:#1c1c1c;border-radius:12px;padding:12px}}
video{{width:100%;aspect-ratio:9/16;background:#000;border-radius:8px}}
h3{{margin:8px 0 4px;font-size:16px}} .meta,.why{{color:#aaa;font-size:13px;margin:4px 0}}
code{{display:block;background:#000;padding:6px;border-radius:6px;margin-top:6px;font-size:12px;user-select:all}}
</style></head><body><h1>Pendentes ({len(cards)})</h1><div class="grid">{''.join(cards) or '<p>Nada pendente.</p>'}</div></body></html>"""
    out = root / "review.html"
    out.write_text(page, encoding="utf-8")
    return out
