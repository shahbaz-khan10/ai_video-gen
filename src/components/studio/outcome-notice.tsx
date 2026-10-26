"use client";

import { AnimatePresence, motion } from "motion/react";
import { CircleAlert, CircleCheck, LoaderCircle, WifiOff, X, type LucideIcon } from "lucide-react";
import { getStyle } from "@/lib/studio-options";
import { cn } from "@/lib/cn";
import type { CheckOutcome } from "./generation-check";

type Variant = { icon: LucideIcon; box: string; iconClass: string; title: string };

const VARIANTS: Record<CheckOutcome["kind"], Variant> = {
  validated: {
    icon: CircleCheck,
    box: "border-amber-300/25 bg-amber-300/[0.06]",
    iconClass: "text-amber-300",
    title: "Settings validated · AI generation isn't connected yet",
  },
  offline: {
    icon: WifiOff,
    box: "border-line-strong bg-ink-850",
    iconClass: "text-fg-muted",
    title: "Backend unreachable · AI generation isn't connected yet",
  },
  rejected: {
    icon: CircleAlert,
    box: "border-red-400/25 bg-red-400/[0.06]",
    iconClass: "text-red-300",
    title: "The backend rejected these settings",
  },
};

function Body({ outcome }: { outcome: CheckOutcome }) {
  if (outcome.kind === "validated") {
    const s = outcome.settings;
    const summary = [
      `${s.prompt_length}-character prompt`,
      s.aspect_ratio,
      getStyle(s.style).label,
      ...(s.duration_seconds ? [`${s.duration_seconds}s`] : []),
    ].join(" · ");
    return (
      <>
        The studio backend accepted your request ({summary}). No AI model is connected, so nothing was generated.
      </>
    );
  }
  if (outcome.kind === "offline") {
    return (
      <>
        {outcome.message} Your settings passed the browser checks, but they couldn&apos;t be validated by the backend.
        Nothing was generated.
      </>
    );
  }
  return (
    <>
      {outcome.message}
      {outcome.messages.length > 0 ? (
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
          {outcome.messages.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      ) : (
        " Check the highlighted fields."
      )}
    </>
  );
}

type OutcomeNoticeProps = {
  outcome: CheckOutcome | null;
  checking: boolean;
  onDismiss: () => void;
};

/** Live region below the preview that reports what Generate did. */
export function OutcomeNotice({ outcome, checking, onDismiss }: OutcomeNoticeProps) {
  const variant = outcome ? VARIANTS[outcome.kind] : null;
  const Icon = variant?.icon;

  return (
    <div aria-live="polite" role="status">
      <AnimatePresence initial={false} mode="wait">
        {checking && (
          <motion.p
            key="checking"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mx-3 mb-3 flex items-center gap-2 rounded-xl border border-line bg-ink-850 p-3.5 text-sm text-fg-muted"
          >
            <LoaderCircle className="size-4 animate-spin text-violet-soft" aria-hidden />
            Validating with the backend…
          </motion.p>
        )}
        {!checking && outcome && variant && Icon && (
          <motion.div
            key={outcome.kind}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className={cn("m-3 mt-0 flex gap-3 rounded-xl border p-3.5", variant.box)}>
              <Icon className={cn("mt-0.5 size-4 shrink-0", variant.iconClass)} aria-hidden />
              <div className="flex-1 text-sm">
                <p className="font-medium text-fg">{variant.title}</p>
                <div className="mt-1 text-xs leading-relaxed text-fg-muted">
                  <Body outcome={outcome} />
                </div>
              </div>
              <button
                type="button"
                onClick={onDismiss}
                aria-label="Dismiss notice"
                className="grid size-7 shrink-0 place-items-center rounded-md text-fg-subtle transition-colors hover:bg-white/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
