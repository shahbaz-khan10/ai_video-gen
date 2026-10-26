"use client";

import { Poster } from "@/components/ui/poster";
import { getStyle, VISUAL_STYLES } from "@/lib/studio-options";
import { cn } from "@/lib/cn";
import { OptionGroup } from "./option-group";

type StyleSelectorProps = {
  value: string;
  onChange: (value: string) => void;
  legend?: string;
};

export function StyleSelector({ value, onChange, legend = "Visual style" }: StyleSelectorProps) {
  return (
    <OptionGroup
      legend={legend}
      hint="A starting look for colour, contrast and texture. You can refine it further in the prompt."
      options={VISUAL_STYLES}
      value={value}
      onChange={onChange}
      className="grid-cols-3"
      optionClassName="overflow-hidden"
      renderOption={(id, checked) => {
        const style = getStyle(id);
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
