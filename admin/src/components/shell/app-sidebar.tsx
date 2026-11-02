"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ChevronsUpDown } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createElement, useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { BrandMark } from "@/components/shell/brand-mark";
import { useBranding, useMe, useSession } from "@/hooks/use-session";
import { apiImage } from "@/lib/api";
import { api } from "@/lib/api/client";
import { initials } from "@/lib/format";
import { entryFor, iconFor, LIST_STATUS, QUEUE_STATUS } from "@/lib/nav";
import type { NavItem } from "@/lib/types";
import { cn } from "@/lib/utils";

import { AccountMenuItems } from "./account-menu";

/**
 * The menu the backend sent for this person's roles.
 *
 * The keyboard works the whole tree: Alt+S comes here, Up and Down walk every
 * visible row, Enter opens a page or folds a group, Right opens a group and Left
 * closes it or goes back to its heading, a letter jumps to the next row starting
 * with it, and Esc returns to the page. Focus stays on the row after Enter, so
 * someone can keep walking. Folded to icons, Enter or Right opens the group's
 * pages beside it and the same keys work in there.
 */
export function AppSidebar() {
  const pathname = usePathname();
  const { navigation } = useSession();
  const branding = useBranding();
  const me = useMe();
  const { state, isMobile, setOpenMobile } = useSidebar();
  const collapsed = state === "collapsed" && !isMobile;
  const entry = entryFor(navigation, pathname);
  const activeKey = entry?.item.key;
  const counts = useCounts();
  const [folded, setFolded] = useFolded(navigation);

  const here = entry?.group?.key;
  useEffect(() => {
    // Landing on a page opens its group, which can still be folded again by hand.
    if (here) setFolded(here, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [here]);

  const tree = useRef<HTMLDivElement>(null);
  const roving = useRef<HTMLElement | null>(null);

  const rows = () =>
    [...(tree.current?.querySelectorAll<HTMLElement>("[data-nav]") ?? [])].filter((el) => el.offsetParent !== null);

  // One tab stop for the whole tree: the last row used, or this page's row.
  useEffect(() => {
    const list = rows();
    const stop =
      (roving.current && list.includes(roving.current) ? roving.current : null) ??
      list.find((el) => el.dataset.navKey === activeKey || el.dataset.navKey === here) ??
      list[0];
    list.forEach((el) => (el.tabIndex = el === stop ? 0 : -1));
  });

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (!e.altKey || e.key.toLowerCase() !== "s") return;
      e.preventDefault();
      if (isMobile) setOpenMobile(true);
      const target = tree.current?.querySelector<HTMLElement>('[data-nav][tabindex="0"]') ?? rows()[0];
      target?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isMobile, setOpenMobile]);

  const move = (el: HTMLElement | undefined) => {
    if (!el) return;
    el.focus();
    el.scrollIntoView({ block: "nearest" });
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const list = rows();
    const row = document.activeElement as HTMLElement;
    const at = list.indexOf(row);
    if (at < 0) return;
    const groupKey = row.dataset.navGroup;
    const stop = () => {
      e.preventDefault();
      e.stopPropagation();
    };

    if (e.key === "ArrowDown") {
      stop();
      move(list[(at + 1) % list.length]);
    } else if (e.key === "ArrowUp") {
      stop();
      move(list[(at - 1 + list.length) % list.length]);
    } else if (e.key === "Home") {
      stop();
      move(list[0]);
    } else if (e.key === "End") {
      stop();
      move(list[list.length - 1]);
    } else if (e.key === "ArrowRight" && groupKey) {
      stop();
      if (row.getAttribute("aria-expanded") === "true") {
        if (!collapsed) move(list[at + 1]);
      } else {
        row.click();
      }
    } else if (e.key === "ArrowLeft") {
      if (groupKey && row.getAttribute("aria-expanded") === "true") {
        stop();
        row.click();
      } else if (row.dataset.navParent) {
        stop();
        move(list.find((el) => el.dataset.navGroup === row.dataset.navParent));
      }
    } else if (e.key === "Escape") {
      stop();
      document.getElementById("content")?.focus();
    } else if (e.key.length === 1 && /\S/.test(e.key)) {
      const letter = e.key.toLowerCase();
      const after = [...list.slice(at + 1), ...list.slice(0, at)];
      const match = after.find((el) => el.textContent?.trim().toLowerCase().startsWith(letter));
      if (match) {
        stop();
        move(match);
      }
    }
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="border-b">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link href="/" />} className="rounded-none">
              <BrandMark branding={branding} className="size-8" />
              <div className="grid flex-1 text-left leading-tight">
                <span className="truncate font-semibold">{branding.display_name || me.organization.name}</span>
                <span className="truncate text-xs text-muted-foreground">Member Onboarding</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <div
          ref={tree}
          role="tree"
          aria-label="Main menu"
          onKeyDown={onKeyDown}
          onFocusCapture={(e) => {
            const row = (e.target as HTMLElement).closest<HTMLElement>("[data-nav]");
            if (row) roving.current = row;
          }}
        >
          {collapsed ? (
            <SidebarGroup>
              <SidebarMenu className="gap-1">
                {navigation.map((item) =>
                  item.children.length ? (
                    <GroupFlyout key={item.key} group={item} activeKey={activeKey} counts={counts} />
                  ) : (
                    <SidebarMenuItem key={item.key}>
                      <SidebarMenuButton
                        data-nav
                        data-nav-key={item.key}
                        tooltip={item.label}
                        isActive={activeKey === item.key}
                        render={<Link href={item.path ?? "/"} />}
                        className={ROW}
                      >
                        <NavIcon name={item.icon} />
                        <span>{item.label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ),
                )}
              </SidebarMenu>
            </SidebarGroup>
          ) : (
            navigation.map((item) =>
              item.children.length ? (
                <Group
                  key={item.key}
                  group={item}
                  open={!folded.includes(item.key)}
                  onOpenChange={(open) => setFolded(item.key, !open)}
                  activeKey={activeKey}
                  counts={counts}
                  onNavigate={() => setOpenMobile(false)}
                />
              ) : (
                <SidebarGroup key={item.key} className="py-0.5">
                  <SidebarMenu>
                    <Row item={item} active={activeKey === item.key} count={0} onNavigate={() => setOpenMobile(false)} />
                  </SidebarMenu>
                </SidebarGroup>
              ),
            )
          )}
        </div>
      </SidebarContent>

      <SidebarFooter className="border-t">
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger render={<SidebarMenuButton size="lg" className="rounded-none" aria-label="Account" />}>
                <Avatar className="size-8">
                  {me.photo_url ? <AvatarImage src={apiImage(me.photo_url)} alt="" /> : null}
                  <AvatarFallback className="bg-primary/12 text-[11px] font-semibold text-primary">
                    {initials(me.full_name || me.email)}
                  </AvatarFallback>
                </Avatar>
                <span className="grid min-w-0 flex-1 text-left leading-tight">
                  <span className="truncate text-sm font-medium">{me.full_name || me.email}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {(me.role_names ?? me.roles).join(", ") || "No role yet"}
                  </span>
                </span>
                <ChevronsUpDown className="text-muted-foreground" />
              </DropdownMenuTrigger>
              <DropdownMenuContent side={collapsed ? "right" : "top"} align="start" className="w-60">
                <AccountMenuItems />
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

const ROW = cn(
  "relative rounded-none text-sidebar-foreground/85",
  "before:absolute before:inset-y-1 before:left-0 before:w-0.5 before:bg-primary before:opacity-0 before:transition-opacity",
  "data-active:bg-primary/8 data-active:font-medium data-active:text-sidebar-foreground data-active:before:opacity-100 dark:data-active:bg-primary/14",
  "[&>svg]:text-muted-foreground hover:[&>svg]:text-sidebar-foreground data-active:[&>svg]:text-primary",
  "focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sidebar-ring",
);

function NavIcon({ name, className }: { name: string; className?: string }) {
  return createElement(iconFor(name), { className });
}

function Row({
  item,
  active,
  count,
  parent,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  count: number;
  parent?: string;
  onNavigate: () => void;
}) {
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        data-nav
        data-nav-key={item.key}
        data-nav-parent={parent}
        isActive={active}
        render={<Link href={item.path ?? "/"} onClick={onNavigate} />}
        className={ROW}
      >
        <NavIcon name={item.icon} />
        <span>{item.label}</span>
      </SidebarMenuButton>
      {count ? (
        <SidebarMenuBadge className="bg-transparent p-0">
          <Count n={count} />
        </SidebarMenuBadge>
      ) : null}
    </SidebarMenuItem>
  );
}

function Group({
  group,
  open,
  onOpenChange,
  activeKey,
  counts,
  onNavigate,
}: {
  group: NavItem;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activeKey: string | undefined;
  counts: Record<string, number>;
  onNavigate: () => void;
}) {
  const waiting = group.children.reduce((n, child) => n + (child.key in QUEUE_STATUS ? (counts[child.key] ?? 0) : 0), 0);
  return (
    <Collapsible open={open} onOpenChange={onOpenChange} render={<SidebarGroup className="py-1" />}>
      <SidebarGroupLabel
        render={<CollapsibleTrigger data-nav data-nav-key={group.key} data-nav-group={group.key} />}
        className="h-7 w-full cursor-pointer rounded-none text-[11px] font-semibold tracking-[0.08em] text-sidebar-foreground/55 uppercase transition-colors hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sidebar-ring"
      >
        <span className="flex-1 truncate text-left">{group.label}</span>
        {!open && waiting ? <Count n={waiting} /> : null}
        <ChevronRight className={cn("ml-1 size-3.5! transition-transform duration-150", open && "rotate-90")} />
      </SidebarGroupLabel>
      <CollapsibleContent className="h-(--collapsible-panel-height) overflow-hidden transition-[height] duration-150 ease-out data-ending-style:h-0 data-starting-style:h-0">
        <SidebarGroupContent>
          <SidebarMenu className="gap-px">
            {group.children.map((child) => (
              <Row
                key={child.key}
                item={child}
                parent={group.key}
                active={activeKey === child.key}
                count={counts[child.key] ?? 0}
                onNavigate={onNavigate}
              />
            ))}
          </SidebarMenu>
        </SidebarGroupContent>
      </CollapsibleContent>
    </Collapsible>
  );
}

/** One group when folded to icons: its icon, and its pages beside it. */
function GroupFlyout({
  group,
  activeKey,
  counts,
}: {
  group: NavItem;
  activeKey: string | undefined;
  counts: Record<string, number>;
}) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const waiting = group.children.reduce((n, child) => n + (child.key in QUEUE_STATUS ? (counts[child.key] ?? 0) : 0), 0);
  const isActive = group.children.some((child) => child.key === activeKey);

  useEffect(() => {
    if (!open || !trigger.current?.matches(":focus")) return;
    const frame = requestAnimationFrame(() => panel.current?.querySelector("a")?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const onPanelKey = (e: KeyboardEvent<HTMLElement>) => {
    const links = [...(panel.current?.querySelectorAll("a") ?? [])];
    const at = links.indexOf(document.activeElement as HTMLAnchorElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      links[(at + step + links.length) % links.length]?.focus();
    } else if (e.key === "ArrowLeft" || e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
      trigger.current?.focus();
    }
  };

  return (
    <SidebarMenuItem>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          openOnHover
          delay={60}
          closeDelay={180}
          render={
            <SidebarMenuButton
              ref={trigger}
              data-nav
              data-nav-key={group.key}
              data-nav-group={group.key}
              isActive={isActive}
              aria-label={group.label}
              aria-expanded={open}
              className={cn(ROW, open && "bg-sidebar-accent text-sidebar-accent-foreground")}
            />
          }
        >
          <NavIcon name={group.icon} />
          <span>{group.label}</span>
          {waiting ? <span className="absolute top-1 right-1 size-2 rounded-full bg-brand-accent ring-2 ring-sidebar" /> : null}
        </PopoverTrigger>
        <PopoverContent side="right" align="start" sideOffset={10} className="w-64 gap-0 p-1.5">
          <p className="flex items-center gap-2 px-2 pt-1 pb-2 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
            <NavIcon name={group.icon} className="size-3.5" /> {group.label}
          </p>
          <nav ref={panel} onKeyDown={onPanelKey} className="flex flex-col gap-px">
            {group.children.map((child) => {
              const count = counts[child.key] ?? 0;
              const here = child.key === activeKey;
              return (
                <Link
                  key={child.key}
                  href={child.path ?? "/"}
                  onClick={() => setOpen(false)}
                  className={cn(
                    "group/item relative flex items-center gap-2.5 px-2 py-1.5 text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                    "before:absolute before:inset-y-1 before:left-0 before:w-0.5 before:bg-primary before:opacity-0",
                    here
                      ? "bg-primary/8 font-medium text-foreground before:opacity-100"
                      : "text-foreground/80 hover:bg-muted hover:text-foreground",
                  )}
                >
                  <NavIcon
                    name={child.icon}
                    className={cn(
                      "size-4 shrink-0",
                      here ? "text-primary" : "text-muted-foreground group-hover/item:text-foreground",
                    )}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{child.label}</span>
                    {child.description ? (
                      <span className="block truncate text-[11px] font-normal text-muted-foreground">
                        {child.description}
                      </span>
                    ) : null}
                  </span>
                  {count ? <Count n={count} className="shrink-0" /> : null}
                </Link>
              );
            })}
          </nav>
        </PopoverContent>
      </Popover>
    </SidebarMenuItem>
  );
}

function Count({ n, className }: { n: number; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-4.5 min-w-4.5 items-center justify-center bg-amber-500/15 px-1 text-[10.5px] font-semibold tracking-normal text-amber-700 tabular-nums dark:text-amber-300",
        className,
      )}
    >
      {n > 99 ? "99+" : n}
    </span>
  );
}

/** Forms waiting in each queue, for the badges. */
function useCounts(): Record<string, number> {
  const { navigation } = useSession();
  const wantsCounts = navigation.some((item) =>
    item.children.some((child) => child.key in QUEUE_STATUS || child.key in LIST_STATUS),
  );
  const { data } = useQuery({
    queryKey: ["queue", "dashboard"],
    queryFn: () => api<{ by_status: Record<string, number> }>("applications/counts"),
    enabled: wantsCounts,
    refetchInterval: 60_000,
  });
  return Object.fromEntries([
    ...Object.entries(QUEUE_STATUS).map(([key, status]) => [key, data?.by_status[status] ?? 0]),
    ...Object.entries(LIST_STATUS).map(([key, statuses]) => [
      key,
      statuses.reduce((total, status) => total + (data?.by_status[status] ?? 0), 0),
    ]),
  ]);
}

const FOLDED_KEY = "mo-sidebar:folded";

/**
 * Groups this person folded, remembered in this browser. Until they fold or open
 * one themselves, every group after the first starts folded, so the menu starts short.
 */
function useFolded(navigation: NavItem[]): [string[], (key: string, fold: boolean) => void] {
  const [saved, setSaved] = useState<string[] | null>(null);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(FOLDED_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- read once, after hydration
      if (raw) setSaved(JSON.parse(raw) as string[]);
    } catch {
      // not remembered
    }
  }, []);
  const groups = navigation.filter((item) => item.children.length);
  const folded = saved ?? groups.slice(1).map((group) => group.key);
  const set = (key: string, fold: boolean) => {
    const next = fold ? [...new Set([...folded, key])] : folded.filter((k) => k !== key);
    setSaved(next);
    try {
      localStorage.setItem(FOLDED_KEY, JSON.stringify(next));
    } catch {
      // not remembered
    }
  };
  return [folded, set];
}
