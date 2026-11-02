"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  CheckCircle2,
  Clock,
  Download,
  FileArchive,
  FileStack,
  Gauge,
  Hourglass,
  Loader2,
  RotateCcw,
  Search,
  Timer,
  X,
  XCircle,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Confirm } from "@/components/admin/confirm";
import { messageOf } from "@/components/admin/feedback";
import { CheckRow } from "@/components/admin/check-row";
import { DateRangePicker } from "@/components/common/date-picker";
import { Field } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCan } from "@/hooks/use-session";
import { api, type Page } from "@/lib/api/client";
import { date, dateTime } from "@/lib/format";
import type { Mcc, Mpp, PdfBatch, PrintPreview } from "@/lib/types";
import { cn } from "@/lib/utils";

const BASE = "reports/pdf-batches";

type Filters = { approved_from: string; approved_to: string; search: string; mcc: string; mpp: string };

const STATUS: Record<PdfBatch["status"], { badge: string; label: string }> = {
  queued: { badge: "queued", label: "Waiting" },
  running: { badge: "processing", label: "Making" },
  done: { badge: "completed", label: "Ready" },
  failed: { badge: "failed", label: "Failed" },
  cancelled: { badge: "draft", label: "Cancelled" },
};

/** 95 → "1 min 35 s", 4000 → "1 h 7 min". */
export function duration(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  if (hours) return `${hours} h ${minutes} min`;
  if (minutes) return `${minutes} min${rest ? ` ${rest} s` : ""}`;
  return `${rest} s`;
}

export function megabytes(bytes: number) {
  return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB` : `${Math.max(1, Math.round(bytes / 1024 ** 2))} MB`;
}

/** A second hand for the live numbers, only while something is running. */
function useNow(running: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return now;
}

/**
 * Where a job is, as one number from 0 to 1, with its speed and time left.
 * Making forms is most of the work; joining them for print is the last stretch.
 */
export function progressOf(job: PdfBatch, now: number) {
  const renderShare = job.want_merged ? 0.85 : 1;
  const step = job.form_count ? job.cursor / job.form_count : 0;
  const done =
    job.status === "done"
      ? 1
      : job.phase === "merge"
        ? renderShare + (1 - renderShare) * step
        : renderShare * step;
  const elapsed = job.started_at ? ((job.finished_at ? Date.parse(job.finished_at) : now) - Date.parse(job.started_at)) / 1000 : 0;
  const perMinute = elapsed > 3 && done > 0 ? (job.phase === "render" ? job.cursor : job.form_count) / (elapsed / 60) : 0;
  const left = done > 0.01 && elapsed > 3 ? (elapsed / done) * (1 - done) : null;
  return { done, elapsed, perMinute, left };
}

function Stat({ icon: Icon, label, value, tone }: { icon: typeof Clock; label: string; value: string; tone?: "bad" }) {
  return (
    <div className="min-w-0 border bg-card px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon className="size-3.5" /> {label}
      </p>
      <p className={cn("mt-0.5 truncate text-lg font-semibold tabular-nums", tone === "bad" && "text-destructive")}>
        {value}
      </p>
    </div>
  );
}

/** The job being made right now, as it happens. */
function LiveJob({ job }: { job: PdfBatch }) {
  const client = useQueryClient();
  const now = useNow(job.status === "running" || job.status === "queued");
  const { done, elapsed, perMinute, left } = progressOf(job, now);
  const cancel = useMutation({
    mutationFn: () => api(`${BASE}/${job.id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Cancelled.");
      client.invalidateQueries({ queryKey: ["pdf-jobs"] });
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const percent = Math.floor(done * 100);
  const waiting = job.status === "queued";

  return (
    <Card className="gap-4 border-primary/40 p-5" aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-medium">
            <Loader2 className="size-4 animate-spin text-primary" />
            {waiting
              ? `Waiting in line${job.queue_position ? ` · ${job.queue_position === 1 ? "next" : `number ${job.queue_position}`}` : ""}`
              : job.phase === "merge"
                ? "Joining the forms into print files"
                : "Making the forms"}
          </p>
          <p className="truncate text-sm text-muted-foreground">
            {job.label} · {job.variant === "full" ? "Full form" : "Single page"} · {job.form_count} forms
          </p>
        </div>
        <Confirm
          title="Cancel this job?"
          description="Forms made so far stay made, so starting again later is quicker."
          action="Cancel job"
          onConfirm={() => cancel.mutate()}
          trigger={
            <Button variant="outline" disabled={cancel.isPending}>
              <Ban /> Cancel
            </Button>
          }
        />
      </div>

      <div className="space-y-1.5">
        <div className="flex items-baseline justify-between text-sm">
          <span className="text-3xl font-semibold tabular-nums">{percent}%</span>
          <span className="text-muted-foreground tabular-nums">
            {job.phase === "merge" ? `Print files: ${job.merged_parts.length}` : `${job.cursor} of ${job.form_count} forms`}
          </span>
        </div>
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="relative h-3 overflow-hidden bg-muted"
        >
          <div className="h-full bg-primary transition-[width] duration-700 ease-out" style={{ width: `${percent}%` }} />
          {waiting ? <div className="absolute inset-0 animate-pulse bg-primary/10" /> : null}
        </div>
        {job.current_form ? (
          <p className="text-xs text-muted-foreground">
            Now: <span className="font-mono tabular-nums">{job.current_form}</span>
          </p>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        <Stat icon={CheckCircle2} label="Made" value={`${job.processed} / ${job.form_count}`} />
        <Stat icon={XCircle} label="Failed" value={String(job.failed_count)} tone={job.failed_count ? "bad" : undefined} />
        <Stat icon={Gauge} label="Speed" value={perMinute ? `${Math.round(perMinute)} / min` : "—"} />
        <Stat icon={Timer} label="Time taken" value={job.started_at ? duration(elapsed) : "—"} />
        <Stat icon={Hourglass} label="Time left" value={left === null ? "Working it out…" : `~${duration(left)}`} />
        <Stat icon={Clock} label="Started" value={job.started_at ? dateTime(job.started_at).split(", ").at(-1) ?? "" : "Not yet"} />
      </div>
      <p className="text-xs text-muted-foreground">
        You can leave this page. The job keeps going, and the bell tells you when it is ready.
      </p>
    </Card>
  );
}

function Downloads({ job }: { job: PdfBatch }) {
  const base = `/api/backend/${BASE}/${job.id}`;
  return (
    <div className="flex flex-wrap justify-end gap-1.5">
      {job.want_zip ? (
        <Button variant="outline" size="sm" nativeButton={false} render={<a href={`${base}/zip`} />}>
          <FileArchive /> ZIP
        </Button>
      ) : null}
      {job.merged_parts.map((part) => (
        <Button
          key={part.index}
          variant="outline"
          size="sm"
          nativeButton={false}
          render={<a href={`${base}/file?part=${part.index}`} />}
          title={`${part.forms} forms${part.bytes ? `, ${megabytes(part.bytes)}` : ""}`}
        >
          <Download /> {job.merged_parts.length > 1 ? `Print ${part.index + 1}` : "Print file"}
        </Button>
      ))}
    </div>
  );
}

function History({ jobs }: { jobs: PdfBatch[] }) {
  const client = useQueryClient();
  const retry = useMutation({
    mutationFn: (job: PdfBatch) => api(`${BASE}/${job.id}/retry`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Trying the failed forms again.");
      client.invalidateQueries({ queryKey: ["pdf-jobs"] });
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const now = useNow(false);

  return (
    <Card className="gap-3 p-5">
      <h2 className="font-medium">Your PDF jobs</h2>
      {jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing yet. Each job you start is kept here for 7 days.</p>
      ) : (
        <div className="overflow-x-auto border-t">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Asked for</TableHead>
                <TableHead className="text-right">Forms</TableHead>
                <TableHead className="hidden md:table-cell">Took</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => {
                const state = STATUS[job.status];
                const expired = !!job.expires_at && Date.parse(job.expires_at) < now;
                return (
                  <TableRow key={job.id}>
                    <TableCell className="max-w-md">
                      <p className="truncate">{job.label}</p>
                      <p className="text-xs text-muted-foreground">
                        {dateTime(job.created_at)} · {job.variant === "full" ? "Full form" : "Single page"}
                        {job.status === "done" && job.expires_at && !expired ? ` · until ${date(job.expires_at)}` : ""}
                      </p>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {job.processed}
                      {job.form_count !== job.processed ? <span className="text-muted-foreground"> / {job.form_count}</span> : null}
                      {job.failed_count ? (
                        <p className="text-xs text-destructive" title={job.failed_forms.join(", ")}>
                          {job.failed_count} failed
                        </p>
                      ) : null}
                    </TableCell>
                    <TableCell className="hidden text-muted-foreground tabular-nums md:table-cell">
                      {job.started_at && job.finished_at
                        ? duration((Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={expired ? "draft" : state.badge} label={expired ? "Removed" : state.label} />
                      {job.error ? <p className="mt-0.5 text-xs text-muted-foreground">{job.error}</p> : null}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap justify-end gap-1.5">
                        {job.status === "done" && !expired ? <Downloads job={job} /> : null}
                        {job.failed_count && (job.status === "done" || job.status === "failed") ? (
                          <Button variant="ghost" size="sm" disabled={retry.isPending} onClick={() => retry.mutate(job)}>
                            <RotateCcw /> Retry failed
                          </Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  );
}

export function PdfCenter() {
  const params = useSearchParams();
  const client = useQueryClient();
  const canFull = useCan("applications.download_full_pdf");
  const canSeeMasters = useCan("hierarchy.view");
  const [filters, setFilters] = useState<Filters>(() => ({
    approved_from: params.get("approved_from") ?? "",
    approved_to: params.get("approved_to") ?? "",
    search: params.get("search") ?? "",
    mcc: "",
    mpp: "",
  }));
  const [variant, setVariant] = useState<"full" | "single">(canFull ? "full" : "single");
  const [wantZip, setWantZip] = useState(true);
  const [wantMerged, setWantMerged] = useState(false);
  const [excluded, setExcluded] = useState<string[]>([]);
  const deferred = useDeferredValue(filters);
  const body = Object.fromEntries(Object.entries(deferred).filter(([, value]) => value));

  const preview = useQuery({
    queryKey: ["pdf-preview", body, variant],
    queryFn: () => api<PrintPreview>(`${BASE}/preview`, { method: "POST", body: { ...body, variant } }),
    placeholderData: (previous) => previous,
  });
  const jobs = useQuery({
    queryKey: ["pdf-jobs"],
    queryFn: () => api<Page<PdfBatch>>(BASE, { query: { page_size: 30 } }),
    // Every second and a half while one runs: close enough to watch it move.
    refetchInterval: (query) =>
      query.state.data?.results.some((job) => job.status === "queued" || job.status === "running") ? 1500 : false,
  });
  const mccs = useQuery({
    queryKey: ["hierarchy", "mccs"],
    queryFn: () => api<Page<Mcc>>("hierarchy/mccs", { query: { page_size: 500, ordering: "code" } }),
    enabled: canSeeMasters,
  });
  const mpps = useQuery({
    queryKey: ["hierarchy", "mpps"],
    queryFn: () => api<Page<Mpp>>("hierarchy/mpps", { query: { page_size: 5000, ordering: "code" } }),
    enabled: canSeeMasters,
  });

  const start = useMutation({
    mutationFn: () =>
      api<PdfBatch>(BASE, {
        method: "POST",
        body: { ...body, variant, want_zip: wantZip, want_merged: wantMerged, exclude: excluded },
      }),
    onSuccess: (job) => {
      toast.success(job.status === "queued" ? "Queued. It starts when the job ahead finishes." : "Started.");
      setExcluded([]);
      client.invalidateQueries({ queryKey: ["pdf-jobs"] });
    },
    onError: (error) => toast.error(messageOf(error)),
  });

  // Tell whoever is watching when their job ends, wherever they scrolled.
  const all = useMemo(() => jobs.data?.results ?? [], [jobs.data]);
  const live = all.find((job) => job.status === "running" || job.status === "queued");
  const lastLive = useRef<string | null>(null);
  useEffect(() => {
    if (live) {
      lastLive.current = live.id;
      return;
    }
    const ended = all.find((job) => job.id === lastLive.current);
    if (!ended) return;
    lastLive.current = null;
    if (ended.status === "done") toast.success(`${ended.processed} forms are ready to download.`);
    else if (ended.status === "failed") toast.error(ended.error || "The job failed.");
  }, [live, all]);

  const set = (key: keyof Filters, value: string) => {
    setExcluded([]);
    setFilters((current) => ({ ...current, [key]: value }));
  };
  const mppOptions = (mpps.data?.results ?? [])
    .filter((mpp) => !filters.mcc || mpp.mcc === filters.mcc)
    .map((mpp) => ({ value: mpp.id, label: `${mpp.code} ${mpp.name}` }));
  const data = preview.data;
  const chosen = data ? data.count - excluded.length : 0;
  const tooMany = !!data && chosen > data.limit;
  const nothingPicked = !wantZip && !wantMerged;

  return (
    <>
      <PageHeader
        title="PDF Center"
        description="Printed forms of approved members, made in the background a few at a time."
      />

      {live ? <LiveJob job={live} /> : null}

      <Card className="gap-4 p-5">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(15rem,1.2fr)_1fr_1fr_minmax(14rem,1.2fr)]">
          <Field label="Approved between">
            <DateRangePicker
              from={filters.approved_from}
              to={filters.approved_to}
              onChange={(range) => {
                setExcluded([]);
                setFilters((current) => ({ ...current, approved_from: range.from, approved_to: range.to }));
              }}
              placeholder="Any day"
              className="[&>button]:h-9"
              aria-label="Approved between"
            />
          </Field>
          <Field label="MCC">
            <Listbox
              value={filters.mcc}
              disabled={!canSeeMasters}
              onChange={(value) => {
                setExcluded([]);
                setFilters((current) => ({ ...current, mcc: value, mpp: "" }));
              }}
              items={[
                { value: "", label: "All" },
                ...(mccs.data?.results ?? []).map((mcc) => ({ value: mcc.id, label: `${mcc.code} ${mcc.name}` })),
              ]}
            />
          </Field>
          <Field label="MPP">
            <Listbox
              value={filters.mpp}
              disabled={!canSeeMasters}
              onChange={(value) => set("mpp", value)}
              items={[{ value: "", label: "All" }, ...mppOptions]}
            />
          </Field>
          <Field label="One member" help="Form number, member code, mobile or name">
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={filters.search}
                onChange={(event) => set("search", event.target.value)}
                placeholder="A54678"
                className="pl-8"
              />
            </div>
          </Field>
        </div>

        <div className="grid gap-4 border-t pt-4 md:grid-cols-2">
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Which form</legend>
            <div className="flex flex-wrap gap-2">
              {(
                [
                  ["full", "Full form", "All 5 pages, with Aadhaar and passbook", canFull],
                  ["single", "Single page", "The first page only", true],
                ] as const
              ).map(([value, label, hint, allowed]) => (
                <button
                  key={value}
                  type="button"
                  disabled={!allowed}
                  aria-pressed={variant === value}
                  onClick={() => setVariant(value)}
                  className={cn(
                    "min-w-44 flex-1 border px-3 py-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
                    variant === value ? "border-primary bg-primary/8" : "hover:border-foreground/30",
                  )}
                >
                  <span className="block text-sm font-medium">{label}</span>
                  <span className="block text-xs text-muted-foreground">{allowed ? hint : "You don't have access to this one"}</span>
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">What to download</legend>
            <div className="border p-1">
              <CheckRow
                label="ZIP of separate PDFs"
                hint="One file per member, named by form number, like A54678.pdf"
                checked={wantZip}
                onChange={setWantZip}
              />
              <CheckRow
                label="Merged file for printing"
                hint="All forms in one PDF, split into files of about 150 MB"
                checked={wantMerged}
                onChange={setWantMerged}
              />
            </div>
          </fieldset>
        </div>
      </Card>

      {preview.error ? (
        <ErrorState error={preview.error} onRetry={() => preview.refetch()} />
      ) : !data ? (
        <Skeleton className="h-48 w-full" />
      ) : data.count === 0 ? (
        <EmptyState
          icon={FileStack}
          title="No approved member matches"
          description="Only members approved through this portal can be printed. Widen the dates or clear a filter."
        />
      ) : (
        <Card className={cn("gap-4 p-5 transition-opacity", preview.isFetching && "opacity-70")}>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat icon={FileStack} label="Forms" value={String(chosen)} tone={tooMany ? "bad" : undefined} />
              <Stat icon={CheckCircle2} label="Already made" value={String(data.ready)} />
              <Stat icon={Timer} label="About" value={duration(data.estimated_seconds)} />
              <Stat icon={FileArchive} label="Size, roughly" value={megabytes(data.estimated_bytes)} />
            </div>
            <Button
              size="lg"
              disabled={start.isPending || tooMany || nothingPicked || chosen <= 0 || !!live}
              onClick={() => start.mutate()}
            >
              {start.isPending ? <Loader2 className="animate-spin" /> : <FileStack />}
              Make {chosen} {chosen === 1 ? "PDF" : "PDFs"}
            </Button>
          </div>
          {tooMany ? (
            <p className="text-sm text-destructive">
              At most {data.limit} forms in one job. Narrow the dates, or pick an MCC or MPP.
            </p>
          ) : live ? (
            <p className="text-sm text-muted-foreground">Your job above has to finish, or be cancelled, before the next one.</p>
          ) : nothingPicked ? (
            <p className="text-sm text-destructive">Choose a ZIP, a merged file, or both.</p>
          ) : null}

          <div className="overflow-x-auto border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Form</TableHead>
                  <TableHead>Member</TableHead>
                  <TableHead className="hidden md:table-cell">MPP</TableHead>
                  <TableHead className="hidden sm:table-cell">Approved</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.rows.map((row) => {
                  const kept = !excluded.includes(row.id);
                  return (
                    <TableRow key={row.id} className={cn(!kept && "opacity-50")}>
                      <TableCell>
                        <Checkbox
                          aria-label={`Include ${row.form_number}`}
                          checked={kept}
                          onCheckedChange={(on) =>
                            setExcluded((current) => (on ? current.filter((id) => id !== row.id) : [...current, row.id]))
                          }
                        />
                      </TableCell>
                      <TableCell className="font-mono text-[13px] tabular-nums">{row.form_number}</TableCell>
                      <TableCell>
                        <span className="font-medium">{row.full_name}</span>
                        <span className="ml-2 font-mono text-xs text-muted-foreground tabular-nums">{row.tr_code}</span>
                      </TableCell>
                      <TableCell className="hidden text-muted-foreground md:table-cell">{row.mpp}</TableCell>
                      <TableCell className="hidden text-muted-foreground tabular-nums sm:table-cell">{date(row.approved_at)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
          {data.count > data.rows.length ? (
            <p className="text-xs text-muted-foreground">
              Showing the first {data.rows.length} of {data.count}. All {chosen} are included.
            </p>
          ) : null}
          {excluded.length ? (
            <Button variant="ghost" size="sm" className="self-start" onClick={() => setExcluded([])}>
              <X /> Put back {excluded.length} taken out
            </Button>
          ) : null}
        </Card>
      )}

      {jobs.error ? (
        <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />
      ) : jobs.isPending ? (
        <Skeleton className="h-32 w-full" />
      ) : (
        <History jobs={all.filter((job) => job.id !== live?.id)} />
      )}
    </>
  );
}
