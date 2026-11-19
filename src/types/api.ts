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

/** Video size tiers: standard ≈ 320p draft, large = 480p. 720p is not offered by the 1.3B model. */
export type VideoResolution = "standard" | "large";

export type VideoAvailability = {
  available: boolean;
  engine: string;
  model_id: string | null;
  state: ImageModelState;
  detail: string;
  device: string | null;
  license: { name: string; url: string; attribution: string } | null;
  message: string;
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
    /** Text-to-video: the video model's real limits. Anything else is rejected by the API. */
    video_duration_options_seconds: number[];
    video_sizes: { resolution: VideoResolution; aspect_ratio: AspectRatio; width: number; height: number }[];
    video_steps: number[];
    video_sampler?: string;
    video_max_frames: number;
    video_fps: number;
    /** "High quality" text-to-video (Wan2.2 TI2V-5B) weights are on the server. */
    video_hq_available?: boolean;
    video_hq_detail?: string;
  };
  generation: {
    available: boolean;
    modes_available: GenerationMode[];
    engine: string;
    model_id: string | null;
    license: { name: string; url: string; attribution: string } | null;
    message: string;
  };
  video: VideoAvailability;
};

export type SourceImageInfo = {
  /** From POST /uploads/images. */
  upload_id: string;
  content_type?: "image/png" | "image/jpeg" | "image/webp" | null;
  size_bytes?: number | null;
};

/** POST /uploads/images: the stored, re-encoded image. */
export type UploadedImage = {
  upload_id: string;
  width: number;
  height: number;
  content_type: "image/png" | "image/jpeg" | "image/webp";
  size_bytes: number;
};

export type I2VQuality = "draft" | "quality";
/** Text-to-video model: fast = FastWan2.1 1.3B, high = Wan2.2 TI2V-5B (single clips, much slower). */
export type T2VQuality = "fast" | "high";
export type I2VMotion = "subtle" | "normal" | "strong";
export type I2VCamera = "none" | "static" | "zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "tilt_up" | "orbit";

type GenerationBase = { prompt: string; aspect_ratio: AspectRatio; style: string; prompt_agent?: boolean };

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
  | (GenerationBase & {
      mode: "text-to-video";
      duration_seconds: number;
      resolution?: VideoResolution;
      steps?: number;
      seed?: number;
      /** Long videos (over 5 s) only: the reviewed/edited scene list. */
      scenes?: SceneInput[];
      continuity?: "prompt" | "last_frame";
      quality?: T2VQuality;
    })
  | (GenerationBase & {
      mode: "image-to-video";
      duration_seconds: number;
      source_image: SourceImageInfo;
      resolution?: VideoResolution;
      quality?: I2VQuality;
      motion?: I2VMotion;
      camera?: I2VCamera;
      seed?: number;
    });

export type SceneInput = { description: string; duration_seconds?: number };

/** How the backend understood a prompt (POST /generations/scene-plan, and `plan` on every job). */
export type GenerationPlan = {
  original_prompt: string;
  planner: string;
  main_subject: string | null;
  people_count: number | null;
  characters: {
    id: string;
    kind: "person" | "group" | "animal" | "creature";
    count: number | null;
    description: string;
    age: string | null;
    clothing: string | null;
    position: string | null;
    action: string | null;
  }[];
  objects: { name: string; position: string | null }[];
  environment: {
    location: string | null;
    setting: "indoor" | "outdoor" | null;
    background: string[];
    weather: string | null;
    time_of_day: string | null;
    lighting: string | null;
  };
  camera: { shot_type: string | null; angle: string | null; movement: string | null };
  style: string | null;
  scenes: { index: number; description: string; duration_seconds: number | null }[];
  instructions: {
    text: string;
    covered_by: string[];
    reaches_model: boolean;
    status: InstructionStatus;
    note?: string | null;
    targets?: string[];
  }[];
  limitations: string[];
  model_prompt: string | null;
  /** The exact prompt of every model call (one per scene for long videos), measured with the model's tokenizer. */
  compiled?: CompiledPrompt[];
};

export type InstructionStatus = "included" | "compressed" | "unsupported" | "omitted_budget";

export type CompiledPrompt = {
  target: string;
  model: string;
  text: string;
  tokens: number;
  budget: number;
  measured: boolean;
  components: { name: string; status: "included" | "compressed" | "omitted"; text: string; full_text: string }[];
};

export type SceneJob = {
  index: number;
  description: string;
  prompt: string;
  duration_seconds: number;
  /** Frame count of each clip in this scene. */
  clips: number[];
  clips_completed: number;
  status: GenerationStatus;
  error: JobError | null;
};

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
  num_frames?: number | null;
  fps?: number | null;
  seed: number | null;
  negative_prompt?: string | null;
  guidance_scale?: number | null;
  model_id?: string | null;
  quality?: I2VQuality | null;
  motion?: I2VMotion | null;
  camera?: I2VCamera | null;
};

export type GenerationStatus = "queued" | "processing" | "completed" | "failed";

export type GeneratedVideo = {
  /** Path on the API, e.g. /api/v1/files/videos/<id>.mp4. Resolve with `assetUrl`. */
  url: string;
  download_url: string;
  content_type: "video/mp4";
  width: number;
  height: number;
  size_bytes: number;
  num_frames: number | null;
  duration_seconds: number | null;
};

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
  video?: GeneratedVideo | null;
  error: JobError | null;
  plan?: GenerationPlan | null;
  scenes?: SceneJob[];
  clips_total?: number | null;
  clips_completed?: number | null;
  agent?: AgentResult | null;
};

export type TalkLanguage = "en" | "hi" | "ur";
export type Voice = { id: string; name: string; gender: "male" | "female"; seconds: number };
export type TalkJob = {
  id: string;
  status: "queued" | "speaking" | "lip_syncing" | "completed" | "failed";
  created_at: string;
  finished_at: string | null;
  audio_seconds: number | null;
  speech_seconds: number | null;
  lipsync_seconds: number | null;
  video_url: string | null;
  error: string | null;
  speaker?: "male" | "female" | null;
  voice_used?: string | null;
};

/** What the prompt agent (Florence-2) saw in the photo, checked in the result and retried. */
export type AgentResult = {
  description: string | null;
  checks: { name: string; expected: string; found: string; passed: boolean }[];
  attempts: number;
  notes: string[];
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
