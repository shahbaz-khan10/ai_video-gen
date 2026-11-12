"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api/client";
import type { GenerationJob, GenerationPayload, ImageModelState } from "@/types/api";
import { isBusy, nextPollDelay, POLL_INTERVAL_MS, viewFromJob, viewFromSubmitError, type JobView } from "./job-view";

/**
 * Submits a text-to-image job and polls its real status until it completes or fails.
 * Polling backs off on network errors and reports "connection-lost" instead of guessing.
 */
export function useImageJob() {
  const [view, setView] = useState<JobView>({ phase: "idle" });
  const [jobId, setJobId] = useState<string | null>(null);
  const [modelState, setModelState] = useState<ImageModelState | null>(null);
  // Bumped to restart polling after a lost connection.
  const [pollRun, setPollRun] = useState(0);
  const lastJob = useRef<GenerationJob | null>(null);
  const submitId = useRef(0);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    const schedule = (delay: number) => {
      timer = setTimeout(tick, delay);
    };

    async function tick() {
      try {
        const [job, model] = await Promise.all([
          api.getGeneration(jobId!),
          api.imageModel().catch(() => null), // cheap status; never loads the model
        ]);
        if (cancelled) return;
        failures = 0;
        lastJob.current = job;
        if (model) setModelState(model.state);
        const next = viewFromJob(job);
        setView(next);
        if (isBusy(next)) schedule(POLL_INTERVAL_MS);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          // Jobs are kept in memory; a backend restart loses them.
          setView({
            phase: "submit-error",
            title: "Job no longer exists",
            message: "The backend restarted and this job was lost. Generate again.",
            retryable: true,
          });
          return;
        }
        failures += 1;
        const delay = nextPollDelay(failures);
        if (delay === null && lastJob.current) setView({ phase: "connection-lost", job: lastJob.current });
        else if (delay !== null) schedule(delay);
      }
    }

    schedule(POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId, pollRun]);

  const submit = useCallback(async (payload: GenerationPayload) => {
    const id = ++submitId.current;
    setJobId(null);
    setView({ phase: "submitting" });
    api
      .imageModel()
      .then((m) => id === submitId.current && setModelState(m.state))
      .catch(() => undefined);
    try {
      const job = await api.createGeneration(payload);
      if (id !== submitId.current) return;
      lastJob.current = job;
      const next = viewFromJob(job);
      setView(next);
      if (isBusy(next)) setJobId(job.id);
    } catch (err) {
      if (id !== submitId.current) return;
      const failure =
        err instanceof ApiError
          ? { kind: err.kind, status: err.status, code: err.code, message: err.message }
          : { kind: "network", message: "Couldn't reach the backend." };
      setView(viewFromSubmitError(failure));
    }
  }, []);

  /** Resume polling after a lost connection; the job may have finished meanwhile. */
  const reconnect = useCallback(() => {
    const job = lastJob.current;
    if (!job) return;
    setView(viewFromJob(job));
    setJobId(job.id);
    setPollRun((n) => n + 1);
  }, []);

  /** Follow a job the server re-queued (e.g. a retried scene), polling it like a fresh submit. */
  const adopt = useCallback((job: GenerationJob) => {
    submitId.current += 1;
    lastJob.current = job;
    const next = viewFromJob(job);
    setView(next);
    setJobId(job.id);
    setPollRun((n) => n + 1);
  }, []);

  const reset = useCallback(() => {
    submitId.current += 1;
    setJobId(null);
    setView({ phase: "idle" });
  }, []);

  return { view, modelState, submit, reconnect, adopt, reset };
}
