"use client";

import { LoaderCircle, Sparkles } from "lucide-react";
import { cn } from "@/lib/cn";
import { buttonStyles } from "@/components/ui/button";

type GenerateButtonProps = {
  onClick: () => void;
  label: string;
  /** True while a request or job is in progress. */
  busy?: boolean;
  busyLabel?: string;
  note: string;
};

/** Primary action. A soft sheen sweeps across on hover; static under reduced motion. */
export function GenerateButton({ onClick, label, busy = false, busyLabel = "Working…", note }: GenerateButtonProps) {
  return (
    <div>
      <button
        type="button"
        onClick={onClick}
        disabled={busy}
        aria-busy={busy}
        aria-describedby="generate-note"
        className={cn(buttonStyles({ size: "lg" }), "w-full overflow-hidden")}
      >
        <span
          aria-hidden
          className="absolute inset-y-0 -left-1/3 w-1/3 -skew-x-12 bg-linear-to-r from-transparent via-white/25 to-transparent opacity-0 transition-[left,opacity] duration-700 ease-out group-hover/button:left-[110%] group-hover/button:opacity-100"
        />
        {busy ? (
          <LoaderCircle className="relative size-4 animate-spin" aria-hidden />
        ) : (
          <Sparkles className="relative size-4 transition-transform duration-300 group-hover/button:rotate-12" aria-hidden />
        )}
        <span className="relative">{busy ? busyLabel : label}</span>
      </button>
      <p id="generate-note" className="mt-2 text-center text-xs text-fg-subtle">
        {note}
      </p>
    </div>
  );
}
