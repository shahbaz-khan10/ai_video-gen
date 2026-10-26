"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Menu, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { MOCK_USER } from "@/lib/mock-data";
import { SidebarContent } from "./sidebar-content";
import { UserAvatar } from "./user-avatar";

const EXPANDED = 248;
const COLLAPSED = 76;

export function StudioShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!mobileOpen) return;
    const menuButton = menuButtonRef.current;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileOpen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
      menuButton?.focus();
    };
  }, [mobileOpen]);

  return (
    <div className="flex min-h-screen w-full">
      <a
        href="#studio-main"
        className="sr-only z-50 rounded-md bg-ink-800 px-3 py-2 text-sm focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <motion.aside
        initial={false}
        animate={{ width: collapsed ? COLLAPSED : EXPANDED }}
        transition={{ type: "spring", stiffness: 380, damping: 38 }}
        className="sticky top-0 hidden h-screen shrink-0 border-r border-line bg-ink-900/60 lg:block"
      >
        <SidebarContent collapsed={collapsed} />
        <button
          type="button"
          onClick={() => setCollapsed((v) => !v)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          className="absolute -right-3 top-[22px] grid size-6 place-items-center rounded-md border border-line-strong bg-ink-850 text-fg-subtle shadow-md transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
        >
          {collapsed ? <PanelLeftOpen className="size-3.5" aria-hidden /> : <PanelLeftClose className="size-3.5" aria-hidden />}
        </button>
      </motion.aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile / tablet top bar */}
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-ink-950/80 px-4 backdrop-blur-xl lg:hidden">
          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
            aria-expanded={mobileOpen}
            aria-controls="studio-drawer"
            className="grid size-10 place-items-center rounded-lg text-fg-muted hover:bg-white/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
          >
            <Menu className="size-5" aria-hidden />
          </button>
          <Logo href="/studio" />
          <UserAvatar initials={MOCK_USER.initials} />
        </header>

        <main id="studio-main" className="flex-1">
          {children}
        </main>
      </div>

      {/* Mobile drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setMobileOpen(false)}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
              aria-hidden
            />
            <motion.div
              id="studio-drawer"
              role="dialog"
              aria-modal="true"
              aria-label="Studio navigation"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 420, damping: 42 }}
              className="absolute inset-y-0 left-0 w-[min(84vw,300px)] border-r border-line bg-ink-900"
            >
              <SidebarContent onNavigate={() => setMobileOpen(false)} />
              <button
                type="button"
                autoFocus
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
                className="absolute right-3 top-3.5 grid size-9 place-items-center rounded-lg text-fg-muted hover:bg-white/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70"
              >
                <X className="size-5" aria-hidden />
              </button>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
