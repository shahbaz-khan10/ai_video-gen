// Run with `npm test` (Node's built-in test runner; no extra dependencies).
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { GenerationJob } from "@/types/api";
import {
  formatElapsed,
  isBusy,
  nextPollDelay,
  parseSeed,
  POLL_INTERVAL_MS,
  progressMessage,
  secondsBetween,
  viewFromJob,
  viewFromSubmitError,
} from "./job-view.ts";

function job(overrides: Partial<GenerationJob> = {}): GenerationJob {
  return {
    id: "6f1c3c1e-0000-4000-8000-000000000000",
    status: "queued",
    settings: {
      mode: "text-to-image",
      prompt: "A fox",
      prompt_length: 5,
      aspect_ratio: "1:1",
      style: "cinematic",
      duration_seconds: null,
      source_image: null,
      resolution: "standard",
      width: 512,
      height: 512,
      steps: 1,
      seed: 42,
    },
    model_id: "stabilityai/sd-turbo",
    device: null,
    created_at: "2026-10-27T10:00:00Z",
    started_at: null,
    finished_at: null,
    queue_position: 0,
    image: null,
    error: null,
    ...overrides,
  };
}

const image = {
  url: "/api/v1/files/images/x.png",
  download_url: "/api/v1/files/images/x.png?download=true",
  content_type: "image/png" as const,
  width: 512,
  height: 512,
  size_bytes: 1000,
};

describe("viewFromJob (loading states)", () => {
  it("maps queued with position", () => {
    const view = viewFromJob(job({ queue_position: 2 }));
    assert.equal(view.phase, "queued");
    assert.equal(view.phase === "queued" && view.position, 2);
    assert.equal(isBusy(view), true);
  });

  it("maps processing as busy", () => {
    const view = viewFromJob(job({ status: "processing" }));
    assert.equal(view.phase, "processing");
    assert.equal(isBusy(view), true);
  });

  it("only treats completed as success when an image is present", () => {
    assert.equal(viewFromJob(job({ status: "completed", image })).phase, "completed");
    const noImage = viewFromJob(job({ status: "completed", image: null }));
    assert.equal(noImage.phase, "failed");
  });
});

describe("viewFromJob (error states)", () => {
  it("uses a clear title for GPU out of memory and keeps it retryable", () => {
    const view = viewFromJob(
      job({ status: "failed", error: { code: "gpu_out_of_memory", message: "The GPU ran out of memory.", retryable: true } }),
    );
    assert.equal(view.phase, "failed");
    if (view.phase !== "failed") return;
    assert.equal(view.title, "GPU out of memory");
    assert.equal(view.message, "The GPU ran out of memory.");
    assert.equal(view.retryable, true);
    assert.equal(isBusy(view), false);
  });

  it("falls back to a generic title for unknown codes", () => {
    const view = viewFromJob(job({ status: "failed", error: { code: "weird", message: "x", retryable: false } }));
    assert.equal(view.phase === "failed" && view.title, "Generation failed");
  });
});

describe("viewFromSubmitError", () => {
  it("reports an unreachable backend as retryable", () => {
    const view = viewFromSubmitError({ kind: "network", message: "Couldn't reach the backend." });
    assert.deepEqual(view, {
      phase: "submit-error",
      title: "Backend unreachable",
      message: "Couldn't reach the backend.",
      retryable: true,
    });
  });

  it("does not offer retry for missing model weights", () => {
    const view = viewFromSubmitError({ kind: "http", status: 503, code: "model_not_downloaded", message: "Run the script." });
    assert.equal(view.phase === "submit-error" && view.title, "Model not downloaded");
    assert.equal(view.phase === "submit-error" && view.retryable, false);
  });

  it("offers retry when the queue is full", () => {
    const view = viewFromSubmitError({ kind: "http", status: 429, code: "queue_full", message: "Full." });
    assert.equal(view.phase === "submit-error" && view.retryable, true);
  });
});

describe("polling", () => {
  it("polls at the base interval and backs off on failures", () => {
    assert.equal(nextPollDelay(0), POLL_INTERVAL_MS);
    assert.ok((nextPollDelay(1) ?? 0) > POLL_INTERVAL_MS);
    assert.ok((nextPollDelay(4) ?? Infinity) <= 15_000);
  });

  it("gives up after repeated failures (connection lost)", () => {
    assert.equal(nextPollDelay(5), null);
  });
});

describe("progressMessage", () => {
  it("never shows a percentage", () => {
    const processing = viewFromJob(job({ status: "processing" }));
    for (const state of ["loaded", "not_loaded", null] as const) {
      assert.doesNotMatch(progressMessage(processing, 42, state), /%/);
    }
  });

  it("mentions model loading until the model is loaded", () => {
    const processing = viewFromJob(job({ status: "processing" }));
    assert.match(progressMessage(processing, 1, "not_loaded"), /Loading the model/);
    assert.doesNotMatch(progressMessage(processing, 1, "loaded"), /Loading the model/);
  });

  it("describes queue position", () => {
    assert.match(progressMessage(viewFromJob(job({ queue_position: 1 })), 0, null), /1 job ahead/);
  });
});

describe("helpers", () => {
  it("formats elapsed time", () => {
    assert.equal(formatElapsed(9.7), "9s");
    assert.equal(formatElapsed(75), "1m 15s");
  });

  it("measures durations between timestamps", () => {
    assert.equal(secondsBetween("2026-10-27T10:00:00Z", "2026-10-27T10:00:12.5Z"), 12.5);
    assert.equal(secondsBetween(null, "2026-10-27T10:00:00Z"), null);
  });

  it("parses seeds", () => {
    assert.deepEqual(parseSeed(""), { seed: null });
    assert.deepEqual(parseSeed(" 42 "), { seed: 42 });
    assert.ok(parseSeed("-1").error);
    assert.ok(parseSeed("1.5").error);
    assert.ok(parseSeed(String(2 ** 32)).error);
  });
});

function videoJob(overrides: Partial<GenerationJob> = {}): GenerationJob {
  const base = job();
  return job({
    settings: { ...base.settings, mode: "text-to-video", duration_seconds: 2, width: 576, height: 320, steps: 25, num_frames: 33, fps: 16 },
    model_id: "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
    ...overrides,
  });
}

const VIDEO = {
  url: "/api/v1/files/videos/6f1c3c1e-0000-4000-8000-000000000000.mp4",
  download_url: "/api/v1/files/videos/6f1c3c1e-0000-4000-8000-000000000000.mp4?download=true",
  content_type: "video/mp4" as const,
  width: 576,
  height: 320,
  size_bytes: 640_000,
  num_frames: 33,
  duration_seconds: 2.06,
};

describe("viewFromJob (text-to-video)", () => {
  it("is busy while queued and processing", () => {
    assert.equal(isBusy(viewFromJob(videoJob({ status: "queued" }))), true);
    assert.equal(isBusy(viewFromJob(videoJob({ status: "processing" }))), true);
  });

  it("only reports success when the server returned a real video", () => {
    assert.equal(viewFromJob(videoJob({ status: "completed", video: VIDEO })).phase, "completed");
    const missing = viewFromJob(videoJob({ status: "completed", video: null }));
    assert.equal(missing.phase, "failed");
    assert.ok(missing.phase === "failed" && missing.message.includes("no video"));
  });

  it("an image on a video job does not count as success", () => {
    const view = viewFromJob(videoJob({ status: "completed", image: { url: "/x.png", download_url: "/x.png", content_type: "image/png", width: 1, height: 1, size_bytes: 1 } }));
    assert.equal(view.phase, "failed");
  });

  it("explains an undecodable video and keeps it retryable", () => {
    const view = viewFromJob(
      videoJob({ status: "failed", error: { code: "video_invalid", message: "The video file could not be decoded.", retryable: true } }),
    );
    assert.ok(view.phase === "failed");
    assert.equal(view.title, "Video file was invalid");
    assert.equal(view.retryable, true);
  });

  it("falls back to a video-specific failure message", () => {
    const view = viewFromJob(videoJob({ status: "failed", error: null }));
    assert.ok(view.phase === "failed" && view.message.startsWith("Video generation failed"));
  });

  it("does not offer retry when the video weights are missing", () => {
    const view = viewFromSubmitError({ kind: "http", status: 503, code: "model_not_downloaded", message: "Not downloaded." });
    assert.ok(view.phase === "submit-error" && !view.retryable);
  });

  it("describes video progress honestly, without percentages", () => {
    const msg = progressMessage(viewFromJob(videoJob({ status: "processing" })), 130, null);
    assert.match(msg, /several minutes/);
    assert.match(msg, /2m 10s elapsed/);
    assert.doesNotMatch(msg, /%/);
  });
});
