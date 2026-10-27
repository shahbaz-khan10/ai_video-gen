import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ApiError } from "@/lib/api/client";
import { GeneratedImage, GenerationFooter, GenerationProgress } from "./generation-result";
import { generationReducer, type GenerationState } from "./generation-state";
import { makeJob } from "./test-fixtures";

afterEach(cleanup);

const IMAGE_PATH = `/api/v1/files/images/${"ab".repeat(16)}.png`;
const completedJob = makeJob({
  status: "completed",
  output_url: IMAGE_PATH,
  result: {
    width: 512,
    height: 512,
    seed: 42,
    num_inference_steps: 1,
    model_id: "stabilityai/sd-turbo",
    device: "cuda",
    duration_seconds: 1.4,
  },
});

function renderFooter(state: GenerationState) {
  const handlers = { onRetry: vi.fn(), onResume: vi.fn(), onReuseSeed: vi.fn(), onDismiss: vi.fn() };
  render(<GenerationFooter state={state} {...handlers} />);
  return handlers;
}

describe("GenerationProgress", () => {
  it("shows a loading state while queued, without a percentage", () => {
    render(<GenerationProgress state={{ phase: "running", job: makeJob(), failures: 0, acceptedAt: Date.now() }} />);
    const status = screen.getByRole("status");
    expect(status.textContent).toMatch(/Waiting in the queue/);
    expect(status.textContent).not.toMatch(/%/);
  });

  it("shows a sending state while submitting", () => {
    render(<GenerationProgress state={{ phase: "submitting" }} />);
    expect(screen.getByRole("status").textContent).toMatch(/Sending to the backend/);
  });

  it("renders nothing when idle", () => {
    const { container } = render(<GenerationProgress state={{ phase: "idle" }} />);
    expect(container.textContent).toBe("");
  });
});

describe("GenerationFooter", () => {
  it("offers a download of the real image and its metadata when completed", () => {
    const { onReuseSeed } = renderFooter({ phase: "completed", job: completedJob });
    const link = screen.getByRole("link", { name: /Download PNG/ });
    expect(link.getAttribute("href")).toBe(`http://localhost:8000${IMAGE_PATH}?download=true`);
    expect(screen.getByText("seed 42")).toBeTruthy();
    expect(screen.getByText("stabilityai/sd-turbo")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Reuse seed/ }));
    expect(onReuseSeed).toHaveBeenCalledWith(42);
  });

  it("explains a failure and offers a retry", () => {
    const state = generationReducer(
      { phase: "submitting" },
      { type: "rejected", error: new ApiError("http", "The GPU ran out of memory.", 500, "gpu_out_of_memory") },
    );
    const { onRetry } = renderFooter(state);
    expect(screen.getByText("GPU out of memory")).toBeTruthy();
    expect(screen.getByText("The GPU ran out of memory.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("hides retry when retrying can't help", () => {
    renderFooter({
      phase: "failed",
      job: null,
      error: { title: "AI libraries not installed", message: "Not installed.", retryable: false },
    });
    expect(screen.queryByRole("button", { name: /Try again/ })).toBeNull();
  });

  it("lets the user check again after losing the backend", () => {
    const { onResume } = renderFooter({
      phase: "disconnected",
      job: makeJob({ status: "processing" }),
      acceptedAt: 0,
      error: { title: "Backend unreachable", message: "Couldn't reach the backend.", retryable: true },
    });
    expect(screen.getByText("Lost contact with the backend")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Check again/ }));
    expect(onResume).toHaveBeenCalled();
  });

  it("renders nothing before the first generation", () => {
    renderFooter({ phase: "idle" });
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("GeneratedImage", () => {
  it("loads the image from the backend file route", () => {
    render(<GeneratedImage job={completedJob} />);
    expect(screen.getByRole("img").getAttribute("src")).toBe(`http://localhost:8000${IMAGE_PATH}`);
  });

  it("refuses URLs outside the backend's image route", () => {
    render(<GeneratedImage job={{ ...completedJob, output_url: "https://evil.example/x.png" }} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText(/couldn't be loaded/)).toBeTruthy();
  });

  it("shows a message if the browser can't fetch the file", () => {
    render(<GeneratedImage job={completedJob} />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByText(/couldn't be loaded/)).toBeTruthy();
  });
});
