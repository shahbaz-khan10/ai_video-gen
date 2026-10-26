import type { ReactNode } from "react";

type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
};

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="mb-2 text-sm text-fg-subtle">{eyebrow}</p>}
        <h1 className="text-balance text-2xl font-semibold tracking-[-0.03em] text-fg sm:text-3xl">{title}</h1>
        {description && <p className="mt-2 max-w-xl text-pretty text-sm leading-relaxed text-fg-muted sm:text-[15px]">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Consistent page padding and width for studio pages. */
export function StudioPage({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-10 lg:py-10">{children}</div>;
}
