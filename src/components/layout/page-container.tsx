import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

const WIDTHS = {
  default: "max-w-6xl",
  wide: "max-w-[1400px]",
};

/** Consistent page padding and max width for app pages. */
export function PageContainer({ children, width = "default" }: { children: ReactNode; width?: keyof typeof WIDTHS }) {
  return <div className={cn("mx-auto w-full px-4 py-8 sm:px-6 lg:px-10 lg:py-10", WIDTHS[width])}>{children}</div>;
}
