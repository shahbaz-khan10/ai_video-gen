import { ApiError } from "@/lib/api/client";
import type { GenerationPayload, ImageResolution, NormalizedSettings, SourceImageInfo } from "@/types/api";
import type { AspectRatio, ClipDuration, GenerationMode } from "@/types/studio";
import type { SelectedImage } from "./use-image-selection";

/** What happened when the user checked video settings. Video generation is not connected, so it is never attempted. */
export type CheckOutcome =
  | { kind: "validated"; settings: NormalizedSettings }
  | { kind: "offline"; message: string }
  | { kind: "rejected"; message: string; messages: string[] };

export type FieldErrors = { prompt?: string; image?: string; seed?: string };

type Draft = {
  mode: GenerationMode;
  prompt: string;
  aspectRatio: AspectRatio;
  style: string;
  duration: ClipDuration;
  image: SelectedImage | null;
  resolution: ImageResolution;
  steps: number;
  /** Digits only, or empty for a random seed. */
  seed: string;
};

export function buildPayload(draft: Draft): GenerationPayload {
  const base = { prompt: draft.prompt, aspect_ratio: draft.aspectRatio, style: draft.style };
  const duration_seconds = Number.parseInt(draft.duration, 10);
  if (draft.mode === "text-to-image") {
    const seed = draft.seed.trim() ? Number(draft.seed) : undefined;
    return {
      ...base,
      mode: draft.mode,
      resolution: draft.resolution,
      num_inference_steps: draft.steps,
      ...(seed === undefined ? {} : { seed }),
    };
  }
  if (draft.mode === "text-to-video") return { ...base, mode: draft.mode, duration_seconds };
  // Callers check for the image first. Only metadata is sent; the image itself stays in the browser.
  if (!draft.image) throw new Error("An image-to-video request needs a source image.");
  const source_image: SourceImageInfo = { content_type: draft.image.type, size_bytes: draft.image.size };
  return { ...base, mode: draft.mode, duration_seconds, source_image };
}

/** Maps a backend error to field messages plus an outcome for the preview panel. */
export function interpretError(err: unknown): { fieldErrors: FieldErrors; outcome: CheckOutcome } {
  if (!(err instanceof ApiError)) {
    return { fieldErrors: {}, outcome: { kind: "offline", message: "Couldn't reach the backend." } };
  }
  if (err.isUnavailable) {
    return { fieldErrors: {}, outcome: { kind: "offline", message: err.message } };
  }

  const fieldErrors: FieldErrors = {};
  const other: string[] = [];
  for (const d of err.details) {
    if (d.field.startsWith("prompt")) fieldErrors.prompt ??= d.message;
    else if (d.field.startsWith("source_image")) fieldErrors.image ??= d.message;
    else if (d.field === "seed") fieldErrors.seed ??= d.message;
    else other.push(`${d.field.replaceAll("_", " ")}: ${d.message}`);
  }
  return { fieldErrors, outcome: { kind: "rejected", message: err.message, messages: other } };
}
