"use client";

import { useId } from "react";
import { Dices } from "lucide-react";
import { IMAGE_RESOLUTIONS, IMAGE_SIZES, IMAGE_STEPS } from "@/lib/studio-options";
import { cn } from "@/lib/cn";
import type { ImageResolution } from "@/types/api";
import type { AspectRatio } from "@/types/studio";
import { FieldLegend, OptionGroup } from "./option-group";

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
      hint="Pixel dimensions adjusted for aspect ratio. Large and Ultra High offer superior multi-person detail."
      options={IMAGE_RESOLUTIONS}
      value={value}
      onChange={onChange}
      className="grid-cols-3"
      renderOption={(id) => {
        const option = IMAGE_RESOLUTIONS.find((r) => r.id === id) || IMAGE_RESOLUTIONS[0];
        const { width, height } = (IMAGE_SIZES[id] || IMAGE_SIZES.standard)[aspectRatio];
        return (
          <span className="block px-2.5 py-2 text-center" title={option.hint}>
            <span className="block text-xs font-medium">{option.label}</span>
            <span className="mt-0.5 block font-mono text-[10px] text-fg-subtle">
              {width} × {height}
            </span>
          </span>
        );
      }}
    />
  );
}

export function StepsSelector({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const currentStepId = IMAGE_STEPS.some((s) => s.steps === value)
    ? String(value)
    : value <= 4
    ? "4"
    : value <= 20
    ? "20"
    : value <= 25
    ? "25"
    : "35";

  const stepOptions = IMAGE_STEPS.map((s) => ({ id: String(s.steps), label: s.label }));

  return (
    <OptionGroup
      legend="Denoising Steps"
      hint="Higher step counts (20-35) produce sharp facial features, lifelike skin textures, and clean hands."
      options={stepOptions}
      value={currentStepId}
      onChange={(v) => onChange(Number(v))}
      className="grid-cols-4"
      renderOption={(id) => {
        const found = IMAGE_STEPS.find((s) => String(s.steps) === id);
        return (
          <span className="block px-1.5 py-2 text-center" title={found?.hint}>
            <span className="block text-xs font-medium">{id}</span>
            <span className="block font-mono text-[9px] text-fg-subtle">steps</span>
          </span>
        );
      }}
    />
  );
}

export function SeedInput({
  value,
  onChange,
  error,
}: {
  value: string;
  onChange: (value: string) => void;
  error?: string;
}) {
  const id = useId();
  return (
    <fieldset>
      <FieldLegend hint="Lock the seed to preserve subject identity and composition across prompt edits.">
        Seed <span className="font-normal text-fg-subtle">(optional)</span>
      </FieldLegend>
      <div className="flex gap-2">
        <input
          id={id}
          aria-label="Seed"
          inputMode="numeric"
          autoComplete="off"
          placeholder="Random seed"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : undefined}
          className={cn(
            "h-10 min-w-0 flex-1 rounded-lg border bg-ink-900 px-3 font-mono text-sm text-fg placeholder:font-sans placeholder:text-fg-subtle transition-colors hover:border-line-strong focus-visible:border-violet-soft/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/40",
            error ? "border-red-400/50" : "border-line",
          )}
        />
        <button
          type="button"
          onClick={() => onChange(String(Math.floor(Math.random() * 2 ** 32)))}
          className="flex h-10 shrink-0 items-center gap-1.5 rounded-lg border border-line bg-ink-900 px-3 text-xs text-fg-muted transition-colors hover:border-line-strong hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
          title="Pick a random seed"
        >
          <Dices className="size-3.5" aria-hidden />
          Random
        </button>
      </div>
      {error && (
        <p id={`${id}-error`} className="mt-1.5 text-xs text-red-300">
          {error}
        </p>
      )}
    </fieldset>
  );
}
