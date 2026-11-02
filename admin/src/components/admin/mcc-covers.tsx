"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { CalendarClock } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Confirm } from "@/components/admin/confirm";
import { messageOf } from "@/components/admin/feedback";
import { FormDialog } from "@/components/admin/form-dialog";
import { DateRangePicker } from "@/components/common/date-picker";
import { Field } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { ErrorState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useCan } from "@/hooks/use-session";
import { api, type Page } from "@/lib/api/client";
import { isoDay } from "@/lib/format";
import type { MccCover, Role, Staff } from "@/lib/types";

const APPROVALS = ["applications.approve_am", "applications.approve_cs", "applications.approve_finance"];
const URL = "hierarchy/mcc-covers";

function days(cover: MccCover) {
  const a = parseISO(cover.starts_on);
  const b = parseISO(cover.ends_on);
  if (cover.starts_on === cover.ends_on) return format(a, "d MMM yyyy");
  return `${format(a, a.getFullYear() === b.getFullYear() ? "d MMM" : "d MMM yyyy")} – ${format(b, "d MMM yyyy")}`;
}

const BADGE: Record<MccCover["state"], { status: string; label: string }> = {
  active: { status: "active", label: "Covering now" },
  upcoming: { status: "pending", label: "Upcoming" },
  over: { status: "draft", label: "Over" },
  ended: { status: "draft", label: "Ended early" },
};

function useApprovers(enabled: boolean) {
  const staff = useQuery({
    queryKey: ["staff", "approvers"],
    queryFn: () => api<Page<Staff>>("staff", { query: { page_size: 500, is_active: true } }),
    enabled,
  });
  const roles = useQuery({
    queryKey: ["roles", "all"],
    queryFn: () => api<Page<Role>>("roles", { query: { page_size: 500 } }),
    enabled,
  });
  const approving = new Set(
    (roles.data?.results ?? [])
      .filter((role) => role.permissions.some((code) => APPROVALS.includes(code)))
      .map((role) => role.code),
  );
  return (staff.data?.results ?? []).filter((person) => person.roles.some((role) => approving.has(role.code)));
}

function HandOver({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const approvers = useApprovers(true);
  const [absent, setAbsent] = useState("");
  const [colleague, setColleague] = useState("");
  const [range, setRange] = useState({ from: isoDay(), to: "" });
  const [reason, setReason] = useState("");

  const give = useMutation({
    mutationFn: () =>
      api<MccCover>(URL, {
        method: "POST",
        body: { absent, colleague, starts_on: range.from, ends_on: range.to || range.from, reason },
      }),
    onSuccess: (cover) => {
      client.invalidateQueries({ queryKey: ["mcc-covers"] });
      client.invalidateQueries({ queryKey: ["queue"] });
      toast.success(`${cover.colleague_name} covers ${cover.absent_name} from ${days(cover)}.`);
      onClose();
    },
  });

  const label = (person: Staff) =>
    `${person.full_name || person.email} · ${person.roles.map((role) => role.name).join(", ")}`;
  const ready = absent && colleague && range.from && reason.trim();

  return (
    <FormDialog
      title="Hand over for leave"
      description="The colleague works the MCCs of the person away, in their own role, on these days only. The person away keeps theirs."
      onClose={onClose}
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        give.mutate();
      }}
      error={give.error}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!ready || give.isPending}>
            {give.isPending ? "Handing over…" : "Hand over"}
          </Button>
        </>
      }
    >
      <Field label="Person away" help="Whatever MCCs they hold during these days go to the colleague.">
        <Listbox
          aria-label="Person away"
          placeholder="Choose a person"
          value={absent}
          onChange={(value) => {
            setAbsent(value);
            if (value === colleague) setColleague("");
          }}
          items={approvers.map((person) => ({ value: person.id, label: label(person) }))}
        />
      </Field>
      <Field label="Colleague who covers" help="Must approve the same stages as the person away.">
        <Listbox
          aria-label="Colleague who covers"
          placeholder="Choose a colleague"
          value={colleague}
          onChange={setColleague}
          items={approvers
            .filter((person) => person.id !== absent)
            .map((person) => ({ value: person.id, label: label(person) }))}
        />
      </Field>
      <Field label="Days" help="Both days count. The cover stops by itself after the last day.">
        <DateRangePicker
          aria-label="Days"
          from={range.from}
          to={range.to}
          min={isoDay()}
          showPresets={false}
          clearable={false}
          placeholder="Pick the first and last day"
          onChange={setRange}
        />
      </Field>
      <Field label="Reason" help="Kept in the history and shown to the colleague.">
        <Textarea
          aria-label="Reason"
          value={reason}
          maxLength={300}
          placeholder="Annual leave"
          onChange={(event) => setReason(event.target.value)}
        />
      </Field>
    </FormDialog>
  );
}

function CoverRow({ cover, canAssign }: { cover: MccCover; canAssign: boolean }) {
  const client = useQueryClient();
  const end = useMutation({
    mutationFn: () => api(`${URL}/${cover.id}/end`, { method: "POST" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["mcc-covers"] });
      client.invalidateQueries({ queryKey: ["queue"] });
      toast.success(cover.state === "upcoming" ? "Cover called off." : "Cover ended.");
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const badge = BADGE[cover.state];
  const live = cover.state === "active" || cover.state === "upcoming";

  return (
    <li className="flex flex-wrap items-start justify-between gap-3 px-3 py-2.5 text-sm">
      <div className="min-w-0 space-y-0.5">
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-medium">
            {cover.colleague_name} covers {cover.absent_name}
          </span>
          <StatusBadge status={badge.status} label={badge.label} />
        </p>
        <p className="text-muted-foreground tabular-nums">
          {days(cover)}
          {live ? (cover.mccs.length ? ` · MCC ${cover.mccs.join(", ")}` : " · holds no MCCs now") : ""}
        </p>
        <p className="text-xs text-muted-foreground">
          {cover.reason} · given by {cover.given_by_name}
          {cover.ended_by_name ? ` · ended by ${cover.ended_by_name}` : ""}
        </p>
      </div>
      {live && canAssign ? (
        <Confirm
          title={cover.state === "upcoming" ? "Call off this cover?" : "End this cover now?"}
          description={`${cover.colleague_name} stops working ${cover.absent_name}'s MCCs at once. It stays in the history.`}
          action={cover.state === "upcoming" ? "Call off" : "End now"}
          onConfirm={() => end.mutate()}
          trigger={
            <Button type="button" variant="outline" size="sm" disabled={end.isPending}>
              {cover.state === "upcoming" ? "Call off" : "End now"}
            </Button>
          }
        />
      ) : null}
    </li>
  );
}

/** Cover for people on leave, above the MCC list: what runs now, what is coming, and the history. */
export function MccCovers() {
  const canAssign = useCan("mpp.assign");
  const [giving, setGiving] = useState(false);
  const [showPast, setShowPast] = useState(false);

  const current = useQuery({
    queryKey: ["mcc-covers", "current"],
    queryFn: () => api<Page<MccCover>>(URL, { query: { state: "current", page_size: 200, ordering: "starts_on" } }),
  });
  const past = useQuery({
    queryKey: ["mcc-covers", "past"],
    queryFn: () => api<Page<MccCover>>(URL, { query: { state: "past", page_size: 50, ordering: "-ends_on" } }),
    enabled: showPast,
  });
  const rows = current.data?.results ?? [];

  return (
    <Card className="gap-0 p-0">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <h2 className="font-medium">Leave cover</h2>
          <p className="text-sm text-muted-foreground">
            While someone is away, a colleague works their MCCs as well. It stops by itself after the last day.
          </p>
        </div>
        {canAssign ? (
          <Button type="button" onClick={() => setGiving(true)}>
            <CalendarClock /> Hand over for leave
          </Button>
        ) : null}
      </div>
      <div className="space-y-3 p-4">
        {current.error ? (
          <ErrorState error={current.error} onRetry={() => current.refetch()} />
        ) : !current.data ? (
          <Skeleton className="h-16 w-full" />
        ) : rows.length ? (
          <ul className="divide-y border">
            {rows.map((cover) => (
              <CoverRow key={cover.id} cover={cover} canAssign={canAssign} />
            ))}
          </ul>
        ) : (
          <p className="border border-dashed px-3 py-4 text-center text-sm text-muted-foreground">
            Nobody is covering for anyone now or soon.
          </p>
        )}

        <Button type="button" variant="ghost" size="sm" onClick={() => setShowPast((open) => !open)}>
          {showPast ? "Hide earlier covers" : "Show earlier covers"}
        </Button>
        {showPast ? (
          past.error ? (
            <ErrorState error={past.error} onRetry={() => past.refetch()} />
          ) : !past.data ? (
            <Skeleton className="h-16 w-full" />
          ) : past.data.results.length ? (
            <ul className="divide-y border">
              {past.data.results.map((cover) => (
                <CoverRow key={cover.id} cover={cover} canAssign={false} />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No earlier covers.</p>
          )
        ) : null}
      </div>
      {giving ? <HandOver onClose={() => setGiving(false)} /> : null}
    </Card>
  );
}
