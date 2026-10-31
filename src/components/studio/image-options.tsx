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
      hint="Exact pixel size depends on the aspect ratio. SD-Turbo is trained at 512×512."
      options={IMAGE_RESOLUTIONS}
      value={value}
      onChange={onChange}
      className="grid-cols-2"
      renderOption={(id) => {
        const option = IMAGE_RESOLUTIONS.find((r) => r.id === id)!;
        const { width, height } = IMAGE_SIZES[id][aspectRatio];
        return (
          <span className="block px-3 py-2.5" title={option.hint}>
            <span className="block text-[13px] font-medium">{option.label}</span>
            <span className="mt-0.5 block font-mono text-[11px] text-fg-subtle">
              {width} × {height}
            </span>
            <span className="sr-only">{option.hint}</span>
          </span>
        );
      }}
    />
  );
}

export function StepsSelector({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <OptionGroup
      legend="Steps"
      hint="Denoising steps. SD-Turbo is built for 1 step; more steps add detail but take longer."
      options={IMAGE_STEPS}
      value={String(value) as "1" | "2" | "4"}
      onChange={(v) => onChange(Number(v))}
      className="grid-cols-3"
      renderOption={(id) => (
        <span className="block px-2 py-2 text-center">
          <span className="block text-xs font-medium">{IMAGE_STEPS.find((s) => s.id === id)!.label}</span>
          <span className="block font-mono text-[10px] text-fg-subtle">
            {id} {id === "1" ? "step" : "steps"}
          </span>
        </span>
      )}
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
      <FieldLegend hint="The same prompt, settings and seed recreate the same image. Leave empty for a random seed.">
        Seed <span className="font-normal text-fg-subtle">(optional)</span>
      </FieldLegend>
      <div className="flex gap-2">
        <input
          id={id}
          aria-label="Seed"
          inputMode="numeric"
          autoComplete="off"
          placeholder="Random"
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
        >
          <Dices className="size-4" aria-hidden />
          Pick
        </button>
      </div>
      {error && (
        <p id={`${id}-error`} className="mt-2 text-xs text-red-300">
          {error}
        </p>
      )}
    </fieldset>
  );
}
