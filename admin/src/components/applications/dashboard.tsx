"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, ChevronRight, Inbox, PenLine, UserRoundX } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { BarChart } from "@/components/common/bar-chart";
import { ErrorState, EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { StatusTabs } from "@/components/common/status-tabs";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan, useMe, useSession } from "@/hooks/use-session";
import { api, type Page } from "@/lib/api/client";
import { rupees, timeAgo } from "@/lib/format";
import { flatten, QUEUE_STATUS } from "@/lib/nav";
import type { ApplicationSummary, Home } from "@/lib/types";
import { cn } from "@/lib/utils";

import { STATUS_OPTIONS, STATUS_ORDER } from "./constants";
import { Performance } from "./performance";

type Numbers = Home;

/** One request: the server sends only the blocks this person's roles are meant to see. */
function useNumbers() {
  return useQuery<Numbers>({ queryKey: ["queue", "home"], queryFn: () => api<Home>("home") });
}

export function Dashboard() {
  const me = useMe();
  const { navigation } = useSession();
  const canList = useCan("applications.view");
  const canSeeDashboard = useCan("dashboard.view");
  const canSeeReports = useCan("reports.view");
  const canSeePerformance = canSeeDashboard || canSeeReports;
  const numbers = useNumbers();
  const firstName = me.full_name.split(" ")[0];
  const roles = (me.role_names ?? me.roles).join(", ");

  return (
    <>
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Welcome back{firstName ? `, ${firstName}` : ""}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {[roles, me.organization.name].filter(Boolean).join(" · ")}
        </p>
      </div>

      {navigation.length === 0 ? (
        <EmptyState
          icon={UserRoundX}
          title="No role yet"
          description="Your account has no role, so there is nothing to show. Ask your administrator to assign one."
        />
      ) : numbers.error ? (
        <ErrorState error={numbers.error} onRetry={() => numbers.refetch()} />
      ) : numbers.isPending ? (
        <HomeSkeleton />
      ) : (
        <>
          {me.needs_signature && !me.has_signature ? <AddSignature /> : null}
          <NeedsYou numbers={numbers.data} />
          {numbers.data.setup ? <Setup setup={numbers.data.setup} /> : null}
          <Highlights numbers={numbers.data} />
          <StatusCards numbers={numbers.data} linked={canList} />
          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <Pipeline numbers={numbers.data} />
            {canList ? <RecentForms /> : numbers.data.by_mcc ? <ByMcc rows={numbers.data.by_mcc} /> : null}
          </div>
          {canSeePerformance ? <Performance /> : null}
          {numbers.data.trend || (canList && numbers.data.by_mcc) ? (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              {numbers.data.trend ? <Trend days={numbers.data.trend} /> : null}
              {canList && numbers.data.by_mcc ? <ByMcc rows={numbers.data.by_mcc} /> : null}
            </div>
          ) : null}
        </>
      )}
    </>
  );
}

function AddSignature() {
  return (
    <div className="flex flex-wrap items-center gap-3 border border-amber-500/30 bg-amber-500/8 p-4">
      <PenLine className="size-5 shrink-0 text-amber-600 dark:text-amber-400" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">Add your signature</p>
        <p className="text-sm text-muted-foreground">
          Forms you submit or approve carry your signature. It takes a minute: a photo or drawn on screen.
        </p>
      </div>
      <Button size="sm" nativeButton={false} render={<Link href="/account#signature" />}>
        Add signature
      </Button>
    </div>
  );
}

function NeedsYou({ numbers }: { numbers: Numbers }) {
  const { navigation } = useSession();
  const queue = flatten(navigation).find(({ item }) => item.key in QUEUE_STATUS)?.item;
  const isFacilitator = useMe().roles.includes("facilitator");
  const waiting = numbers.my_queue?.waiting ?? 0;
  const rejected = numbers.by_status.rejected ?? 0;

  if (queue && waiting > 0) {
    return (
      <Hero
        count={waiting}
        title={waiting === 1 ? "form has steps for you to check" : "forms have steps for you to check"}
        detail="Start with the oldest, so nobody waits too long."
        action={
          <Button size="lg" nativeButton={false} render={<Link href={queue.path ?? "/"} />}>
            Review forms <ArrowRight />
          </Button>
        }
      />
    );
  }
  if (isFacilitator && rejected > 0) {
    return (
      <Hero
        count={rejected}
        title={rejected === 1 ? "form came back to be corrected" : "forms came back to be corrected"}
        detail="Open each in the app, make the correction and submit it again."
        action={
          <Button size="lg" nativeButton={false} render={<Link href="/applications?f_status=rejected" />}>
            See them <ArrowRight />
          </Button>
        }
      />
    );
  }
  if (queue) {
    return (
      <Card className="flex-row items-center gap-3 p-4">
        <CheckCircle2 className="size-5 shrink-0 text-emerald-600 dark:text-emerald-400" />
        <p className="text-sm">
          <span className="font-medium">You&apos;re all caught up.</span>{" "}
          <span className="text-muted-foreground">Nothing is waiting for your decision.</span>
        </p>
      </Card>
    );
  }
  return null;
}

function Hero({
  count,
  title,
  detail,
  action,
}: {
  count: number;
  title: string;
  detail: string;
  action: React.ReactNode;
}) {
  return (
    <Card className="relative flex-row flex-wrap items-center justify-between gap-4 overflow-hidden border-primary/30 bg-primary/5 p-5">
      <span aria-hidden className="absolute inset-y-0 left-0 w-1 bg-brand-accent" />
      <div className="flex min-w-0 items-center gap-4">
        <span className="text-4xl font-semibold text-primary tabular-nums">{count}</span>
        <div className="min-w-0">
          <p className="font-medium">{title}</p>
          <p className="text-sm text-muted-foreground">{detail}</p>
        </div>
      </div>
      {action}
    </Card>
  );
}

function StatusCards({ numbers, linked }: { numbers: Numbers; linked: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {STATUS_OPTIONS.map((option) => {
        const body = (
          <>
            <p className="truncate text-xs text-muted-foreground">{option.label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{numbers.by_status[option.value] ?? 0}</p>
          </>
        );
        const className = "block border bg-card p-4";
        return linked ? (
          <Link
            key={option.value}
            href={`/applications?f_status=${option.value}`}
            className={cn(
              className,
              "outline-none transition-[border-color,box-shadow,transform] hover:-translate-y-px hover:border-primary/50 hover:shadow-(--lift) focus-visible:border-primary focus-visible:shadow-(--lift)",
            )}
          >
            {body}
          </Link>
        ) : (
          <div key={option.value} className={className}>
            {body}
          </div>
        );
      })}
    </div>
  );
}

/** Where forms are right now, longest bar for the fullest stage. */
function Pipeline({ numbers }: { numbers: Numbers }) {
  const rows = STATUS_ORDER.map((status) => ({
    status,
    label: STATUS_OPTIONS.find((option) => option.value === status)?.label ?? status,
    count: numbers.by_status[status] ?? 0,
  }));
  const max = Math.max(...rows.map((row) => row.count), 1);
  return (
    <Card className="gap-3 p-5">
      <h2 className="font-medium">Forms by stage</h2>
      <ul className="space-y-2.5">
        {rows.map((row) => (
          <li key={row.status} className="grid grid-cols-[9.5rem_minmax(0,1fr)_2rem] items-center gap-2 text-sm">
            <span className="truncate text-muted-foreground">{row.label}</span>
            <span className="h-2 bg-muted">
              <span
                className={cn(
                  "block h-full",
                  row.status === "approved"
                    ? "bg-emerald-500"
                    : row.status === "rejected"
                      ? "bg-red-500"
                      : row.status === "draft"
                        ? "bg-muted-foreground/40"
                        : "bg-primary",
                )}
                style={{ width: `${(row.count / max) * 100}%` }}
              />
            </span>
            <span className="text-right font-medium tabular-nums">{row.count}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function RecentForms() {
  const recent = useQuery({
    queryKey: ["queue", "recent"],
    queryFn: () =>
      api<Page<ApplicationSummary>>("applications", { query: { page_size: 6, ordering: "-updated_at" } }),
  });
  const rows = recent.data?.results ?? [];
  return (
    <Card className="gap-0 p-0">
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <h2 className="font-medium">Recent forms</h2>
        <Link href="/applications" className="text-xs font-medium text-primary underline-offset-4 hover:underline">
          See all
        </Link>
      </div>
      {recent.isPending ? (
        <div className="space-y-2 px-5 pb-4">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-9 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <p className="flex items-center gap-2 px-5 pb-5 text-sm text-muted-foreground">
          <Inbox className="size-4" /> No forms yet.
        </p>
      ) : (
        <ul className="divide-y border-t">
          {rows.map((row) => (
            <li key={row.id}>
              <Link
                href={`/applications/${row.id}`}
                className="group flex items-center gap-3 px-5 py-2.5 outline-none hover:bg-muted/60 focus-visible:bg-muted/60"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{row.applicant_name || "No name yet"}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {[row.form_number, `${row.mpp_code} ${row.mpp_name}`, timeAgo(row.updated_at)]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                <StatusBadge status={row.status} label={row.status_label} className="hidden sm:inline-flex" />
                <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Tile({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "warn" | "bad";
}) {
  return (
    <div className="border bg-card p-4">
      <p className="truncate text-xs text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mt-1 text-2xl font-semibold tabular-nums",
          tone === "warn" && "text-amber-700 dark:text-amber-300",
          tone === "bad" && "text-destructive",
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-0.5 truncate text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

/** The few numbers that matter for this person's own work. */
function Highlights({ numbers }: { numbers: Numbers }) {
  const tiles: React.ReactNode[] = [];
  const queue = numbers.my_queue;
  if (queue) {
    tiles.push(
      <Tile key="wait" label="Waiting for you" value={queue.waiting} tone={queue.waiting ? "warn" : undefined} />,
      <Tile
        key="late"
        label="Late"
        value={queue.overdue}
        hint={`Waiting over ${queue.overdue_days} days`}
        tone={queue.overdue ? "bad" : undefined}
      />,
      <Tile
        key="old"
        label="Oldest waiting"
        value={queue.oldest_days === null ? "—" : `${queue.oldest_days} d`}
        hint="Since it reached your stage"
        tone={(queue.oldest_days ?? 0) > queue.overdue_days ? "warn" : undefined}
      />,
      <Tile key="today" label="Steps you approved today" value={queue.steps_today} />,
      <Tile key="week" label="This week" value={queue.steps_week} hint="Steps you approved" />,
    );
  }
  if (numbers.fee) {
    tiles.push(
      <Tile
        key="pay"
        label="Payment not recorded"
        value={numbers.fee.payment_missing}
        hint="At the Finance stage"
        tone={numbers.fee.payment_missing ? "warn" : undefined}
      />,
      <Tile key="fee" label="Fees this month" value={rupees(numbers.fee.collected_month)} hint="From members who joined" />,
    );
  }
  if (numbers.mine) {
    tiles.push(
      <Tile key="drafts" label="Drafts in progress" value={numbers.mine.edited_by_me} />,
      <Tile key="joined" label="Joined this month" value={numbers.mine.approved_month} hint="From your MPPs" />,
    );
  }
  if (numbers.members && !numbers.mine) {
    tiles.push(
      <Tile key="month" label="Joined this month" value={numbers.members.joined_month} />,
      <Tile key="total" label="Joined through this portal" value={numbers.members.joined_total} />,
      <Tile key="existing" label="Existing active members" value={numbers.members.existing_active.toLocaleString("en-IN")} />,
    );
  }
  if (!tiles.length) return null;
  return <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">{tiles.slice(0, 6)}</div>;
}

/** What still stops forms moving. Shown to whoever runs the organization. */
function Setup({ setup }: { setup: NonNullable<Numbers["setup"]> }) {
  const items = [
    { count: setup.steps_without_role, text: "review steps have no role", href: "/admin/review-steps" },
    { count: setup.signatories_missing, text: "stages have no signatory for the PDF", href: "/admin/review-steps" },
    { count: setup.mccs_without_area_manager, text: "MCCs have no Area Manager", href: "/masters/assignments" },
    { count: setup.signatures_missing, text: "people who sign forms have no signature on file", href: "/admin/staff" },
  ].filter((item) => item.count > 0);
  if (!items.length) return null;
  return (
    <Card className="gap-2 border-amber-500/40 bg-amber-500/5 p-4">
      <h2 className="text-sm font-medium">Before forms can move</h2>
      <ul className="space-y-1 text-sm">
        {items.map((item) => (
          <li key={item.text}>
            <Link href={item.href} className="inline-flex items-center gap-1.5 underline-offset-4 hover:underline">
              <span className="font-semibold tabular-nums">{item.count}</span> {item.text}
              <ChevronRight className="size-3.5 text-muted-foreground" />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Trend({ days }: { days: NonNullable<Numbers["trend"]> }) {
  const [series, setSeries] = useState<"submitted" | "joined">("submitted");
  return (
    <Card className="gap-3 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-medium">Last 14 days</h2>
        <StatusTabs
          value={series}
          onChange={setSeries}
          options={[
            { value: "submitted", label: "Submitted" },
            { value: "joined", label: "Became members" },
          ]}
        />
      </div>
      <BarChart
        data={days.map((day) => ({
          label: new Date(day.day).toLocaleDateString("en-IN", { day: "numeric", month: "short" }),
          value: day[series],
        }))}
        height={160}
      />
    </Card>
  );
}

function ByMcc({ rows }: { rows: NonNullable<Numbers["by_mcc"]> }) {
  const max = Math.max(...rows.map((row) => row.waiting), 1);
  return (
    <Card className="gap-3 p-5">
      <h2 className="font-medium">Waiting by MCC</h2>
      {rows.length ? (
        <ul className="space-y-2.5">
          {rows.map((row) => (
            <li key={row.code} className="grid grid-cols-[9.5rem_minmax(0,1fr)_2rem_3.5rem] items-center gap-2 text-sm">
              <span className="truncate text-muted-foreground">
                {row.code} {row.name}
              </span>
              <span className="flex h-2 bg-muted">
                <span className="block h-full bg-destructive" style={{ width: `${(row.overdue / max) * 100}%` }} />
                <span
                  className="block h-full bg-primary"
                  style={{ width: `${((row.waiting - row.overdue) / max) * 100}%` }}
                />
              </span>
              <span className="text-right font-medium tabular-nums">{row.waiting}</span>
              <span className={cn("text-right text-xs tabular-nums", row.overdue ? "text-destructive" : "text-muted-foreground")}>
                {row.overdue ? `${row.overdue} late` : ""}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Nothing is waiting in your MCCs.</p>
      )}
    </Card>
  );
}

function HomeSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-24 w-full" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-56 w-full" />
    </div>
  );
}
