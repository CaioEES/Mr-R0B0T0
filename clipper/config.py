from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Config não encontrada: {path}. Copie config.example.yaml para config.yaml.")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for ch in cfg.get("channels", []):
        if not ch.get("authorization"):
            raise SystemExit(
                f"Canal '{ch.get('name')}' sem campo 'authorization'. "
                "Só processe canais com permissão explícita."
            )
    return cfg


def data_dir(cfg: dict) -> Path:
    d = Path(cfg.get("data_dir", "data"))
    (d / "videos").mkdir(parents=True, exist_ok=True)
    (d / "clips").mkdir(parents=True, exist_ok=True)
    return d


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
