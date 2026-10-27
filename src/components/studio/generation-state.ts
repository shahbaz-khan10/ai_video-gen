import { ApiError } from "@/lib/api/client";
import type { GenerationJob } from "@/types/api";

/** A failure explained for people. `message` comes from the backend, which never includes paths or traces. */
export type GenerationError = {
  title: string;
  message: string;
  hint?: string;
  code?: string;
  /** Whether trying the same request again could succeed. */
  retryable: boolean;
};

export type GenerationState =
  | { phase: "idle" }
  | { phase: "submitting" }
  | { phase: "running"; job: GenerationJob; failures: number; acceptedAt: number }
  | { phase: "completed"; job: GenerationJob }
  | { phase: "failed"; error: GenerationError; job: GenerationJob | null }
  /** Polling lost the backend. The job may still finish; `resume` checks again. */
  | { phase: "disconnected"; job: GenerationJob; error: GenerationError; acceptedAt: number };

export type GenerationEvent =
  | { type: "submit" }
  | { type: "accepted"; job: GenerationJob; at: number }
  | { type: "polled"; job: GenerationJob }
  | { type: "pollFailed"; error: unknown }
  | { type: "rejected"; error: unknown }
  | { type: "resume" }
  | { type: "reset" };

export const POLL_INTERVAL_MS = 1500;
/** Consecutive failed polls before the UI reports a lost connection. */
export const MAX_POLL_FAILURES = 4;

type Copy = { title: string; hint?: string; retryable: boolean };

const ERROR_COPY: Record<string, Copy> = {
  model_not_downloaded: {
    title: "Model not downloaded",
    hint: "In backend/, run: python scripts/download_model.py (about 2.6 GB, one time).",
    retryable: true,
  },
  engine_not_installed: {
    title: "AI libraries not installed",
    hint: "Install PyTorch and requirements-ai.txt on the backend (see backend/README.md).",
    retryable: false,
  },
  engine_not_configured: {
    title: "Image engine is off",
    hint: "Set IMAGE_ENGINE=diffusers in backend/.env and restart the API.",
    retryable: false,
  },
  mode_not_supported: { title: "Not available yet", retryable: false },
  queue_full: { title: "Queue is full", hint: "Wait for the current images to finish.", retryable: true },
  gpu_out_of_memory: {
    title: "GPU out of memory",
    hint: "Try Standard resolution, close other GPU-heavy apps, or set IMAGE_CPU_OFFLOAD=true.",
    retryable: true,
  },
  model_unavailable: {
    title: "Model couldn't be loaded",
    hint: "The weights may be missing or incomplete. Re-run scripts/download_model.py.",
    retryable: true,
  },
  model_download_failed: { title: "Model download failed", retryable: true },
  cuda_unavailable: {
    title: "No CUDA GPU available",
    hint: "Check the NVIDIA driver and the CUDA build of PyTorch, or set IMAGE_DEVICE=auto.",
    retryable: false,
  },
  generation_timeout: { title: "Generation timed out", retryable: true },
  image_save_failed: { title: "Image couldn't be saved", hint: "Check IMAGE_OUTPUT_DIR on the backend.", retryable: true },
  generation_not_found: {
    title: "Generation lost",
    hint: "The backend restarted, and jobs aren't kept across restarts.",
    retryable: true,
  },
  missing_output: { title: "No image was returned", retryable: true },
};

export function describeFailure(code: string | null | undefined, message: string | null | undefined): GenerationError {
  const copy = (code && ERROR_COPY[code]) || { title: "Generation failed", retryable: true };
  return {
    ...copy,
    code: code ?? undefined,
    message: message?.trim() || "Something went wrong while generating the image.",
  };
}

/** Explains an error thrown by the API client. */
export function describeApiError(err: unknown): GenerationError {
  if (!(err instanceof ApiError)) {
    return { title: "Backend unreachable", message: "Couldn't reach the backend.", retryable: true };
  }
  if (err.isUnavailable) {
    return {
      title: err.kind === "timeout" ? "Backend not responding" : "Backend unreachable",
      message: err.message,
      hint: err.kind === "unconfigured" ? undefined : "Start it in backend/: uvicorn app.main:app --port 8000",
      retryable: err.kind !== "unconfigured",
    };
  }
  return describeFailure(err.code, err.message);
}

function fromJob(job: GenerationJob, acceptedAt: number): GenerationState {
  if (job.status === "completed") {
    // Never show success without an image to show.
    return job.output_url
      ? { phase: "completed", job }
      : { phase: "failed", job, error: describeFailure("missing_output", "The backend finished without an image.") };
  }
  if (job.status === "failed") return { phase: "failed", job, error: describeFailure(job.error_code, job.error) };
  return { phase: "running", job, failures: 0, acceptedAt };
}

export function generationReducer(state: GenerationState, event: GenerationEvent): GenerationState {
  switch (event.type) {
    case "submit":
      return state.phase === "submitting" || state.phase === "running" ? state : { phase: "submitting" };
    case "accepted":
      return state.phase === "submitting" ? fromJob(event.job, event.at) : state;
    case "polled":
      if ((state.phase === "running" || state.phase === "disconnected") && state.job.id === event.job.id) {
        return fromJob(event.job, state.acceptedAt);
      }
      return state;
    case "pollFailed": {
      if (state.phase !== "running") return state;
      const error = describeApiError(event.error);
      if (error.code === "generation_not_found") return { phase: "failed", job: state.job, error };
      const failures = state.failures + 1;
      return failures >= MAX_POLL_FAILURES
        ? { phase: "disconnected", job: state.job, error, acceptedAt: state.acceptedAt }
        : { ...state, failures };
    }
    case "rejected":
      return state.phase === "submitting" ? { phase: "failed", job: null, error: describeApiError(event.error) } : state;
    case "resume":
      return state.phase === "disconnected"
        ? { phase: "running", job: state.job, failures: 0, acceptedAt: state.acceptedAt }
        : state;
    case "reset":
      return { phase: "idle" };
  }
}

export function isBusy(state: GenerationState) {
  return state.phase === "submitting" || state.phase === "running";
}

/** Honest progress text: what the backend says is happening, never an invented percentage. */
export function progressMessage(state: GenerationState): { title: string; detail: string } | null {
  if (state.phase === "submitting") return { title: "Sending to the backend…", detail: "Queuing your image." };
  if (state.phase !== "running") return null;
  if (state.job.status === "queued") {
    return { title: "Waiting in the queue…", detail: "One image is generated at a time. Yours starts next." };
  }
  return {
    title: "Generating on the local model…",
    detail: "The first image after the backend starts also loads the model, which can take a minute.",
  };
}

export function formatElapsed(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}
