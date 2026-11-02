"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Info, MapPin } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

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

/** Each level and the one above it. */
const LEVELS: {
  key: Tab;
  label: string;
  one: string;
  parent?: { field: "state" | "district" | "tehsil" | "village"; kind: MasterKind; label: string };
}[] = [
  { key: "states", label: "States", one: "State" },
  { key: "districts", label: "Districts", one: "District", parent: { field: "state", kind: "states", label: "State" } },
  { key: "tehsils", label: "Tehsils", one: "Tehsil", parent: { field: "district", kind: "districts", label: "District" } },
  { key: "villages", label: "Villages", one: "Village", parent: { field: "tehsil", kind: "tehsils", label: "Tehsil" } },
  { key: "hamlets", label: "Hamlets", one: "Hamlet", parent: { field: "village", kind: "villages", label: "Village" } },
];

/**
 * The ERP has tehsil codes but no names, so a tehsil's name is the one thing set here.
 * Everything else comes from the ERP through the masters import.
 */
function TehsilName({ item, onClose }: { item: Row; onClose: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: object) => api(`hierarchy/tehsils/${item.id}`, { method: "PATCH", body }),
    onSuccess: () => {
      // The MPPs in this tehsil, and forms not yet submitted, show the new name.
      client.invalidateQueries({ queryKey: ["hierarchy"] });
      toast.success("Tehsil name saved.");
      onClose();
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    save.mutate(Object.fromEntries(new FormData(event.currentTarget)));
  };

  return (
    <FormDialog
      title={`Tehsil ${item.code}`}
      description={`${item.parent_label ?? ""}. The code comes from the ERP; only the name is set here.`}
      onClose={onClose}
      onSubmit={submit}
      error={save.error}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <Field label="Name" htmlFor="name">
        <Input id="name" name="name" required defaultValue={item.name === item.code ? "" : item.name} autoFocus />
      </Field>
      <Field label="Name in Hindi" htmlFor="name_hi" optional>
        <Input id="name_hi" name="name_hi" lang="hi" defaultValue={item.name_hi} />
      </Field>
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
  const [naming, setNaming] = useState<Row | null>(null);
  const nameable = canManage && level.key === "tehsils";

  return (
    <>
      <PageHeader
        title="Locations"
        description="State, district, tehsil, village and hamlet, as in the ERP. They come in through the masters import under Hierarchy, and fill each MPP's forms."
      />
      <p className="flex items-start gap-2 border border-primary/20 bg-primary/5 px-3 py-2 text-sm">
        <Info className="mt-0.5 size-4 shrink-0 text-primary" />
        <span>
          Read-only: a change here would drift from the ERP and the member codes built from it. The one exception is a
          tehsil&apos;s name, which the ERP does not keep. Open a tehsil to name it.
        </span>
      </p>

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
        onRowClick={nameable ? setNaming : undefined}
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

      {naming ? <TehsilName item={naming} onClose={() => setNaming(null)} /> : null}
    </>
  );
}
