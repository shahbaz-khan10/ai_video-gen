"use client";

import { ASPECT_RATIOS } from "@/lib/studio-options";
import { cn } from "@/lib/cn";
import type { AspectRatio } from "@/types/studio";
import { OptionGroup } from "./option-group";

const RATIO_SHAPE: Record<AspectRatio, string> = {
  "16:9": "w-6 h-[13.5px]",
  "9:16": "w-[13.5px] h-6",
  "1:1": "size-[18px]",
};

type AspectRatioSelectorProps = {
  value: AspectRatio;
  onChange: (value: AspectRatio) => void;
  legend?: string;
};

export function AspectRatioSelector({ value, onChange, legend = "Aspect ratio" }: AspectRatioSelectorProps) {
  return (
    <OptionGroup
      legend={legend}
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
            <span className="sr-only">
              {ratio.label}, {ratio.hint}
            </span>
          </span>
        );
      }}
    />
  );
}
