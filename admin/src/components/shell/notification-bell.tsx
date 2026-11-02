"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api, type Page } from "@/lib/api/client";
import { timeAgo } from "@/lib/format";
import type { AppNotification } from "@/lib/types";

export function NotificationBell() {
  const router = useRouter();
  const client = useQueryClient();
  const { data } = useQuery({
    queryKey: ["notifications", "bell"],
    queryFn: () => api<Page<AppNotification>>("notifications", { query: { page_size: 15 } }),
    refetchInterval: 60_000,
  });
  const items = data?.results ?? [];
  const unread = items.filter((n) => !n.read_at).length;

  const markAll = useMutation({
    mutationFn: () => api("notifications/read-all", { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const open = async (n: AppNotification) => {
    if (!n.read_at) {
      await api(`notifications/${n.id}/read`, { method: "POST" }).catch(() => null);
      client.invalidateQueries({ queryKey: ["notifications"] });
    }
    if (n.application) router.push(`/applications/${n.application}`);
  };

  return (
    <Popover>
      <PopoverTrigger render={<Button variant="ghost" size="icon" className="relative" aria-label="Notifications" />}>
        <Bell className="size-4" />
        {unread ? (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        ) : null}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <p className="text-sm font-semibold">Notifications</p>
          {unread ? (
            <Button variant="ghost" size="xs" onClick={() => markAll.mutate()}>
              <CheckCheck className="size-3.5" /> Mark all read
            </Button>
          ) : null}
        </div>
        <ScrollArea orientation="vertical" className="max-h-96">
          {items.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              Nothing yet. Forms that need you show up here.
            </p>
          ) : (
            <ul className="divide-y">
              {items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => open(n)}
                    className="flex w-full gap-3 px-4 py-3 text-left hover:bg-muted/60"
                  >
                    <span
                      className={`mt-1.5 size-2 shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-brand-accent"}`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{n.title}</span>
                      <span className="line-clamp-2 text-xs text-muted-foreground">{n.body}</span>
                      <span className="mt-1 block text-[11px] text-muted-foreground">{timeAgo(n.created_at)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>
        <div className="border-t px-4 py-2 text-center">
          <Link href="/notifications" className="text-xs font-medium text-primary underline-offset-4 hover:underline">
            See all
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
