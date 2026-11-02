"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { messageOf } from "@/components/admin/feedback";
import { ErrorState } from "@/components/common/states";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api/client";
import type { NotificationPreference } from "@/lib/types";

const URL = "notifications/preferences";

/** The 9 o'clock note to approvers. Each person can turn it off for themselves. */
export function MorningSummarySetting() {
  const client = useQueryClient();
  const preference = useQuery({
    queryKey: ["notification-preferences"],
    queryFn: () => api<NotificationPreference>(URL),
  });
  const save = useMutation({
    mutationFn: (morning_summary: boolean) =>
      api<NotificationPreference>(URL, { method: "PATCH", body: { morning_summary } }),
    onSuccess: (data) => {
      client.setQueryData(["notification-preferences"], data);
      toast.success(data.morning_summary ? "Morning summary turned on." : "Morning summary turned off.");
    },
    onError: (error) => toast.error(messageOf(error)),
  });

  return (
    <Card className="gap-4 p-5">
      <h2 className="font-semibold">Notifications</h2>
      {preference.error ? (
        <ErrorState error={preference.error} onRetry={() => preference.refetch()} />
      ) : !preference.data ? (
        <Skeleton className="h-10 w-full" />
      ) : (
        <label className="flex items-center justify-between gap-3 text-sm">
          <span>
            <span className="block font-medium">Morning summary</span>
            <span className="block text-xs text-muted-foreground">
              At 9 each morning, how many forms wait for you and how many are late. Sent only when something waits,
              and by email too when mail is set up.
            </span>
          </span>
          <Switch
            checked={preference.data.morning_summary}
            disabled={save.isPending}
            onCheckedChange={(on) => save.mutate(Boolean(on))}
          />
        </label>
      )}
    </Card>
  );
}
