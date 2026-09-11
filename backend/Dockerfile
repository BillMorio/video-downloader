# yt-dlp needs ffmpeg to merge separate video+audio streams and to extract
# audio (mp3). Render's plain Python env has no ffmpeg, so we ship our own.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV WORK_DIR=/tmp/vdl
EXPOSE 8000

# Render provides $PORT; default to 8000 for local docker run.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
