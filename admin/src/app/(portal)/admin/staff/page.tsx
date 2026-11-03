"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, MailCheck, Power, Send, ShieldOff, UserPlus, Users } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { CheckRow } from "@/components/admin/check-row";
import { Confirm } from "@/components/admin/confirm";
import { messageOf } from "@/components/admin/feedback";
import { FormDialog } from "@/components/admin/form-dialog";
import { PhotoField } from "@/components/admin/photo-field";
import { SignatureSetup } from "@/components/admin/signature-setup";
import { CopyButton } from "@/components/applications/copy-button";
import { DataTable, FilterSelect, type Column } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { SecretInput } from "@/components/common/form-input";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCan, useMe } from "@/hooks/use-session";
import { api, type Page } from "@/lib/api/client";
import { apiImage } from "@/lib/api";
import { date, initials } from "@/lib/format";
import type { Role, Staff } from "@/lib/types";

function RolePicker({
  roles,
  selected,
  onChange,
}: {
  roles: Role[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">Roles</legend>
      <div className="max-h-56 overflow-y-auto border p-1">
        {roles.map((role) => (
          <CheckRow
            key={role.id}
            label={role.name}
            hint={role.requires_mfa ? "Needs two-step sign-in" : undefined}
            checked={selected.includes(role.id)}
            onChange={(on) => onChange(on ? [...selected, role.id] : selected.filter((id) => id !== role.id))}
          />
        ))}
      </div>
    </fieldset>
  );
}

/** The link from the invitation email, for sending another way too, such as WhatsApp. */
function InviteLink({ link, email }: { link: string; email: string }) {
  return (
    <div
      ref={(panel) => panel?.scrollIntoView({ block: "nearest" })}
      className="space-y-1.5 border border-primary/30 bg-primary/5 p-3"
    >
      <p className="flex items-center gap-2 text-sm font-medium">
        <MailCheck className="size-4 text-primary" /> Invitation sent to {email}
      </p>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate font-mono text-xs">{link}</code>
        <CopyButton value={link} />
      </div>
      <p className="text-xs text-muted-foreground">
        It works once, for 7 days. If the email does not arrive, send this link to them directly. Sending a new
        invitation ends this one.
      </p>
    </div>
  );
}

function AddStaff({ roles, onClose }: { roles: Role[]; onClose: () => void }) {
  const client = useQueryClient();
  const [roleIds, setRoleIds] = useState<string[]>([]);
  const [withPassword, setWithPassword] = useState(false);
  const create = useMutation({
    mutationFn: (body: object) => api<Staff & { invite_link?: string }>("staff", { method: "POST", body }),
    onSuccess: (person) => {
      client.invalidateQueries({ queryKey: ["queue"] });
      client.invalidateQueries({ queryKey: ["staff"] });
      if (!person.invite_link) {
        toast.success("Staff added. They must change the password when they first sign in.");
        onClose();
      }
    },
  });
  const invited = create.data?.invite_link ? create.data : null;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({
      email: form.get("email"),
      full_name: form.get("full_name"),
      ...(withPassword ? { password: form.get("password") } : {}),
      role_ids: roleIds,
    });
  };

  return (
    <FormDialog
      title="Add staff"
      description="They get an email to choose their own password, and confirm their name."
      onClose={onClose}
      onSubmit={submit}
      error={create.error}
      footer={
        invited ? (
          <Button type="button" onClick={onClose}>
            Done
          </Button>
        ) : (
          <>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending || roleIds.length === 0}>
              {create.isPending ? "Adding…" : withPassword ? "Add staff" : "Send invitation"}
            </Button>
          </>
        )
      }
    >
      {invited ? (
        <InviteLink link={invited.invite_link!} email={invited.email} />
      ) : (
        <>
          <Field label="Full name" htmlFor="full_name" help="They can correct it to their official name.">
            <Input id="full_name" name="full_name" required autoFocus />
          </Field>
          <Field label="Email" htmlFor="email">
            <Input id="email" name="email" type="email" required />
          </Field>
          <RolePicker roles={roles} selected={roleIds} onChange={setRoleIds} />
          <CheckRow
            label="Set a temporary password instead"
            hint="For someone without email access. You share the password with them privately."
            checked={withPassword}
            onChange={setWithPassword}
          />
          {withPassword ? (
            <Field label="Temporary password" htmlFor="password" help="At least 12 characters.">
              <SecretInput id="password" name="password" required minLength={12} autoComplete="new-password" />
            </Field>
          ) : null}
        </>
      )}
    </FormDialog>
  );
}

function ManageStaff({ person, roles, onClose }: { person: Staff; roles: Role[]; onClose: () => void }) {
  const client = useQueryClient();
  const me = useMe();
  const [roleIds, setRoleIds] = useState(person.roles.map((role) => role.id));
  const [name, setName] = useState(person.full_name);
  const [email, setEmail] = useState(person.email);
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["queue"] });
    client.invalidateQueries({ queryKey: ["staff"] });
  };

  const update = useMutation({
    mutationFn: (body: object) => api(`staff/${person.id}`, { method: "PATCH", body }),
    onSuccess: (_, body) => {
      refresh();
      toast.success(
        "is_active" in body
          ? person.is_active
            ? "Deactivated."
            : "Reactivated."
          : "full_name" in body
            ? "Name saved."
            : "email" in body
              ? "Email saved. They sign in with the new one from now on."
              : "Roles saved.",
      );
      onClose();
    },
  });
  const invite = useMutation({
    mutationFn: () => api<{ invite_link: string }>(`staff/${person.id}/invite`, { method: "POST" }),
    onError: (error) => toast.error(messageOf(error)),
  });
  const resetMfa = useMutation({
    mutationFn: () => api(`staff/${person.id}/mfa-reset`, { method: "POST" }),
    onSuccess: () => toast.success("Two-step sign-in reset. They set it up again at next sign-in."),
    onError: (error) => toast.error(messageOf(error)),
  });

  const resetPassword = useMutation({
    mutationFn: () => api<{ temporary_password: string }>(`staff/${person.id}/password-reset`, { method: "POST" }),
    onError: (error) => toast.error(messageOf(error)),
  });

  const self = person.email === me.email;
  const rolesChanged =
    [...roleIds].sort().join() !== person.roles.map((role) => role.id).sort().join();

  return (
    <FormDialog
      title={person.full_name || person.email}
      description={person.email}
      onClose={onClose}
      error={update.error}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button
            type="button"
            disabled={update.isPending || !rolesChanged}
            onClick={() => update.mutate({ role_ids: roleIds })}
          >
            Save roles
          </Button>
        </>
      }
    >
      <div className="flex items-end gap-4">
        <PhotoField name={person.full_name || person.email} photo={person.photo_url} membership={person.id} />
        <Field label="Full name" htmlFor="staff-name" className="min-w-0 flex-1">
          <div className="flex gap-2">
            <Input id="staff-name" value={name} onChange={(event) => setName(event.target.value)} />
            <Button
              type="button"
              variant="outline"
              disabled={update.isPending || !name.trim() || name.trim() === person.full_name}
              onClick={() => update.mutate({ full_name: name.trim() })}
            >
              Save name
            </Button>
          </div>
        </Field>
      </div>

      <Field
        label="Email"
        htmlFor="staff-email"
        help={
          person.status === "invited"
            ? "They sign in with this. Send the invitation again after changing it."
            : "They sign in with this."
        }
      >
        <div className="flex gap-2">
          <Input
            id="staff-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Button
            type="button"
            variant="outline"
            disabled={
              update.isPending ||
              !email.includes("@") ||
              email.trim().toLowerCase() === person.email.toLowerCase()
            }
            onClick={() => update.mutate({ email: email.trim() })}
          >
            Save email
          </Button>
        </div>
      </Field>

      <RolePicker roles={roles} selected={roleIds} onChange={setRoleIds} />
      {self ? (
        <p className="text-xs text-muted-foreground">
          This is your own account. Nobody can raise their own access, so another admin must do that.
        </p>
      ) : null}

      {person.status === "invited" ? (
        <div className="space-y-2 border-t pt-4">
          <p className="text-sm">
            <StatusBadge status="invited" /> They have not accepted the invitation yet.
          </p>
          {invite.data ? (
            <InviteLink link={invite.data.invite_link} email={person.email} />
          ) : (
            <Button type="button" variant="outline" disabled={invite.isPending} onClick={() => invite.mutate()}>
              <Send /> {invite.isPending ? "Sending…" : "Send the invitation again"}
            </Button>
          )}
        </div>
      ) : null}

      <div className="space-y-2 border-t pt-4">
        <p className="text-sm font-medium">Signature</p>
        {person.needs_signature ? (
          <SignatureSetup membership={person.id} hasSignature={person.has_signature} />
        ) : (
          <p className="text-sm text-muted-foreground">
            Not needed. Forms approved by this team carry the signature of its head.
          </p>
        )}
      </div>

      <div className="space-y-2 border-t pt-4">
        {resetPassword.data ? (
          <div
            ref={(panel) => panel?.scrollIntoView({ block: "nearest" })}
            className="space-y-1.5 border border-primary/30 bg-primary/5 p-3"
          >
            <p className="text-sm font-medium">One-time password. It is shown only now.</p>
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 font-mono text-sm break-all">
                {resetPassword.data.temporary_password}
              </code>
              <CopyButton value={resetPassword.data.temporary_password} />
            </div>
            <p className="text-xs text-muted-foreground">
              Give it to them directly. They choose a new password at their next sign-in, and are signed out everywhere now.
            </p>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {self ? null : (
            <Confirm
              title="Reset this person's password?"
              description="They are signed out everywhere, and you get a one-time password to give them. This is recorded in the audit log."
              action="Reset password"
              onConfirm={() => resetPassword.mutate()}
              trigger={
                <Button type="button" variant="outline" disabled={resetPassword.isPending}>
                  <KeyRound /> Reset password
                </Button>
              }
            />
          )}
          <Confirm
            title="Reset two-step sign-in?"
            description="Use this when someone loses their phone. They set it up again at their next sign-in."
            action="Reset"
            onConfirm={() => resetMfa.mutate()}
            trigger={
              <Button type="button" variant="outline" disabled={resetMfa.isPending}>
                <ShieldOff /> Reset two-step sign-in
              </Button>
            }
          />
          <Confirm
            title={person.is_active ? "Deactivate this person?" : "Reactivate this person?"}
            description={
              person.is_active
                ? "They can no longer sign in, and their MPP assignments end straight away."
                : "They can sign in again. MPP assignments have to be given again."
            }
            action={person.is_active ? "Deactivate" : "Reactivate"}
            onConfirm={() => update.mutate({ is_active: !person.is_active })}
            trigger={
              <Button type="button" variant="destructive" disabled={update.isPending}>
                <Power /> {person.is_active ? "Deactivate" : "Reactivate"}
              </Button>
            }
          />
        </div>
      </div>
    </FormDialog>
  );
}

export default function StaffPage() {
  const canManage = useCan("staff.manage");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Staff | null>(null);
  const roles = useQuery({
    queryKey: ["roles", "all"],
    queryFn: () => api<Page<Role>>("roles", { query: { page_size: 200 } }),
  });
  const roleList = roles.data?.results ?? [];

  const columns = useMemo<Column<Staff>[]>(
    () => [
      {
        id: "name",
        header: "Name",
        required: true,
        sortKey: "full_name",
        csv: (row) => row.full_name,
        cell: (row) => (
          <span className="flex items-center gap-2.5">
            <Avatar className="size-7">
              {row.photo_url ? <AvatarImage src={apiImage(row.photo_url)} alt="" /> : null}
              <AvatarFallback className="bg-primary/12 text-[11px] font-semibold text-primary">
                {initials(row.full_name || row.email)}
              </AvatarFallback>
            </Avatar>
            <span className="font-medium">{row.full_name || row.email.split("@")[0]}</span>
          </span>
        ),
      },
      {
        id: "email",
        header: "Email",
        sortKey: "email",
        csv: (row) => row.email,
        cell: (row) => <span className="text-muted-foreground">{row.email}</span>,
      },
      {
        id: "roles",
        header: "Roles",
        csv: (row) => row.roles.map((role) => role.name).join(", "),
        cell: (row) =>
          row.roles.length ? (
            <span className="flex flex-wrap gap-1">
              {row.roles.map((role) => (
                <Badge key={role.id} variant="secondary">
                  {role.name}
                </Badge>
              ))}
            </span>
          ) : (
            <StatusBadge status="draft" label="No role" />
          ),
      },
      {
        id: "status",
        header: "Status",
        sortKey: "is_active",
        csv: (row) => row.status,
        cell: (row) => <StatusBadge status={row.status} />,
      },
      {
        id: "signature",
        header: "Signature",
        hideBelow: "lg",
        csv: (row) => (row.needs_signature ? (row.has_signature ? "On file" : "Missing") : "Not needed"),
        cell: (row) =>
          row.needs_signature ? (
            <StatusBadge status={row.has_signature ? "active" : "pending"} label={row.has_signature ? "On file" : "Missing"} />
          ) : (
            <span className="text-muted-foreground">Not needed</span>
          ),
      },
      {
        id: "added",
        header: "Added",
        sortKey: "created_at",
        hideBelow: "lg",
        csv: (row) => date(row.created_at),
        cell: (row) => <span className="text-muted-foreground tabular-nums">{date(row.created_at)}</span>,
      },
    ],
    [],
  );

  return (
    <>
      <PageHeader
        title="Staff"
        description="People with access to this organization, and what they can do."
        actions={
          canManage ? (
            <Button onClick={() => setAdding(true)}>
              <UserPlus /> Add staff
            </Button>
          ) : null
        }
      />
      <DataTable<Staff>
        id="staff"
        endpoint="staff"
        columns={columns}
        rowKey={(row) => row.id}
        searchPlaceholder="Search by name or email"
        defaultOrdering="full_name"
        exportName="staff"
        onRowClick={canManage ? setEditing : undefined}
        views={[
          { name: "Active", filters: { is_active: "true" } },
          { name: "Inactive", filters: { is_active: "false" } },
        ]}
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
            icon={Users}
            title="No staff found"
            description="Try another search, or add someone who should have access."
          />
        }
      />
      {adding ? <AddStaff roles={roleList} onClose={() => setAdding(false)} /> : null}
      {editing ? <ManageStaff person={editing} roles={roleList} onClose={() => setEditing(null)} /> : null}
    </>
  );
}
