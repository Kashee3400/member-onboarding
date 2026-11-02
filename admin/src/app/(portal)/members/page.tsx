"use client";

import { UserRoundCheck } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { CopyButton } from "@/components/applications/copy-button";
import { DataTable, FilterSelect, type Column } from "@/components/common/data-table";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { StatusTabs } from "@/components/common/status-tabs";
import { date } from "@/lib/format";
import type { LegacyMember, Member } from "@/lib/types";

const COLUMNS: Column<Member>[] = [
  {
    id: "code",
    header: "Member code",
    sortKey: "tr_code",
    required: true,
    csv: (row) => row.tr_code,
    cell: (row) => (
      <span className="inline-flex items-center gap-1">
        <span className="font-mono text-[13px] tabular-nums">{row.tr_code}</span>
        <CopyButton value={row.tr_code} label="Copy member code" />
      </span>
    ),
  },
  {
    id: "name",
    header: "Name",
    sortKey: "full_name",
    required: true,
    csv: (row) => row.full_name,
    cell: (row) => <span className="font-medium">{row.full_name}</span>,
  },
  {
    id: "mobile",
    header: "Mobile",
    hideBelow: "md",
    csv: (row) => row.mobile,
    cell: (row) => <span className="tabular-nums">{row.mobile}</span>,
  },
  { id: "mpp", header: "MPP", csv: (row) => row.mpp_code, cell: (row) => <span className="tabular-nums">{row.mpp_code}</span> },
  {
    id: "joined",
    header: "Joined",
    sortKey: "joined_at",
    hideBelow: "sm",
    csv: (row) => date(row.joined_at),
    cell: (row) => <span className="text-muted-foreground">{date(row.joined_at)}</span>,
  },
];

const EXISTING_COLUMNS: Column<LegacyMember>[] = [
  {
    id: "code",
    header: "Member code",
    sortKey: "tr_code",
    required: true,
    csv: (row) => row.tr_code,
    cell: (row) => (
      <span className="inline-flex items-center gap-1">
        <span className="font-mono text-[13px] tabular-nums">{row.tr_code}</span>
        <CopyButton value={row.tr_code} label="Copy member code" />
      </span>
    ),
  },
  {
    id: "name",
    header: "Name",
    sortKey: "full_name",
    required: true,
    csv: (row) => row.full_name,
    cell: (row) => <span className="font-medium">{row.full_name || "—"}</span>,
  },
  {
    id: "mpp",
    header: "MPP",
    csv: (row) => `${row.mpp_code} ${row.mpp_name}`,
    cell: (row) =>
      row.mpp_code ? (
        <span>
          <span className="tabular-nums">{row.mpp_code}</span>{" "}
          <span className="text-muted-foreground">{row.mpp_name}</span>
        </span>
      ) : (
        <span className="text-muted-foreground">Not in the MPP list</span>
      ),
  },
  {
    id: "status",
    header: "Status",
    csv: (row) => (row.is_active ? "Active" : "Inactive"),
    cell: (row) => <StatusBadge status={row.is_active ? "active" : "inactive"} />,
  },
];

const TABS = [
  { value: "new", label: "Joined here" },
  { value: "existing", label: "Existing members" },
] as const;

function Members() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = params.get("tab") === "existing" ? "existing" : "new";

  return (
    <>
      <StatusTabs value={tab} onChange={(value) => router.replace(`${pathname}?tab=${value}`)} options={[...TABS]} />
      {tab === "existing" ? (
        <DataTable
          key="existing"
          id="legacy-members"
          endpoint="legacy-members"
          columns={EXISTING_COLUMNS}
          rowKey={(row) => row.id}
          defaultOrdering="tr_code"
          searchPlaceholder="Member code, name or MPP"
          exportName="existing-members"
          filters={({ filters, setFilter }) => (
            <FilterSelect
              label="Status"
              value={filters.is_active}
              onChange={(value) => setFilter("is_active", value)}
              options={{ true: "Active", false: "Inactive" }}
            />
          )}
          empty={
            <EmptyState
              icon={UserRoundCheck}
              title="No existing members"
              description="Members from the ERP appear here once they have been imported."
            />
          }
        />
      ) : (
        <DataTable
          key="new"
          id="members"
          endpoint="members"
          columns={COLUMNS}
          rowKey={(row) => row.id}
          searchPlaceholder="Member code, name or MPP"
          exportName="members"
          bulkActions={() => <span className="text-muted-foreground">Use Export to download these rows.</span>}
          empty={
            <EmptyState
              icon={UserRoundCheck}
              title="No members yet"
              description="A member appears here when a form gets its final approval."
            />
          }
        />
      )}
    </>
  );
}

export default function MembersPage() {
  return (
    <>
      <PageHeader title="Members" description="Members who joined here, and everyone from before this system." />
      <Suspense>
        <Members />
      </Suspense>
    </>
  );
}
