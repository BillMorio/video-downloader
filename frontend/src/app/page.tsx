"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Loader2, AlertTriangle, CheckCircle2, Youtube, Instagram, Facebook, Link2 } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Status = "idle" | "queued" | "downloading" | "processing" | "ready" | "error";

function detectPlatform(url: string): "youtube" | "instagram" | "facebook" | null {
  if (/youtube\.com|youtu\.be/i.test(url)) return "youtube";
  if (/instagram\.com/i.test(url)) return "instagram";
  if (/facebook\.com|fb\.watch|fb\.com/i.test(url)) return "facebook";
  return null;
}

const PLATFORM_META = {
  youtube: { label: "YouTube", Icon: Youtube, color: "#ef4444" },
  instagram: { label: "Instagram", Icon: Instagram, color: "#e1306c" },
  facebook: { label: "Facebook", Icon: Facebook, color: "#60a5fa" },
} as const;

export default function Page() {
  const [url, setUrl] = useState("");
  const [resolution, setResolution] = useState("1080");
  const [audioOnly, setAudioOnly] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [pct, setPct] = useState(0);
  const [title, setTitle] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const platform = useMemo(() => detectPlatform(url), [url]);
  const busy = status === "queued" || status === "downloading" || status === "processing";
  const canSubmit = platform !== null && !busy;

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPoll(), [stopPoll]);

  const poll = useCallback(
    (id: string) => {
      stopPoll();
      pollRef.current = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/api/status/${id}`);
          if (!res.ok) throw new Error("lost the job");
          const d = await res.json();
          setStatus(d.status as Status);
          setPct(d.pct ?? 0);
          setTitle(d.title ?? null);
          if (d.status === "ready") {
            stopPoll();
          } else if (d.status === "error") {
            setError(d.error || "Something went wrong.");
            stopPoll();
          }
        } catch {
          setStatus("error");
          setError("Lost contact with the server. Try again.");
          stopPoll();
        }
      }, 1000);
    },
    [stopPoll]
  );

  async function start() {
    if (!canSubmit) return;
    setStatus("queued");
    setPct(0);
    setError(null);
    setTitle(null);
    setJobId(null);
    try {
      const res = await fetch(`${API_BASE}/api/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, resolution, audio_only: audioOnly }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Request failed.");
      setJobId(d.job_id);
      poll(d.job_id);
    } catch (e) {
      setStatus("error");
      setError(e instanceof Error ? e.message : "Request failed.");
    }
  }

  function reset() {
    stopPoll();
    setStatus("idle");
    setPct(0);
    setError(null);
    setTitle(null);
    setJobId(null);
  }

  const statusLabel: Record<Status, string> = {
    idle: "",
    queued: "Queued…",
    downloading: `Downloading… ${pct}%`,
    processing: "Processing (merging audio + video)…",
    ready: "Ready",
    error: "Failed",
  };

  return (
    <main className="min-h-screen flex flex-col items-center px-4 py-16">
      <div className="w-full max-w-xl">
        {/* Header */}
        <div className="mb-8 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand mb-2">
            Lumina · personal tool
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-[#fafafa]">
            Video Downloader
          </h1>
          <p className="text-sm text-[#b8b8c0] mt-2">
            Paste a YouTube, Instagram, or Facebook link.
          </p>
        </div>

        {/* Card */}
        <div className="card-lumina rounded-[16px] p-6">
          {/* URL input */}
          <label className="block text-xs font-semibold uppercase tracking-wider text-[#9a9aa4] mb-2">
            Video link
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9a9aa4]">
              {platform ? (
                (() => {
                  const { Icon, color } = PLATFORM_META[platform];
                  return <Icon className="w-4 h-4" style={{ color }} />;
                })()
              ) : (
                <Link2 className="w-4 h-4" />
              )}
            </span>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && start()}
              placeholder="https://…"
              spellCheck={false}
              className="min-h-11 w-full bg-[#191a1e] border border-[#26272b] text-[#fafafa] text-sm rounded-[10px] pl-9 pr-3 outline-none placeholder:text-[#9a9aa4] focus-visible:border-[#22c55e] focus-visible:ring-2 focus-visible:ring-[#22c55e]/20 transition-all"
            />
          </div>
          {url && !platform && (
            <p className="text-xs text-[#fbbf24] mt-1.5">
              Only YouTube, Instagram, and Facebook links are supported.
            </p>
          )}
          {platform && (
            <p className="text-xs text-[#9a9aa4] mt-1.5">
              Detected: <span className="text-brand-soft">{PLATFORM_META[platform].label}</span>
            </p>
          )}

          {/* Options */}
          <div className="flex flex-wrap items-center gap-3 mt-4">
            <div className="flex-1 min-w-[140px]">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[#9a9aa4] mb-2">
                Quality
              </label>
              <select
                value={resolution}
                disabled={audioOnly}
                onChange={(e) => setResolution(e.target.value)}
                className="min-h-11 w-full bg-[#191a1e] border border-[#26272b] text-[#fafafa] text-sm rounded-[10px] px-3 outline-none focus-visible:border-[#22c55e] focus-visible:ring-2 focus-visible:ring-[#22c55e]/20 transition-all disabled:opacity-40"
              >
                <option value="1080">1080p</option>
                <option value="720">720p</option>
                <option value="480">480p</option>
              </select>
            </div>
            <label className="flex items-center gap-2 mt-6 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={audioOnly}
                onChange={(e) => setAudioOnly(e.target.checked)}
                className="accent-[#22c55e] w-4 h-4"
              />
              <span className="text-sm text-[#b8b8c0]">Audio only (MP3)</span>
            </label>
          </div>

          {/* Action */}
          <button
            onClick={start}
            disabled={!canSubmit}
            className="mt-6 w-full min-h-11 bg-[#22c55e] text-[#052e16] text-sm font-semibold px-5 rounded-[10px] shadow-[0_0_20px_-4px_rgba(34,197,94,0.7)] hover:bg-[#16a34a] transition-all duration-200 active:translate-y-px disabled:opacity-40 disabled:shadow-none flex items-center justify-center gap-2"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            {busy ? statusLabel[status] : "Download"}
          </button>

          {/* Progress */}
          {busy && (
            <div className="mt-4">
              <div className="h-2 w-full rounded-full bg-[#191a1e] overflow-hidden">
                <div
                  className="h-full bg-[#22c55e] transition-all duration-300"
                  style={{ width: `${status === "processing" ? 100 : pct}%` }}
                />
              </div>
              <p className="text-xs text-[#9a9aa4] mt-2 text-center">{statusLabel[status]}</p>
            </div>
          )}

          {/* Ready */}
          {status === "ready" && jobId && (
            <div className="mt-5 rounded-[10px] border border-[#22c55e]/30 bg-[#22c55e]/5 p-4">
              <div className="flex items-center gap-2 text-brand mb-3">
                <CheckCircle2 className="w-4 h-4" />
                <span className="text-sm font-semibold">Ready to save</span>
              </div>
              {title && <p className="text-xs text-[#b8b8c0] mb-3 truncate">{title}</p>}
              <a
                href={`${API_BASE}/api/file/${jobId}`}
                className="w-full min-h-11 bg-[#22c55e] text-[#052e16] text-sm font-semibold px-5 rounded-[10px] hover:bg-[#16a34a] transition-all flex items-center justify-center gap-2"
              >
                <Download className="w-4 h-4" />
                Save {audioOnly ? "MP3" : "video"}
              </a>
              <button
                onClick={reset}
                className="mt-2 w-full text-xs text-[#9a9aa4] hover:text-[#fafafa] transition-colors"
              >
                Download another
              </button>
            </div>
          )}

          {/* Error */}
          {status === "error" && (
            <div className="mt-5 rounded-[10px] border border-[#ef4444]/20 bg-[#ef4444]/5 p-4">
              <div className="flex items-start gap-2 text-[#ef4444]">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <span className="text-sm">{error}</span>
              </div>
              <button
                onClick={reset}
                className="mt-3 w-full text-xs text-[#9a9aa4] hover:text-[#fafafa] transition-colors"
              >
                Try again
              </button>
            </div>
          )}
        </div>

        {/* Disclaimer */}
        <p className="text-[11px] text-[#6b6b74] text-center mt-6 leading-relaxed">
          Personal use only. Download content you own or have the rights to. Respect each
          platform's terms of service and applicable copyright law.
        </p>
      </div>
    </main>
  );
}
