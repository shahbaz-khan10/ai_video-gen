import { useId, type ReactNode } from "react";
import { cn } from "@/lib/cn";

type TooltipProps = {
  label: string;
  children: (describedBy: string) => ReactNode;
  side?: "top" | "right" | "bottom";
  className?: string;
};

const placement = {
  top: "bottom-full left-1/2 mb-2 -translate-x-1/2",
  bottom: "top-full left-1/2 mt-2 -translate-x-1/2",
  right: "left-full top-1/2 ml-3 -translate-y-1/2",
};

/**
 * Lightweight CSS tooltip shown on hover and keyboard focus.
 * The render prop receives the id to wire into `aria-describedby`.
 */
export function Tooltip({ label, children, side = "top", className }: TooltipProps) {
  const id = useId();
  return (
    <span className={cn("group/tooltip relative inline-flex", className)}>
      {children(id)}
      <span
        id={id}
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 w-max max-w-56 rounded-md border border-line-strong bg-ink-800 px-2.5 py-1.5 text-xs leading-snug text-fg-muted shadow-xl",
          "opacity-0 transition-opacity duration-150 group-focus-within/tooltip:opacity-100 group-hover/tooltip:opacity-100",
          placement[side],
        )}
      >
        {label}
      </span>
    </span>
  );
}
