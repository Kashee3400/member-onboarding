"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Check, Copy, Plus, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { FormDialog } from "@/components/admin/form-dialog";
import { Field } from "@/components/common/field";
import { PageHeader } from "@/components/common/page-header";
import {
  EmptyState,
  ErrorState,
  ListSkeleton,
} from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/client";
import type { ConsoleOrganization } from "@/lib/types";

const KEY = ["console", "organizations"];
const ENDPOINT = "console/organizations";

function bytes(value: number) {
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}

function ago(value: string | null) {
  if (!value) return "Never";
  const days = Math.floor(
    (Date.now() - new Date(value).getTime()) / 86_400_000,
  );
  return days <= 0 ? "Today" : days === 1 ? "Yesterday" : `${days} days ago`;
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "bad" | "warn";
}) {
  const color =
    tone === "bad"
      ? "text-destructive"
      : tone === "warn"
        ? "text-amber-600"
        : "";
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-lg font-semibold tabular-nums ${color}`}>{value}</p>
    </div>
  );
}

function SetupItem({ done, label }: { done: boolean; label: string }) {
  return (
    <li className="flex items-center gap-1.5 text-xs">
      {done ? (
        <Check className="size-3.5 text-emerald-600" />
      ) : (
        <X className="size-3.5 text-destructive" />
      )}
      <span className={done ? "text-muted-foreground" : ""}>{label}</span>
    </li>
  );
}

function OrganizationCard({
  organization,
}: {
  organization: ConsoleOrganization;
}) {
  const client = useQueryClient();
  const { health } = organization;
  const { setup } = health;
  const failures = health.failures_this_week;
  const failed = failures.mail + failures.sms + failures.push;
  const limit = useMutation({
    mutationFn: (storage_limit_mb: number | null) =>
      api(`${ENDPOINT}/${organization.id}`, {
        method: "PATCH",
        body: { storage_limit_mb },
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: KEY });
      toast.success("Storage limit saved.");
    },
    onError: (error) =>
      toast.error(
        error instanceof Error ? error.message : "Could not save it.",
      ),
  });
  const askLimit = () => {
    const answer = window.prompt(
      `Storage limit for ${organization.name}, in MB. Leave empty for no limit.`,
      health.storage_limit_mb ? String(health.storage_limit_mb) : "",
    );
    if (answer === null) return;
    const value = answer.trim() ? Number.parseInt(answer, 10) : null;
    if (value !== null && !(value > 0))
      return toast.error("Enter a whole number of MB, or leave it empty.");
    limit.mutate(value);
  };
  const full =
    !!health.storage_limit_mb &&
    health.storage_bytes >= health.storage_limit_mb * 1024 * 1024;
  const toggle = useMutation({
    mutationFn: () =>
      api(`${ENDPOINT}/${organization.id}`, {
        method: "PATCH",
        body: { is_active: !organization.is_active },
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: KEY });
      toast.success(
        organization.is_active
          ? "Organization switched off."
          : "Organization switched on.",
      );
    },
    onError: (error) =>
      toast.error(
        error instanceof Error ? error.message : "Could not change it.",
      ),
  });

  return (
    <section className="space-y-4 border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">{organization.name}</h2>
          <p className="font-mono text-xs text-muted-foreground">
            {organization.slug}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge
            status={organization.is_active ? "active" : "inactive"}
            label={organization.is_active ? "Active" : "Off"}
          />
          <Button
            size="sm"
            variant="outline"
            disabled={toggle.isPending}
            onClick={() => {
              const verb = organization.is_active ? "Switch off" : "Switch on";
              const warning = organization.is_active
                ? " Nobody in it will be able to sign in."
                : "";
              if (window.confirm(`${verb} ${organization.name}?${warning}`))
                toggle.mutate();
            }}
          >
            {organization.is_active ? "Switch off" : "Switch on"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
        <Stat label="Forms" value={health.forms_total} />
        <Stat label="This week" value={health.forms_this_week} />
        <Stat label="Pending" value={health.pending} />
        <Stat
          label="Late"
          value={health.late}
          tone={health.late ? "warn" : undefined}
        />
        <Stat label="Members" value={health.members} />
        <Stat label="Staff" value={health.staff} />
      </div>

      <div className="grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <p className="text-xs text-muted-foreground">Last activity</p>
          <p>{ago(health.last_activity)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Files stored</p>
          <p
            className={`tabular-nums ${full ? "font-medium text-destructive" : ""}`}
          >
            {bytes(health.storage_bytes)}
            {health.storage_limit_mb
              ? ` of ${bytes(health.storage_limit_mb * 1024 * 1024)}`
              : ""}{" "}
            <button
              type="button"
              className="text-xs text-primary underline-offset-2 hover:underline"
              disabled={limit.isPending}
              onClick={askLimit}
            >
              {health.storage_limit_mb ? "Change limit" : "Set limit"}
            </button>
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">
            Failed deliveries, 7 days
          </p>
          <p className={failed ? "font-medium text-destructive" : ""}>
            {failed
              ? `Mail ${failures.mail} · SMS ${failures.sms} · Push ${failures.push}`
              : "None"}
          </p>
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium">Setup</p>
        <ul className="grid grid-cols-2 gap-1 sm:grid-cols-3">
          <SetupItem done={setup.branding} label="Logo" />
          <SetupItem done={setup.email_domain} label="Staff email domain" />
          <SetupItem done={setup.mail} label="Mail" />
          <SetupItem done={setup.sms} label="SMS" />
          <SetupItem done={setup.push} label="Push" />
          <SetupItem done={setup.review_steps} label="Review steps" />
          <SetupItem
            done={setup.signatories >= 2}
            label={`Signatories (${setup.signatories})`}
          />
          <SetupItem
            done={setup.connected_apps > 0}
            label={`Connected apps (${setup.connected_apps})`}
          />
          <SetupItem done={setup.mpps > 0} label={`MPPs (${setup.mpps})`} />
        </ul>
      </div>
    </section>
  );
}

function NewOrganization({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const [link, setLink] = useState<string | null | undefined>(undefined);
  const create = useMutation({
    mutationFn: (body: object) =>
      api<{ invitation_link: string | null }>(ENDPOINT, {
        method: "POST",
        body,
      }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: KEY });
      setLink(data.invitation_link);
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate(Object.fromEntries(form.entries()));
  };

  if (link !== undefined) {
    return (
      <FormDialog
        title="Organization created"
        description="It has the standard roles and its first admin."
        onClose={onClose}
        footer={<Button onClick={onClose}>Done</Button>}
      >
        {link ? (
          <Alert>
            <AlertTitle>Send this link to the admin</AlertTitle>
            <AlertDescription className="space-y-2">
              <p>
                A new organization has no mail set up yet, so share the link
                yourself. It works once, for 7 days, and lets them choose a
                password.
              </p>
              <div className="flex gap-2">
                <Input
                  readOnly
                  value={link}
                  className="font-mono text-xs"
                  onFocus={(event) => event.target.select()}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    navigator.clipboard
                      .writeText(link)
                      .then(() => toast.success("Link copied."))
                  }
                >
                  <Copy /> Copy
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        ) : (
          <p className="text-sm">
            The admin already has an account, so they sign in with their usual
            password.
          </p>
        )}
        <p className="text-sm text-muted-foreground">
          Next, the admin sets up mail and SMS, branding, review steps and
          signatories, then imports the masters. This page shows what is still
          missing.
        </p>
      </FormDialog>
    );
  }

  return (
    <FormDialog
      title="New organization"
      description="Creates the organization with the standard roles and invites its first admin."
      onClose={onClose}
      onSubmit={submit}
      error={create.error}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Create organization"}
          </Button>
        </>
      }
    >
      <Field label="Name" htmlFor="org-name">
        <Input id="org-name" name="name" required autoFocus />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Short name"
          htmlFor="org-slug"
          help="Used at sign-in. Lowercase, no spaces."
        >
          <Input
            id="org-slug"
            name="slug"
            required
            pattern="[a-z0-9-]+"
            className="font-mono"
          />
        </Field>
        <Field
          label="Staff email domain"
          htmlFor="org-domain"
          optional
          help="Like paayasmilk.com."
        >
          <Input id="org-domain" name="email_domain" className="font-mono" />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="First admin's name" htmlFor="org-admin-name">
          <Input id="org-admin-name" name="admin_name" required />
        </Field>
        <Field label="First admin's email" htmlFor="org-admin-email">
          <Input
            id="org-admin-email"
            name="admin_email"
            type="email"
            required
          />
        </Field>
      </div>
    </FormDialog>
  );
}

export default function ConsolePage() {
  const [creating, setCreating] = useState(false);
  const organizations = useQuery({
    queryKey: KEY,
    queryFn: () => api<ConsoleOrganization[]>(ENDPOINT),
  });

  return (
    <>
      <PageHeader
        title="Platform"
        description="Every organization on this platform: how it is used, what is stuck or failing, and what is still to set up."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus /> New organization
          </Button>
        }
      />
      {organizations.isPending ? (
        <ListSkeleton />
      ) : organizations.isError ? (
        <ErrorState
          error={organizations.error}
          onRetry={() => organizations.refetch()}
        />
      ) : organizations.data.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {organizations.data.map((organization) => (
            <OrganizationCard
              key={organization.id}
              organization={organization}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Building2}
          title="No organizations yet"
          description="Create the first one."
        />
      )}
      {creating ? <NewOrganization onClose={() => setCreating(false)} /> : null}
    </>
  );
}
