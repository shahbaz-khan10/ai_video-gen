"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { CircleAlert, Dices, Download, ImageOff, LoaderCircle, RefreshCw, RotateCcw, WifiOff, X } from "lucide-react";
import { buttonStyles } from "@/components/ui/button";
import { assetUrl } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import type { GenerationJob } from "@/types/api";
import { formatElapsed, progressMessage, type GenerationState } from "./generation-state";

/** Re-renders every second while `active`, for an honest elapsed-time readout. */
function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

/** Shown inside the preview frame while a job is being sent, queued or generated. */
export function GenerationProgress({ state }: { state: GenerationState }) {
  const message = progressMessage(state);
  const acceptedAt = state.phase === "running" ? state.acceptedAt : null;
  const now = useNow(acceptedAt !== null);
  if (!message) return null;

  return (
    <motion.div
      key="progress"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      role="status"
      className="absolute inset-0 flex flex-col items-center justify-center bg-ink-950/70 p-6 text-center backdrop-blur-[2px]"
    >
      <span aria-hidden className="absolute inset-0 animate-pulse bg-[radial-gradient(60%_50%_at_50%_50%,rgb(124_92_255/0.16),transparent)]" />
      <span className="relative grid size-12 place-items-center rounded-full border border-violet-soft/30 bg-ink-850 text-violet-soft">
        <LoaderCircle className="size-5 animate-spin" aria-hidden />
      </span>
      <p className="relative mt-4 text-sm font-medium text-fg">{message.title}</p>
      <p className="relative mt-1.5 max-w-xs text-xs leading-relaxed text-fg-muted">{message.detail}</p>
      {acceptedAt !== null && (
        <p className="relative mt-3 font-mono text-[11px] text-fg-subtle" aria-hidden>
          {formatElapsed(now - acceptedAt)} elapsed
        </p>
      )}
    </motion.div>
  );
}

/** The generated image, loaded from the backend's file route. */
export function GeneratedImage({ job }: { job: GenerationJob }) {
  const [failed, setFailed] = useState(false);
  const src = job.output_url ? assetUrl(job.output_url) : null;

  if (!src || failed) {
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center">
        <ImageOff className="size-5 text-fg-subtle" aria-hidden />
        <p className="mt-3 text-sm text-fg">The image couldn&apos;t be loaded</p>
        <p className="mt-1 max-w-xs text-xs text-fg-muted">
          It was generated, but the browser couldn&apos;t fetch it. Check that the backend is still running.
        </p>
      </div>
    );
  }

  return (
    <motion.figure key={job.id} initial={{ opacity: 0, scale: 1.02 }} animate={{ opacity: 1, scale: 1 }} className="absolute inset-0">
      {/* eslint-disable-next-line @next/next/no-img-element -- served by the local FastAPI backend, not optimizable by Next */}
      <img
        src={src}
        alt={`Generated image: ${job.settings.prompt}`}
        width={job.result?.width}
        height={job.result?.height}
        onError={() => setFailed(true)}
        className="size-full object-cover"
      />
    </motion.figure>
  );
}

function Meta({ job }: { job: GenerationJob }) {
  const r = job.result;
  if (!r) return null;
  const items = [
    `${r.width}×${r.height}`,
    `seed ${r.seed}`,
    `${r.num_inference_steps} step${r.num_inference_steps > 1 ? "s" : ""}`,
    `${r.duration_seconds.toFixed(1)}s on ${r.device === "cuda" ? "GPU" : r.device.toUpperCase()}`,
    r.model_id,
  ];
  return (
    <ul aria-label="Generation details" className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li key={item} className="rounded-md border border-line bg-ink-850 px-2 py-1 font-mono text-[11px] text-fg-muted">
          {item}
        </li>
      ))}
    </ul>
  );
}

type GenerationFooterProps = {
  state: GenerationState;
  onRetry: () => void;
  onResume: () => void;
  onReuseSeed: (seed: number) => void;
  onDismiss: () => void;
};

/** Actions and messages below the preview: download a finished image, or explain a failure. */
export function GenerationFooter({ state, onRetry, onResume, onReuseSeed, onDismiss }: GenerationFooterProps) {
  if (state.phase === "completed") {
    const { job } = state;
    const download = job.output_url ? assetUrl(job.output_url, { download: true }) : null;
    return (
      <div className="m-3 mt-0 flex flex-col gap-3 rounded-xl border border-emerald-400/20 bg-emerald-400/[0.05] p-3.5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="mr-auto text-sm font-medium text-fg">Image generated</p>
          {job.result && (
            <button
              type="button"
              onClick={() => onReuseSeed(job.result!.seed)}
              className={buttonStyles({ variant: "ghost", size: "sm" })}
            >
              <Dices className="size-3.5" aria-hidden />
              Reuse seed
            </button>
          )}
          {download && (
            <a href={download} download className={buttonStyles({ variant: "secondary", size: "sm" })}>
              <Download className="size-3.5" aria-hidden />
              Download PNG
            </a>
          )}
        </div>
        <Meta job={job} />
      </div>
    );
  }

  if (state.phase === "failed" || state.phase === "disconnected") {
    const { error } = state;
    const lost = state.phase === "disconnected";
    const Icon = lost ? WifiOff : CircleAlert;
    return (
      <div
        className={cn(
          "m-3 mt-0 flex gap-3 rounded-xl border p-3.5",
          lost ? "border-line-strong bg-ink-850" : "border-red-400/25 bg-red-400/[0.06]",
        )}
      >
        <Icon className={cn("mt-0.5 size-4 shrink-0", lost ? "text-fg-muted" : "text-red-300")} aria-hidden />
        <div className="min-w-0 flex-1 text-sm">
          <p className="font-medium text-fg">{lost ? "Lost contact with the backend" : error.title}</p>
          <p className="mt-1 text-xs leading-relaxed text-fg-muted">
            {lost
              ? `${error.message} Your image may still be generating; check again once the backend is back.`
              : error.message}
          </p>
          {error.hint && !lost && <p className="mt-1 text-xs leading-relaxed text-fg-subtle">{error.hint}</p>}
          {(lost || error.retryable) && (
            <div className="mt-3 flex gap-2">
              {lost ? (
                <button type="button" onClick={onResume} className={buttonStyles({ variant: "secondary", size: "sm" })}>
                  <RefreshCw className="size-3.5" aria-hidden />
                  Check again
                </button>
              ) : (
                <button type="button" onClick={onRetry} className={buttonStyles({ variant: "secondary", size: "sm" })}>
                  <RotateCcw className="size-3.5" aria-hidden />
                  Try again
                </button>
              )}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="grid size-7 shrink-0 place-items-center rounded-md text-fg-subtle transition-colors hover:bg-white/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>
    );
  }

  return null;
}
