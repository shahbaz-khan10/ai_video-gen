/**
 * The single place the frontend talks to the FastAPI backend.
 * Components call the typed functions in `api`, never `fetch` directly.
 */

import type {
  ApiErrorBody,
  ApiErrorDetail,
  GenerationPayload,
  HealthResponse,
  InfoResponse,
  ReadinessResponse,
  ValidationResponse,
} from "@/types/api";

const DEV_FALLBACK_URL = "http://localhost:8000";
const API_PREFIX = "/api/v1";
const TIMEOUT_MS = 8000;

/** Resolved base URL, or null when no backend is configured (e.g. a production build without the env var). */
export function getApiBaseUrl(): string | null {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured) return configured.replace(/\/+$/, "");
  return process.env.NODE_ENV === "development" ? DEV_FALLBACK_URL : null;
}

export type ApiErrorKind =
  | "unconfigured" // no base URL
  | "network" // backend unreachable (offline, refused, CORS)
  | "timeout"
  | "validation" // 422 from the backend
  | "http"; // any other non-2xx

export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    message: string,
    readonly status?: number,
    readonly code?: string,
    readonly details: ApiErrorDetail[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True when the backend could not be reached at all. */
  get isUnavailable() {
    return this.kind === "unconfigured" || this.kind === "network" || this.kind === "timeout";
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ApiErrorBody).error?.message === "string"
  );
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const base = getApiBaseUrl();
  if (!base) throw new ApiError("unconfigured", "The backend URL is not configured (NEXT_PUBLIC_API_BASE_URL).");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(`${base}${API_PREFIX}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}) },
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("timeout", "The backend took too long to respond.");
    }
    throw new ApiError("network", "Couldn't reach the backend. Is it running?");
  } finally {
    clearTimeout(timer);
  }

  const body: unknown = await res.json().catch(() => null);

  if (!res.ok) {
    if (isErrorBody(body)) {
      const { code, message, details } = body.error;
      throw new ApiError(res.status === 422 ? "validation" : "http", message, res.status, code, details ?? []);
    }
    throw new ApiError("http", `The backend responded with an error (${res.status}).`, res.status);
  }
  if (body === null) throw new ApiError("http", "The backend returned an unreadable response.", res.status);
  return body as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  ready: () => request<ReadinessResponse>("/health/ready"),
  info: () => request<InfoResponse>("/info"),
  validateGeneration: (payload: GenerationPayload) =>
    request<ValidationResponse>("/generations/validate", { method: "POST", body: JSON.stringify(payload) }),
};
