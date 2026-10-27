import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/client";
import {
  describeApiError,
  formatElapsed,
  generationReducer,
  isBusy,
  MAX_POLL_FAILURES,
  progressMessage,
  type GenerationState,
} from "./generation-state";
import { makeJob } from "./test-fixtures";

const idle: GenerationState = { phase: "idle" };
const submitting = generationReducer(idle, { type: "submit" });
const running = generationReducer(submitting, { type: "accepted", job: makeJob(), at: 1000 });

describe("generationReducer", () => {
  it("goes idle → submitting → running", () => {
    expect(submitting.phase).toBe("submitting");
    expect(running).toMatchObject({ phase: "running", failures: 0, acceptedAt: 1000 });
    expect(isBusy(submitting) && isBusy(running)).toBe(true);
  });

  it("ignores a second submit while busy", () => {
    expect(generationReducer(running, { type: "submit" })).toBe(running);
  });

  it("tracks processing, then completes only with an image URL", () => {
    const processing = generationReducer(running, { type: "polled", job: makeJob({ status: "processing" }) });
    expect(processing).toMatchObject({ phase: "running", job: { status: "processing" } });

    const done = generationReducer(processing, {
      type: "polled",
      job: makeJob({ status: "completed", output_url: `/api/v1/files/images/${"a".repeat(32)}.png` }),
    });
    expect(done.phase).toBe("completed");
  });

  it("never reports success when a completed job has no image", () => {
    const state = generationReducer(running, { type: "polled", job: makeJob({ status: "completed" }) });
    expect(state).toMatchObject({ phase: "failed", error: { code: "missing_output" } });
  });

  it("shows the backend's message and a hint for failed jobs", () => {
    const state = generationReducer(running, {
      type: "polled",
      job: makeJob({ status: "failed", error_code: "gpu_out_of_memory", error: "The GPU ran out of memory." }),
    });
    expect(state).toMatchObject({
      phase: "failed",
      error: { title: "GPU out of memory", message: "The GPU ran out of memory.", retryable: true },
    });
    if (state.phase === "failed") expect(state.error.hint).toMatch(/smaller resolution/);
  });

  it("ignores poll results for a different job", () => {
    const other = makeJob({ id: "other", status: "completed", output_url: "/x" });
    expect(generationReducer(running, { type: "polled", job: other })).toBe(running);
  });

  it("tolerates a few failed polls, then reports a lost connection", () => {
    const offline = new ApiError("network", "Couldn't reach the backend. Is it running?");
    let state = running;
    for (let i = 1; i < MAX_POLL_FAILURES; i++) {
      state = generationReducer(state, { type: "pollFailed", error: offline });
      expect(state).toMatchObject({ phase: "running", failures: i });
    }
    state = generationReducer(state, { type: "pollFailed", error: offline });
    expect(state.phase).toBe("disconnected");

    const resumed = generationReducer(state, { type: "resume" });
    expect(resumed).toMatchObject({ phase: "running", failures: 0, acceptedAt: 1000 });
  });

  it("fails at once when the backend no longer knows the job (restart)", () => {
    const gone = new ApiError("http", "No generation exists with this ID.", 404, "generation_not_found");
    const state = generationReducer(running, { type: "pollFailed", error: gone });
    expect(state).toMatchObject({ phase: "failed", error: { title: "Generation lost" } });
  });

  it("explains a rejected submission", () => {
    const missing = new ApiError("http", "Weights are not downloaded.", 503, "model_not_downloaded");
    const state = generationReducer(submitting, { type: "rejected", error: missing });
    expect(state).toMatchObject({ phase: "failed", job: null, error: { title: "Model not downloaded" } });
    if (state.phase === "failed") expect(state.error.hint).toMatch(/download_model\.py/);
  });

  it("reset returns to idle from anywhere", () => {
    expect(generationReducer(running, { type: "reset" })).toEqual({ phase: "idle" });
  });
});

describe("messages", () => {
  it("describes an unreachable backend with how to start it", () => {
    const err = describeApiError(new ApiError("network", "Couldn't reach the backend. Is it running?"));
    expect(err).toMatchObject({ title: "Backend unreachable", retryable: true });
    expect(err.hint).toMatch(/uvicorn/);
  });

  it("progress text never invents a percentage", () => {
    const queued = progressMessage(running)!;
    const processing = progressMessage({ phase: "running", job: makeJob({ status: "processing" }), failures: 0, acceptedAt: 0 })!;
    expect(queued.title).toMatch(/queue/i);
    expect(processing.title).toMatch(/Generating/);
    for (const m of [queued, processing]) expect(`${m.title} ${m.detail}`).not.toMatch(/\d+\s*%/);
    expect(progressMessage(idle)).toBeNull();
  });

  it("formats elapsed time", () => {
    expect(formatElapsed(0)).toBe("0s");
    expect(formatElapsed(59_900)).toBe("59s");
    expect(formatElapsed(125_000)).toBe("2m 05s");
  });
});
