"""
Lumina Video Downloader — backend API.

A small, self-contained yt-dlp wrapper. Personal-use tool, staging-only.
Does NOT touch any Lumina Clippers production service, database, or env.

Flow:
  POST /api/download   -> validate URL, spawn a yt-dlp job, return {job_id}
  GET  /api/status/ID  -> {status, pct, title, error}
  GET  /api/file/ID    -> stream the finished file, then reap it

State is in-memory (single process). A restart drops in-flight jobs — fine
for a personal tool.
"""

import os
import re
import time
import uuid
import shutil
import threading
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Config (all via env; sane defaults for local dev)
# ---------------------------------------------------------------------------
WORK_DIR = Path(os.getenv("WORK_DIR", "/tmp/vdl"))
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", "900"))          # 15 min
MAX_FILESIZE_MB = int(os.getenv("MAX_FILESIZE_MB", "1024"))         # 1 GB cap
JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "300"))  # 5 min
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "6"))
# Comma-separated exact origins allowed to call us (the Vercel frontend).
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

WORK_DIR.mkdir(parents=True, exist_ok=True)

# Hosts we advertise support for. yt-dlp handles far more, but we gate to the
# ones the UI offers so a random link doesn't spin up a doomed job.
ALLOWED_HOST_RE = re.compile(
    r"(^|\.)(youtube\.com|youtu\.be|instagram\.com|facebook\.com|fb\.watch|fb\.com)$",
    re.IGNORECASE,
)

RESOLUTIONS = {"1080": 1080, "720": 720, "480": 480}

app = FastAPI(title="Lumina Video Downloader", docs_url=None, redoc_url=None)

# Also allow the Lumina Clippers portals + any Vercel preview deploy of them to
# call us (the client-facing Download button lives in that portal). Vercel
# preview URLs are dynamic per deploy, so match them by regex instead of an
# exact allowlist. localhost stays allowed for local dev.
ALLOWED_ORIGIN_REGEX = os.getenv(
    "ALLOWED_ORIGIN_REGEX",
    r"^https://([a-z0-9-]+\.)*(luminaclippers\.com|luminaclips\.co|vercel\.app)$"
    r"|^http://localhost(:\d+)?$",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# job_id -> dict(status, pct, title, error, path, created_at)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# ip -> list[timestamps] (naive fixed-window limiter)
_hits: dict[str, list[float]] = {}
_hits_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _host_ok(url: str) -> bool:
    m = re.match(r"^https?://([^/]+)", url.strip(), re.IGNORECASE)
    if not m:
        return False
    host = m.group(1).split("@")[-1].split(":")[0].lower()
    return bool(ALLOWED_HOST_RE.search(host))


def _rate_limited(ip: str) -> bool:
    now = time.time()
    with _hits_lock:
        window = [t for t in _hits.get(ip, []) if now - t < 60]
        if len(window) >= RATE_LIMIT_PER_MIN:
            _hits[ip] = window
            return True
        window.append(now)
        _hits[ip] = window
        return False


def _set(job_id: str, **kw) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kw)


def _run_job(job_id: str, url: str, resolution: str, audio_only: bool) -> None:
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    def hook(d):
        # Abort runaway jobs from inside yt-dlp's own loop.
        if time.time() - started > JOB_TIMEOUT_SECONDS:
            raise yt_dlp.utils.DownloadError("job exceeded time limit")
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = int(done / total * 100) if total else 0
            _set(job_id, status="downloading", pct=min(pct, 99))
        elif d.get("status") == "finished":
            # video downloaded; ffmpeg merge / postprocess happens next
            _set(job_id, status="processing", pct=99)

    height = RESOLUTIONS.get(resolution, 1080)
    if audio_only:
        fmt = "bestaudio/best"
    else:
        fmt = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"

    ydl_opts = {
        "format": fmt,
        "outtmpl": str(job_dir / "%(title).80s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "max_filesize": MAX_FILESIZE_MB * 1024 * 1024,
        "progress_hooks": [hook],
        "socket_timeout": 30,
        "retries": 3,
        # From a datacenter IP, YouTube bot-checks the default "web" client
        # ("sign in to confirm you're not a bot"). The tv / ios / mweb player
        # clients often slip past that without cookies. Order matters — yt-dlp
        # tries them left to right. A cookies file (COOKIES_FILE) closes the
        # rest of the gap for IG/FB/age-gated content if we ever add it.
        "extractor_args": {
            "youtube": {"player_client": ["tv", "ios", "mweb", "web_safari"]}
        },
        # A real desktop UA helps IG/FB return the public media JSON.
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
        },
    }
    cookies_file = os.getenv("COOKIES_FILE")
    if cookies_file and Path(cookies_file).exists():
        ydl_opts["cookiefile"] = cookies_file
    if audio_only:
        ydl_opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ]
    else:
        ydl_opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title") or "video"
        # yt-dlp renamed/merged; grab whatever landed in the job dir.
        files = sorted(job_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        real = next((p for p in files if p.is_file() and not p.name.endswith(".part")), None)
        if not real:
            raise RuntimeError("no output file produced")
        _set(job_id, status="ready", pct=100, title=title, path=str(real))
    except Exception as e:  # noqa: BLE001 — translate to a clean user message
        _set(job_id, status="error", error=_friendly_error(str(e)), raw_error=str(e)[:300])
        shutil.rmtree(job_dir, ignore_errors=True)


def _friendly_error(raw: str) -> str:
    low = raw.lower()
    if "time limit" in low:
        return "This took too long and was cancelled."
    if "login" in low or "private" in low or "not available for this" in low:
        return "This content is private or requires sign-in."
    if "geo" in low or "not available in your country" in low:
        return "This video isn't available (removed or region-locked)."
    if "sign in to confirm" in low or "bot" in low or "429" in low or "rate" in low:
        return "The platform blocked this request. Try again in a bit."
    if "unsupported url" in low or "no video" in low:
        return "Couldn't find a downloadable video at that link."
    if "filesize" in low or "max_filesize" in low:
        return f"That video is larger than the {MAX_FILESIZE_MB} MB limit."
    return "Couldn't download this one. Double-check the link and try again."


def _reaper() -> None:
    while True:
        time.sleep(60)
        now = time.time()
        with _jobs_lock:
            stale = [jid for jid, j in _jobs.items() if now - j["created_at"] > JOB_TTL_SECONDS]
            for jid in stale:
                _jobs.pop(jid, None)
        for jid in stale:
            shutil.rmtree(WORK_DIR / jid, ignore_errors=True)


threading.Thread(target=_reaper, daemon=True).start()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class DownloadReq(BaseModel):
    url: str
    resolution: str = "1080"
    audio_only: bool = False

    @field_validator("resolution")
    @classmethod
    def _res(cls, v: str) -> str:
        return v if v in RESOLUTIONS else "1080"


@app.get("/api/health")
def health():
    cf = os.getenv("COOKIES_FILE")
    cookies_loaded = bool(cf and Path(cf).exists())
    cookies_bytes = Path(cf).stat().st_size if cookies_loaded else 0
    return {
        "ok": True,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "cookies_file": cf or None,
        "cookies_loaded": cookies_loaded,
        "cookies_bytes": cookies_bytes,
    }


@app.post("/api/download")
def download(req: DownloadReq, request: Request):
    ip = (request.headers.get("x-forwarded-for", "") or request.client.host or "?").split(",")[0].strip()
    if _rate_limited(ip):
        raise HTTPException(429, "Too many requests — slow down a moment.")
    if not _host_ok(req.url):
        raise HTTPException(400, "We support YouTube, Instagram, and Facebook links.")

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "queued", "pct": 0, "title": None,
            "error": None, "path": None, "created_at": time.time(),
        }
    threading.Thread(
        target=_run_job,
        args=(job_id, req.url, req.resolution, req.audio_only),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Unknown or expired job.")
        return {
            "status": job["status"],
            "pct": job["pct"],
            "title": job["title"],
            "error": job["error"],
            "raw_error": job.get("raw_error"),
        }


@app.get("/api/file/{job_id}")
def file(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or job["status"] != "ready" or not job["path"]:
        raise HTTPException(404, "File not ready or expired.")
    path = Path(job["path"])
    if not path.exists():
        raise HTTPException(404, "File expired.")
    filename = path.name
    media = "audio/mpeg" if path.suffix == ".mp3" else "video/mp4"
    return FileResponse(str(path), media_type=media, filename=filename)


@app.exception_handler(HTTPException)
def _http_err(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
