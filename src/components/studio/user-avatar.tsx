import { cn } from "@/lib/cn";

const SIZES = {
  sm: "size-8 text-[11px]",
  lg: "size-12 text-sm",
};

/** Placeholder avatar using initials until real accounts exist. */
export function UserAvatar({ initials, size = "sm" }: { initials: string; size?: keyof typeof SIZES }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid shrink-0 place-items-center rounded-full bg-linear-to-br from-violet-soft/80 via-indigo to-azure font-semibold text-white ring-2 ring-ink-950",
        SIZES[size],
      )}
    >
      {initials}
    </span>
  );
}
