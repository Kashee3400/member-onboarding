"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MapPin, Plus } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { CheckRow } from "@/components/admin/check-row";
import { FormDialog } from "@/components/admin/form-dialog";
import { DataTable, FilterSelect, type Column } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { MasterSelect, type MasterKind } from "@/components/common/master-select";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCan } from "@/hooks/use-session";
import { api } from "@/lib/api/client";
import type { PlaceMaster } from "@/lib/types";

type Tab = "states" | "districts" | "tehsils" | "villages" | "hamlets";
type Row = PlaceMaster & Partial<Record<"state" | "district" | "tehsil" | "village", string>>;

/** Each level and the one above it, which a row must name. */
const LEVELS: {
  key: Tab;
  label: string;
  one: string;
  parent?: { field: "state" | "district" | "tehsil" | "village"; kind: MasterKind; label: string };
  code: { pattern?: string; maxLength: number; help: string };
}[] = [
  {
    key: "states",
    label: "States",
    one: "State",
    code: { pattern: "\\d{2}", maxLength: 2, help: "2 digits, like 09. Every member code starts with it." },
  },
  {
    key: "districts",
    label: "Districts",
    one: "District",
    parent: { field: "state", kind: "states", label: "State" },
    code: { maxLength: 10, help: "As in the ERP." },
  },
  {
    key: "tehsils",
    label: "Tehsils",
    one: "Tehsil",
    parent: { field: "district", kind: "districts", label: "District" },
    code: { maxLength: 10, help: "As in the ERP." },
  },
  {
    key: "villages",
    label: "Villages",
    one: "Village",
    parent: { field: "tehsil", kind: "tehsils", label: "Tehsil" },
    code: { pattern: "\\d{8}", maxLength: 8, help: "8 digits. The middle of every member code." },
  },
  {
    key: "hamlets",
    label: "Hamlets",
    one: "Hamlet",
    parent: { field: "village", kind: "villages", label: "Village" },
    code: { pattern: "\\d{2}", maxLength: 2, help: "2 digits, numbered within the village." },
  },
];

function LocationForm({ level, item, onClose }: { level: (typeof LEVELS)[number]; item: Row | null; onClose: () => void }) {
  const client = useQueryClient();
  const [parent, setParent] = useState((level.parent && item?.[level.parent.field]) ?? "");
  const [active, setActive] = useState(item?.is_active ?? true);

  const save = useMutation({
    mutationFn: (body: object) =>
      item
        ? api(`hierarchy/${level.key}/${item.id}`, { method: "PATCH", body })
        : api(`hierarchy/${level.key}`, { method: "POST", body }),
    onSuccess: () => {
      // MPPs under an edited place change with it.
      client.invalidateQueries({ queryKey: ["hierarchy"] });
      toast.success(`${level.one} saved.`);
      onClose();
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    save.mutate({ ...fields, is_active: active, ...(level.parent ? { [level.parent.field]: parent } : {}) });
  };

  return (
    <FormDialog
      title={item ? `${level.one} ${item.code}` : `Add ${level.one.toLowerCase()}`}
      description={item ? "The MPPs here, and forms not yet submitted, follow the change." : undefined}
      onClose={onClose}
      onSubmit={submit}
      error={save.error}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending || (!!level.parent && !parent)}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      {level.parent ? (
        <Field label={level.parent.label}>
          <MasterSelect
            kind={level.parent.kind}
            placeholder={`Choose a ${level.parent.label.toLowerCase()}`}
            clearable={false}
            value={parent}
            onChange={setParent}
          />
        </Field>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-[10rem_minmax(0,1fr)]">
        <Field label="Code" htmlFor="code" help={level.code.help}>
          <Input
            id="code"
            name="code"
            required
            pattern={level.code.pattern}
            maxLength={level.code.maxLength}
            defaultValue={item?.code}
            className="font-mono"
            autoFocus
          />
        </Field>
        <Field label="Name" htmlFor="name">
          <Input id="name" name="name" required defaultValue={item?.name} />
        </Field>
      </div>
      <Field label="Name in Hindi" htmlFor="name_hi" optional>
        <Input id="name_hi" name="name_hi" lang="hi" defaultValue={item?.name_hi} />
      </Field>
      <CheckRow
        className="-mx-2"
        label="Active"
        hint="Inactive places stay on the MPPs and forms that have them."
        checked={active}
        onChange={setActive}
      />
    </FormDialog>
  );
}

const COLUMNS = (parent?: string): Column<Row>[] => [
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
    id: "name_hi",
    header: "Hindi",
    hideBelow: "md",
    csv: (row) => row.name_hi,
    cell: (row) => <span lang="hi">{row.name_hi || "—"}</span>,
  },
  ...(parent
    ? [
        {
          id: "parent",
          header: parent,
          csv: (row: Row) => row.parent_label ?? "",
          cell: (row: Row) => <span className="text-muted-foreground">{row.parent_label}</span>,
        },
      ]
    : []),
  {
    id: "status",
    header: "Status",
    csv: (row) => (row.is_active ? "Active" : "Inactive"),
    cell: (row) => <StatusBadge status={row.is_active ? "active" : "inactive"} />,
  },
];

export default function LocationsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const level = LEVELS.find((entry) => entry.key === params.get("tab")) ?? LEVELS[0];
  const canManage = useCan("hierarchy.manage");
  const [editing, setEditing] = useState<{ item: Row | null } | null>(null);

  return (
    <>
      <PageHeader
        title="Locations"
        description="State, district, tehsil, village and hamlet. An MPP's place fills its forms, and facilitators can't change it."
        actions={
          canManage ? (
            <Button onClick={() => setEditing({ item: null })}>
              <Plus /> Add {level.one.toLowerCase()}
            </Button>
          ) : null
        }
      />

      <Tabs value={level.key} onValueChange={(next) => router.replace(`${pathname}?tab=${next}`, { scroll: false })}>
        <TabsList>
          {LEVELS.map((entry) => (
            <TabsTrigger key={entry.key} value={entry.key}>
              {entry.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <DataTable<Row>
        key={level.key}
        id={`locations-${level.key}`}
        endpoint={`hierarchy/${level.key}`}
        columns={COLUMNS(level.parent?.label)}
        rowKey={(row) => row.id}
        searchPlaceholder="Search by code or name"
        defaultOrdering="code"
        exportName={level.key}
        onRowClick={canManage ? (item) => setEditing({ item }) : undefined}
        empty={
          <EmptyState
            icon={MapPin}
            title={`No ${level.label.toLowerCase()} found`}
            description="Try another search, or import MPPs with their place under Hierarchy."
          />
        }
        filters={({ filters, setFilter }) => (
          <>
            {level.parent ? (
              <MasterSelect
                kind={level.parent.kind}
                className="w-full sm:w-64"
                placeholder={`All ${level.parent.label.toLowerCase()}s`}
                value={filters[level.parent.field] ?? ""}
                onChange={(value) => setFilter(level.parent!.field, value || undefined)}
              />
            ) : null}
            <FilterSelect
              label="Status"
              value={filters.is_active}
              onChange={(value) => setFilter("is_active", value)}
              options={{ true: "Active", false: "Inactive" }}
            />
          </>
        )}
      />

      {editing ? <LocationForm level={level} item={editing.item} onClose={() => setEditing(null)} /> : null}
    </>
  );
}
