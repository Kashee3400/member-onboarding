"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Route, UserMinus } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Confirm } from "@/components/admin/confirm";
import { messageOf } from "@/components/admin/feedback";
import { FormDialog } from "@/components/admin/form-dialog";
import { MccCovers } from "@/components/admin/mcc-covers";
import { DataTable, type Column } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { EmptyState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { useCan } from "@/hooks/use-session";
import { api, type Page } from "@/lib/api/client";
import { date } from "@/lib/format";
import type { Mcc, MccAssignment, Role, Staff } from "@/lib/types";

const APPROVALS = ["applications.approve_am", "applications.approve_cs", "applications.approve_finance"];

function ManageMcc({ mcc, onClose }: { mcc: Mcc; onClose: () => void }) {
  const client = useQueryClient();
  const canAssign = useCan("mpp.assign");
  const [membership, setMembership] = useState("");
  const url = `hierarchy/mccs/${mcc.id}/area-manager`;

  const history = useQuery({
    queryKey: ["mcc-area-managers", mcc.id],
    queryFn: () => api<MccAssignment[]>(url),
  });
  const staff = useQuery({
    queryKey: ["staff", "approvers"],
    queryFn: () => api<Page<Staff>>("staff", { query: { page_size: 500, is_active: true } }),
    enabled: canAssign,
  });
  const roles = useQuery({
    queryKey: ["roles", "all"],
    queryFn: () => api<Page<Role>>("roles", { query: { page_size: 500 } }),
    enabled: canAssign,
  });
  const approving = new Set(
    (roles.data?.results ?? [])
      .filter((role) => role.permissions.some((code) => APPROVALS.includes(code)))
      .map((role) => role.code),
  );
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["queue"] });
    client.invalidateQueries({ queryKey: ["mcc-area-managers", mcc.id] });
  };

  const add = useMutation({
    mutationFn: () => api(url, { method: "POST", body: { membership } }),
    onSuccess: () => {
      refresh();
      setMembership("");
      toast.success("Added to this MCC.");
    },
    onError: (error) => toast.error(messageOf(error)),
  });
  const end = useMutation({
    mutationFn: (person: string) => api(`${url}/${person}/end`, { method: "POST" }),
    onSuccess: () => {
      refresh();
      toast.success("Removed from this MCC.");
    },
    onError: (error) => toast.error(messageOf(error)),
  });

  const rows = history.data ?? [];
  const current = rows.filter((row) => !row.ended_at);
  const past = rows.filter((row) => row.ended_at);
  const holding = new Set(current.map((row) => row.membership));
  const eligible = (staff.data?.results ?? []).filter(
    (person) => person.roles.some((role) => approving.has(role.code)) && !holding.has(person.id),
  );

  return (
    <FormDialog
      title={`${mcc.code} ${mcc.name}`}
      description={`${mcc.mpp_count} active MPPs. Everyone here works all of them, in their own role.`}
      onClose={onClose}
      footer={
        <Button type="button" variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
    >
      {canAssign ? (
        <Field label="Add someone">
          <div className="flex gap-2">
            <Listbox
              aria-label="Add someone"
              placeholder={eligible.length ? "Choose a person" : "Nobody else approves forms"}
              value={membership}
              onChange={setMembership}
              items={eligible.map((person) => ({
                value: person.id,
                label: `${person.full_name || person.email} · ${person.roles.map((role) => role.name).join(", ")}`,
              }))}
            />
            <Button type="button" disabled={!membership || add.isPending} onClick={() => add.mutate()}>
              Add
            </Button>
          </div>
        </Field>
      ) : null}

      <section className="space-y-1.5">
        <h3 className="text-sm font-medium">Working this MCC now</h3>
        {current.length ? (
          <ul className="divide-y border">
            {current.map((row) => (
              <li key={row.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block truncate font-medium">{row.person}</span>
                  <span className="block truncate text-xs text-muted-foreground">{row.roles.join(", ")}</span>
                  <span className="text-xs text-muted-foreground">Since {date(row.started_at)}</span>
                </span>
                {canAssign ? (
                  <Confirm
                    title={`Remove ${row.person}?`}
                    description="They lose access to this MCC's MPPs at once, unless they hold them another way."
                    action="Remove"
                    onConfirm={() => end.mutate(row.membership)}
                    trigger={
                      <Button type="button" variant="ghost" size="icon-sm" aria-label={`Remove ${row.person}`}>
                        <UserMinus />
                      </Button>
                    }
                  />
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="border border-dashed px-3 py-4 text-center text-sm text-muted-foreground">
            Nobody yet. Forms here reach only those who see every MCC.
          </p>
        )}
      </section>

      {past.length ? (
        <section className="space-y-1.5">
          <h3 className="text-sm font-medium">Earlier</h3>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {past.map((row) => (
              <li key={row.id}>
                {row.person}, {date(row.started_at)} to {date(row.ended_at)}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </FormDialog>
  );
}

/**
 * People who approve hold whole MCCs: an Area Manager, or one of a CS or Finance team.
 * Someone with MCCs works only those; a head with none keeps every MCC. Leave cover
 * lends one person's MCCs to a colleague for some days.
 */
export function MccAssignments() {
  const [open, setOpen] = useState<Mcc | null>(null);

  const columns = useMemo<Column<Mcc>[]>(
    () => [
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
        header: "MCC",
        sortKey: "name",
        csv: (row) => row.name,
        cell: (row) => <span className="font-medium">{row.name}</span>,
      },
      {
        id: "mpps",
        header: "Active MPPs",
        align: "right",
        csv: (row) => row.mpp_count,
        cell: (row) => <span className="tabular-nums">{row.mpp_count}</span>,
      },
      {
        id: "allotted",
        header: "Working this MCC",
        csv: (row) => row.allotted.map((person) => `${person.name} (${person.roles.join(", ")})`).join("; "),
        cell: (row) =>
          row.allotted.length ? (
            <span className="flex flex-wrap gap-x-3 gap-y-1">
              {row.allotted.map((person) => (
                <span key={person.name}>
                  {person.name} <span className="text-xs text-muted-foreground">{person.roles.join(", ")}</span>
                </span>
              ))}
            </span>
          ) : (
            <span className="text-amber-700 dark:text-amber-300">Nobody yet</span>
          ),
      },
    ],
    [],
  );

  return (
    <>
      <MccCovers />
      <DataTable<Mcc>
        id="assignment-mccs"
        endpoint="hierarchy/mccs"
        columns={columns}
        rowKey={(row) => row.id}
        searchPlaceholder="Search by code or name"
        defaultOrdering="code"
        exportName="mcc-area-managers"
        onRowClick={setOpen}
        empty={<EmptyState icon={Route} title="No MCCs found" description="Add them under Plants, MCCs & MPPs first." />}
      />
      {open ? <ManageMcc mcc={open} onClose={() => setOpen(null)} /> : null}
    </>
  );
}
