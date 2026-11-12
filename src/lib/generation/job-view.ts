/**
 * Pure state logic for a text-to-image or text-to-video job in the UI: what to show, what to say,
 * and when to poll next. No React, no fetch, so it is unit-tested directly
 * (job-view.test.ts). Progress is described in words; no percentages are invented.
 */

import type { GenerationJob, ImageModelState } from "@/types/api";

export type JobView =
  | { phase: "idle" }
  | { phase: "submitting" }
  | { phase: "queued"; job: GenerationJob; position: number | null }
  | { phase: "processing"; job: GenerationJob }
  | { phase: "completed"; job: GenerationJob }
  | { phase: "failed"; job: GenerationJob; title: string; message: string; retryable: boolean }
  | { phase: "submit-error"; title: string; message: string; retryable: boolean }
  /** Polling failed repeatedly. The job may still be running on the server. */
  | { phase: "connection-lost"; job: GenerationJob };

export const POLL_INTERVAL_MS = 1500;
const MAX_POLL_FAILURES = 5;

/** Delay before the next poll, or null to stop and report a lost connection. */
export function nextPollDelay(consecutiveFailures: number): number | null {
  if (consecutiveFailures >= MAX_POLL_FAILURES) return null;
  if (consecutiveFailures === 0) return POLL_INTERVAL_MS;
  return Math.min(POLL_INTERVAL_MS * 2 ** consecutiveFailures, 15_000);
}

const ERROR_TITLES: Record<string, string> = {
  gpu_out_of_memory: "GPU out of memory",
  gpu_error: "GPU driver error",
  out_of_memory: "Server out of memory",
  cuda_unavailable: "GPU not available",
  model_not_downloaded: "Model not downloaded",
  ai_libraries_missing: "AI libraries not installed",
  model_load_failed: "Model failed to load",
  generation_timeout: "Generation timed out",
  image_save_failed: "Couldn't save the image",
  video_save_failed: "Couldn't save the video",
  video_invalid: "Video file was invalid",
  queue_full: "Queue is full",
  mode_not_available: "Not available yet",
  engine_not_configured: "Generation is turned off",
  validation_error: "Check your settings",
};

export function errorTitle(code: string | undefined): string {
  return (code && ERROR_TITLES[code]) || "Generation failed";
}

/** Server-side setup problems the user can't fix by retrying from the browser. */
const SETUP_ERRORS = new Set(["model_not_downloaded", "ai_libraries_missing", "engine_not_configured", "mode_not_available"]);

function isVideoJob(job: GenerationJob): boolean {
  return job.settings.mode === "text-to-video";
}

export function viewFromJob(job: GenerationJob): JobView {
  const noun = isVideoJob(job) ? "video" : "image";
  switch (job.status) {
    case "queued":
      return { phase: "queued", job, position: job.queue_position };
    case "processing":
      return { phase: "processing", job };
    case "completed":
      // Only trust "completed" when the server actually returned the file.
      return (isVideoJob(job) ? job.video : job.image)
        ? { phase: "completed", job }
        : {
            phase: "failed",
            job,
            title: "Generation failed",
            message: `The server reported success but returned no ${noun}.`,
            retryable: true,
          };
    case "failed":
      return {
        phase: "failed",
        job,
        title: errorTitle(job.error?.code),
        message: job.error?.message ?? `${noun === "video" ? "Video" : "Image"} generation failed on the server.`,
        retryable: job.error?.retryable ?? true,
      };
  }
}

export type SubmitFailure = { kind: string; status?: number; code?: string; message: string };

export function viewFromSubmitError(err: SubmitFailure): JobView {
  if (err.kind === "network" || err.kind === "timeout" || err.kind === "unconfigured") {
    return { phase: "submit-error", title: "Backend unreachable", message: err.message, retryable: true };
  }
  return {
    phase: "submit-error",
    title: errorTitle(err.code),
    message: err.message,
    retryable: !SETUP_ERRORS.has(err.code ?? "") && err.kind !== "validation",
  };
}

export function isBusy(view: JobView): boolean {
  return view.phase === "submitting" || view.phase === "queued" || view.phase === "processing";
}

/** Plain-language progress, based only on what the server has actually reported. */
export function progressMessage(view: JobView, elapsedSeconds: number, modelState: ImageModelState | null): string {
  switch (view.phase) {
    case "submitting":
      return "Sending your prompt to the studio backend…";
    case "queued":
      return view.position && view.position > 0
        ? `Waiting in the queue: ${view.position} ${view.position === 1 ? "job" : "jobs"} ahead.`
        : "Queued. Starting shortly…";
    case "processing": {
      if (view.job.scenes && view.job.scenes.length > 0) return longVideoProgress(view.job, elapsedSeconds);
      if (isVideoJob(view.job)) {
        // Video on an 8 GB GPU takes minutes; the server reports no per-step progress, so none is shown.
        const base = "Generating your video on the local model. This usually takes several minutes.";
        return elapsedSeconds >= 5 ? `${base} ${formatElapsed(elapsedSeconds)} elapsed.` : base;
      }
      const loading = modelState !== "loaded";
      const base = loading
        ? "Loading the model and generating. The first image takes longer."
        : "Generating your image on the local model.";
      return elapsedSeconds >= 5 ? `${base} ${formatElapsed(elapsedSeconds)} elapsed.` : base;
    }
    default:
      return "";
  }
}

/**
 * Long videos: real counts reported by the server (scene k of n, clips finished) and an estimate of the time
 * left from this job's own measured pace. No estimate is shown before the first clip has finished.
 */
export function longVideoProgress(job: GenerationJob, elapsedSeconds: number): string {
  const scenes = job.scenes ?? [];
  const total = job.clips_total ?? scenes.reduce((n, s) => n + s.clips.length, 0);
  const done = job.clips_completed ?? 0;
  const current = scenes.find((s) => s.status === "processing") ?? scenes.find((s) => s.status === "queued");
  const where = current ? `Scene ${current.index} of ${scenes.length}` : "Joining scenes";
  let text = `${where} · ${done} of ${total} clips finished.`;
  if (done > 0 && done < total && elapsedSeconds > 0) {
    const left = (elapsedSeconds / done) * (total - done);
    text += ` About ${formatElapsed(left)} left at the current pace.`;
  }
  return elapsedSeconds >= 5 ? `${text} ${formatElapsed(elapsedSeconds)} elapsed.` : text;
}

export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

/** Seconds between two ISO timestamps, or null if either is missing. */
export function secondsBetween(start: string | null, end: string | null): number | null {
  if (!start || !end) return null;
  const ms = Date.parse(end) - Date.parse(start);
  return Number.isFinite(ms) && ms >= 0 ? ms / 1000 : null;
}

/** Parses the optional seed field. Empty means random; anything invalid is an error message. */
export function parseSeed(raw: string, maxSeed = 2 ** 32 - 1): { seed: number | null; error?: string } {
  const value = raw.trim();
  if (value === "") return { seed: null };
  if (!/^\d+$/.test(value)) return { seed: null, error: "Seed must be a whole number, or leave it empty." };
  const seed = Number(value);
  if (!Number.isSafeInteger(seed) || seed > maxSeed) {
    return { seed: null, error: `Seed must be between 0 and ${maxSeed}.` };
  }
  return { seed };
}
