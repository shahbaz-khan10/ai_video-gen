import type { GenerationJob } from "@/types/api";

/** A text-to-image job as the backend returns it. Test-only. */
export function makeJob(overrides: Partial<GenerationJob> = {}): GenerationJob {
  return {
    id: "6f1c1d3e-0000-4000-8000-000000000001",
    status: "queued",
    settings: {
      mode: "text-to-image",
      prompt: "A red fox",
      prompt_length: 9,
      aspect_ratio: "1:1",
      style: "cinematic",
      duration_seconds: null,
      source_image: null,
      width: 512,
      height: 512,
      num_inference_steps: 1,
      seed: 42,
    },
    created_at: "2026-10-26T12:00:00Z",
    started_at: null,
    completed_at: null,
    output_url: null,
    result: null,
    error: null,
    error_code: null,
    ...overrides,
  };
}
