"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Route } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Confirm } from "@/components/admin/confirm";
import { FormError, messageOf } from "@/components/admin/feedback";
import { MccAssignments } from "@/components/admin/mcc-assignments";
import { SettingsCard } from "@/components/admin/settings-form";
import { DataTable, type Column } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { StatusTabs } from "@/components/common/status-tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useCan } from "@/hooks/use-session";
import { api, type Page } from "@/lib/api/client";
import { date } from "@/lib/format";
import type { Assignment, Mpp, OpenWork, Staff } from "@/lib/types";

const RESPONSIBILITIES = [
  { value: "facilitator", label: "Facilitator", role: "facilitator" },
  { value: "area_manager", label: "Area Manager", role: "area_manager" },
] as const;

const labelOf = (value: string) => RESPONSIBILITIES.find((item) => item.value === value)?.label ?? value;

function MppDetail({ mppId, onBack }: { mppId: string; onBack: () => void }) {
  const client = useQueryClient();
  const canAssign = useCan("mpp.assign");
  const [responsibility, setResponsibility] = useState("facilitator");
  const [membership, setMembership] = useState("");

  const mpp = useQuery({
    queryKey: ["hierarchy", "mpp", mppId],
    queryFn: () => api<Mpp>(`hierarchy/mpps/${mppId}`),
  });
  const staff = useQuery({
    queryKey: ["staff", "all"],
    queryFn: () => api<Page<Staff>>("staff", { query: { page_size: 5000, is_active: "true" } }),
  });
  const openWork = useQuery({
    queryKey: ["open-work", mppId],
    queryFn: () => api<OpenWork>(`hierarchy/mpps/${mppId}/open-work`),
  });
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["queue"] });
    client.invalidateQueries({ queryKey: ["open-work", mppId] });
  };
  const assign = useMutation({
    mutationFn: (body: object) => api(`hierarchy/mpps/${mppId}/assignments`, { method: "POST", body }),
    onSuccess: () => {
      setMembership("");
      refresh();
      toast.success("Assigned. Access moved straight away.");
    },
  });
  const end = useMutation({
    mutationFn: (value: string) => api(`hierarchy/mpps/${mppId}/assignments/${value}`, { method: "DELETE" }),
    onSuccess: () => {
      refresh();
      toast.success("Assignment ended.");
    },
    onError: (error) => toast.error(messageOf(error)),
  });

  const columns = useMemo<Column<Assignment>[]>(
    () => [
      {
        id: "person",
        header: "Person",
        required: true,
        sortKey: "person",
        csv: (row) => row.person,
        cell: (row) => <span className="font-medium break-all">{row.person}</span>,
      },
      {
        id: "responsibility",
        header: "Responsibility",
        sortKey: "responsibility",
        csv: (row) => labelOf(row.responsibility),
        cell: (row) => labelOf(row.responsibility),
      },
      {
        id: "from",
        header: "From",
        sortKey: "started_at",
        sortValue: (row) => row.started_at,
        csv: (row) => date(row.started_at),
        cell: (row) => <span className="tabular-nums">{date(row.started_at)}</span>,
      },
      {
        id: "until",
        header: "Until",
        sortKey: "ended_at",
        sortValue: (row) => row.ended_at,
        csv: (row) => (row.ended_at ? date(row.ended_at) : "Current"),
        cell: (row) =>
          row.ended_at ? (
            <span className="tabular-nums">{date(row.ended_at)}</span>
          ) : (
            <StatusBadge status="active" label="Current" />
          ),
      },
      {
        id: "actions",
        header: "",
        required: true,
        align: "right",
        cell: (row) =>
          !row.ended_at && canAssign ? (
            <Confirm
              title="End this assignment?"
              description={`${row.person} loses access to this MPP straight away, and stays in the history.`}
              action="End assignment"
              onConfirm={() => end.mutate(row.responsibility)}
              trigger={
                <Button variant="destructive" size="sm" disabled={end.isPending}>
                  End
                </Button>
              }
            />
          ) : null,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canAssign, end.isPending],
  );

  const role = RESPONSIBILITIES.find((item) => item.value === responsibility)?.role;
  const eligible = (staff.data?.results ?? []).filter(
    (person) => person.is_active && person.roles.some((item) => item.code === role),
  );
  const drafts = openWork.data?.drafts ?? [];

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    assign.mutate({ membership, responsibility });
  };

  if (mpp.error) return <ErrorState error={mpp.error} onRetry={() => mpp.refetch()} />;
  if (!mpp.data) return <ListSkeleton />;

  return (
    <>
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Button variant="ghost" size="icon-sm" aria-label="Back to all MPPs" onClick={onBack}>
              <ArrowLeft />
            </Button>
            {mpp.data.code} {mpp.data.name}
          </span>
        }
        description="Forms belong to the MPP, so access follows whoever holds it."
      />

      {drafts.length ? (
        <Alert>
          <AlertTriangle className="text-amber-600" />
          <AlertTitle>Open forms move with this MPP</AlertTitle>
          <AlertDescription>
            <ul className="list-inside list-disc">
              {drafts.map((draft) => (
                <li key={draft.id}>
                  {draft.applicant_name || "Unnamed"}, last edited by {draft.last_edited_by_name}
                </li>
              ))}
            </ul>
            <p className="mt-1">
              Ask the current facilitator to open the app online first: forms that never left a phone do not appear
              here.
            </p>
          </AlertDescription>
        </Alert>
      ) : null}

      {canAssign ? (
        <SettingsCard
          title="Assign someone"
          description="This moves the MPP and its forms at once. The previous person loses access and stays in the history."
        >
          <form onSubmit={submit} className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
            <Field label="Responsibility">
              <Listbox
                aria-label="Responsibility"
                value={responsibility}
                onChange={(value) => {
                  setResponsibility(value);
                  setMembership("");
                }}
                items={RESPONSIBILITIES.map(({ value, label }) => ({ value, label }))}
              />
            </Field>
            <Field label="Assign to">
              <Listbox
                aria-label="Assign to"
                placeholder={eligible.length ? "Choose a person" : "Nobody holds this role"}
                value={membership}
                onChange={setMembership}
                items={eligible.map((person) => ({ value: person.id, label: person.full_name || person.email }))}
              />
            </Field>
            <Button type="submit" className="h-9" disabled={assign.isPending || !membership}>
              {assign.isPending ? "Assigning…" : "Assign"}
            </Button>
          </form>
          <div className="mt-3 empty:hidden">
            <FormError error={assign.error} />
          </div>
        </SettingsCard>
      ) : null}

      <div className="space-y-2">
        <h2 className="font-medium">History</h2>
        <DataTable<Assignment>
          key={mppId}
          id={`assignments-${mppId}`}
          endpoint={`hierarchy/mpps/${mppId}/assignments`}
          columns={columns}
          rowKey={(row) => row.id}
          searchPlaceholder="Search history"
          exportName={`assignments-${mpp.data.code}`}
          empty={<EmptyState icon={Route} title="Nobody has been assigned to this MPP yet" />}
        />
      </div>
    </>
  );
}

const MPP_COLUMNS: Column<Mpp>[] = [
  {
    id: "code",
    header: "Code",
    required: true,
    sortKey: "code",
    csv: (row) => row.code,
    cell: (row) => <span className="font-mono text-xs tabular-nums">{row.code}</span>,
  },
  {
    id: "name",
    header: "Name",
    sortKey: "name",
    csv: (row) => row.name,
    cell: (row) => <span className="font-medium">{row.name}</span>,
  },
  {
    id: "village",
    header: "Village code",
    sortKey: "village_code",
    csv: (row) => row.village_code,
    cell: (row) => <span className="font-mono text-xs tabular-nums">{row.village_code}</span>,
  },
  {
    id: "status",
    header: "Status",
    csv: (row) => (row.is_active ? "Active" : "Inactive"),
    cell: (row) => <StatusBadge status={row.is_active ? "active" : "inactive"} />,
  },
];

const TABS = [
  { value: "mccs", label: "People by MCC" },
  { value: "mpps", label: "MPPs" },
] as const;

export default function AssignmentsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const mppId = params.get("mpp");
  const tab = params.get("tab") === "mpps" ? "mpps" : "mccs";

  if (mppId) return <MppDetail key={mppId} mppId={mppId} onBack={() => router.push(`${pathname}?tab=mpps`)} />;

  return (
    <>
      <PageHeader
        title="Assignments"
        description="Approvers hold MCCs and work every MPP under them. Facilitators hold single MPPs."
      />
      <StatusTabs value={tab} onChange={(value) => router.push(`${pathname}?tab=${value}`)} options={[...TABS]} />
      {tab === "mccs" ? (
        <MccAssignments />
      ) : (
        <DataTable<Mpp>
          id="assignment-mpps"
          endpoint="hierarchy/mpps"
          columns={MPP_COLUMNS}
          rowKey={(row) => row.id}
          searchPlaceholder="Search by code, name or village code"
          defaultOrdering="code"
          exportName="mpps"
          onRowClick={(mpp) => router.push(`${pathname}?mpp=${mpp.id}`)}
          empty={
            <EmptyState icon={Route} title="No MPPs found" description="Add MPPs under Plants, MCCs & MPPs first." />
          }
        />
      )}
    </>
  );
}
