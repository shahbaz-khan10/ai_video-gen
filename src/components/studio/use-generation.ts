"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { api, ApiError } from "@/lib/api/client";
import type { GenerationPayload } from "@/types/api";
import { generationReducer, POLL_INTERVAL_MS, type GenerationState } from "./generation-state";

/**
 * Submits a text-to-image job and polls it until it completes or fails.
 * Polling runs on timers, so the page stays responsive while the GPU works.
 */
export function useGeneration() {
  const [state, dispatch] = useReducer(generationReducer, { phase: "idle" } as GenerationState);
  // Ignores a submit response that arrives after the user reset the panel.
  const submission = useRef(0);

  useEffect(() => {
    if (state.phase !== "running") return;
    const { id } = state.job;
    let cancelled = false;
    // Back off a little while polls are failing.
    const delay = POLL_INTERVAL_MS * (state.failures > 0 ? 2 : 1);
    const timer = setTimeout(() => {
      api
        .getGeneration(id)
        .then((job) => !cancelled && dispatch({ type: "polled", job }))
        .catch((error: unknown) => !cancelled && dispatch({ type: "pollFailed", error }));
    }, delay);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [state]);

  /** Returns the error when the backend rejected the settings (422), so fields can show it; otherwise null. */
  const submit = useCallback(async (payload: GenerationPayload): Promise<ApiError | null> => {
    const token = ++submission.current;
    dispatch({ type: "submit" });
    try {
      const job = await api.createGeneration(payload);
      if (token === submission.current) dispatch({ type: "accepted", job, at: Date.now() });
      return null;
    } catch (error) {
      if (token !== submission.current) return null;
      if (error instanceof ApiError && error.kind === "validation") {
        dispatch({ type: "reset" });
        return error;
      }
      dispatch({ type: "rejected", error });
      return null;
    }
  }, []);

  const reset = useCallback(() => {
    submission.current += 1;
    dispatch({ type: "reset" });
  }, []);

  const resume = useCallback(() => dispatch({ type: "resume" }), []);

  return { state, submit, reset, resume };
}
