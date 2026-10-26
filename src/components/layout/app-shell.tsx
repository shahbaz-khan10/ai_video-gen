"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { usePreferences } from "@/components/providers/preferences-provider";
import { AppHeader } from "./app-header";
import { AppSidebar } from "./app-sidebar";

const EXPANDED = 248;
const COLLAPSED = 76;

export function AppShell({ children }: { children: ReactNode }) {
  const { preferences } = usePreferences();
  const [collapsed, setCollapsed] = useState(preferences.startSidebarCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Follow the Settings preference when it changes; manual toggles still win in between.
  const [syncedPreference, setSyncedPreference] = useState(preferences.startSidebarCollapsed);
  if (syncedPreference !== preferences.startSidebarCollapsed) {
    setSyncedPreference(preferences.startSidebarCollapsed);
    setCollapsed(preferences.startSidebarCollapsed);
  }
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
        href="#app-main"
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
        <AppSidebar collapsed={collapsed} />
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
        <AppHeader ref={menuButtonRef} menuOpen={mobileOpen} onOpenMenu={() => setMobileOpen(true)} />
        <main id="app-main" className="flex-1">
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
              id="app-drawer"
              role="dialog"
              aria-modal="true"
              aria-label="Studio navigation"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 420, damping: 42 }}
              className="absolute inset-y-0 left-0 w-[min(84vw,300px)] border-r border-line bg-ink-900"
            >
              <AppSidebar onNavigate={() => setMobileOpen(false)} />
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
