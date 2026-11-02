"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { BarChart3, ChevronRight, Download } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Fragment, useState, type ReactNode } from "react";

import { DateRangeFilter } from "@/components/common/date-filter";
import { DataTable, type Column } from "@/components/common/data-table";
import { Listbox } from "@/components/common/listbox";
import { DateRangePicker } from "@/components/common/date-picker";
import { EmptyState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api/client";
import type { BreakdownRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const GROUPS = {
  facilitator: "Facilitator",
  mcc: "MCC",
  bmc: "BMC",
  route: "Route",
  mpp: "MPP",
  mcc_facilitator: "MCC, then facilitator",
} as const;

const COUNTS: { id: keyof BreakdownRow; header: string; hint: string }[] = [
  { id: "started", header: "Started", hint: "Forms begun in these dates" },
  { id: "submitted", header: "Submitted", hint: "Sent for approval in these dates" },
  { id: "pending", header: "Pending", hint: "Of those submitted, still waiting" },
  { id: "approved", header: "Approved", hint: "Became members in these dates" },
  { id: "rejected", header: "Rejected", hint: "Sent back in these dates" },
];

const today = () => {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
};

function columns(by: string): Column<BreakdownRow>[] {
  return [
    {
      id: "name",
      header: GROUPS[by as keyof typeof GROUPS] ?? "Name",
      required: true,
      sortKey: "name",
      csv: (row) => (row.code ? `${row.code} ${row.name}` : row.name),
      cell: (row) => (
        <span className="font-medium">
          {row.code ? <span className="mr-1.5 font-mono text-xs text-muted-foreground tabular-nums">{row.code}</span> : null}
          {row.name}
        </span>
      ),
    },
    ...COUNTS.map(
      (count): Column<BreakdownRow> => ({
        id: count.id,
        header: <span title={count.hint}>{count.header}</span>,
        align: "right",
        sortKey: count.id,
        sortValue: (row) => row[count.id] as number,
        csv: (row) => row[count.id] as number,
        cell: (row) => (
          <span className={row[count.id] ? "tabular-nums" : "text-muted-foreground tabular-nums"}>{row[count.id]}</span>
        ),
      }),
    ),
  ];
}

/** Who and where the work came from, for a day or any range. Today unless changed. */
export function Performance() {
  const day = today();
  const by = useSearchParams().get("p_f_by") ?? "facilitator";
  if (by === "mcc_facilitator") {
    return (
      <Shell>
        <GroupedBreakdown day={day} />
      </Shell>
    );
  }
  return (
    <Shell>
      <DataTable<BreakdownRow>
        id="performance"
        urlPrefix="p_"
        endpoint="home/breakdown"
        columns={columns(by)}
        rowKey={(row) => row.key || row.name}
        defaultFilters={{ by: "facilitator", from: day, to: day }}
        defaultOrdering="-started"
        searchPlaceholder="Search by name or code"
        exportName="performance"
        filters={({ filters, setFilter, setFilters }) => (
          <>
            <Listbox
              aria-label="Group by"
              className="w-auto min-w-36"
              value={filters.by ?? "facilitator"}
              onChange={(value) => setFilter("by", value)}
              items={Object.fromEntries(Object.entries(GROUPS).map(([key, label]) => [key, `By ${label}`]))}
            />
            <DateRangeFilter filters={filters} setFilters={setFilters} placeholder="Today" />
          </>
        )}
        above={(_, data) => {
          const rows = Array.isArray(data) ? (data as BreakdownRow[]) : [];
          if (!rows.length) return null;
          const sum = (id: keyof BreakdownRow) => rows.reduce((total, row) => total + (row[id] as number), 0);
          return (
            <p className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
              <span className="text-muted-foreground">Total</span>
              {COUNTS.map((count) => (
                <span key={count.id}>
                  {count.header} <span className="font-semibold tabular-nums">{sum(count.id)}</span>
                </span>
              ))}
            </p>
          );
        }}
        empty={<EmptyState icon={BarChart3} title="No forms in these dates" description="Try another day or range." />}
      />
    </Shell>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <section className="space-y-2">
      <div>
        <h2 className="font-medium">Performance</h2>
        <p className="text-sm text-muted-foreground">
          Forms per facilitator, or per MCC, BMC, route or MPP. Pending counts what was submitted in these dates and is
          still waiting.
        </p>
      </div>
      {children}
    </section>
  );
}

/** Each MCC with its own total, and its facilitators under it. */
function GroupedBreakdown({ day }: { day: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const from = params.get("p_f_from") ?? day;
  const to = params.get("p_f_to") ?? day;
  const [closed, setClosed] = useState<string[]>([]);

  const set = (values: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(values)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  const query = useQuery({
    queryKey: ["queue", "breakdown", "mcc_facilitator", from, to],
    queryFn: () => api<BreakdownRow[]>("home/breakdown", { query: { by: "mcc_facilitator", from, to } }),
    placeholderData: keepPreviousData,
  });
  const rows = query.data ?? [];
  const groups = [...new Set(rows.map((row) => row.group_code ?? ""))].map((code) => {
    const people = rows.filter((row) => row.group_code === code);
    return {
      code,
      name: people[0]?.group_name ?? "",
      people,
      sum: Object.fromEntries(COUNTS.map((count) => [count.id, people.reduce((n, row) => n + (row[count.id] as number), 0)])),
    };
  });

  const download = () => {
    const lines = [
      ["MCC", "Facilitator", ...COUNTS.map((count) => count.header)],
      ...rows.map((row) => [`${row.group_code} ${row.group_name}`, row.name, ...COUNTS.map((count) => row[count.id])]),
    ];
    const csv = lines.map((line) => line.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(",")).join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    link.download = `mcc-facilitators-${from}-to-${to}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Listbox
          aria-label="Group by"
          className="w-auto min-w-36"
          value="mcc_facilitator"
          onChange={(value) => set({ p_f_by: value })}
          items={Object.fromEntries(Object.entries(GROUPS).map(([key, label]) => [key, `By ${label}`]))}
        />
        <DateRangePicker
          size="sm"
          from={from}
          to={to}
          onChange={(range) => set({ p_f_from: range.from || undefined, p_f_to: range.to || undefined })}
          placeholder="Today"
          aria-label="Dates"
        />
        <div className="ml-auto flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setClosed(closed.length ? [] : groups.map((group) => group.code))}
          >
            {closed.length ? "Open all" : "Close all"}
          </Button>
          <Button variant="ghost" size="sm" disabled={!rows.length} onClick={download}>
            <Download /> Export
          </Button>
        </div>
      </div>
      {query.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : !groups.length ? (
        <EmptyState icon={BarChart3} title="No forms in these dates" description="Try another day or range." />
      ) : (
        <Card className="gap-0 overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>MCC / facilitator</TableHead>
                {COUNTS.map((count) => (
                  <TableHead key={count.id} className="text-right" title={count.hint}>
                    {count.header}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {groups.map((group) => {
                const open = !closed.includes(group.code);
                return (
                  <Fragment key={group.code}>
                    <TableRow className="bg-muted/50 hover:bg-muted">
                      <TableCell>
                        <button
                          type="button"
                          aria-expanded={open}
                          onClick={() =>
                            setClosed(open ? [...closed, group.code] : closed.filter((code) => code !== group.code))
                          }
                          className="inline-flex items-center gap-1.5 font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <ChevronRight className={cn("size-4 transition-transform", open && "rotate-90")} />
                          <span className="font-mono text-xs text-muted-foreground tabular-nums">{group.code}</span>
                          {group.name}
                          <span className="text-xs font-normal text-muted-foreground">
                            {group.people.length} {group.people.length === 1 ? "facilitator" : "facilitators"}
                          </span>
                        </button>
                      </TableCell>
                      {COUNTS.map((count) => (
                        <TableCell key={count.id} className="text-right font-semibold tabular-nums">
                          {group.sum[count.id]}
                        </TableCell>
                      ))}
                    </TableRow>
                    {open
                      ? group.people.map((row) => (
                          <TableRow key={row.key}>
                            <TableCell className="pl-11">{row.name}</TableCell>
                            {COUNTS.map((count) => (
                              <TableCell
                                key={count.id}
                                className={cn("text-right tabular-nums", !row[count.id] && "text-muted-foreground")}
                              >
                                {row[count.id]}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))
                      : null}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
