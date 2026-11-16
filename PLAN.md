# Clipper: plano de implantação

Pipeline de cortes verticais (Shorts, Reels e TikTok) a partir de lives de GTA 6 **autorizadas**.

## 1. Arquitetura

```
 [cron diário] ─► 1 INGEST ─► 2 TRANSCRIBE ─► 3 DETECT ─► 3b RANK (Claude) ─► 4 RENDER ─► 5 REVIEW ─► 6 PUBLISH
                  yt-dlp       faster-whisper   áudio+chat     JSON ranqueado    ffmpeg 9:16   você      YouTube API
                  + chat       (pt, palavras)   +palavras      título/hook       + legenda     ~10 min   (+IG/TikTok)
```

| Etapa | Módulo | Status |
|---|---|---|
| 1. Ingestão (canais autorizados + live chat) | `clipper/ingest.py` | Código pronto. Não foi testado com o YouTube real porque a rede da sessão bloqueia o acesso |
| 2. Transcrição com timestamp por palavra | `clipper/transcribe.py` | Código pronto. O modelo Whisper precisa ser baixado do HuggingFace, que está bloqueado aqui |
| 3. Detecção (pico de áudio, explosão de chat, palavras de reação) | `clipper/detect.py` | **Testado** |
| 3b. Ranqueamento e títulos com Claude (opcional) | `clipper/rank_llm.py` | Código pronto. Precisa de `ANTHROPIC_API_KEY` |
| 4. Render 1080x1920 com fundo desfocado, legenda e loudnorm | `clipper/render.py` | **Testado** |
| 5. Fila de revisão e galeria HTML | `clipper/review.py` | **Testado** |
| 6. Upload para o YouTube (OAuth, limite diário) | `clipper/publish_youtube.py` | Código pronto. Precisa do OAuth |
| Instagram e TikTok | — | Ainda não implementado (ver seção 4) |

O teste de ponta a ponta sem internet é `python tests/smoke_test.py`. Ele cria uma "live" sintética com 2 picos, e o pipeline acerta os 2 e gera os cortes em 9:16.

## 2. O que o Claude consegue fazer sozinho e o que depende de você

### Claude faz sozinho
- Escrever, testar e manter todo o código, incluindo ajustes na detecção, novos sinais e o estilo da legenda.
- Instalar as dependências e preparar o setup script do ambiente.
- Agendar a rodada diária com uma tarefa agendada desta conta.
- Ranquear os momentos e escrever título, hook e hashtags (via API do Claude).
- Mandar o resumo diário por **Gmail** (conector já ativo) e subir os cortes pendentes no **Google Drive** (conector já ativo), para você revisar pelo celular.
- Publicar no YouTube depois que o OAuth estiver configurado.

### Só você pode fazer (exige identidade, conta ou decisão)
1. **Conseguir autorização dos streamers.** Isso significa entrar em campanhas de clipping (Whop, aba *Content Rewards*) ou fazer acordo direto com eles. **Sem isso, o pipeline não deve rodar.** O `config.yaml` recusa canais que não tenham o campo `authorization`.
2. **Criar as contas de destino:** um canal no YouTube, o Instagram como conta Business/Creator ligada a uma página do Facebook, e o TikTok.
3. **Configurar o Google Cloud:** criar o projeto, ativar a YouTube Data API v3, configurar a tela de consentimento OAuth e baixar `client_secret.json` (cerca de 15 min, só uma vez).
4. **Gerar a chave da API da Anthropic** (console.anthropic.com). Ela é opcional: sem a chave, o pipeline ranqueia só pelos sinais de áudio, chat e palavras.
5. **Revisar a fila** (cerca de 10 min por dia): aprovar ou rejeitar cada corte.
6. **Definir onde o pipeline roda** (ver seção 3).

## 3. Onde rodar

| Opção | Prós | Contras |
|---|---|---|
| **PC de casa ou mini-PC (recomendado)** | IP residencial (o YouTube bloqueia menos o yt-dlp), GPU para o Whisper, custo zero | Precisa ficar ligado no horário da rodada |
| Sessão cloud do Claude Code | O Claude configura tudo sozinho | O container é efêmero, o YouTube costuma bloquear download de IP de datacenter ("Sign in to confirm you're not a bot") e não há GPU |
| VPS (cerca de US$ 5–10/mês) | Fica ligado 24/7 | Também é IP de datacenter, com o mesmo problema de bloqueio. Whisper em CPU é lento |

Ordem de grandeza da transcrição de 1 hora de live com o modelo `small`: cerca de 5–10 min com GPU e cerca de 30–60 min em CPU de 4 núcleos.

Recomendação: rodar no seu PC via **Remote Control**. Assim o Claude opera a pasta do seu computador a partir do app.

## 4. Conectores

| Necessidade | Conector | Status |
|---|---|---|
| Resumo diário e lembrete de revisão | Gmail | ✅ Conectado |
| Cortes para revisar pelo celular | Google Drive | ✅ Conectado |
| Lembrete de revisão na agenda | Google Calendar | ✅ Conectado |
| Publicar no YouTube | Zapier (YouTube, upload) **ou** YouTube Data API direta | ✅ Zapier conectado (falta habilitar a ação). A API direta já está no código e é a preferida, por cota e controle |
| Publicar Reels | Zapier → Instagram for Business (3 ações de escrita) **ou** Instagram Graph API (app Meta) | ⚠️ Falta habilitar e autorizar a conta IG Business |
| Publicar no TikTok | **Nenhum.** O Zapier não tem ação de postagem no TikTok | ❌ É preciso criar um app no TikTok for Developers com a Content Posting API. Sem passar pela auditoria, os posts saem só como privados. Até lá, poste manualmente pelo app (cerca de 1 min por corte) |
| Código e versionamento | GitHub | ✅ Conectado |
| Edição de vídeo (VEED) | veedcrawl | ⚠️ Falhou ao conectar nesta sessão. Não é necessário, porque o ffmpeg resolve |

## 5. Plano de execução

**Fase 0: liberações (você, cerca de 1 h)**
- [ ] Entrar em 2 ou 3 campanhas de clipping de GTA 6 ou fechar acordo com streamers BR.
- [ ] Criar o canal no YouTube e o Instagram Business.
- [ ] Gerar o OAuth no Google Cloud (`secrets/client_secret.json`) e a chave da API da Anthropic.
- [ ] Escolher onde roda: PC com Remote Control, ou uma sessão cloud com rede liberada.

**Fase 1: instalação (Claude, cerca de 30 min)**
- [ ] `python -m venv .venv && pip install -r requirements.txt` (ffmpeg via apt, brew ou winget).
- [ ] Preencher o `config.yaml` com os canais autorizados.
- [ ] Rodar `python -m clipper run` em 1 VOD real e calibrar `detect.weights` e o `pre_roll_s`.

**Fase 2: piloto (2 semanas)**
- [ ] 3–5 cortes por dia, publicados como `unlisted` na primeira semana e depois `public`.
- [ ] Medir quais sinais acertam mais (taxa de aprovação na revisão) e ajustar os pesos.

**Fase 3: automação**
- [ ] Tarefa agendada diária: ingest → render → cortes no Drive → e-mail com a galeria.
- [ ] Publicação automática **apenas dos aprovados**, respeitando `daily_limit`.
- [ ] Reels via Zapier ou Graph API. TikTok fica manual até a auditoria do app.

## 6. Guard-rails já no código
- Canal sem o campo `authorization` impede o pipeline de rodar.
- O crédito e o link do vídeo original entram automaticamente na descrição.
- Nenhum corte é publicado sem passar por `approve`. Existe também um limite diário de publicações.
- O upload começa como `private` até você mudar no `config.yaml`.
