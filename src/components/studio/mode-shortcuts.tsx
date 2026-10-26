import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { MODES } from "@/lib/studio-options";

/** Quick-start tiles that open the Create workspace in a specific mode. */
export function ModeShortcuts() {
  return (
    <ul className="grid gap-3 sm:grid-cols-3">
      {MODES.map((mode) => {
        const Icon = mode.icon;
        return (
          <li key={mode.id}>
            <Link
              href={`/studio/create?mode=${mode.id}`}
              className="group relative flex h-full flex-col gap-4 overflow-hidden rounded-xl border border-line bg-ink-900 p-5 transition-[border-color,background-color,transform] duration-300 hover:-translate-y-0.5 hover:border-line-strong hover:bg-ink-850 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
            >
              <span
                aria-hidden
                className="absolute -right-10 -top-10 size-32 rounded-full bg-[radial-gradient(closest-side,rgb(139_92_246/0.18),transparent)] opacity-0 transition-opacity duration-500 group-hover:opacity-100"
              />
              <div className="flex items-center justify-between">
                <span className="grid size-9 place-items-center rounded-lg border border-line-strong bg-ink-800 text-violet-soft">
                  <Icon className="size-[18px]" aria-hidden />
                </span>
                <ArrowUpRight
                  className="size-4 text-fg-subtle transition-[color,transform] duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-fg"
                  aria-hidden
                />
              </div>
              <div>
                <p className="text-[15px] font-medium text-fg">{mode.label}</p>
                <p className="mt-1 text-sm leading-relaxed text-fg-muted">{mode.description}</p>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
