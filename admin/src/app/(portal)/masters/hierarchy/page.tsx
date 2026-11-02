"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Network, Plus, Upload, XCircle } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { CheckRow } from "@/components/admin/check-row";
import { FormError } from "@/components/admin/feedback";
import { FileDrop } from "@/components/admin/file-drop";
import { FormDialog } from "@/components/admin/form-dialog";
import { DataTable, FilterSelect, type Column } from "@/components/common/data-table";
import { Field, FormSection } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { MasterSelect } from "@/components/common/master-select";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCan } from "@/hooks/use-session";
import { api, type Page } from "@/lib/api/client";
import type { Bmc, Mcc, Mpp, MppImportResult, Plant, Route } from "@/lib/types";

type Tab = "plants" | "mccs" | "bmcs" | "routes" | "mpps";
type Master = Plant | Mcc | Bmc | Route | Mpp;

const TABS: { key: Tab; label: string; one: string }[] = [
  { key: "plants", label: "Plants", one: "Plant" },
  { key: "mccs", label: "MCCs", one: "MCC" },
  { key: "bmcs", label: "BMCs", one: "BMC" },
  { key: "routes", label: "Routes", one: "Route" },
  { key: "mpps", label: "MPPs", one: "MPP" },
];
const IMPORT_COLUMNS = [
  "plant_code",
  "plant_name",
  "mcc_code",
  "mcc_name",
  "mpp_code",
  "mpp_internal_code",
  "mpp_name",
  "village_code",
  "state_code (optional)",
  "hamlet_code (optional)",
  "bmc_code (optional)",
  "bmc_name (optional)",
  "route_code (optional)",
  "route_name (optional)",
  "village_name (optional)",
  "state_name (optional)",
  "district_code (optional)",
  "district_name (optional)",
  "tehsil_code (optional)",
  "tehsil_name (optional)",
  "hamlet_name (optional)",
  "pincode (optional)",
  "post_office (optional)",
];
const MB = 1024 * 1024;

const useMasters = <T,>(tab: Tab) =>
  useQuery({
    queryKey: ["hierarchy", tab],
    queryFn: () => api<Page<T>>(`hierarchy/${tab}`, { query: { page_size: 5000, ordering: "code" } }),
  });

const refreshKeys = (client: ReturnType<typeof useQueryClient>) => {
  client.invalidateQueries({ queryKey: ["queue"] });
  client.invalidateQueries({ queryKey: ["hierarchy"] });
};

function MasterForm({
  tab,
  item,
  plants,
  bmcs,
  onClose,
}: {
  tab: Tab;
  item: Master | null;
  plants: Plant[];
  bmcs: Bmc[];
  onClose: () => void;
}) {
  const client = useQueryClient();
  const one = TABS.find((entry) => entry.key === tab)!.one;
  const mpp = tab === "mpps" ? (item as Mpp | null) : null;
  const mcc = tab === "mccs" ? (item as Mcc | null) : null;
  const bmc = tab === "bmcs" ? (item as Bmc | null) : null;
  const route = tab === "routes" ? (item as Route | null) : null;
  const [parent, setParent] = useState(mpp?.mcc ?? mcc?.plant ?? bmc?.mcc ?? route?.bmc ?? "");
  const [routeId, setRouteId] = useState(mpp?.route ?? "");
  // Linked to a village by the ERP import, its codes come from there and are not typed.
  const linked = !!mpp?.village;
  const [active, setActive] = useState(item?.is_active ?? true);

  const save = useMutation({
    mutationFn: (body: object) =>
      item
        ? api(`hierarchy/${tab}/${item.id}`, { method: "PATCH", body })
        : api(`hierarchy/${tab}`, { method: "POST", body }),
    onSuccess: () => {
      refreshKeys(client);
      toast.success(`${one} saved.`);
      onClose();
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    save.mutate({
      ...fields,
      is_active: active,
      ...(tab === "mccs" ? { plant: parent } : {}),
      ...(tab === "bmcs" ? { mcc: parent } : {}),
      ...(tab === "routes" ? { bmc: parent } : {}),
      ...(tab === "mpps"
        ? { mcc: parent, route: routeId || null }
        : {}),
    });
  };

  return (
    <FormDialog
      title={item ? `${one} ${item.code}` : `Add ${one}`}
      onClose={onClose}
      onSubmit={submit}
      error={save.error}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending || (tab !== "plants" && !parent)}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      {tab === "mccs" ? (
        <Field label="Plant">
          <Listbox
            aria-label="Plant"
            placeholder="Choose a plant"
            value={parent}
            onChange={setParent}
            items={plants.map((plant) => ({ value: plant.id, label: `${plant.code} - ${plant.name}` }))}
          />
        </Field>
      ) : null}
      {tab === "mpps" || tab === "bmcs" ? (
        <Field label="MCC">
          <MasterSelect
            kind="mccs"
            placeholder="Choose an MCC"
            clearable={false}
            value={parent}
            onChange={(value) => {
              setParent(value);
              setRouteId("");
            }}
          />
        </Field>
      ) : null}
      {tab === "routes" ? (
        <Field label="BMC">
          <Listbox
            aria-label="BMC"
            placeholder="Choose a BMC"
            value={parent}
            onChange={setParent}
            items={bmcs.map((entry) => ({ value: entry.id, label: `${entry.code} - ${entry.name}` }))}
          />
        </Field>
      ) : null}
      {tab === "mpps" ? (
        <Field label="Route" optional>
          <MasterSelect
            kind="routes"
            disabled={!parent}
            placeholder={parent ? "Choose a route" : "Choose an MCC first"}
            value={routeId}
            filters={{ bmc__mcc: parent || undefined }}
            onChange={setRouteId}
          />
        </Field>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-[10rem_minmax(0,1fr)]">
        <Field label="Code" htmlFor="code">
          <Input id="code" name="code" required defaultValue={item?.code} className="font-mono" autoFocus />
        </Field>
        <Field label="Name" htmlFor="name">
          <Input id="name" name="name" required defaultValue={item?.name} />
        </Field>
      </div>
      {tab === "mpps" ? (
        <>
          <FormSection
            title="Place"
            description="Comes from the ERP through the masters import, and fills this MPP's forms. Facilitators can't change it."
          >
            {mpp?.place.village_name || mpp?.place.tehsil ? (
              <dl className="grid gap-x-4 gap-y-1.5 border bg-muted/40 p-3 text-sm sm:grid-cols-2">
                {(
                  [
                    ["Revenue village", mpp.place.village_name],
                    ["Hamlet", mpp.place.hamlet_name],
                    ["Tehsil", mpp.place.tehsil],
                    ["District", mpp.place.district],
                    ["State", mpp.place.state],
                    ["Post office", mpp.place.post_office],
                    ["PIN code", mpp.place.pincode],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label} className="min-w-0">
                    <dt className="text-xs text-muted-foreground">{label}</dt>
                    <dd className="truncate">{value || "—"}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-sm text-muted-foreground">Not loaded yet. Import the masters file from the ERP.</p>
            )}
            {/* Disabled fields are left out of the form, so the server takes them from the village. */}
            <Field
              label="Village code"
              htmlFor="village_code"
              help={linked ? "From the village." : "8 digits, from the ERP."}
            >
              <Input
                id="village_code"
                name="village_code"
                required={!linked}
                disabled={linked}
                pattern="\d{8}"
                inputMode="numeric"
                maxLength={8}
                defaultValue={mpp?.village_code}
                className="font-mono"
              />
            </Field>
            {linked ? null : (
              <Field label="Village name" htmlFor="village_name" optional>
                <Input id="village_name" name="village_name" defaultValue={mpp?.village_name} />
              </Field>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="State code"
                htmlFor="state_code"
                optional
                help={linked ? "From the village." : "2 digits, like 09 for Uttar Pradesh."}
              >
                <Input
                  id="state_code"
                  name="state_code"
                  disabled={linked}
                  pattern="\d{2}"
                  inputMode="numeric"
                  maxLength={2}
                  defaultValue={mpp?.state_code}
                  className="font-mono"
                />
              </Field>
              <Field
                label="Hamlet code"
                htmlFor="hamlet_code"
                optional
                help={mpp?.hamlet ? "From the hamlet." : "2 digits, after the village code."}
              >
                <Input
                  id="hamlet_code"
                  name="hamlet_code"
                  disabled={!!mpp?.hamlet}
                  pattern="\d{2}"
                  inputMode="numeric"
                  maxLength={2}
                  defaultValue={mpp?.hamlet_code}
                  className="font-mono"
                />
              </Field>
            </div>
          </FormSection>
          <Field
            label="ERP internal code"
            htmlFor="source_code"
            optional
            help="Used only to match with the ERP. Never shown elsewhere."
          >
            <Input id="source_code" name="source_code" defaultValue={mpp?.source_code} className="font-mono" />
          </Field>
        </>
      ) : null}
      <CheckRow
        className="-mx-2"
        label="Active"
        hint="Inactive entries stay in the records but can't take new forms."
        checked={active}
        onChange={setActive}
      />
    </FormDialog>
  );
}

function ImportMasters({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<MppImportResult>("hierarchy/mpps/import", { method: "POST", body: form });
    },
    onSuccess: () => refreshKeys(client),
  });
  const result = upload.data;
  const failed = !!result && result.problems.length > 0;

  return (
    <FormDialog
      title="Import from Excel"
      description="Existing MPPs are updated. A row with a district or tehsil code needs state, district and tehsil codes, and loads the place chain too. One bad row stops the whole file, so nothing is half done."
      className="sm:max-w-2xl"
      onClose={onClose}
      footer={
        <Button type="button" variant={result && !failed ? "default" : "ghost"} onClick={onClose}>
          {result && !failed ? "Done" : "Close"}
        </Button>
      }
    >
      <div className="space-y-1.5">
        <p className="text-sm font-medium">The first row must have these columns</p>
        <div className="flex flex-wrap gap-1">
          {IMPORT_COLUMNS.map((name) => (
            <code key={name} className="bg-muted px-1.5 py-0.5 font-mono text-xs">
              {name}
            </code>
          ))}
        </div>
      </div>
      <FileDrop
        label="Excel file"
        accept={[".xlsx"]}
        maxBytes={10 * MB}
        busy={upload.isPending}
        onFile={(file) => upload.mutate(file)}
      />
      <FormError error={upload.error} />
      {result && !failed ? (
        <Alert>
          <CheckCircle2 className="text-emerald-600" />
          <AlertTitle>Import finished</AlertTitle>
          <AlertDescription>
            {result.created} created, {result.updated} updated.
          </AlertDescription>
        </Alert>
      ) : null}
      {failed ? (
        <div className="space-y-2">
          <Alert variant="destructive">
            <XCircle />
            <AlertTitle>Nothing was imported</AlertTitle>
            <AlertDescription>Fix these rows in the file, then upload it again.</AlertDescription>
          </Alert>
          <div className="max-h-64 overflow-y-auto border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted text-left text-xs text-muted-foreground">
                <tr>
                  <th className="w-16 px-3 py-1.5 font-medium">Row</th>
                  <th className="px-3 py-1.5 font-medium">Problem</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {result.problems.map((item) => (
                  <tr key={`${item.row}-${item.problem}`}>
                    <td className="px-3 py-1.5 tabular-nums">{item.row}</td>
                    <td className="px-3 py-1.5">{item.problem}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </FormDialog>
  );
}

const code = <T extends Plant>(): Column<T> => ({
  id: "code",
  header: "Code",
  required: true,
  sortKey: "code",
  csv: (row) => row.code,
  cell: (row) => <span className="font-mono text-xs tabular-nums">{row.code}</span>,
});
const name = <T extends Plant>(): Column<T> => ({
  id: "name",
  header: "Name",
  sortKey: "name",
  csv: (row) => row.name,
  cell: (row) => <span className="font-medium">{row.name}</span>,
});
const status = <T extends Plant>(): Column<T> => ({
  id: "status",
  header: "Status",
  csv: (row) => (row.is_active ? "Active" : "Inactive"),
  cell: (row) => <StatusBadge status={row.is_active ? "active" : "inactive"} />,
});

export default function HierarchyPage() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = (TABS.find((entry) => entry.key === params.get("tab"))?.key ?? "plants") as Tab;
  const canManage = useCan("hierarchy.manage");
  const [editing, setEditing] = useState<{ item: Master | null } | null>(null);
  const [importing, setImporting] = useState(false);

  const plants = useMasters<Plant>("plants").data?.results ?? [];
  const mccs = useMasters<Mcc>("mccs").data?.results ?? [];
  const bmcs = useMasters<Bmc>("bmcs").data?.results ?? [];
  const routes = useMasters<Route>("routes").data?.results ?? [];
  const nameOf = (list: Plant[], id: string | null) => list.find((entry) => entry.id === id)?.name ?? "—";
  const options = (list: Plant[]) =>
    Object.fromEntries(list.map((entry) => [entry.id, `${entry.code} - ${entry.name}`]));

  const plantColumns = useMemo<Column<Plant>[]>(() => [code(), name(), status()], []);
  const mccColumns: Column<Mcc>[] = [
    code(),
    name(),
    {
      id: "plant",
      header: "Plant",
      csv: (row) => nameOf(plants, row.plant),
      cell: (row) => <span className="text-muted-foreground">{nameOf(plants, row.plant)}</span>,
    },
    status(),
  ];
  const bmcColumns: Column<Bmc>[] = [
    code(),
    name(),
    {
      id: "mcc",
      header: "MCC",
      csv: (row) => nameOf(mccs, row.mcc),
      cell: (row) => <span className="text-muted-foreground">{nameOf(mccs, row.mcc)}</span>,
    },
    status(),
  ];
  const routeColumns: Column<Route>[] = [
    code(),
    name(),
    {
      id: "bmc",
      header: "BMC",
      csv: (row) => nameOf(bmcs, row.bmc),
      cell: (row) => <span className="text-muted-foreground">{nameOf(bmcs, row.bmc)}</span>,
    },
    status(),
  ];
  const mppColumns: Column<Mpp>[] = [
    code(),
    name(),
    {
      id: "village",
      header: "Village code",
      sortKey: "village_code",
      csv: (row) => row.village_code,
      cell: (row) => <span className="font-mono text-xs tabular-nums">{row.village_code}</span>,
    },
    {
      id: "code_parts",
      header: "State / hamlet",
      csv: (row) => `${row.state_code}/${row.hamlet_code}`,
      cell: (row) => (
        <span className="font-mono text-xs tabular-nums">
          {row.state_code || "default"} / {row.hamlet_code || "default"}
        </span>
      ),
    },
    {
      id: "place",
      header: "Place",
      hideBelow: "lg",
      csv: (row) => [row.place.village_name, row.place.tehsil, row.place.district].filter(Boolean).join(", "),
      cell: (row) =>
        row.village ? (
          <span className="text-muted-foreground">
            {[row.place.village_name, row.place.tehsil, row.place.district].filter(Boolean).join(", ")}
          </span>
        ) : (
          <span className="text-xs text-amber-700 dark:text-amber-400">Not linked</span>
        ),
    },
    {
      id: "mcc",
      header: "MCC",
      hideBelow: "md",
      csv: (row) => nameOf(mccs, row.mcc),
      cell: (row) => <span className="text-muted-foreground">{nameOf(mccs, row.mcc)}</span>,
    },
    {
      id: "route",
      header: "Route",
      hideBelow: "lg",
      csv: (row) => nameOf(routes, row.route),
      cell: (row) => <span className="text-muted-foreground">{nameOf(routes, row.route)}</span>,
    },
    status(),
  ];

  const open = canManage ? (item: Master) => setEditing({ item }) : undefined;
  const one = TABS.find((entry) => entry.key === tab)!.one;
  const empty = (
    <EmptyState
      icon={Network}
      title={`No ${TABS.find((entry) => entry.key === tab)!.label} found`}
      description="Try another search, or import them from Excel."
    />
  );
  const activeFilter = (filters: Record<string, string | undefined>, setFilter: (key: string, value: string | undefined) => void) => (
    <FilterSelect
      label="Status"
      value={filters.is_active}
      onChange={(value) => setFilter("is_active", value)}
      options={{ true: "Active", false: "Inactive" }}
    />
  );

  return (
    <>
      <PageHeader
        title="Hierarchy"
        description="Plant, MCC, BMC, route and MPP, in the same structure as the ERP."
        actions={
          canManage ? (
            <>
              <Button variant="outline" onClick={() => setImporting(true)}>
                <Upload /> Import
              </Button>
              <Button onClick={() => setEditing({ item: null })}>
                <Plus /> Add {one}
              </Button>
            </>
          ) : null
        }
      />

      <Tabs value={tab} onValueChange={(next) => router.replace(`${pathname}?tab=${next}`, { scroll: false })}>
        <TabsList>
          {TABS.map((entry) => (
            <TabsTrigger key={entry.key} value={entry.key}>
              {entry.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {tab === "plants" ? (
        <DataTable<Plant>
          key="plants"
          id="plants"
          endpoint="hierarchy/plants"
          columns={plantColumns}
          rowKey={(row) => row.id}
          searchPlaceholder="Search by code or name"
          defaultOrdering="code"
          exportName="plants"
          onRowClick={open}
          empty={empty}
          filters={({ filters, setFilter }) => activeFilter(filters, setFilter)}
        />
      ) : null}
      {tab === "mccs" ? (
        <DataTable<Mcc>
          key="mccs"
          id="mccs"
          endpoint="hierarchy/mccs"
          columns={mccColumns}
          rowKey={(row) => row.id}
          searchPlaceholder="Search by code or name"
          defaultOrdering="code"
          exportName="mccs"
          onRowClick={open}
          empty={empty}
          filters={({ filters, setFilter }) => (
            <>
              <FilterSelect
                label="Plant"
                value={filters.plant}
                onChange={(value) => setFilter("plant", value)}
                options={options(plants)}
              />
              {activeFilter(filters, setFilter)}
            </>
          )}
        />
      ) : null}
      {tab === "bmcs" ? (
        <DataTable<Bmc>
          key="bmcs"
          id="bmcs"
          endpoint="hierarchy/bmcs"
          columns={bmcColumns}
          rowKey={(row) => row.id}
          searchPlaceholder="Search by code or name"
          defaultOrdering="code"
          exportName="bmcs"
          onRowClick={open}
          empty={empty}
          filters={({ filters, setFilter }) => (
            <>
              <FilterSelect
                label="MCC"
                value={filters.mcc}
                onChange={(value) => setFilter("mcc", value)}
                options={options(mccs)}
              />
              {activeFilter(filters, setFilter)}
            </>
          )}
        />
      ) : null}
      {tab === "routes" ? (
        <DataTable<Route>
          key="routes"
          id="routes"
          endpoint="hierarchy/routes"
          columns={routeColumns}
          rowKey={(row) => row.id}
          searchPlaceholder="Search by code or name"
          defaultOrdering="code"
          exportName="routes"
          onRowClick={open}
          empty={empty}
          filters={({ filters, setFilter }) => (
            <>
              <FilterSelect
                label="BMC"
                value={filters.bmc}
                onChange={(value) => setFilter("bmc", value)}
                options={options(bmcs)}
              />
              {activeFilter(filters, setFilter)}
            </>
          )}
        />
      ) : null}
      {tab === "mpps" ? (
        <DataTable<Mpp>
          key="mpps"
          id="mpps"
          endpoint="hierarchy/mpps"
          columns={mppColumns}
          rowKey={(row) => row.id}
          searchPlaceholder="Search by code, name or village code"
          defaultOrdering="code"
          exportName="mpps"
          onRowClick={open}
          empty={empty}
          filters={({ filters, setFilter }) => (
            <>
              <FilterSelect
                label="MCC"
                value={filters.mcc}
                onChange={(value) => setFilter("mcc", value)}
                options={options(mccs)}
              />
              {activeFilter(filters, setFilter)}
            </>
          )}
        />
      ) : null}

      {importing ? <ImportMasters onClose={() => setImporting(false)} /> : null}
      {editing ? (
        <MasterForm
          tab={tab}
          item={editing.item}
          plants={plants}
          bmcs={bmcs}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </>
  );
}
