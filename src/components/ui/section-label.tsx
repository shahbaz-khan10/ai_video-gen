import type { ReactNode } from "react";

/** Small uppercase eyebrow label used above section headings. */
export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-violet-soft">
      {children}
    </p>
  );
}
