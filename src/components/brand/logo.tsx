import Link from "next/link";
import { cn } from "@/lib/cn";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "relative grid size-8 shrink-0 place-items-center overflow-hidden rounded-[9px] bg-linear-to-br from-violet via-indigo to-azure shadow-[inset_0_1px_0_rgb(255_255_255/0.3)]",
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className="size-4 text-white" fill="currentColor">
        <path d="M8 5.5v13a1 1 0 0 0 1.53.85l10.4-6.5a1 1 0 0 0 0-1.7L9.53 4.65A1 1 0 0 0 8 5.5Z" opacity="0.95" />
        <path d="M4 7.5v9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.55" />
      </svg>
    </span>
  );
}

export function Logo({ href = "/", showText = true }: { href?: string; showText?: boolean }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
      aria-label="AI Video Studio home"
    >
      <LogoMark />
      {showText && (
        <span className="text-[15px] font-semibold tracking-tight text-fg">
          AI Video <span className="text-fg-muted">Studio</span>
        </span>
      )}
    </Link>
  );
}
