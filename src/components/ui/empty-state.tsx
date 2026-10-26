import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type EmptyStateProps = {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
  className?: string;
};

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-center overflow-hidden rounded-xl border border-dashed border-line-strong px-6 py-14 text-center",
        className,
      )}
    >
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 h-32 bg-[radial-gradient(60%_100%_at_50%_0%,rgb(139_92_246/0.10),transparent)]"
      />
      <div className="relative mb-4 grid size-11 place-items-center rounded-xl border border-line-strong bg-ink-850 text-violet-soft">
        <Icon className="size-5" aria-hidden />
      </div>
      <h3 className="relative text-[15px] font-medium text-fg">{title}</h3>
      <p className="relative mt-1.5 max-w-sm text-sm leading-relaxed text-fg-muted">{description}</p>
      {action && <div className="relative mt-5">{action}</div>}
    </div>
  );
}
