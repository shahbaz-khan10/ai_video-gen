import type { LucideIcon } from "lucide-react";
import { Compass, FolderOpen, LayoutDashboard, Settings, WandSparkles } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon };

export const PRIMARY_NAV: NavItem[] = [
  { href: "/studio", label: "Overview", icon: LayoutDashboard },
  { href: "/studio/create", label: "Create", icon: WandSparkles },
  { href: "/studio/projects", label: "My Projects", icon: FolderOpen },
  { href: "/studio/explore", label: "Explore", icon: Compass },
];

export const SECONDARY_NAV: NavItem[] = [{ href: "/studio/settings", label: "Settings", icon: Settings }];

export function isActive(pathname: string, href: string) {
  return href === "/studio" ? pathname === href : pathname.startsWith(href);
}
