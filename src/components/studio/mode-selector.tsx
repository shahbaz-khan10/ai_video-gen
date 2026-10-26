"use client";

import { useId } from "react";
import { motion } from "motion/react";
import { MODES, type GenerationMode } from "@/lib/studio-options";
import { cn } from "@/lib/cn";

type ModeSelectorProps = {
  value: GenerationMode;
  onChange: (mode: GenerationMode) => void;
};

/** Segmented control for the three generation modes, with a sliding indicator. */
export function ModeSelector({ value, onChange }: ModeSelectorProps) {
  const name = useId();
  return (
    <fieldset>
      <legend className="sr-only">Generation mode</legend>
      <div className="grid grid-cols-3 gap-1 rounded-xl border border-line bg-ink-900 p-1">
        {MODES.map((mode) => {
          const Icon = mode.icon;
          const checked = mode.id === value;
          return (
            <label
              key={mode.id}
              className={cn(
                "relative flex cursor-pointer flex-col items-center gap-1 rounded-lg px-2 py-2.5 text-center text-xs font-medium transition-colors sm:flex-row sm:justify-center sm:gap-2 sm:text-[13px]",
                "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-violet-soft/70",
                checked ? "text-fg" : "text-fg-muted hover:text-fg",
              )}
            >
              <input
                type="radio"
                name={name}
                value={mode.id}
                checked={checked}
                onChange={() => onChange(mode.id)}
                className="sr-only"
              />
              {checked && (
                <motion.span
                  layoutId={`${name}-pill`}
                  aria-hidden
                  className="absolute inset-0 rounded-lg border border-line-strong bg-ink-700 shadow-[inset_0_1px_0_rgb(255_255_255/0.06)]"
                  transition={{ type: "spring", stiffness: 500, damping: 40 }}
                />
              )}
              <Icon className={cn("relative size-4 shrink-0", checked && "text-violet-soft")} aria-hidden />
              <span className="relative">{mode.label}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
