import type { ReactNode } from "react";

export function SectionHeading({ title, aside }: { title: string; aside?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-4">
      <h2 className="text-[15px] font-medium text-fg">{title}</h2>
      {aside}
    </div>
  );
}

/** Marks content that is placeholder data rather than real user work. */
export function SampleBadge({ children = "Sample data" }: { children?: ReactNode }) {
  return (
    <span className="rounded-full border border-line-strong px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
      {children}
    </span>
  );
}
