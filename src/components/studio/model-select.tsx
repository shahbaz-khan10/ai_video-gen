"use client";

import { useId } from "react";
import { ChevronDown } from "lucide-react";
import { MODELS } from "@/lib/studio-options";
import { FieldLegend } from "./option-group";

export function ModelSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const id = useId();
  const current = MODELS.find((m) => m.id === value);
  return (
    <fieldset>
      <FieldLegend hint="Model slots are placeholders. Real models will be connected in a later phase.">Model</FieldLegend>
      <div className="relative">
        <select
          id={id}
          aria-label="Model"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={`${id}-note`}
          className="h-10 w-full cursor-pointer appearance-none rounded-lg border border-line bg-ink-900 pl-3 pr-9 text-sm text-fg transition-colors hover:border-line-strong focus-visible:border-violet-soft/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/40"
        >
          {MODELS.map((m) => (
            <option key={m.id} value={m.id} className="bg-ink-850">
              {m.label}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" aria-hidden />
      </div>
      <p id={`${id}-note`} className="mt-2 text-xs text-fg-subtle">
        {current?.note} · not connected
      </p>
    </fieldset>
  );
}
