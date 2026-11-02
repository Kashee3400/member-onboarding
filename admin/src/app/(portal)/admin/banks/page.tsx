"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Landmark, Plus, Upload } from "lucide-react";
import { Suspense, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { CheckRow } from "@/components/admin/check-row";
import { FormError } from "@/components/admin/feedback";
import { FileDrop } from "@/components/admin/file-drop";
import { FormDialog } from "@/components/admin/form-dialog";
import { DataTable, FilterSelect, type Column } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/client";
import type { BankBranch, BankImportResult } from "@/lib/types";

const ENDPOINT = "banks/branches";
const IMPORT_COLUMNS = [
  "ifsc",
  "bank_name",
  "branch_name",
  "address (optional)",
  "district (optional)",
  "bank_code (optional)",
  "branch_code (optional)",
  "is_active (optional)",
];
const MB = 1024 * 1024;

const refresh = (client: ReturnType<typeof useQueryClient>) => client.invalidateQueries({ queryKey: ["queue"] });

const COLUMNS: Column<BankBranch>[] = [
  {
    id: "ifsc",
    header: "IFSC",
    sortKey: "ifsc",
    required: true,
    csv: (row) => row.ifsc,
    cell: (row) => <span className="font-mono text-[13px]">{row.ifsc}</span>,
  },
  {
    id: "bank",
    header: "Bank",
    sortKey: "bank_name",
    csv: (row) => row.bank_name,
    cell: (row) => <span className="font-medium">{row.bank_name}</span>,
  },
  { id: "branch", header: "Branch", sortKey: "branch_name", csv: (row) => row.branch_name, cell: (row) => row.branch_name },
  {
    id: "district",
    header: "District",
    hideBelow: "md",
    csv: (row) => row.district,
    cell: (row) => <span className="text-muted-foreground">{row.district}</span>,
  },
  {
    id: "address",
    header: "Address",
    hideBelow: "lg",
    defaultHidden: true,
    csv: (row) => row.address,
    cell: (row) => <span className="text-muted-foreground">{row.address}</span>,
  },
  {
    id: "status",
    header: "Status",
    csv: (row) => (row.is_active && row.bank_is_active ? "Active" : "Inactive"),
    cell: (row) => <StatusBadge status={row.is_active && row.bank_is_active ? "active" : "inactive"} />,
  },
];

function BranchForm({ branch, onClose }: { branch: BankBranch | null; onClose: () => void }) {
  const client = useQueryClient();
  const [active, setActive] = useState(branch?.is_active ?? true);
  const save = useMutation({
    mutationFn: (body: object) =>
      branch ? api(`${ENDPOINT}/${branch.id}`, { method: "PATCH", body }) : api(ENDPOINT, { method: "POST", body }),
    onSuccess: () => {
      refresh(client);
      toast.success("Branch saved.");
      onClose();
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    save.mutate({ ...Object.fromEntries(new FormData(event.currentTarget)), is_active: active });
  };

  return (
    <FormDialog
      title={branch ? `Branch ${branch.ifsc}` : "Add a branch"}
      description="A facilitator who types this IFSC gets the bank and branch filled in."
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
      <Field label="IFSC" htmlFor="ifsc" help="11 characters, as on the passbook.">
        <Input
          id="ifsc"
          name="ifsc"
          required
          maxLength={11}
          pattern="[A-Za-z]{4}0[A-Za-z0-9]{6}"
          defaultValue={branch?.ifsc}
          className="font-mono uppercase"
          autoFocus
        />
      </Field>
      <Field label="Bank" htmlFor="bank_name">
        <Input id="bank_name" name="bank_name" required maxLength={200} defaultValue={branch?.bank_name} />
      </Field>
      <Field label="Branch" htmlFor="branch_name">
        <Input id="branch_name" name="branch_name" required maxLength={200} defaultValue={branch?.branch_name} />
      </Field>
      <Field label="District" htmlFor="district" optional>
        <Input id="district" name="district" maxLength={100} defaultValue={branch?.district} />
      </Field>
      <Field label="Address" htmlFor="address" optional>
        <Input id="address" name="address" maxLength={300} defaultValue={branch?.address} />
      </Field>
      <CheckRow
        className="-mx-2"
        label="In use"
        hint="A branch out of use is not filled in from its IFSC; the app then looks it up online."
        checked={active}
        onChange={setActive}
      />
    </FormDialog>
  );
}

function ImportBranches({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<BankImportResult>(`${ENDPOINT}/import`, { method: "POST", body: form });
    },
    onSuccess: () => refresh(client),
  });
  const result = upload.data;

  return (
    <FormDialog
      title="Import banks and branches"
      description="Use the file from the ERP's export_banks_for_onboarding command, or any file with these columns. Branches are matched by IFSC, so a known one is updated."
      className="sm:max-w-2xl"
      onClose={onClose}
      footer={
        <Button type="button" variant={result ? "default" : "ghost"} onClick={onClose}>
          {result ? "Done" : "Close"}
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
        label="CSV or Excel file"
        accept={[".csv", ".xlsx"]}
        maxBytes={8 * MB}
        busy={upload.isPending}
        onFile={(file) => upload.mutate(file)}
      />
      <FormError error={upload.error} />
      {result ? (
        <Alert>
          <CheckCircle2 className="text-emerald-600" />
          <AlertTitle>Import finished</AlertTitle>
          <AlertDescription>
            {result.created} added, {result.updated} updated
            {result.skipped ? `, ${result.skipped} rows skipped` : ""}
            {result.repeated ? `, ${result.repeated} repeated IFSCs (the last row was kept)` : ""}.
          </AlertDescription>
        </Alert>
      ) : null}
      {result?.problems.length ? (
        <div className="max-h-64 overflow-y-auto border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th className="w-16 px-3 py-1.5 font-medium">Row</th>
                <th className="px-3 py-1.5 font-medium">Skipped because</th>
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
      ) : null}
    </FormDialog>
  );
}

export default function BanksPage() {
  const [editing, setEditing] = useState<{ branch: BankBranch | null } | null>(null);
  const [importing, setImporting] = useState(false);

  return (
    <>
      <PageHeader
        title="Banks"
        description="Banks and branches by IFSC. Typing a full IFSC in the form fills the bank and branch from here; an IFSC not here is looked up online."
        actions={
          <>
            <Button variant="outline" onClick={() => setImporting(true)}>
              <Upload /> Import
            </Button>
            <Button onClick={() => setEditing({ branch: null })}>
              <Plus /> Add branch
            </Button>
          </>
        }
      />
      <Suspense>
        <DataTable<BankBranch>
          id="bank-branches"
          endpoint={ENDPOINT}
          columns={COLUMNS}
          rowKey={(row) => row.id}
          searchPlaceholder="IFSC, bank, branch or district"
          exportName="bank-branches"
          onRowClick={(branch) => setEditing({ branch })}
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
              icon={Landmark}
              title="No branches found"
              description="Try another search, or import the ERP's bank file."
            />
          }
        />
      </Suspense>
      {editing ? <BranchForm branch={editing.branch} onClose={() => setEditing(null)} /> : null}
      {importing ? <ImportBranches onClose={() => setImporting(false)} /> : null}
    </>
  );
}
