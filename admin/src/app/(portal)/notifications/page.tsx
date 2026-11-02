"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { Suspense } from "react";

import { DataTable, type Column } from "@/components/common/data-table";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { dateTime, timeAgo } from "@/lib/format";
import type { AppNotification } from "@/lib/types";
import { cn } from "@/lib/utils";

const COLUMNS: Column<AppNotification>[] = [
  {
    id: "message",
    header: "Message",
    required: true,
    csv: (row) => `${row.title}: ${row.body}`,
    cell: (row) => (
      <span className="flex min-w-0 gap-3">
        <span
          aria-label={row.read_at ? undefined : "Unread"}
          className={cn("mt-1.5 size-2 shrink-0 rounded-full", row.read_at ? "bg-transparent" : "bg-brand-accent")}
        />
        <span className="min-w-0 whitespace-normal">
          <span className={cn("block text-sm", !row.read_at && "font-semibold")}>{row.title}</span>
          <span className="block text-sm text-muted-foreground">{row.body}</span>
        </span>
      </span>
    ),
  },
  {
    id: "when",
    header: "When",
    sortKey: "created_at",
    align: "right",
    hideBelow: "sm",
    className: "w-32",
    csv: (row) => dateTime(row.created_at),
    cell: (row) => (
      <span className="text-xs text-muted-foreground" title={dateTime(row.created_at)}>
        {timeAgo(row.created_at)}
      </span>
    ),
  },
];

const TABS = {
  filter: "read_at__isnull",
  options: [
    { value: "", label: "All" },
    { value: "true", label: "Unread" },
  ],
};

export default function NotificationsPage() {
  const router = useRouter();
  const client = useQueryClient();
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["queue"] });
    client.invalidateQueries({ queryKey: ["notifications"] });
  };
  const readAll = useMutation({
    mutationFn: () => api("notifications/read-all", { method: "POST" }),
    onSuccess: refresh,
  });

  const open = async (item: AppNotification) => {
    if (!item.read_at) {
      await api(`notifications/${item.id}/read`, { method: "POST" }).catch(() => null);
      refresh();
    }
    if (item.application) router.push(`/applications/${item.application}`);
  };

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Forms that need you, and what happened to the ones you sent on."
        actions={
          <Button variant="outline" disabled={readAll.isPending} onClick={() => readAll.mutate()}>
            <CheckCheck /> Mark all read
          </Button>
        }
      />
      <Suspense>
        <DataTable
          id="notifications"
          endpoint="notifications"
          columns={COLUMNS}
          rowKey={(row) => row.id}
          tabs={TABS}
          searchPlaceholder="Search notifications"
          exportName="notifications"
          onRowClick={open}
          empty={
            <EmptyState
              icon={Bell}
              title="Nothing here"
              description="You'll be told here when a form needs you or something changes on one of yours."
            />
          }
        />
      </Suspense>
    </>
  );
}
