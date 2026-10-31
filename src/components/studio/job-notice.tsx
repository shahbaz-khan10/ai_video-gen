"use client";

import { AnimatePresence, motion } from "motion/react";
import { CircleAlert, CircleCheck, Download, ExternalLink, LoaderCircle, RotateCcw, WifiOff } from "lucide-react";
import { Button, buttonStyles } from "@/components/ui/button";
import { assetUrl } from "@/lib/api/client";
import { formatElapsed, secondsBetween, type JobView } from "@/lib/generation/job-view";
import { cn } from "@/lib/cn";

type JobNoticeProps = {
  view: JobView;
  progress: string;
  attribution: { text: string; url: string } | null;
  onRetry: () => void;
  onReconnect: () => void;
};

function Card({ tone, children }: { tone: "ok" | "error" | "muted"; children: React.ReactNode }) {
  const tones = {
    ok: "border-emerald-400/20 bg-emerald-400/[0.05]",
    error: "border-red-400/25 bg-red-400/[0.06]",
    muted: "border-line-strong bg-ink-850",
  };
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      className="overflow-hidden"
    >
      <div className={cn("m-3 mt-0 rounded-xl border p-3.5", tones[tone])}>{children}</div>
    </motion.div>
  );
}

function Completed({ view, attribution }: { view: Extract<JobView, { phase: "completed" }>; attribution: JobNoticeProps["attribution"] }) {
  const { job } = view;
  const image = job.image!;
  const s = job.settings;
  const took = secondsBetween(job.started_at, job.finished_at);
  const meta = [
    `${image.width} × ${image.height}`,
    `seed ${s.seed}`,
    `${s.steps} ${s.steps === 1 ? "step" : "steps"}`,
    job.device?.toUpperCase(),
    took !== null ? `${formatElapsed(took)}` : null,
  ].filter(Boolean);
  const download = assetUrl(image.download_url);
  const open = assetUrl(image.url);

  return (
    <div className="flex gap-3">
      <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-300" aria-hidden />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-medium text-fg">Image generated</p>
        <p className="mt-1 font-mono text-[11px] text-fg-muted">{meta.join(" · ")}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {download && (
            <a href={download} className={buttonStyles({ size: "sm" })}>
              <Download className="size-3.5" aria-hidden />
              Download PNG
            </a>
          )}
          {open && (
            <a href={open} target="_blank" rel="noopener noreferrer" className={buttonStyles({ variant: "secondary", size: "sm" })}>
              <ExternalLink className="size-3.5" aria-hidden />
              Open full size
            </a>
          )}
        </div>
        <p className="mt-3 text-[11px] text-fg-subtle">
          Generated locally with <span className="font-mono">{job.model_id}</span>
          {attribution && (
            <>
              {" · "}
              <a href={attribution.url} target="_blank" rel="noopener noreferrer" className="underline-offset-2 hover:text-fg hover:underline">
                {attribution.text}
              </a>
            </>
          )}
        </p>
      </div>
    </div>
  );
}

/** Live region below the preview describing the real state of the current job. */
export function JobNotice({ view, progress, attribution, onRetry, onReconnect }: JobNoticeProps) {
  return (
    <div role="status" aria-live="polite">
      <AnimatePresence initial={false} mode="wait">
        {(view.phase === "submitting" || view.phase === "queued" || view.phase === "processing") && (
          <Card key="busy" tone="muted">
            <p className="flex items-center gap-2 text-sm text-fg-muted">
              <LoaderCircle className="size-4 shrink-0 animate-spin text-violet-soft" aria-hidden />
              {progress}
            </p>
          </Card>
        )}

        {view.phase === "completed" && (
          <Card key={`done-${view.job.id}`} tone="ok">
            <Completed view={view} attribution={attribution} />
          </Card>
        )}

        {(view.phase === "failed" || view.phase === "submit-error") && (
          <Card key="error" tone="error">
            <div className="flex gap-3">
              <CircleAlert className="mt-0.5 size-4 shrink-0 text-red-300" aria-hidden />
              <div className="flex-1 text-sm">
                <p className="font-medium text-fg">{view.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-fg-muted">{view.message}</p>
                {view.retryable && (
                  <Button variant="secondary" size="sm" onClick={onRetry} className="mt-3">
                    <RotateCcw className="size-3.5" aria-hidden />
                    Try again
                  </Button>
                )}
              </div>
            </div>
          </Card>
        )}

        {view.phase === "connection-lost" && (
          <Card key="lost" tone="muted">
            <div className="flex gap-3">
              <WifiOff className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden />
              <div className="flex-1 text-sm">
                <p className="font-medium text-fg">Lost connection to the backend</p>
                <p className="mt-1 text-xs leading-relaxed text-fg-muted">
                  Your image may still be generating. Reconnect to check its status.
                </p>
                <Button variant="secondary" size="sm" onClick={onReconnect} className="mt-3">
                  <RotateCcw className="size-3.5" aria-hidden />
                  Reconnect
                </Button>
              </div>
            </div>
          </Card>
        )}
      </AnimatePresence>
    </div>
  );
}
