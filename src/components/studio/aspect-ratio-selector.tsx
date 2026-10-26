"use client";

import { useId } from "react";
import { ChevronDown } from "lucide-react";
import { Poster } from "@/components/ui/poster";
import { ASPECT_RATIOS, MODELS, VISUAL_STYLES, type AspectRatio } from "@/lib/studio-options";
import { cn } from "@/lib/cn";
import { FieldLegend, OptionGroup } from "./option-group";

const RATIO_SHAPE: Record<AspectRatio, string> = {
  "16:9": "w-6 h-[13.5px]",
  "9:16": "w-[13.5px] h-6",
  "1:1": "size-[18px]",
};

export function AspectRatioSelector({ value, onChange }: { value: AspectRatio; onChange: (v: AspectRatio) => void }) {
  return (
    <OptionGroup
      legend="Aspect ratio"
      hint="Choose the frame for where the result will be published."
      options={ASPECT_RATIOS}
      value={value}
      onChange={onChange}
      className="grid-cols-3"
      renderOption={(id, checked) => {
        const ratio = ASPECT_RATIOS.find((r) => r.id === id)!;
        return (
          <span className="flex flex-col items-center gap-2 px-2 py-3" title={ratio.hint}>
            <span className="grid h-6 place-items-center" aria-hidden>
              <span
                className={cn(
                  "rounded-[3px] border-[1.5px] transition-colors",
                  RATIO_SHAPE[id],
                  checked ? "border-violet-soft bg-violet-soft/15" : "border-current",
                )}
              />
            </span>
            <span className="text-xs font-medium">{id}</span>
            <span className="sr-only">{ratio.label}, {ratio.hint}</span>
          </span>
        );
      }}
    />
  );
}

export function StyleSelector({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <OptionGroup
      legend="Visual style"
      hint="A starting look for colour, contrast and texture. You can refine it further in the prompt."
      options={VISUAL_STYLES}
      value={value}
      onChange={onChange}
      className="grid-cols-3"
      optionClassName="overflow-hidden"
      renderOption={(id, checked) => {
        const style = VISUAL_STYLES.find((s) => s.id === id)!;
        return (
          <span className="block">
            <Poster
              tone={style.tone}
              className={cn("h-12 transition-opacity duration-200", checked ? "opacity-100" : "opacity-70")}
            />
            <span className="block truncate px-2 py-1.5 text-center text-xs font-medium">{style.label}</span>
          </span>
        );
      }}
    />
  );
}

const DURATIONS = [{ id: "4s" }, { id: "6s" }, { id: "8s" }] as const;
export type Duration = (typeof DURATIONS)[number]["id"];

export function DurationSelector({ value, onChange }: { value: Duration; onChange: (v: Duration) => void }) {
  return (
    <OptionGroup
      legend="Clip length"
      hint="Shorter clips usually hold together better. Length limits will depend on the connected model."
      options={DURATIONS}
      value={value}
      onChange={onChange}
      className="grid-cols-3"
      renderOption={(id) => <span className="block py-2 text-center text-xs font-medium">{id}</span>}
    />
  );
}

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
