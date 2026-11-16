"""Etapa 6: publica cortes APROVADOS no YouTube (Data API v3, OAuth do próprio canal).

Pré-requisitos (uma vez, feitos por você):
  1. Google Cloud Console → criar projeto → ativar "YouTube Data API v3"
  2. Tela de consentimento OAuth (External, adicione seu e-mail como test user)
  3. Credenciais → OAuth client ID → "Desktop app" → baixar JSON em secrets/client_secret.json
  4. Primeira execução abre o navegador para autorizar; o token fica em secrets/youtube_token.json
Cota padrão: 10.000 unidades/dia; cada upload custa ~1.600 → ~6 uploads/dia.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .config import read_json, write_json
from .review import all_clips

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _service(ycfg: dict):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token = Path(ycfg.get("token_file", "secrets/youtube_token.json"))
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(ycfg["client_secrets"], SCOPES)
            creds = flow.run_local_server(port=0)
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def published_today(root: Path) -> int:
    today = dt.date.today().isoformat()
    return sum(1 for _, m in all_clips(root, "published") if (m.get("published_at") or "").startswith(today))


def publish(root: Path, cfg: dict, dry_run: bool = False) -> None:
    pcfg = cfg.get("publish", {})
    ycfg = pcfg.get("youtube", {})
    if not ycfg.get("enabled") and not dry_run:
        print("[publish] publish.youtube.enabled=false — nada a fazer")
        return
    budget = int(pcfg.get("daily_limit", 5)) - published_today(root)
    queue = all_clips(root, "approved")[:max(budget, 0)]
    if not queue:
        print(f"[publish] nada para publicar (aprovados na fila ou limite diário atingido)")
        return

    yt = None
    if not dry_run:
        yt = _service(ycfg)
        from googleapiclient.http import MediaFileUpload

    for cdir, m in queue:
        title = (m["title"] or "Corte GTA 6")[:95]
        if "#shorts" not in title.lower():
            title = f"{title} #shorts"[:100]
        body = {
            "snippet": {"title": title, "description": m["description"], "tags": [h.lstrip("#") for h in m["hashtags"]],
                        "categoryId": ycfg.get("category_id", "20")},
            "status": {"privacyStatus": ycfg.get("privacy", "private"), "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": False},
        }
        if dry_run:
            print(f"[publish:dry-run] {cdir.name}: {title}")
            continue
        req = yt.videos().insert(part="snippet,status", body=body,
                                 media_body=MediaFileUpload(str(cdir / "clip.mp4"), chunksize=-1, resumable=True))
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        m.update(status="published", youtube_id=resp["id"], published_at=dt.datetime.now().isoformat())
        write_json(cdir / "clip.json", m)
        print(f"[publish] {cdir.name} → https://youtube.com/shorts/{resp['id']}")
