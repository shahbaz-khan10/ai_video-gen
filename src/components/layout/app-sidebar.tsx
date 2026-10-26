"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useId, type ReactNode } from "react";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { Plus } from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { Tooltip } from "@/components/ui/tooltip";
import { MOCK_USER } from "@/lib/mock-data";
import { cn } from "@/lib/cn";
import { isActive, PRIMARY_NAV, SECONDARY_NAV, type NavItem } from "./nav-items";
import { UserAvatar } from "@/components/ui/user-avatar";

type AppSidebarProps = {
  collapsed?: boolean;
  onNavigate?: () => void;
};

function FadeLabel({ show, children }: { show: boolean; children: ReactNode }) {
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, transition: { delay: 0.08, duration: 0.2 } }}
          exit={{ opacity: 0, transition: { duration: 0.1 } }}
          className="truncate"
        >
          {children}
        </motion.span>
      )}
    </AnimatePresence>
  );
}

function NavLink({ item, collapsed, onNavigate }: { item: NavItem; collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = isActive(pathname, item.href);
  const Icon = item.icon;

  const link = (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? item.label : undefined}
      className={cn(
        "relative flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70",
        active ? "text-fg" : "text-fg-muted hover:bg-white/[0.04] hover:text-fg",
      )}
    >
      {active && (
        <motion.span
          layoutId="sidebar-active"
          aria-hidden
          className="absolute inset-0 rounded-lg border border-line-strong bg-white/[0.06]"
          transition={{ type: "spring", stiffness: 500, damping: 40 }}
        />
      )}
      <Icon className={cn("relative size-[18px] shrink-0", active && "text-violet-soft")} aria-hidden />
      <span className="relative flex min-w-0">
        <FadeLabel show={!collapsed}>{item.label}</FadeLabel>
      </span>
    </Link>
  );

  if (!collapsed) return link;
  return (
    <Tooltip label={item.label} side="right" className="w-full">
      {() => link}
    </Tooltip>
  );
}

/** Sidebar contents, shared by the desktop rail and the mobile drawer. */
export function AppSidebar({ collapsed = false, onNavigate }: AppSidebarProps) {
  // Desktop and drawer instances can co-exist; scope the active-pill animation to each.
  const groupId = useId();
  return (
    <LayoutGroup id={groupId}>
      <div className="flex h-full flex-col">
        <div className={cn("flex h-16 shrink-0 items-center", collapsed ? "justify-center" : "px-4")}>
          <Logo href="/" showText={!collapsed} />
        </div>

        <div className="px-3 pb-2">
          <Link
            href="/create"
            onClick={onNavigate}
            aria-label="Create new project"
            className={cn(
              "group flex h-10 items-center gap-2 rounded-lg border border-line-strong bg-white/[0.03] text-sm font-medium text-fg transition-colors hover:border-violet-soft/40 hover:bg-violet/10",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70",
              collapsed ? "justify-center" : "px-3",
            )}
          >
            <Plus className="size-4 shrink-0 text-violet-soft transition-transform group-hover:rotate-90" aria-hidden />
            <FadeLabel show={!collapsed}>New project</FadeLabel>
          </Link>
        </div>

        <nav aria-label="Studio" className="flex flex-1 flex-col gap-1 px-3 py-3">
          <p className={cn("mb-1 px-3 font-mono text-[10px] uppercase tracking-[0.16em] text-fg-subtle", collapsed && "sr-only")}>
            Workspace
          </p>
          {PRIMARY_NAV.map((item) => (
            <NavLink key={item.href} item={item} collapsed={collapsed} onNavigate={onNavigate} />
          ))}
          <div className="mt-auto pt-4">
            {SECONDARY_NAV.map((item) => (
              <NavLink key={item.href} item={item} collapsed={collapsed} onNavigate={onNavigate} />
            ))}
          </div>
        </nav>

        <div className="border-t border-line p-3">
          <Link
            href="/settings"
            onClick={onNavigate}
            aria-label={`${MOCK_USER.name}, open settings`}
            className={cn(
              "flex items-center gap-3 rounded-lg p-1.5 transition-colors hover:bg-white/[0.04]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-soft/70",
              collapsed && "justify-center",
            )}
          >
            <UserAvatar initials={MOCK_USER.initials} />
            {!collapsed && (
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-fg">{MOCK_USER.name}</span>
                <span className="block truncate text-xs text-fg-subtle">{MOCK_USER.plan}</span>
              </span>
            )}
          </Link>
        </div>
      </div>
    </LayoutGroup>
  );
}
