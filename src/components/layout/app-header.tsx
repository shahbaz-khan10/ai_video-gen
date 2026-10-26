"use client";

import Link from "next/link";
import type { Ref } from "react";
import { Menu } from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { UserAvatar } from "@/components/ui/user-avatar";
import { MOCK_USER } from "@/lib/mock-data";

type AppHeaderProps = {
  menuOpen: boolean;
  onOpenMenu: () => void;
  ref?: Ref<HTMLButtonElement>;
};

/** Top bar shown below the `lg` breakpoint, where the sidebar becomes a drawer. */
export function AppHeader({ menuOpen, onOpenMenu, ref }: AppHeaderProps) {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-ink-950/80 px-4 backdrop-blur-xl lg:hidden">
      <button
        ref={ref}
        type="button"
        onClick={onOpenMenu}
        aria-label="Open navigation"
        aria-expanded={menuOpen}
        aria-controls="app-drawer"
        className="grid size-10 place-items-center rounded-lg text-fg-muted hover:bg-white/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
      >
        <Menu className="size-5" aria-hidden />
      </button>
      <Logo href="/dashboard" />
      <Link
        href="/settings"
        aria-label={`${MOCK_USER.name}, open settings`}
        className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
      >
        <UserAvatar initials={MOCK_USER.initials} />
      </Link>
    </header>
  );
}
