import type { LucideIcon } from "lucide-react";
import { Compass, FolderOpen, LayoutDashboard, Settings, WandSparkles } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon };

export const PRIMARY_NAV: NavItem[] = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/create", label: "Create", icon: WandSparkles },
  { href: "/projects", label: "My Projects", icon: FolderOpen },
  { href: "/explore", label: "Explore", icon: Compass },
];

export const SECONDARY_NAV: NavItem[] = [{ href: "/settings", label: "Settings", icon: Settings }];

export function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}
