"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, ChevronRight, FileText } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { BulkAction } from "@/components/common/bulk-action";
import { DoubleConfirm } from "@/components/common/double-confirm";
import { DataTable, type Column, type TableView } from "@/components/common/data-table";
import { DateRangePicker } from "@/components/common/date-picker";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Kbd } from "@/components/shell/shortcuts-help";
import { api, ApiError } from "@/lib/api/client";
import { date, dateTime, timeAgo } from "@/lib/format";
import type { ApplicationSummary, StatusCounts } from "@/lib/types";
import { cn } from "@/lib/utils";

import { STATUS_OPTIONS } from "./constants";

/** How long a form has sat at its stage, in whole days once it is a day old. */
function waitedFor(since: string) {
  const hours = Math.floor((Date.now() - new Date(since).getTime()) / 3_600_000);
  if (hours < 1) return "Just now";
  if (hours < 24) return `${hours} h`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "1 day" : `${days} days`;
}

const decideApproved = (row: ApplicationSummary) =>
  api(`applications/${row.id}/decide`, { method: "POST", body: { decision: "approved" } });

const COLUMNS: Column<ApplicationSummary>[] = [
  {
    id: "form",
    header: "Form",
    sortKey: "form_number",
    required: true,
    csv: (row) => row.form_number,
    cell: (row) =>
      row.form_number ? (
        <span className="font-mono text-[13px] tabular-nums">{row.form_number}</span>
      ) : (
        <span className="text-muted-foreground">Draft</span>
      ),
  },
  {
    id: "applicant",
    header: "Applicant",
    required: true,
    csv: (row) => row.applicant_name,
    cell: (row) => <span className="font-medium">{row.applicant_name || "No name yet"}</span>,
  },
  {
    id: "mpp",
    header: "MPP",
    csv: (row) => `${row.mpp_code} ${row.mpp_name}`,
    cell: (row) => (
      <span>
        <span className="tabular-nums">{row.mpp_code}</span>{" "}
        <span className="text-muted-foreground">{row.mpp_name}</span>
      </span>
    ),
  },
  {
    id: "prepared",
    header: "Prepared by",
    hideBelow: "lg",
    csv: (row) => row.created_by_name,
    cell: (row) => <span className="text-muted-foreground">{row.created_by_name}</span>,
  },
  {
    id: "submitted",
    header: "Submitted",
    sortKey: "submitted_at",
    hideBelow: "md",
    csv: (row) => dateTime(row.submitted_at),
    cell: (row) => (
      <span className="text-muted-foreground" title={dateTime(row.submitted_at)}>
        {row.submitted_at ? timeAgo(row.submitted_at) : "—"}
      </span>
    ),
  },
  {
    id: "waiting",
    header: "Waiting",
    sortKey: "waiting_since",
    csv: (row) => (row.status.startsWith("pending") && row.waiting_since ? dateTime(row.waiting_since) : ""),
    cell: (row) =>
      row.status.startsWith("pending") && row.waiting_since ? (
        <span
          title={`At this stage since ${dateTime(row.waiting_since)}`}
          className={cn(
            "tabular-nums",
            row.is_overdue ? "font-medium text-destructive" : "text-muted-foreground",
          )}
        >
          {waitedFor(row.waiting_since)}
        </span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
  },
  {
    id: "updated",
    header: "Last change",
    sortKey: "updated_at",
    defaultHidden: true,
    csv: (row) => dateTime(row.updated_at),
    cell: (row) => <span className="text-muted-foreground">{timeAgo(row.updated_at)}</span>,
  },
  {
    id: "status",
    header: "Status",
    sortKey: "status",
    csv: (row) => row.status_label,
    cell: (row) => <StatusBadge status={row.status} label={row.status_label} />,
  },
  {
    id: "open",
    header: "",
    required: true,
    align: "right",
    className: "w-8",
    cell: () => <ChevronRight className="ml-auto size-4 text-muted-foreground" />,
  },
];

const VIEWS: TableView[] = [
  { name: "Waiting for a decision", filters: { status: "pending_am,pending_cs,pending_finance" }, ordering: "waiting_since" },
  { name: "Changed most recently", ordering: "-updated_at" },
];

const open = (row: ApplicationSummary) => `/applications/${row.id}`;

/** Every form this person may see, with a tab for each status. */
export function AllApplications() {
  const router = useRouter();
  const counts = useQuery({
    queryKey: ["queue", "counts"],
    queryFn: () => api<StatusCounts>("applications/counts"),
  });
  const tabs = useMemo(
    () => ({
      filter: "status",
      options: [
        { value: "", label: "All", count: counts.data?.total },
        ...STATUS_OPTIONS.map((option) => ({
          value: option.value,
          label: option.label.replace("Pending ", ""),
          count: counts.data?.by_status[option.value],
        })),
      ],
    }),
    [counts.data],
  );

  return (
    <>
      <PageHeader title="All Applications" description="Every membership form in the MPPs you can access." />
      <DataTable
        id="applications"
        endpoint="applications"
        columns={COLUMNS}
        rowKey={(row) => row.id}
        tabs={tabs}
        views={VIEWS}
        searchPlaceholder="Form, name, MPP or member code"
        exportName="applications"
        onRowClick={(row) => router.push(open(row))}
        bulkActions={() => <span className="text-muted-foreground">Use Export to download these rows.</span>}
        empty={
          <EmptyState
            icon={FileText}
            title="No forms here"
            description="Forms appear here once a facilitator starts one in the app. Try another tab or search."
          />
        }
      />
    </>
  );
}

const PENDING = "pending_am,pending_cs,pending_finance";

const column = (id: string) => COLUMNS.find((item) => item.id === id)!;

/** Members made through this portal: their code, and the day of final approval. */
const MEMBER_COLUMNS: Column<ApplicationSummary>[] = [
  column("form"),
  {
    id: "code",
    header: "Member code",
    required: true,
    csv: (row) => row.tr_code,
    cell: (row) => <span className="font-mono text-[13px] tabular-nums">{row.tr_code}</span>,
  },
  column("applicant"),
  column("mpp"),
  column("prepared"),
  {
    id: "approved",
    header: "Approved",
    sortKey: "member__joined_at",
    csv: (row) => dateTime(row.approved_at),
    cell: (row) => (
      <span className="text-muted-foreground tabular-nums" title={dateTime(row.approved_at)}>
        {row.approved_at ? date(row.approved_at) : "—"}
      </span>
    ),
  },
  column("open"),
];

const LISTS = {
  pending: {
    title: "Pending Members",
    description: "Forms somewhere in approval, longest waiting first.",
    status: PENDING,
    ordering: "waiting_since",
    columns: COLUMNS.filter((item) => item.id !== "updated"),
    empty: "Nothing is waiting for approval.",
  },
  approved: {
    title: "Approved Members",
    description: "Members made through this portal. Old members brought over from the ERP are under Members.",
    status: "approved",
    ordering: "-member__joined_at",
    columns: MEMBER_COLUMNS,
    empty: "No member has been approved here yet.",
  },
  rejected: {
    title: "Rejected Members",
    description: "Forms sent back to the facilitator to correct.",
    status: "rejected",
    ordering: "-updated_at",
    columns: COLUMNS.filter((item) => item.id !== "waiting"),
    empty: "No form is waiting for corrections.",
  },
} as const;

/** One status of form as its own list: pending, approved or rejected. */
export function StatusList({ kind }: { kind: keyof typeof LISTS }) {
  const router = useRouter();
  const list = LISTS[kind];
  const counts = useQuery({
    queryKey: ["queue", "counts"],
    queryFn: () => api<StatusCounts>("applications/counts"),
    enabled: kind === "pending",
  });
  const tabs = useMemo(
    () =>
      kind === "pending"
        ? {
            filter: "status",
            options: [
              {
                value: PENDING,
                label: "All pending",
                count: PENDING.split(",").reduce((n, status) => n + (counts.data?.by_status[status] ?? 0), 0),
              },
              ...STATUS_OPTIONS.filter((option) => PENDING.includes(option.value)).map((option) => ({
                value: option.value,
                label: option.label.replace("Pending ", "With "),
                count: counts.data?.by_status[option.value],
              })),
            ],
          }
        : undefined,
    [kind, counts.data],
  );

  return (
    <>
      <PageHeader title={list.title} description={list.description} />
      <DataTable
        id={`applications-${kind}`}
        endpoint="applications"
        columns={[...list.columns]}
        rowKey={(row) => row.id}
        baseParams={kind === "pending" ? undefined : { status: list.status }}
        defaultFilters={kind === "pending" ? { status: PENDING } : undefined}
        tabs={tabs}
        defaultOrdering={list.ordering}
        searchPlaceholder="Form, name, MPP or member code"
        exportName={`${kind}-members`}
        onRowClick={(row) => router.push(open(row))}
        filters={
          kind === "approved"
            ? ({ filters, setFilters }) => (
                <DateRangePicker
                  from={filters.approved_from}
                  to={filters.approved_to}
                  onChange={(range) => setFilters({ ...filters, approved_from: range.from, approved_to: range.to })}
                  placeholder="Approved any day"
                  className="[&>button]:h-9"
                  aria-label="Approved between"
                />
              )
            : undefined
        }
        above={
          kind === "approved"
            ? (filters) => (
                <p className="text-sm text-muted-foreground">
                  Need the forms printed?{" "}
                  <Link
                    className="font-medium text-primary underline-offset-4 hover:underline"
                    href={`/applications/pdf?${new URLSearchParams(
                      Object.entries({ approved_from: filters.approved_from, approved_to: filters.approved_to }).filter(
                        (entry): entry is [string, string] => !!entry[1],
                      ),
                    )}`}
                  >
                    Make PDFs of these in the PDF Center
                  </Link>
                </p>
              )
            : undefined
        }
        empty={<EmptyState icon={FileText} title="Nothing here" description={list.empty} />}
      />
    </>
  );
}

/** One approval stage, oldest first, so nobody waits too long. */
export function ApprovalQueue({
  title,
  description,
  status,
}: {
  title: string;
  description: string;
  status: string;
}) {
  const router = useRouter();
  const client = useQueryClient();
  const [approving, setApproving] = useState<ApplicationSummary | null>(null);

  const approve = async (row: ApplicationSummary) => {
    try {
      await decideApproved(row);
      toast.success(`Your steps on ${row.form_number} are approved.`);
      client.invalidateQueries({ queryKey: ["queue"] });
    } catch (error) {
      toast.error(error instanceof ApiError ? error.summary : "Could not approve this form.");
    }
  };

  return (
    <>
      <PageHeader title={title} description={description} />
      <DoubleConfirm
        open={!!approving}
        onOpenChange={(open) => !open && setApproving(null)}
        title={`Approve ${approving?.form_number ?? ""}?`}
        description={`${approving?.applicant_name ?? ""}. This approves all your open steps on the form, without you opening it.`}
        finalTitle="Are you sure?"
        finalDescription="Your name goes on each step. This can't be undone."
        action="Yes, approve"
        onConfirm={() => approving && approve(approving)}
      />
      <DataTable
        id={`queue-${status}`}
        endpoint="applications"
        baseParams={{ status }}
        columns={COLUMNS.filter((column) => column.id !== "status")}
        rowKey={(row) => row.id}
        defaultOrdering="waiting_since"
        searchPlaceholder="Form, name or MPP"
        exportName={`queue-${status}`}
        onRowClick={(row) => router.push(open(row))}
        bulkActions={(rows, clear) => (
          <BulkAction
            rows={rows}
            label="Approve"
            icon={Check}
            done="approved"
            clear={clear}
            run={decideApproved}
            confirm={{
              title: `Approve ${rows.length} ${rows.length === 1 ? "form" : "forms"}?`,
              description:
                "This approves all your open steps on each form, without you opening them. A form moves on only when its stage is complete, and any that can't stay here.",
            }}
          />
        )}
        rowKeys={{
          onApprove: setApproving,
          // A rejection needs a reason and marked fields, so it happens on the form.
          onDismiss: (row) => router.push(`${open(row)}?reject=1`),
        }}
        above={() => (
          <p className="hidden items-center gap-1.5 text-xs text-muted-foreground lg:flex">
            <Kbd>J</Kbd>
            <Kbd>K</Kbd> move <Kbd className="ml-2">Enter</Kbd> read the form
            <Kbd className="ml-2">A</Kbd> approve <Kbd className="ml-2">D</Kbd> reject
          </p>
        )}
        empty={
          <EmptyState
            icon={CheckCircle2}
            title="All clear"
            description="No forms are waiting for you. New ones appear here and in your notifications."
          />
        }
      />
    </>
  );
}
