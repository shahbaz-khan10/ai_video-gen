"use client";

import { CircleAlert, RefreshCw, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getApiBaseUrl } from "@/lib/api/client";
import { useBackendStatus, type BackendStatus } from "@/lib/api/use-backend-status";
import { cn } from "@/lib/cn";
import type { ModelState } from "@/types/api";

type Tone = "ok" | "warn" | "off" | "pending";

const DOT: Record<Tone, string> = {
  ok: "bg-emerald-400",
  warn: "bg-amber-300",
  off: "bg-red-400",
  pending: "bg-fg-subtle animate-pulse",
};

function StatusDot({ tone }: { tone: Tone }) {
  return <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", DOT[tone])} />;
}

const MODEL_LABEL: Record<ModelState, { tone: Tone; label: string }> = {
  ready: { tone: "ok", label: "Model loaded" },
  not_loaded: { tone: "ok", label: "Model ready to load" },
  loading: { tone: "pending", label: "Loading model" },
  error: { tone: "warn", label: "Model load failed" },
  weights_missing: { tone: "warn", label: "Model not downloaded" },
  not_installed: { tone: "warn", label: "AI libraries missing" },
  disabled: { tone: "warn", label: "Engine disabled" },
};

function summarize(status: BackendStatus): { tone: Tone; label: string } {
  if (status.state === "loading") return { tone: "pending", label: "Checking backend" };
  if (status.state === "offline") return { tone: "off", label: "Backend offline" };
  return MODEL_LABEL[status.ready.model.state];
}

/** Compact status pill, e.g. in the Create preview header. */
export function BackendStatusPill() {
  const { status } = useBackendStatus();
  const { tone, label } = summarize(status);
  return (
    <span role="status" className="flex items-center gap-1.5 font-mono text-[11px] text-fg-subtle">
      <StatusDot tone={tone} />
      {label}
    </span>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 text-sm">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="flex items-center gap-2 text-right text-fg">
        <StatusDot tone={tone} />
        {value}
      </dd>
    </div>
  );
}

/** Dashboard card with live health, readiness and engine availability. */
export function BackendStatusCard() {
  const { status, retry } = useBackendStatus();

  return (
    <section
      aria-labelledby="backend-status-heading"
      aria-busy={status.state === "loading"}
      className="rounded-xl border border-line bg-ink-900 p-5"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-lg border border-line-strong bg-ink-800 text-violet-soft">
            <Server className="size-[18px]" aria-hidden />
          </span>
          <div>
            <h2 id="backend-status-heading" className="text-[15px] font-medium text-fg">
              Backend
            </h2>
            <p className="font-mono text-[11px] text-fg-subtle">{getApiBaseUrl() ?? "Not configured"}</p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={retry} disabled={status.state === "loading"} aria-label="Check backend again">
          <RefreshCw className={cn("size-3.5", status.state === "loading" && "animate-spin")} aria-hidden />
          <span className="hidden sm:inline">Recheck</span>
        </Button>
      </div>

      <div aria-live="polite" className="mt-4">
        {status.state === "loading" && (
          <dl className="divide-y divide-line">
            <Row label="API" value="Checking…" tone="pending" />
            <Row label="AI engine" value="Checking…" tone="pending" />
          </dl>
        )}

        {status.state === "online" && (
          <>
            <dl className="divide-y divide-line">
              <Row label="API" value={`Online · v${status.health.version}`} tone="ok" />
              <Row label="Ready" value={status.ready.ready ? "Yes" : "No"} tone={status.ready.ready ? "ok" : "off"} />
              <Row
                label="Image model"
                value={MODEL_LABEL[status.ready.model.state].label}
                tone={MODEL_LABEL[status.ready.model.state].tone}
              />
              {status.ready.model.model_id && (
                <Row label="Model ID" value={status.ready.model.model_id} tone={MODEL_LABEL[status.ready.model.state].tone} />
              )}
              <Row
                label="GPU"
                value={
                  status.ready.model.cuda_available === null
                    ? "Unknown"
                    : status.ready.model.cuda_available
                      ? "CUDA available"
                      : "No CUDA · CPU only"
                }
                tone={status.ready.model.cuda_available ? "ok" : "warn"}
              />
            </dl>
            <p className="mt-3 text-xs leading-relaxed text-fg-muted">
              {status.info.generation.message} {status.ready.model.detail}
            </p>
          </>
        )}

        {status.state === "offline" && (
          <div className="flex gap-3 rounded-lg border border-red-400/20 bg-red-400/[0.05] p-3.5">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-red-300" aria-hidden />
            <div className="text-sm">
              <p className="font-medium text-fg">{status.error.message}</p>
              <p className="mt-1 text-xs leading-relaxed text-fg-muted">
                The studio still works, and settings are checked in the browser. To start the API, run{" "}
                <code className="rounded bg-ink-800 px-1 py-0.5 font-mono text-[11px] text-fg">
                  python -m uvicorn app.main:app --reload
                </code>{" "}
                in <code className="font-mono text-[11px] text-fg">backend/</code>.
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
