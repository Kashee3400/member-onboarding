import {
  BadgeCheck,
  BarChart3,
  Bell,
  Circle,
  CircleX,
  Clock,
  Database,
  FileDown,
  FileText,
  Files,
  Hash,
  History,
  IdCard,
  Landmark,
  LayoutDashboard,
  ListChecks,
  Network,
  Palette,
  Plug,
  Route,
  Scale,
  Settings,
  Shield,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";

import type { NavItem } from "@/lib/types";

// The backend names icons, so a new menu entry needs no frontend logic.
const ICONS: Record<string, LucideIcon> = {
  "layout-dashboard": LayoutDashboard,
  "file-text": FileText,
  files: Files,
  "user-check": UserCheck,
  scale: Scale,
  landmark: Landmark,
  "list-checks": ListChecks,
  users: Users,
  "bar-chart": BarChart3,
  bell: Bell,
  database: Database,
  network: Network,
  palette: Palette,
  route: Route,
  settings: Settings,
  "id-card": IdCard,
  shield: Shield,
  plug: Plug,
  history: History,
  hash: Hash,
  clock: Clock,
  "badge-check": BadgeCheck,
  "circle-x": CircleX,
  "file-down": FileDown,
};

export const iconFor = (name: string): LucideIcon => ICONS[name] ?? Circle;

/** Which application status each queue in the menu counts. */
export const QUEUE_STATUS: Record<string, string> = {
  "applications.am": "pending_am",
  "applications.cs": "pending_cs",
  "applications.finance": "pending_finance",
};

/**
 * Lists that show a count beside them too. Not added into the group's total, since
 * the same forms are already counted in the queues above.
 */
export const LIST_STATUS: Record<string, string[]> = {
  "applications.pending": ["pending_am", "pending_cs", "pending_finance"],
  "applications.rejected": ["rejected"],
};

export function isActive(path: string | null, pathname: string): boolean {
  if (!path) return false;
  return path === "/" ? pathname === "/" : pathname === path || pathname.startsWith(`${path}/`);
}

/** Every page in the menu, each with the group it sits in. */
export function flatten(navigation: NavItem[]) {
  return navigation.flatMap<{ item: NavItem; group: NavItem | null }>((item) =>
    item.children.length
      ? item.children.map((child) => ({ item: child, group: item }))
      : [{ item, group: null }],
  );
}

/** The menu entry for this page. The longest match wins, so a detail page finds its parent. */
export function entryFor(navigation: NavItem[], pathname: string) {
  return flatten(navigation)
    .filter(({ item }) => isActive(item.path, pathname))
    .sort((a, b) => (b.item.path?.length ?? 0) - (a.item.path?.length ?? 0))[0];
}
