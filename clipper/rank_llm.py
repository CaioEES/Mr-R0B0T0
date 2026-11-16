"""Etapa 3b: Claude lê a transcrição de cada candidato e escolhe/ajusta os melhores.

Opcional: sem ANTHROPIC_API_KEY (ou llm.enabled=false) o pipeline usa só o score dos sinais.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import write_json
from .transcribe import text_between

SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "keep": {"type": "boolean"},
                    "funny_score": {"type": "integer"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["index", "keep", "funny_score", "start", "end", "title", "hook", "hashtags", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}

SYSTEM = """Você é editor de cortes curtos (Shorts/Reels/TikTok) de lives de GTA em português.
Para cada candidato você recebe o intervalo, os sinais (volume, chat, palavras) e a transcrição.
Decida se vira um corte bom: engraçado, com começo-meio-fim compreensível fora de contexto.
Ajuste start/end (segundos absolutos do vídeo) para começar no setup e terminar logo após a reação;
duração entre {min_s} e {max_s} segundos. Título curto (até 70 caracteres), sem clickbait enganoso,
sem palavrões no título. 'hook' é a frase de legenda dos 2 primeiros segundos.
Marque keep=false para trechos sem graça, ofensivos, com dados pessoais ou que dependem demais de contexto.
funny_score de 0 a 10."""


def rank(vdir: Path, candidates: list[dict], transcript: list[dict], meta: dict, cfg: dict) -> list[dict]:
    lcfg = cfg.get("llm", {})
    dcfg = cfg.get("detect", {})
    keep_top = int(lcfg.get("keep_top", 5))

    if not lcfg.get("enabled", True) or not os.environ.get("ANTHROPIC_API_KEY") or not transcript:
        picked = sorted(candidates, key=lambda c: c["score"], reverse=True)[:keep_top]
        for c in picked:
            c.setdefault("title", f"{meta.get('credit', '')} no GTA 6 😂".strip())
            c.setdefault("hook", "")
            c.setdefault("hashtags", ["#gta6", "#shorts"])
        return picked

    import anthropic

    payload = []
    for i, c in enumerate(candidates):
        payload.append({
            "index": i, "start": c["start"], "end": c["end"], "signals": c["signals"],
            "transcript": text_between(transcript, c["start"] - 5, c["end"] + 5)[:2500],
        })

    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=lcfg.get("model", "claude-opus-5-5"),
        max_tokens=16000,
        system=SYSTEM.format(min_s=dcfg.get("min_clip_s", 15), max_s=dcfg.get("max_clip_s", 59)),
        messages=[{
            "role": "user",
            "content": f"Live: {meta.get('title')}\nStreamer: {meta.get('credit')}\n\nCandidatos:\n"
                       + json.dumps(payload, ensure_ascii=False),
        }],
        output_config={"effort": lcfg.get("effort", "low"),
                       "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        print("[rank] modelo recusou; usando ranking por sinais")
        lcfg2 = {**cfg, "llm": {**lcfg, "enabled": False}}
        return rank(vdir, candidates, transcript, meta, lcfg2)

    text = next(b.text for b in resp.content if b.type == "text")
    ranked = json.loads(text)["clips"]
    write_json(vdir / "ranked.json", ranked)

    picked = []
    for r in sorted((r for r in ranked if r["keep"]), key=lambda r: r["funny_score"], reverse=True)[:keep_top]:
        if not 0 <= r["index"] < len(candidates):
            continue
        base = dict(candidates[r["index"]])
        start, end = float(r["start"]), float(r["end"])
        if not (0 <= start < end) or end - start > float(dcfg.get("max_clip_s", 59)) + 1:
            start, end = base["start"], base["end"]  # ajuste inválido: mantém o original
        base.update(start=start, end=end, title=r["title"], hook=r["hook"],
                    hashtags=r["hashtags"], llm_score=r["funny_score"], reason=r["reason"])
        picked.append(base)
    return picked
