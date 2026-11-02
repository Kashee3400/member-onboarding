"use client";

import { ChevronRight, Moon, Sun } from "lucide-react";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useMe, useSession } from "@/hooks/use-session";
import { apiImage } from "@/lib/api";
import { initials } from "@/lib/format";
import { entryFor } from "@/lib/nav";

import { AccountMenuItems } from "./account-menu";
import { CommandSearch } from "./command-search";
import { NotificationBell } from "./notification-bell";

export function Topbar() {
  const pathname = usePathname();
  const { navigation } = useSession();
  const me = useMe();
  const entry = entryFor(navigation, pathname);
  const { setTheme, resolvedTheme } = useTheme();

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <SidebarTrigger />
      <Separator orientation="vertical" className="mx-1 h-5" />
      <p className="flex min-w-0 items-center gap-1 truncate text-sm">
        {entry?.group ? (
          <>
            <span className="hidden text-muted-foreground sm:inline">{entry.group.label}</span>
            <ChevronRight className="hidden size-3.5 text-muted-foreground sm:inline" />
          </>
        ) : null}
        <span className="truncate font-medium">{entry?.item.label ?? (pathname === "/account" ? "My account" : "Member Onboarding")}</span>
      </p>
      <div className="ml-auto flex items-center gap-1">
        <CommandSearch />
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Switch between light and dark"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
          <Sun className="hidden dark:block" />
          <Moon className="dark:hidden" />
        </Button>
        <NotificationBell />
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" className="h-9 gap-2 px-2" aria-label="Account" />}>
            <Avatar className="size-7">
              {me.photo_url ? <AvatarImage src={apiImage(me.photo_url)} alt="" /> : null}
              <AvatarFallback className="text-[11px]">{initials(me.full_name || me.email)}</AvatarFallback>
            </Avatar>
            <span className="hidden max-w-40 truncate text-sm sm:inline">{me.full_name || me.email}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <AccountMenuItems />
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
