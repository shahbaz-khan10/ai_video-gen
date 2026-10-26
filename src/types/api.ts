/** Types for the FastAPI backend (`backend/app/schemas`). */

import type { AspectRatio, GenerationMode } from "./studio";

export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
  timestamp: string;
};

export type ReadinessCheck = { status: "ok" | "not_configured" | "error"; detail: string };

export type ReadinessResponse = {
  ready: boolean;
  checks: Record<string, ReadinessCheck>;
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
  };
  generation: { available: boolean; engine: string; message: string };
};

export type SourceImageInfo = {
  content_type: "image/png" | "image/jpeg" | "image/webp";
  size_bytes: number;
};

type GenerationBase = { prompt: string; aspect_ratio: AspectRatio; style: string };

export type GenerationPayload =
  | (GenerationBase & { mode: "text-to-image" })
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
};

export type ValidationResponse = {
  valid: true;
  settings: NormalizedSettings;
  generation_available: boolean;
};

export type ApiErrorDetail = { field: string; message: string };

export type ApiErrorBody = {
  error: { code: string; message: string; details?: ApiErrorDetail[] };
};
