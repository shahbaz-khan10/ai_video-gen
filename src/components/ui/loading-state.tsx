import { cn } from "@/lib/cn";

type LoadingStateProps = {
  label?: string;
  className?: string;
};

/** Neutral loading placeholder. Announces itself to assistive tech once. */
export function LoadingState({ label = "Loading", className }: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("flex min-h-[320px] flex-col items-center justify-center gap-4 text-center", className)}
    >
      <span className="relative grid size-10 place-items-center" aria-hidden>
        <span className="absolute inset-0 animate-ping rounded-full bg-violet/20 [animation-duration:1.6s]" />
        <span className="size-3 rounded-full bg-linear-to-br from-violet-soft to-azure" />
      </span>
      <p className="text-sm text-fg-muted">{label}…</p>
    </div>
  );
}

/** Shimmering block for skeleton layouts. */
export function SkeletonBlock({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-xl bg-ink-900", className)} />;
}
