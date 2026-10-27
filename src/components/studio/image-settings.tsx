"use client";

import { useId } from "react";
import { Dices, X } from "lucide-react";
import { IMAGE_RESOLUTIONS, IMAGE_STEPS, SEED_MAX } from "@/lib/studio-options";
import { cn } from "@/lib/cn";
import type { ImageResolution } from "@/types/api";
import type { AspectRatio } from "@/types/studio";
import { FieldLegend, OptionGroup } from "./option-group";

const RESOLUTION_OPTIONS = IMAGE_RESOLUTIONS.map((r) => ({ id: String(r.id) as `${ImageResolution}` }));
const STEP_OPTIONS = IMAGE_STEPS.map((s) => ({ id: String(s.id) }));

export function ResolutionSelector({
  value,
  aspectRatio,
  onChange,
}: {
  value: ImageResolution;
  aspectRatio: AspectRatio;
  onChange: (value: ImageResolution) => void;
}) {
  return (
    <OptionGroup
      legend="Resolution"
      hint="Exact pixel size follows the aspect ratio. Higher sizes take longer and use more GPU memory."
      options={RESOLUTION_OPTIONS}
      value={String(value) as `${ImageResolution}`}
      onChange={(id) => onChange(Number(id) as ImageResolution)}
      className="grid-cols-2"
      renderOption={(id) => {
        const tier = IMAGE_RESOLUTIONS.find((r) => String(r.id) === id)!;
        const [w, h] = tier.sizes[aspectRatio];
        return (
          <span className="flex flex-col gap-0.5 px-3 py-2.5" title={tier.note}>
            <span className="text-xs font-medium">{tier.label}</span>
            <span className="font-mono text-[11px] text-fg-subtle">
              {w}×{h}
            </span>
          </span>
        );
      }}
    />
  );
}

export function StepsSelector({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <OptionGroup
      legend="Quality"
      hint="Denoising steps. SD-Turbo is built for 1 to 4; more steps add detail and time."
      options={STEP_OPTIONS}
      value={String(value)}
      onChange={(id) => onChange(Number(id))}
      className="grid-cols-3"
      renderOption={(id) => {
        const step = IMAGE_STEPS.find((s) => String(s.id) === id)!;
        return (
          <span className="flex flex-col items-center gap-0.5 py-2">
            <span className="text-xs font-medium">{step.label}</span>
            <span className="font-mono text-[11px] text-fg-subtle">
              {step.id} step{step.id > 1 ? "s" : ""}
            </span>
          </span>
        );
      }}
    />
  );
}

/** Returns an error message, or null when the seed is empty (random) or a valid integer. */
export function seedError(value: string): string | null {
  if (!value.trim()) return null;
  if (!/^\d+$/.test(value.trim())) return "Use a whole number, or leave it empty for a random seed.";
  return Number(value) > SEED_MAX ? `The seed can be at most ${SEED_MAX.toLocaleString("en-US")}.` : null;
}

export function SeedInput({
  value,
  onChange,
  error,
}: {
  value: string;
  onChange: (value: string) => void;
  error?: string | null;
}) {
  const id = useId();
  return (
    <fieldset>
      <FieldLegend hint="The same prompt, settings and seed reproduce the same image. Leave empty for a random seed.">
        Seed <span className="font-normal text-fg-subtle">· optional</span>
      </FieldLegend>
      <div className="relative">
        <Dices className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" aria-hidden />
        <input
          id={id}
          aria-label="Seed"
          inputMode="numeric"
          autoComplete="off"
          placeholder="Random"
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/[^\d]/g, ""))}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          className={cn(
            "h-10 w-full rounded-lg border bg-ink-900 pl-9 pr-9 font-mono text-sm text-fg placeholder:font-sans placeholder:text-fg-subtle transition-colors",
            "focus-visible:outline-none focus-visible:ring-2",
            error
              ? "border-red-400/50 focus-visible:ring-red-400/40"
              : "border-line hover:border-line-strong focus-visible:border-violet-soft/50 focus-visible:ring-violet-soft/40",
          )}
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange("")}
            aria-label="Clear seed"
            className="absolute right-1.5 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-md text-fg-subtle transition-colors hover:bg-white/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
          >
            <X className="size-3.5" aria-hidden />
          </button>
        )}
      </div>
      {error && (
        <p id={`${id}-error`} className="mt-2 text-xs text-red-300">
          {error}
        </p>
      )}
    </fieldset>
  );
}
