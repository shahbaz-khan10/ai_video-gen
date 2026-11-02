/** Types for the FastAPI backend (`backend/app/schemas`). */

import type { AspectRatio, GenerationMode } from "./studio";

export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
  timestamp: string;
};

export type ReadinessCheck = {
  status: "ok" | "not_configured" | "unavailable" | "not_downloaded" | "not_loaded" | "loading" | "error";
  detail: string;
};

export type ReadinessResponse = {
  ready: boolean;
  /** The image model is loaded in memory (reported separately from API readiness). */
  model_ready: boolean;
  checks: Record<string, ReadinessCheck>;
};

export type ImageResolution = "standard" | "large" | "high";

export type ImageModelState = "disabled" | "unavailable" | "not_downloaded" | "not_loaded" | "loading" | "loaded" | "error";

export type ImageModelStatus = {
  engine: string;
  model_id: string | null;
  state: ImageModelState;
  detail: string;
  device: string | null;
  optimizations: string[];
  can_generate: boolean;
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
    image_sizes: { resolution: ImageResolution; aspect_ratio: AspectRatio; width: number; height: number }[];
    image_steps: number[];
    max_seed: number;
  };
  generation: {
    available: boolean;
    modes_available: GenerationMode[];
    engine: string;
    model_id: string | null;
    license: { name: string; url: string; attribution: string } | null;
    message: string;
  };
};

export type SourceImageInfo = {
  content_type: "image/png" | "image/jpeg" | "image/webp";
  size_bytes: number;
};

type GenerationBase = { prompt: string; aspect_ratio: AspectRatio; style: string };

export type GenerationPayload =
  | (GenerationBase & {
      mode: "text-to-image";
      resolution: ImageResolution;
      steps: number;
      seed?: number;
      negative_prompt?: string;
      guidance_scale?: number;
      model_id?: string;
    })
  | (GenerationBase & { mode: "text-to-video"; duration_seconds: number })
  | (GenerationBase & { mode: "image-to-video"; duration_seconds: number; source_image: SourceImageInfo });

export type ScenePlan = {
  scene: { category: string; environment: string; weather?: string; time_of_day?: string; lighting: string };
  people: {
    count: number;
    individuals: Array<{
      person_id: number;
      description: string;
      clothing?: string;
      activity?: string;
      position?: string;
    }>;
  };
  composition: { shot_type: string; camera: string; spatial_arrangement: string; objects: string[] };
  prompts: { positive: string; negative: string };
};

export type NormalizedSettings = {
  mode: GenerationMode;
  prompt: string;
  prompt_length: number;
  aspect_ratio: AspectRatio;
  style: string;
  duration_seconds: number | null;
  source_image: SourceImageInfo | null;
  resolution: ImageResolution | null;
  width: number | null;
  height: number | null;
  steps: number | null;
  seed: number | null;
  negative_prompt?: string | null;
  guidance_scale?: number | null;
  model_id?: string | null;
};

export type GenerationStatus = "queued" | "processing" | "completed" | "failed";

export type GeneratedImage = {
  /** Path on the API, e.g. /api/v1/files/images/<id>.png. Resolve with `assetUrl`. */
  url: string;
  download_url: string;
  content_type: "image/png";
  width: number;
  height: number;
  size_bytes: number;
};

export type JobError = { code: string; message: string; retryable: boolean };

export type GenerationJob = {
  id: string;
  status: GenerationStatus;
  settings: NormalizedSettings;
  model_id: string;
  device: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  queue_position: number | null;
  image: GeneratedImage | null;
  error: JobError | null;
};

export type ValidationResponse = {
  valid: true;
  settings: NormalizedSettings;
  generation_available: boolean;
  scene_plan?: ScenePlan;
};

export type ApiErrorDetail = { field: string; message: string };

export type ApiErrorBody = {
  error: { code: string; message: string; details?: ApiErrorDetail[] };
};
