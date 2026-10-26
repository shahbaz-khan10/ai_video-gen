"use client";

import { useCallback, useEffect, useState } from "react";
import type { HealthResponse, InfoResponse, ReadinessResponse } from "@/types/api";
import { api, ApiError } from "./client";

export type BackendStatus =
  | { state: "loading" }
  | { state: "online"; health: HealthResponse; ready: ReadinessResponse; info: InfoResponse }
  | { state: "offline"; error: ApiError };

function toApiError(err: unknown) {
  return err instanceof ApiError ? err : new ApiError("network", "Couldn't reach the backend.");
}

/** Fetches health, readiness and info together. `retry` re-runs the checks. */
export function useBackendStatus() {
  const [status, setStatus] = useState<BackendStatus>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.health(), api.ready(), api.info()])
      .then(([health, ready, info]) => {
        if (!cancelled) setStatus({ state: "online", health, ready, info });
      })
      .catch((err: unknown) => {
        if (!cancelled) setStatus({ state: "offline", error: toApiError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setStatus({ state: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  return { status, retry };
}
