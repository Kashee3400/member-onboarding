"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Plus, RotateCcw, ShieldCheck, Trash2 } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { CheckRow } from "@/components/admin/check-row";
import { Confirm } from "@/components/admin/confirm";
import { FormDialog } from "@/components/admin/form-dialog";
import { DataTable, type Column } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import { SearchBox } from "@/components/common/search-box";
import { EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCan, useMe } from "@/hooks/use-session";
import { api } from "@/lib/api/client";
import { humanize } from "@/lib/format";
import type { Permission, Role } from "@/lib/types";

function PermissionPicker({
  permissions,
  selected,
  locked,
  onChange,
}: {
  permissions: Permission[];
  selected: string[];
  locked: boolean;
  onChange: (codes: string[]) => void;
}) {
  const me = useMe();
  const [text, setText] = useState("");
  const needle = text.toLowerCase();
  // Nobody can hand out a permission they do not hold, except the platform operator.
  // Taking one away is always possible.
  const grantable = (code: string) =>
    me.platform_operator ||
    me.permissions.includes(code) ||
    selected.includes(code);
  const shown = permissions.filter(
    (item) =>
      item.code.toLowerCase().includes(needle) ||
      item.description.toLowerCase().includes(needle),
  );
  const groups = Object.entries(
    Object.groupBy(shown, (item) => item.code.split(".")[0]),
  );

  return (
    <fieldset className="space-y-2">
      <legend className="flex w-full items-center justify-between text-sm font-medium">
        Permissions
        <span className="font-normal text-muted-foreground tabular-nums">
          {selected.length} of {permissions.length}
        </span>
      </legend>
      <SearchBox
        value={text}
        onChange={setText}
        placeholder="Find a permission"
        className="w-full"
      />
      <div className="max-h-72 space-y-3 overflow-y-auto border p-2">
        {groups.map(([group, items = []]) => {
          const codes = items.map((item) => item.code).filter(grantable);
          const all =
            codes.length > 0 && codes.every((code) => selected.includes(code));
          return (
            <section key={group}>
              <div className="flex items-center justify-between px-2 pb-0.5">
                <h3 className="text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
                  {humanize(group)}
                </h3>
                {locked || codes.length === 0 ? null : (
                  <button
                    type="button"
                    className="text-xs text-primary hover:underline"
                    onClick={() =>
                      onChange(
                        all
                          ? selected.filter((code) => !codes.includes(code))
                          : [...new Set([...selected, ...codes])],
                      )
                    }
                  >
                    {all ? "Clear" : "Select all"}
                  </button>
                )}
              </div>
              {items.map((item) => (
                <CheckRow
                  key={item.code}
                  label={item.description}
                  hint={
                    grantable(item.code)
                      ? item.code
                      : `${item.code}. You do not hold this, so you cannot give it.`
                  }
                  disabled={locked || !grantable(item.code)}
                  checked={selected.includes(item.code)}
                  onChange={(on) =>
                    onChange(
                      on
                        ? [...selected, item.code]
                        : selected.filter((code) => code !== item.code),
                    )
                  }
                />
              ))}
            </section>
          );
        })}
        {shown.length === 0 ? (
          <p className="px-2 py-4 text-center text-sm text-muted-foreground">
            No permission matches that.
          </p>
        ) : null}
      </div>
    </fieldset>
  );
}

function RoleForm({
  role,
  permissions,
  onClose,
}: {
  role: Role | null;
  permissions: Permission[];
  onClose: () => void;
}) {
  const client = useQueryClient();
  const canManage = useCan("roles.manage");
  const [selected, setSelected] = useState(role?.permissions ?? []);
  const [mfa, setMfa] = useState(role?.requires_mfa ?? false);
  const system = role?.is_system ?? false;
  // A standard role's permissions and two-step sign-in can change; its code and name cannot.
  const locked = !canManage;
  const fixedName = system || locked;

  const done = (message: string) => {
    client.invalidateQueries({ queryKey: ["queue"] });
    client.invalidateQueries({ queryKey: ["roles"] });
    toast.success(message);
    onClose();
  };
  const save = useMutation({
    mutationFn: (body: object) =>
      role
        ? api(`roles/${role.id}`, { method: "PATCH", body })
        : api("roles", { method: "POST", body }),
    onSuccess: () => done("Role saved."),
  });
  const remove = useMutation({
    mutationFn: () => api(`roles/${role!.id}`, { method: "DELETE" }),
    onSuccess: () => done("Role deleted."),
  });
  const reset = useMutation({
    mutationFn: () => api(`roles/${role!.id}/reset`, { method: "POST" }),
    onSuccess: () => done("Role set back to its standard permissions."),
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    save.mutate(
      system
        ? { requires_mfa: mfa, permissions: selected }
        : {
            code: form.get("code"),
            name: form.get("name"),
            requires_mfa: mfa,
            permissions: selected,
          },
    );
  };

  return (
    <FormDialog
      title={role ? role.name : "New role"}
      description={
        role ? undefined : "Choose exactly what people with this role can do."
      }
      className="sm:max-w-2xl"
      onClose={onClose}
      onSubmit={submit}
      error={save.error ?? remove.error ?? reset.error}
      footer={
        locked ? (
          <Button type="button" variant="ghost" onClick={onClose}>
            Close
          </Button>
        ) : (
          <>
            {role && system && role.customized ? (
              <Confirm
                title="Back to the standard permissions?"
                description="This organization's changes to the role are undone, and later updates set it again."
                action="Reset"
                onConfirm={() => reset.mutate()}
                trigger={
                  <Button
                    type="button"
                    variant="outline"
                    className="mr-auto"
                    disabled={reset.isPending}
                  >
                    <RotateCcw /> Reset to standard
                  </Button>
                }
              />
            ) : null}
            {role && !system ? (
              <Confirm
                title="Delete this role?"
                description="People who hold only this role lose their access. This cannot be undone."
                action="Delete"
                onConfirm={() => remove.mutate()}
                trigger={
                  <Button
                    type="button"
                    variant="destructive"
                    className="mr-auto"
                    disabled={remove.isPending}
                  >
                    <Trash2 /> Delete
                  </Button>
                }
              />
            ) : null}
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save role"}
            </Button>
          </>
        )
      }
    >
      {system ? (
        <Alert>
          <Lock />
          <AlertDescription>
            {role?.customized
              ? "A standard role this organization has changed. Updates no longer change it; reset it to follow them again."
              : "A standard role. Its code and name stay as they are; its permissions are yours to change."}
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" htmlFor="role-name">
          <Input
            id="role-name"
            name="name"
            required
            defaultValue={role?.name}
            disabled={fixedName}
            autoFocus={!fixedName}
          />
        </Field>
        <Field
          label="Code"
          htmlFor="role-code"
          help="Lowercase letters, numbers, hyphens and underscores."
        >
          <Input
            id="role-code"
            name="code"
            required
            defaultValue={role?.code}
            disabled={fixedName}
            pattern="[a-z0-9_\-]+"
            className="font-mono"
          />
        </Field>
      </div>
      <CheckRow
        className="-mx-2"
        label="Require two-step sign-in"
        hint="Use this for anyone who approves forms or changes settings."
        checked={mfa}
        disabled={locked}
        onChange={setMfa}
      />
      <PermissionPicker
        permissions={permissions}
        selected={selected}
        locked={locked}
        onChange={setSelected}
      />
    </FormDialog>
  );
}

export default function RolesPage() {
  const canManage = useCan("roles.manage");
  const [form, setForm] = useState<{ role: Role | null } | null>(null);
  const permissions = useQuery({
    queryKey: ["permissions"],
    queryFn: () => api<Permission[]>("permissions"),
  });

  const columns = useMemo<Column<Role>[]>(
    () => [
      {
        id: "name",
        header: "Role",
        required: true,
        sortKey: "name",
        csv: (row) => row.name,
        cell: (row) => <span className="font-medium">{row.name}</span>,
      },
      {
        id: "code",
        header: "Code",
        sortKey: "code",
        csv: (row) => row.code,
        cell: (row) => (
          <span className="font-mono text-xs text-muted-foreground">
            {row.code}
          </span>
        ),
      },
      {
        id: "type",
        header: "Type",
        csv: (row) =>
          row.is_system
            ? row.customized
              ? "Standard, changed"
              : "Standard"
            : "Custom",
        cell: (row) => (
          <StatusBadge
            status={row.customized ? "pending" : "draft"}
            label={
              row.is_system
                ? row.customized
                  ? "Standard, changed"
                  : "Standard"
                : "Custom"
            }
          />
        ),
      },
      {
        id: "permissions",
        header: "Permissions",
        align: "right",
        csv: (row) => row.permissions.length,
        cell: (row) => (
          <span className="tabular-nums">{row.permissions.length}</span>
        ),
      },
      {
        id: "mfa",
        header: "Two-step sign-in",
        csv: (row) => (row.requires_mfa ? "Required" : "Optional"),
        cell: (row) =>
          row.requires_mfa ? (
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck className="size-4 text-primary" /> Required
            </span>
          ) : (
            <span className="text-muted-foreground">Optional</span>
          ),
      },
    ],
    [],
  );

  return (
    <>
      <PageHeader
        title="Roles & Permissions"
        description="A role decides what someone can do, and what their menu shows."
        actions={
          canManage ? (
            <Button onClick={() => setForm({ role: null })}>
              <Plus /> New role
            </Button>
          ) : null
        }
      />
      <DataTable<Role>
        id="roles"
        endpoint="roles"
        columns={columns}
        rowKey={(row) => row.id}
        searchPlaceholder="Search roles"
        defaultOrdering="name"
        exportName="roles"
        onRowClick={(role) => setForm({ role })}
        empty={
          <EmptyState
            title="No roles found"
            description="Try another search."
          />
        }
      />
      {form ? (
        <RoleForm
          role={form.role}
          permissions={permissions.data ?? []}
          onClose={() => setForm(null)}
        />
      ) : null}
    </>
  );
}
