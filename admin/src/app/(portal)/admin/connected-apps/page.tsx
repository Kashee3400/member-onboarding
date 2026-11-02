"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plug } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { CheckRow } from "@/components/admin/check-row";
import { FormDialog } from "@/components/admin/form-dialog";
import { DataTable, type Column } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, type Page } from "@/lib/api/client";
import type { Role, TrustedIssuer } from "@/lib/types";

const NO_ROLE = "none";

function IssuerForm({ issuer, onClose }: { issuer: TrustedIssuer | null; onClose: () => void }) {
  const client = useQueryClient();
  const [role, setRole] = useState((issuer ? issuer.default_role_code : "facilitator") || NO_ROLE);
  const [syncs, setSyncs] = useState(issuer?.syncs_mpp_assignments ?? true);
  const [active, setActive] = useState(issuer?.is_active ?? true);
  const roles = useQuery({
    queryKey: ["roles", "all"],
    queryFn: () => api<Page<Role>>("roles", { query: { page_size: 200 } }),
  });
  const save = useMutation({
    mutationFn: (body: object) =>
      issuer
        ? api(`auth/trusted-issuers/${issuer.id}`, { method: "PATCH", body })
        : api("auth/trusted-issuers", { method: "POST", body }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["queue"] });
      toast.success("App saved.");
      onClose();
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    save.mutate({
      name: form.get("name"),
      issuer: form.get("issuer"),
      audience: form.get("audience"),
      public_key: form.get("public_key"),
      default_role_code: role === NO_ROLE ? "" : role,
      syncs_mpp_assignments: syncs,
      is_active: active,
    });
  };

  const roleItems = [
    { value: NO_ROLE, label: "No role" },
    ...(roles.data?.results ?? []).map((item) => ({ value: item.code, label: item.name })),
  ];

  return (
    <FormDialog
      title={issuer ? issuer.name : "Connect an app"}
      description="The app signs its own users in, and this service trusts its signature."
      onClose={onClose}
      onSubmit={submit}
      error={save.error}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save app"}
          </Button>
        </>
      }
    >
      <Field label="Name" htmlFor="app-name">
        <Input id="app-name" name="name" required defaultValue={issuer?.name} autoFocus />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Issuer" htmlFor="app-issuer" help="Must match the app's setting exactly.">
          <Input id="app-issuer" name="issuer" required defaultValue={issuer?.issuer} className="font-mono" />
        </Field>
        <Field label="Audience" htmlFor="app-audience">
          <Input
            id="app-audience"
            name="audience"
            required
            defaultValue={issuer?.audience ?? "member-onboarding"}
            className="font-mono"
          />
        </Field>
      </div>
      <Field label="Public key (PEM)" htmlFor="app-key">
        <Textarea
          id="app-key"
          name="public_key"
          required
          rows={6}
          defaultValue={issuer?.public_key}
          className="font-mono text-xs"
        />
      </Field>
      <Field label="Role on first sign-in" help="Usually Facilitator." optional>
        <Listbox items={roleItems} value={role} onChange={setRole} aria-label="Role on first sign-in" />
      </Field>
      <div className="-mx-2 space-y-1">
        <CheckRow
          label="Take MPP assignments from this app"
          hint="Each sign-in updates the MPPs this person holds."
          checked={syncs}
          onChange={setSyncs}
        />
        <CheckRow label="Active" hint="Turn off to stop this app signing anyone in." checked={active} onChange={setActive} />
      </div>
    </FormDialog>
  );
}

export default function ConnectedAppsPage() {
  const [form, setForm] = useState<{ issuer: TrustedIssuer | null } | null>(null);

  const columns = useMemo<Column<TrustedIssuer>[]>(
    () => [
      {
        id: "name",
        header: "Name",
        required: true,
        csv: (row) => row.name,
        sortValue: (row) => row.name,
        cell: (row) => <span className="font-medium">{row.name}</span>,
      },
      {
        id: "issuer",
        header: "Issuer",
        csv: (row) => row.issuer,
        cell: (row) => <span className="font-mono text-xs text-muted-foreground">{row.issuer}</span>,
      },
      {
        id: "role",
        header: "First role",
        hideBelow: "md",
        csv: (row) => row.default_role_code,
        cell: (row) => <span className="text-muted-foreground">{row.default_role_code || "—"}</span>,
      },
      {
        id: "sync",
        header: "MPP assignments",
        hideBelow: "lg",
        csv: (row) => (row.syncs_mpp_assignments ? "From this app" : "Set here"),
        cell: (row) => (
          <span className="text-muted-foreground">{row.syncs_mpp_assignments ? "From this app" : "Set here"}</span>
        ),
      },
      {
        id: "status",
        header: "Status",
        csv: (row) => (row.is_active ? "Active" : "Off"),
        cell: (row) => <StatusBadge status={row.is_active ? "active" : "draft"} label={row.is_active ? "Active" : "Off"} />,
      },
    ],
    [],
  );

  return (
    <>
      <PageHeader
        title="Connected Apps"
        description="Apps allowed to sign in their own users, such as the facilitator app."
        actions={
          <Button onClick={() => setForm({ issuer: null })}>
            <Plug /> Connect an app
          </Button>
        }
      />
      <DataTable<TrustedIssuer>
        id="connected-apps"
        endpoint="auth/trusted-issuers"
        columns={columns}
        rowKey={(row) => row.id}
        searchable={false}
        exportName="connected-apps"
        onRowClick={(issuer) => setForm({ issuer })}
        empty={
          <EmptyState
            icon={Plug}
            title="No apps connected yet"
            description="Connect the facilitator app so field staff can reach the forms."
          />
        }
      />
      {form ? <IssuerForm issuer={form.issuer} onClose={() => setForm(null)} /> : null}
    </>
  );
}
