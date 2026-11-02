"use client";

import { useQuery } from "@tanstack/react-query";
import { FileSpreadsheet, FileStack, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { STATUS_OPTIONS } from "@/components/applications/constants";
import { DateRangePicker } from "@/components/common/date-picker";
import { Field } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { MasterSelect } from "@/components/common/master-select";
import { MppSelect } from "@/components/common/mpp-select";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/hooks/use-session";
import { api } from "@/lib/api/client";
import type { ReportSummary } from "@/lib/types";

type Filters = {
  status: string;
  mcc: string;
  route: string;
  mpp: string;
  submitted_from: string;
  submitted_to: string;
};

const EMPTY: Filters = { status: "", mcc: "", route: "", mpp: "", submitted_from: "", submitted_to: "" };

const asQuery = (filters: Filters) =>
  new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();

export default function ReportsPage() {
  const [filters, setFilters] = useState(EMPTY);
  const set = (key: keyof Filters, value: string) => setFilters({ ...filters, [key]: value });
  const canExport = useCan("reports.export");
  const canSeeMasters = useCan("hierarchy.view");
  const query = useMemo(() => asQuery(filters), [filters]);
  const active = query.length > 0;

  const summary = useQuery({
    queryKey: ["report-summary", query],
    queryFn: () => api<ReportSummary>(`reports/summary${query ? `?${query}` : ""}`),
  });


  return (
    <>
      <PageHeader
        title="Reports"
        description="Forms by status, limited to the MPPs you can access."
        actions={
          canExport ? (
            <Button nativeButton={false} render={<a href={`/api/backend/reports/export${query ? `?${query}` : ""}`} />}>
              <FileSpreadsheet /> Export to Excel
            </Button>
          ) : null
        }
      />

      <Card className="gap-0 p-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-[1fr_1fr_1fr_1fr_minmax(15rem,1.2fr)_auto] xl:items-start">
          <Field label="Status">
            <Listbox
              value={filters.status}
              onChange={(value) => set("status", value)}
              items={[{ value: "", label: "All" }, ...STATUS_OPTIONS]}
            />
          </Field>
          <Field label="MCC">
            <MasterSelect
              kind="mccs"
              value={filters.mcc}
              disabled={!canSeeMasters}
              onChange={(value) => setFilters({ ...filters, mcc: value, route: "", mpp: "" })}
            />
          </Field>
          <Field label="Route">
            <MasterSelect
              kind="routes"
              value={filters.route}
              filters={{ bmc__mcc: filters.mcc || undefined }}
              disabled={!canSeeMasters}
              onChange={(value) => setFilters({ ...filters, route: value, mpp: "" })}
            />
          </Field>
          <Field label="MPP">
            <MppSelect
              value={filters.mpp}
              mcc={filters.mcc || undefined}
              route={filters.route || undefined}
              disabled={!canSeeMasters}
              onChange={(value) => set("mpp", value)}
            />
          </Field>
          <Field label="Submitted">
            <DateRangePicker
              from={filters.submitted_from}
              to={filters.submitted_to}
              onChange={(range) =>
                setFilters({ ...filters, submitted_from: range.from, submitted_to: range.to })
              }
              placeholder="Any date"
              className="[&>button]:h-9"
              aria-label="Submitted between"
            />
          </Field>
          {active ? (
            <Button variant="ghost" onClick={() => setFilters(EMPTY)}>
              <X /> Clear
            </Button>
          ) : null}
        </div>
      </Card>

      {summary.error ? (
        <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
      ) : summary.isPending ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          {Array.from({ length: 7 }).map((_, index) => (
            <Skeleton key={index} className="h-20" />
          ))}
        </div>
      ) : summary.data.total === 0 ? (
        <EmptyState
          icon={FileStack}
          title="No forms match"
          description="Nothing fits these filters. Widen the dates or clear a filter."
        />
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <div className="border border-primary/30 bg-primary/5 p-4">
            <p className="text-xs text-muted-foreground">Total</p>
            <p className="mt-1 text-2xl font-semibold text-primary tabular-nums">{summary.data.total}</p>
          </div>
          {STATUS_OPTIONS.map((option) => (
            <div key={option.value} className="border bg-card p-4">
              <p className="truncate text-xs text-muted-foreground">{option.label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{summary.data.by_status[option.value] ?? 0}</p>
            </div>
          ))}
        </div>
      )}

      <Card className="flex-row flex-wrap items-center justify-between gap-3 p-5">
        <div>
          <h2 className="font-medium">Printing forms in bulk</h2>
          <p className="text-sm text-muted-foreground">
            The PDF Center makes them in the background, with progress, a ZIP of separate forms and print files.
          </p>
        </div>
        <Button variant="outline" nativeButton={false} render={<Link href="/applications/pdf" />}>
          <FileStack /> Open the PDF Center
        </Button>
      </Card>
    </>
  );
}
