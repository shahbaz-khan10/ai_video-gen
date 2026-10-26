import Link, { type LinkProps } from "next/link";
import type { ButtonHTMLAttributes, AnchorHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md" | "lg";

const base =
  "group/button relative inline-flex shrink-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium " +
  "transition-[background-color,border-color,color,box-shadow,transform] duration-200 ease-out active:scale-[0.98] " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 " +
  "disabled:pointer-events-none disabled:opacity-45";

const variants: Record<Variant, string> = {
  primary:
    "bg-linear-to-b from-[#8f6bff] to-indigo text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_8px_24px_-10px_rgb(124_92_255/0.7)] " +
    "hover:shadow-[inset_0_1px_0_rgb(255_255_255/0.28),0_12px_32px_-10px_rgb(124_92_255/0.85)] hover:brightness-110",
  secondary:
    "border border-line-strong bg-white/[0.03] text-fg hover:border-white/20 hover:bg-white/[0.06]",
  ghost: "text-fg-muted hover:bg-white/[0.05] hover:text-fg",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-[15px]",
};

export function buttonStyles({
  variant = "primary",
  size = "md",
  className,
}: { variant?: Variant; size?: Size; className?: string } = {}) {
  return cn(base, variants[variant], sizes[size], className);
}

type StyleProps = { variant?: Variant; size?: Size };

export function Button({
  variant,
  size,
  className,
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & StyleProps) {
  return <button type={type} className={buttonStyles({ variant, size, className })} {...props} />;
}

export function ButtonLink({
  variant,
  size,
  className,
  children,
  ...props
}: LinkProps &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, keyof LinkProps> &
  StyleProps & { children: ReactNode }) {
  return (
    <Link className={buttonStyles({ variant, size, className })} {...props}>
      {children}
    </Link>
  );
}
