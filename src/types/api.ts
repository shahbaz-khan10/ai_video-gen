/** Types for the FastAPI backend (`backend/app/schemas`). */

import type { AspectRatio, GenerationMode } from "./studio";

export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
  timestamp: string;
};

export type ReadinessCheck = { status: "ok" | "not_configured" | "error"; detail: string };

export type ModelState =
  | "disabled"
  | "not_installed"
  | "weights_missing"
  | "not_loaded"
  | "loading"
  | "ready"
  | "error";

/** The image model's state, reported without loading it. */
export type ModelReadiness = {
  state: ModelState;
  loaded: boolean;
  accepts_jobs: boolean;
  model_id: string | null;
  device: string | null;
  cuda_available: boolean | null;
  detail: string;
};

export type ReadinessResponse = {
  ready: boolean;
  checks: Record<string, ReadinessCheck>;
  model: ModelReadiness;
};

export type InfoResponse = {
  name: string;
  version: string;
  api_version: "v1";
  environment: string;
  modes: GenerationMode[];
  aspect_ratios: AspectRatio[];
  styles: string[];
  limits: {
    prompt_max_chars: number;
    duration_options_seconds: number[];
    source_image_max_bytes: number;
    source_image_types: string[];
    max_request_bytes: number;
    image_resolutions: ImageResolution[];
    image_default_resolution: ImageResolution;
    image_max_steps: number;
    image_step_presets: number[];
    image_default_steps: number;
    seed_max: number;
  };
  generation: {
    available: boolean;
    engine: string;
    model_id: string | null;
    available_modes: GenerationMode[];
    message: string;
  };
};

export type SourceImageInfo = {
  content_type: "image/png" | "image/jpeg" | "image/webp";
  size_bytes: number;
};

export type ImageResolution = 512 | 768 | 1024;

type GenerationBase = { prompt: string; aspect_ratio: AspectRatio; style: string };

export type GenerationPayload =
  | (GenerationBase & {
      mode: "text-to-image";
      resolution: ImageResolution;
      num_inference_steps: number;
      /** Omit for a random seed; the backend reports the seed it used. */
      seed?: number;
    })
  | (GenerationBase & { mode: "text-to-video"; duration_seconds: number })
  | (GenerationBase & { mode: "image-to-video"; duration_seconds: number; source_image: SourceImageInfo });

export type NormalizedSettings = {
  mode: GenerationMode;
  prompt: string;
  prompt_length: number;
  aspect_ratio: AspectRatio;
  style: string;
  duration_seconds: number | null;
  source_image: SourceImageInfo | null;
  /** Still-image settings; null for video modes. */
  width: number | null;
  height: number | null;
  num_inference_steps: number | null;
  seed: number | null;
};

export type ValidationResponse = {
  valid: true;
  settings: NormalizedSettings;
  generation_available: boolean;
};

export type GenerationStatus = "queued" | "processing" | "completed" | "failed";

export type GenerationResult = {
  width: number;
  height: number;
  seed: number;
  num_inference_steps: number;
  model_id: string;
  device: string;
  duration_seconds: number;
};

/** A job from `POST/GET /generations`. Jobs live in backend memory and vanish on restart. */
export type GenerationJob = {
  id: string;
  status: GenerationStatus;
  settings: NormalizedSettings;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  /** Server-relative path, set only once the image exists. Load it through `assetUrl`. */
  output_url: string | null;
  result: GenerationResult | null;
  error: string | null;
  error_code: string | null;
};

export type ApiErrorDetail = { field: string; message: string };

export type ApiErrorBody = {
  error: { code: string; message: string; details?: ApiErrorDetail[] };
};
