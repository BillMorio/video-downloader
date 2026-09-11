# Lumina Video Downloader

Personal video downloader (YouTube · Instagram · Facebook). Paste a link, pick a
quality, get an MP4 (or MP3). Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp).

> **Standalone & isolated.** This is its own repo with its own Render service and
> Vercel project. It shares **nothing** with the Lumina Clippers app — no env,
> no database, no services. Staging / personal use only.

## Layout
```
backend/    FastAPI + yt-dlp, deployed as a Docker service on Render (needs ffmpeg)
frontend/   Next.js single page on Vercel, Lumina-styled
```

## Run locally

**Backend**
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# ffmpeg must be on PATH locally (brew install ffmpeg / choco install ffmpeg)
ALLOWED_ORIGINS=http://localhost:3000 uvicorn app:app --reload
```

**Frontend**
```bash
cd frontend
cp .env.local.example .env.local   # points at http://localhost:8000
npm install
npm run dev
```

## Deploy

### Backend → Render (new Docker Web Service)
- **Runtime:** Docker · **Root directory:** `backend`
- **Env vars:**
  | Var | Value |
  |---|---|
  | `ALLOWED_ORIGINS` | your Vercel URL, e.g. `https://lumina-downloader.vercel.app` |
  | `MAX_FILESIZE_MB` | `1024` (optional) |
  | `RATE_LIMIT_PER_MIN` | `6` (optional) |
- Render injects `$PORT`; the Dockerfile uses it. `/api/health` reports `ffmpeg: true`.

### Frontend → Vercel (new project)
- **Root directory:** `frontend`
- **Env var:** `NEXT_PUBLIC_API_BASE` = the Render backend URL (no trailing slash)

## API
| Route | Purpose |
|---|---|
| `POST /api/download` | `{url, resolution, audio_only}` → `{job_id}` |
| `GET /api/status/{job_id}` | `{status, pct, title, error}` |
| `GET /api/file/{job_id}` | streams the finished file, then reaps it |
| `GET /api/health` | `{ok, ffmpeg}` |

Jobs and files live in memory / `/tmp` and are auto-reaped after 15 min.

## Live instances
- **Frontend:** https://lumina-video-downloader.vercel.app (Vercel project `lumina-video-downloader`)
- **Backend:** https://lumina-video-downloader-api.onrender.com (Render `srv-dai41aeq1p3s73b16a4g`, Lumina Agency)
- **Repo:** https://github.com/BillMorio/video-downloader (public — so Render can clone it)

## Real-world platform status (tested from the Render IP, 2026-09-11)
| Platform | Works from server? |
|---|---|
| **Facebook** | ✅ Yes |
| **YouTube** | ⚠️ Bot-checked from the datacenter IP — usually fails without cookies |
| **Instagram** | ⚠️ Blocked from the datacenter IP without cookies |

YouTube/IG both download fine from a residential IP (e.g. your laptop running
locally). The block is the server's datacenter IP, not the code. We shipped
**best-effort, no cookies** by choice.

## Enabling cookies later (unlocks YouTube + Instagram)
The code already supports it — no redeploy of logic needed:
1. In a browser logged into YouTube/Instagram, export `cookies.txt` (Netscape
   format) with a "Get cookies.txt LOCALLY" extension.
2. On Render → this service → **Secret Files**, add the file (e.g. `cookies.txt`).
3. Set env var `COOKIES_FILE` to its mounted path (e.g. `/etc/secrets/cookies.txt`).
4. Redeploy (see below). Cookies expire every few weeks — re-export when YT/IG
   start failing again.

## Deploying updates (IMPORTANT)
Render added this repo **by URL**, not via the GitHub App, so it gets **no push
webhook** — `git push` does NOT auto-deploy. After pushing, trigger a deploy
manually:
```bash
curl -X POST -H "Authorization: Bearer $RENDER_API_KEY" \
  https://api.render.com/v1/services/srv-dai41aeq1p3s73b16a4g/deploys \
  -d '{"clearCache":"do_not_clear"}'
```
The Vercel frontend deploys with `vercel deploy --prod --yes --token $VERCEL_TOKEN`
from the `frontend/` dir.

## Notes / limits
- Single process, in-memory state — a restart drops in-flight jobs. Fine for
  personal use.
- ffmpeg is bundled in the Docker image; that's why the backend is Docker, not
  a plain Python service.
- `yt-dlp` must be kept current (see `backend/requirements.txt`) — YouTube/IG/FB
  change often and stale releases break.
