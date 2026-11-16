import { ApiError } from "@/lib/api/client";
import type {
  GenerationPayload,
  I2VCamera,
  I2VMotion,
  I2VQuality,
  ImageResolution,
  NormalizedSettings,
  SceneInput,
  SourceImageInfo,
  VideoResolution,
} from "@/types/api";
import type { AspectRatio, ClipDuration, GenerationMode } from "@/types/studio";
import type { SelectedImage } from "./use-image-selection";

/** What happened when the user pressed Generate. */
export type CheckOutcome =
  | { kind: "validated"; settings: NormalizedSettings }
  | { kind: "offline"; message: string }
  | { kind: "rejected"; message: string; messages: string[] };

export type FieldErrors = { prompt?: string; image?: string; seed?: string };

export type Draft = {
  mode: GenerationMode;
  prompt: string;
  negativePrompt?: string;
  aspectRatio: AspectRatio;
  style: string;
  duration: ClipDuration;
  image: SelectedImage | null;
  resolution: ImageResolution;
  steps: number;
  /** Null for a random seed. */
  seed: number | null;
  guidanceScale?: number;
  modelId?: string;
  /** Text-to-video only: seconds, size tier and steps the video model supports. */
  video?: {
    durationSeconds: number;
    resolution: VideoResolution;
    /** Null when the backend's sampler has a fixed step count (FastWan). */
    steps: number | null;
    /** Long videos: the reviewed scene list. */
    scenes?: SceneInput[];
  };
  /** Prompt agent: describe the photo, check the result, retry once on a failed check. */
  promptAgent?: boolean;
  /** Image-to-video only. */
  i2v?: { durationSeconds: number; resolution: VideoResolution; quality: I2VQuality; motion: I2VMotion; camera: I2VCamera };
};

export function buildPayload(draft: Draft): GenerationPayload {
  const base = { prompt: draft.prompt, aspect_ratio: draft.aspectRatio, style: draft.style, prompt_agent: draft.promptAgent ?? true };
  if (draft.mode === "text-to-image") {
    return {
      ...base,
      mode: draft.mode,
      resolution: draft.resolution,
      steps: draft.steps,
      ...(draft.seed === null ? {} : { seed: draft.seed }),
      ...(draft.negativePrompt ? { negative_prompt: draft.negativePrompt } : {}),
      ...(draft.guidanceScale ? { guidance_scale: draft.guidanceScale } : {}),
      ...(draft.modelId && draft.modelId !== "auto" ? { model_id: draft.modelId } : {}),
    };
  }
  if (draft.mode === "text-to-video") {
    if (!draft.video) throw new Error("A text-to-video request needs video settings.");
    return {
      ...base,
      mode: draft.mode,
      duration_seconds: draft.video.durationSeconds,
      resolution: draft.video.resolution,
      ...(draft.video.steps === null ? {} : { steps: draft.video.steps }),
      ...(draft.video.scenes?.length ? { scenes: draft.video.scenes } : {}),
      ...(draft.seed === null ? {} : { seed: draft.seed }),
    };
  }
  if (!draft.image?.uploadId) throw new Error("An image-to-video request needs an uploaded source image.");
  if (!draft.i2v) throw new Error("An image-to-video request needs its settings.");
  const source_image: SourceImageInfo = {
    upload_id: draft.image.uploadId,
    content_type: draft.image.type,
    size_bytes: draft.image.size,
  };
  return {
    ...base,
    mode: draft.mode,
    duration_seconds: draft.i2v.durationSeconds,
    resolution: draft.i2v.resolution,
    quality: draft.i2v.quality,
    motion: draft.i2v.motion,
    camera: draft.i2v.camera,
    source_image,
    ...(draft.seed === null ? {} : { seed: draft.seed }),
  };
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
