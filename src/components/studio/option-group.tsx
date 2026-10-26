"use client";

import { useId, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { InfoHint } from "@/components/ui/info-hint";

type OptionGroupProps<T extends string> = {
  legend: string;
  hint?: string;
  options: readonly { id: T }[];
  value: T;
  onChange: (value: T) => void;
  renderOption: (id: T, checked: boolean) => ReactNode;
  className?: string;
  optionClassName?: string;
};

/**
 * Accessible single-choice group built on native radio inputs, so arrow-key
 * navigation and form semantics work for free. Visuals come from `renderOption`.
 */
export function OptionGroup<T extends string>({
  legend,
  hint,
  options,
  value,
  onChange,
  renderOption,
  className,
  optionClassName,
}: OptionGroupProps<T>) {
  const name = useId();
  return (
    <fieldset>
      <FieldLegend hint={hint}>{legend}</FieldLegend>
      <div className={cn("grid gap-2", className)}>
        {options.map(({ id }) => {
          const checked = id === value;
          return (
            <label
              key={id}
              className={cn(
                "relative cursor-pointer rounded-lg border transition-[border-color,background-color,color] duration-200",
                "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-violet-soft/70",
                checked
                  ? "border-violet-soft/50 bg-violet/[0.08] text-fg"
                  : "border-line bg-ink-900 text-fg-muted hover:border-line-strong hover:text-fg",
                optionClassName,
              )}
            >
              <input
                type="radio"
                name={name}
                value={id}
                checked={checked}
                onChange={() => onChange(id)}
                className="sr-only"
              />
              {renderOption(id, checked)}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export function FieldLegend({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <legend className="mb-2.5 flex items-center gap-1.5 text-[13px] font-medium text-fg">
      {children}
      {hint && <InfoHint label={hint} />}
    </legend>
  );
}
