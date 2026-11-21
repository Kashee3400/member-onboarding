"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRightLeft,
  Download,
  FileSpreadsheet,
  KeyRound,
  ListChecks,
  MoreHorizontal,
  Pencil,
  Power,
  ShieldOff,
  Upload,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CheckRow } from "@/components/admin/check-row";
import { FileDrop } from "@/components/admin/file-drop";
import { FormDialog } from "@/components/admin/form-dialog";
import { CopyButton } from "@/components/applications/copy-button";
import { Field } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCan, useMe } from "@/hooks/use-session";
import { ApiError, api, type Page } from "@/lib/api/client";
import type { Staff } from "@/lib/types";

const APPROVER_ROLES = new Set(["area_manager", "cs_legal", "finance"]);
const label = (person: Staff) => person.full_name || person.email;
const approves = (person: Staff) =>
  person.roles.some((role) => APPROVER_ROLES.has(role.code));
const facilitatorOnly = (person: Staff) =>
  person.roles.length > 0 &&
  person.roles.every((role) => role.code === "facilitator");

function useRefresh() {
  const client = useQueryClient();
  return () => {
    client.invalidateQueries({ queryKey: ["staff"] });
    client.invalidateQueries({ queryKey: ["queue"] });
  };
}

// Transfer ----------------------------------------------------------------------------

type TransferResult = {
  mccs: string[];
  mpps: string[];
  facilitator_mpps: number;
};

/** Hands someone's MCCs and Area Manager MPPs to another person for good. */
function TransferWork({
  person,
  thenDeactivate = false,
  onClose,
}: {
  person: Staff;
  thenDeactivate?: boolean;
  onClose: () => void;
}) {
  const refresh = useRefresh();
  const [target, setTarget] = useState<string | null>(null);
  const staff = useQuery({
    queryKey: ["staff", "active-approvers"],
    queryFn: () =>
      api<Page<Staff>>("staff", {
        query: { page_size: 200, is_active: "true" },
      }),
  });
  const candidates = (staff.data?.results ?? []).filter(
    (other) => other.id !== person.id && approves(other),
  );

  const move = useMutation({
    mutationFn: async () => {
      const result = await api<TransferResult>(`staff/${person.id}/transfer`, {
        method: "POST",
        body: { to: target },
      });
      if (thenDeactivate) {
        await api(`staff/${person.id}`, {
          method: "PATCH",
          body: { is_active: false },
        });
      }
      return result;
    },
    onSuccess: (result) => {
      refresh();
      const to = candidates.find((other) => other.id === target);
      const parts = [
        result.mccs.length ? `MCC ${result.mccs.join(", ")}` : "",
        result.mpps.length ? `${result.mpps.length} MPPs` : "",
      ].filter(Boolean);
      toast.success(
        `${parts.join(" and ")} moved to ${to ? label(to) : "them"}${thenDeactivate ? `. ${label(person)} is deactivated.` : "."}`,
      );
      onClose();
    },
  });

  return (
    <FormDialog
      title={
        thenDeactivate ? "Transfer work, then deactivate" : "Transfer work"
      }
      description={`Everything ${label(person)} approves moves for good: their MCCs and the MPPs they hold as Area Manager. Their forms follow the MPPs.`}
      onClose={onClose}
      error={move.error}
      onSubmit={(event) => {
        event.preventDefault();
        move.mutate();
      }}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant={thenDeactivate ? "destructive" : "default"}
            disabled={!target || move.isPending}
          >
            <ArrowRightLeft />{" "}
            {move.isPending
              ? "Moving…"
              : thenDeactivate
                ? "Transfer and deactivate"
                : "Transfer"}
          </Button>
        </>
      }
    >
      <Field
        label="Takes over"
        help="Must approve the same stages. Only active approvers are listed."
      >
        <Listbox
          aria-label="Takes over"
          placeholder={staff.isLoading ? "Loading…" : "Choose a person"}
          value={target}
          onChange={setTarget}
          items={candidates.map((other) => ({
            value: other.id,
            label: `${label(other)} · ${other.roles.map((role) => role.name).join(", ")}`,
          }))}
        />
      </Field>
      <p className="text-xs text-muted-foreground">
        A facilitator&apos;s MPPs come from the ERP: move those there. For a few
        days only, use Temporary cover under Masters instead.
      </p>
    </FormDialog>
  );
}

// Own review steps --------------------------------------------------------------------

type StepState = {
  custom: boolean;
  steps: string[];
  role_steps: string[];
  eligible: string[];
  approves_all: boolean;
};
type StepsSettings = {
  steps: { key: string; number: number; title: string }[];
};

/** One person's own review steps, in place of what their roles give. */
function StaffSteps({
  person,
  onClose,
}: {
  person: Staff;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const url = `staff/${person.id}/review-steps`;
  const state = useQuery({
    queryKey: ["staff-steps", person.id],
    queryFn: () => api<StepState>(url),
  });
  const settings = useQuery({
    queryKey: ["review-steps"],
    queryFn: () => api<StepsSettings>("settings/review-steps"),
  });
  const [custom, setCustom] = useState<boolean | null>(null);
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  const isCustom = custom ?? state.data?.custom ?? false;
  const picked = chosen ?? state.data?.steps ?? [];
  const eligible = new Set(state.data?.eligible ?? []);

  const save = useMutation({
    mutationFn: (confirm: boolean) =>
      api<StepState>(url, {
        method: "PUT",
        body: { steps: isCustom ? picked : null, confirm },
      }),
    onSuccess: (saved) => {
      client.setQueryData(["staff-steps", person.id], saved);
      toast.success(
        saved.custom ? "Own steps saved." : "Back to the steps of their roles.",
      );
      onClose();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "steps_left_uncovered") {
        setWarning(error.message);
      }
    },
  });
  const failed =
    save.error instanceof ApiError && save.error.code === "steps_left_uncovered"
      ? null
      : save.error;

  return (
    <FormDialog
      title={`Review steps · ${label(person)}`}
      description="By default a person approves the steps their roles give. Choose their own to narrow it for them alone."
      onClose={onClose}
      error={failed}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          {warning ? (
            <Button
              type="button"
              variant="destructive"
              disabled={save.isPending}
              onClick={() => save.mutate(true)}
            >
              Save anyway
            </Button>
          ) : (
            <Button
              type="button"
              disabled={
                save.isPending ||
                !state.data ||
                (isCustom && picked.length === 0)
              }
              onClick={() => save.mutate(false)}
            >
              Save
            </Button>
          )}
        </>
      }
    >
      {state.data?.approves_all ? (
        <Alert>
          <AlertDescription>
            This person may approve every step anyway, as an administrator.
          </AlertDescription>
        </Alert>
      ) : null}
      {state.data && state.data.eligible.length === 0 ? (
        <Alert>
          <AlertDescription>
            They approve at no stage. Give them an approver role first.
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="space-y-1">
        <CheckRow
          label="Use the steps of their roles"
          hint={
            state.data?.role_steps.length
              ? `${state.data.role_steps.length} steps, set under Review Steps`
              : "None"
          }
          checked={!isCustom}
          onChange={(on) => {
            setCustom(!on);
            setWarning(null);
            if (!on && chosen === null) setChosen(state.data?.role_steps ?? []);
          }}
        />
      </div>
      <fieldset className="space-y-1.5" disabled={!isCustom}>
        <legend className="text-sm font-medium">Their steps</legend>
        <div className="border p-1">
          {(settings.data?.steps ?? []).map((step) => (
            <CheckRow
              key={step.key}
              label={`${step.number}. ${step.title}`}
              hint={
                eligible.has(step.key)
                  ? undefined
                  : "Not a step of the stages they approve"
              }
              checked={picked.includes(step.key)}
              disabled={!isCustom || !eligible.has(step.key)}
              onChange={(on) => {
                setWarning(null);
                setChosen(
                  on
                    ? [...picked, step.key]
                    : picked.filter((key) => key !== step.key),
                );
              }}
            />
          ))}
        </div>
      </fieldset>
      {warning ? (
        <Alert variant="destructive">
          <AlertDescription>
            {warning} Give these steps to someone else on their MPPs, or save
            anyway and their forms will wait for an administrator.
          </AlertDescription>
        </Alert>
      ) : null}
    </FormDialog>
  );
}

// One-time password -------------------------------------------------------------------

function TemporaryPassword({
  person,
  onClose,
}: {
  person: Staff;
  onClose: () => void;
}) {
  const reset = useMutation({
    mutationFn: () =>
      api<{ temporary_password: string }>(`staff/${person.id}/password-reset`, {
        method: "POST",
      }),
  });
  return (
    <FormDialog
      title={`Temporary password · ${label(person)}`}
      description="They are signed out everywhere and choose their own password at the next sign-in. Recorded in the audit log."
      onClose={onClose}
      error={reset.error}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            {reset.data ? "Done" : "Cancel"}
          </Button>
          {reset.data ? null : (
            <Button
              type="button"
              disabled={reset.isPending}
              onClick={() => reset.mutate()}
            >
              <KeyRound /> Set a temporary password
            </Button>
          )}
        </>
      }
    >
      {reset.data ? (
        <div className="space-y-1.5 border border-primary/30 bg-primary/5 p-3">
          <p className="text-sm font-medium">
            Shown only now. Give it to them directly.
          </p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 font-mono text-sm break-all">
              {reset.data.temporary_password}
            </code>
            <CopyButton value={reset.data.temporary_password} />
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Their current password stops working at once.
        </p>
      )}
    </FormDialog>
  );
}

function SimpleConfirm({
  title,
  description,
  action,
  destructive,
  onConfirm,
  onClose,
}: {
  title: string;
  description: string;
  action: string;
  destructive?: boolean;
  onConfirm: () => Promise<unknown>;
  onClose: () => void;
}) {
  const run = useMutation({ mutationFn: onConfirm, onSuccess: onClose });
  return (
    <FormDialog
      title={title}
      description={description}
      onClose={onClose}
      error={run.error}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            variant={destructive ? "destructive" : "default"}
            disabled={run.isPending}
            onClick={() => run.mutate()}
          >
            {action}
          </Button>
        </>
      }
    >
      <span className="sr-only">{description}</span>
    </FormDialog>
  );
}

// The row menu ------------------------------------------------------------------------

type Open =
  "transfer" | "leave" | "steps" | "password" | "mfa" | "active" | null;

export function StaffRowActions({
  person,
  onEdit,
}: {
  person: Staff;
  onEdit: (person: Staff) => void;
}) {
  const me = useMe();
  const refresh = useRefresh();
  const canManage = useCan("staff.manage");
  const canAssign = useCan("mpp.assign");
  const canSteps = useCan("settings.review_steps");
  const [open, setOpen] = useState<Open>(null);
  const self = person.email === me.email;
  const close = () => setOpen(null);

  if (!canManage && !canAssign && !canSteps) return null;
  return (
    // The row opens on click; the menu must not.
    <span
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Actions for ${label(person)}`}
            />
          }
        >
          <MoreHorizontal />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          {canManage ? (
            <DropdownMenuItem onClick={() => onEdit(person)}>
              <Pencil /> Edit details and roles
            </DropdownMenuItem>
          ) : null}
          {canSteps && approves(person) ? (
            <DropdownMenuItem onClick={() => setOpen("steps")}>
              <ListChecks /> Review steps
            </DropdownMenuItem>
          ) : null}
          {canAssign && person.is_active && !facilitatorOnly(person) ? (
            <DropdownMenuItem onClick={() => setOpen("transfer")}>
              <ArrowRightLeft /> Transfer work
            </DropdownMenuItem>
          ) : null}
          {canManage && !self ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setOpen("password")}>
                <KeyRound /> Set a temporary password
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setOpen("mfa")}>
                <ShieldOff /> Reset two-step sign-in
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {person.is_active && canAssign && approves(person) ? (
                <DropdownMenuItem
                  variant="destructive"
                  onClick={() => setOpen("leave")}
                >
                  <ArrowRightLeft /> Transfer work and deactivate
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuItem
                variant={person.is_active ? "destructive" : "default"}
                onClick={() => setOpen("active")}
              >
                <Power /> {person.is_active ? "Deactivate" : "Reactivate"}
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      {open === "transfer" ? (
        <TransferWork person={person} onClose={close} />
      ) : null}
      {open === "leave" ? (
        <TransferWork person={person} thenDeactivate onClose={close} />
      ) : null}
      {open === "steps" ? <StaffSteps person={person} onClose={close} /> : null}
      {open === "password" ? (
        <TemporaryPassword person={person} onClose={close} />
      ) : null}
      {open === "mfa" ? (
        <SimpleConfirm
          title={`Reset two-step sign-in · ${label(person)}`}
          description="Use this when someone loses their phone. They set it up again at their next sign-in."
          action="Reset"
          onConfirm={() =>
            api(`staff/${person.id}/mfa-reset`, { method: "POST" }).then(() =>
              toast.success("Two-step sign-in reset."),
            )
          }
          onClose={close}
        />
      ) : null}
      {open === "active" ? (
        <SimpleConfirm
          title={
            person.is_active
              ? `Deactivate ${label(person)}?`
              : `Reactivate ${label(person)}?`
          }
          description={
            person.is_active
              ? "They can no longer sign in, and their MCCs and MPPs are freed with nobody holding them. To hand them to someone, use Transfer work and deactivate."
              : "They can sign in again. MCCs and MPPs have to be given again."
          }
          action={person.is_active ? "Deactivate" : "Reactivate"}
          destructive={person.is_active}
          onConfirm={() =>
            api(`staff/${person.id}`, {
              method: "PATCH",
              body: { is_active: !person.is_active },
            }).then(() => {
              refresh();
              toast.success(person.is_active ? "Deactivated." : "Reactivated.");
            })
          }
          onClose={close}
        />
      ) : null}
    </span>
  );
}

// Import and export -------------------------------------------------------------------

type PlanRow = {
  row: number;
  full_name: string;
  email: string;
  mobile: string;
  roles: string[];
  mccs: string[];
  mpps: string[];
  action: "create" | "add" | "skip";
  problems: string[];
  notes: string[];
};
type Credential = {
  full_name: string;
  email: string;
  mobile: string;
  roles: string[];
  temporary_password: string;
};
type ImportResult = {
  rows: PlanRow[];
  create: number;
  add: number;
  skip: number;
  problems: number;
  credentials?: Credential[];
};

const ACTION: Record<PlanRow["action"], { status: string; label: string }> = {
  create: { status: "active", label: "New" },
  add: { status: "pending", label: "Add to this organization" },
  skip: { status: "draft", label: "Left out" },
};

function csv(rows: Credential[]) {
  const quote = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const lines = [
    ["Name", "Email", "Mobile", "Roles", "Temporary password"],
    ...rows.map((row) => [
      row.full_name,
      row.email,
      row.mobile,
      row.roles.join(", "),
      row.temporary_password,
    ]),
  ];
  return lines.map((line) => line.map(quote).join(",")).join("\r\n");
}

/** Downloads through the portal's own server, which holds the session. */
function download(href: string) {
  const link = document.createElement("a");
  link.href = href;
  link.download = "";
  link.click();
}

function saveCredentials(rows: Credential[]) {
  const url = URL.createObjectURL(new Blob([csv(rows)], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "staff_passwords.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export function ImportStaff({ onClose }: { onClose: () => void }) {
  const refresh = useRefresh();
  const [file, setFile] = useState<File | null>(null);
  const send = (chosen: File, preview: boolean) => {
    const body = new FormData();
    body.append("file", chosen);
    body.append("preview", preview ? "true" : "false");
    return api<ImportResult>("staff/import", { method: "POST", body });
  };
  const check = useMutation({
    mutationFn: (chosen: File) => send(chosen, true),
  });
  const run = useMutation({
    mutationFn: (chosen: File) => send(chosen, false),
    onSuccess: (result) => {
      if (!result.problems) {
        refresh();
        toast.success(`${result.create + result.add} people added.`);
      }
    },
  });
  const plan = run.data ?? check.data;
  const done = run.data && !run.data.problems;
  const credentials = run.data?.credentials ?? [];

  return (
    <FormDialog
      title="Import staff"
      description="From the staff template: one row per person. Checked first; nothing changes until you import, and a file with a mistake changes nothing."
      onClose={onClose}
      className="sm:max-w-4xl"
      error={check.error ?? run.error}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            {done ? "Done" : "Cancel"}
          </Button>
          {done ? (
            credentials.some((row) => row.temporary_password) ? (
              <Button
                type="button"
                onClick={() => saveCredentials(credentials)}
              >
                <Download /> Download passwords
              </Button>
            ) : null
          ) : (
            <Button
              type="button"
              disabled={
                !check.data ||
                !!check.data.problems ||
                check.data.create + check.data.add === 0 ||
                run.isPending
              }
              onClick={() => file && run.mutate(file)}
            >
              <Upload />{" "}
              {run.isPending
                ? "Importing…"
                : `Import ${check.data ? check.data.create + check.data.add : ""} people`}
            </Button>
          )}
        </>
      }
    >
      {done ? null : (
        <FileDrop
          label="Staff file"
          hint={
            <>
              An .xlsx in the staff template. Facilitators are left out: they
              come from the ERP.{" "}
              <button
                type="button"
                className="underline"
                onClick={() => download("/api/backend/staff/export?template=1")}
              >
                Download the template
              </button>
            </>
          }
          accept={[".xlsx"]}
          maxBytes={2 * 1024 * 1024}
          busy={check.isPending}
          onFile={(next) => {
            setFile(next);
            run.reset();
            // Checked at once, so mistakes show before anything else.
            check.mutate(next);
          }}
          onRemove={() => {
            setFile(null);
            check.reset();
            run.reset();
          }}
        />
      )}

      {done && credentials.length ? (
        <Alert>
          <AlertDescription>
            The one-time passwords are shown only now. Download them, and give
            each person their own. They choose a new password at the first
            sign-in. People who already had an account elsewhere keep their own
            password.
          </AlertDescription>
        </Alert>
      ) : null}

      {plan ? (
        <div className="space-y-2">
          <p className="text-sm">
            {plan.create} new · {plan.add} added from another organization ·{" "}
            {plan.skip} left out
            {plan.problems ? (
              <span className="font-medium text-destructive">
                {" "}
                · {plan.problems} with mistakes
              </span>
            ) : null}
          </p>
          <div className="max-h-[50dvh] overflow-auto border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted text-left text-xs text-muted-foreground">
                <tr>
                  <th className="p-2">Row</th>
                  <th className="p-2">Person</th>
                  <th className="p-2">Roles</th>
                  <th className="p-2">MCC / MPP</th>
                  <th className="p-2">
                    {done ? "Temporary password" : "What happens"}
                  </th>
                </tr>
              </thead>
              <tbody>
                {plan.rows.map((row) => {
                  const login = credentials.find(
                    (item) =>
                      item.email === row.email && item.mobile === row.mobile,
                  );
                  return (
                    <tr key={row.row} className="border-t align-top">
                      <td className="p-2 tabular-nums text-muted-foreground">
                        {row.row}
                      </td>
                      <td className="p-2">
                        <div className="font-medium">
                          {row.full_name || "—"}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {row.email || row.mobile}
                        </div>
                      </td>
                      <td className="p-2">{row.roles.join(", ")}</td>
                      <td className="p-2 text-xs">
                        {[
                          row.mccs.length ? `MCC ${row.mccs.join(", ")}` : "",
                          row.mpps.length ? `MPP ${row.mpps.join(", ")}` : "",
                        ]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </td>
                      <td className="space-y-1 p-2">
                        {done && login?.temporary_password ? (
                          <span className="flex items-center gap-1">
                            <code className="font-mono text-xs">
                              {login.temporary_password}
                            </code>
                            <CopyButton value={login.temporary_password} />
                          </span>
                        ) : row.problems.length ? (
                          <StatusBadge status="rejected" label="Mistake" />
                        ) : (
                          <StatusBadge
                            status={ACTION[row.action].status}
                            label={ACTION[row.action].label}
                          />
                        )}
                        {row.problems.map((problem) => (
                          <p key={problem} className="text-xs text-destructive">
                            {problem}
                          </p>
                        ))}
                        {row.notes.map((note) => (
                          <p
                            key={note}
                            className="text-xs text-muted-foreground"
                          >
                            {note}
                          </p>
                        ))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {plan.problems && !done ? (
            <p className="text-xs text-muted-foreground">
              Correct these rows in the file and choose it again.
            </p>
          ) : null}
        </div>
      ) : null}
    </FormDialog>
  );
}

/** Excel of everyone active, in the layout Import takes, or the empty template. */
export function StaffDownloads() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button type="button" variant="outline" />}>
        <FileSpreadsheet /> Excel
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem onClick={() => download("/api/backend/staff/export")}>
          <Download /> Download staff list
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => download("/api/backend/staff/export?template=1")}
        >
          <Download /> Download empty template
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
