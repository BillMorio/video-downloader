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

## Notes / limits
- **Best-effort for IG/FB.** Public content usually downloads fine. Private,
  age-gated, or login-walled posts will fail from a datacenter IP — that's
  expected without a `cookies.txt` (not wired up in this version).
- Single process, in-memory state — a restart drops in-flight jobs. Fine for
  personal use.
- ffmpeg is bundled in the Docker image; that's why the backend is Docker, not
  a plain Python service.
