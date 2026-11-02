"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound, Keyboard, LogOut, Monitor, Moon, Sun, UserRound } from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";

import {
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useMe } from "@/hooks/use-session";
import { auth, reloadTo } from "@/lib/api";

/** The account menu's items: the same in the top bar and the sidebar's profile card. */
export function AccountMenuItems() {
  const me = useMe();
  const { setTheme, theme } = useTheme();
  const client = useQueryClient();
  return (
    <>
      <DropdownMenuGroup>
        <DropdownMenuLabel>
          <span className="block truncate font-medium text-foreground">{me.full_name || me.email}</span>
          <span className="block truncate text-xs font-normal text-muted-foreground">{me.email}</span>
        </DropdownMenuLabel>
      </DropdownMenuGroup>
      <DropdownMenuSeparator />
      <DropdownMenuItem render={<Link href="/account" />}>
        <UserRound /> My account
      </DropdownMenuItem>
      <DropdownMenuItem render={<Link href="/change-password" />}>
        <KeyRound /> Change password
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuGroup>
        <DropdownMenuLabel className="text-xs">Theme</DropdownMenuLabel>
        {(
          [
            ["light", Sun, "Light"],
            ["dark", Moon, "Dark"],
            ["system", Monitor, "Same as this computer"],
          ] as const
        ).map(([value, Icon, label]) => (
          <DropdownMenuItem key={value} onClick={() => setTheme(value)}>
            <Icon /> {label}
            {theme === value ? <Check className="ml-auto" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuGroup>
      <DropdownMenuSeparator />
      <DropdownMenuItem onClick={() => window.dispatchEvent(new Event("mo:shortcuts"))}>
        <Keyboard /> Keyboard shortcuts
        <span className="ml-auto text-xs text-muted-foreground">?</span>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        variant="destructive"
        onClick={async () => {
          client.clear();
          await auth("logout").catch(() => null);
          // A full load, so no cached staff data survives the sign-out.
          reloadTo("/login");
        }}
      >
        <LogOut /> Sign out
      </DropdownMenuItem>
    </>
  );
}
