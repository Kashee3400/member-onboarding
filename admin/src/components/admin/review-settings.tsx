"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ListChecks, Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Confirm } from "@/components/admin/confirm";
import { messageOf } from "@/components/admin/feedback";
import { FormDialog } from "@/components/admin/form-dialog";
import { Field } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/client";
import type { RejectReason, ReviewSettings } from "@/lib/types";

/** Without `checks`, the checklists stay as they are. */
type Body = Pick<ReviewSettings, "overdue_days" | "reject_reasons"> & { checks?: ReviewSettings["checks"] };

const MAX_CHECKS = 10;

/** Every change is saved at once: the list is sent whole, in the order shown. */
function useSave() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Body) => api<ReviewSettings>("settings/review", { method: "PUT", body }),
    onSuccess: (saved) => {
      client.setQueryData(["review-settings"], saved);
      client.invalidateQueries({ queryKey: ["reject-reasons"] });
    },
  });
}

function LateThreshold({ state }: { state: ReviewSettings }) {
  const [days, setDays] = useState(String(state.overdue_days));
  const save = useSave();
  const value = Number(days);
  const valid = Number.isInteger(value) && value >= 1 && value <= 60;

  return (
    <Card className="gap-4 p-5">
      <div>
        <h2 className="font-medium">Late forms</h2>
        <p className="text-sm text-muted-foreground">
          A form waiting longer than this at one stage is shown as late in queues and on the home page.
        </p>
      </div>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          save.mutate(
            { overdue_days: value, reject_reasons: state.reject_reasons },
            {
              onSuccess: () => toast.success("Late threshold saved."),
              onError: (error) => toast.error(messageOf(error)),
            },
          );
        }}
      >
        <Field label="Late after (days)" htmlFor="overdue-days" help="Between 1 and 60 days.">
          <Input
            id="overdue-days"
            type="number"
            min={1}
            max={60}
            className="w-32 tabular-nums"
            value={days}
            aria-invalid={!valid}
            onChange={(event) => setDays(event.target.value)}
          />
        </Field>
        <Button type="submit" disabled={!valid || value === state.overdue_days || save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </form>
    </Card>
  );
}

function ReasonDialog({
  state,
  initial,
  onClose,
  onSave,
}: {
  state: ReviewSettings;
  initial: RejectReason | null;
  onClose: () => void;
  onSave: (reason: RejectReason, done: () => void, fail: (error: unknown) => void) => void;
}) {
  const [text, setText] = useState(initial?.text ?? "");
  const [section, setSection] = useState(initial?.section ?? "");
  const [fields, setFields] = useState<string[]>(initial?.fields ?? []);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const markable = state.sections.find((item) => item.key === section)?.fields ?? [];

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!text.trim() || !section) return;
    setPending(true);
    onSave(
      { text: text.trim(), section, fields: fields.filter((path) => markable.some((field) => field.path === path)) },
      onClose,
      (failure) => {
        setPending(false);
        setError(failure);
      },
    );
  };

  return (
    <FormDialog
      title={initial ? "Edit reject reason" : "Add a reject reason"}
      description="Reviewers whose steps cover this section can pick it with one press."
      onClose={onClose}
      onSubmit={submit}
      error={error}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" disabled={!text.trim() || !section || pending}>
            {pending ? "Saving…" : "Save reason"}
          </Button>
        </>
      }
    >
      <Field label="Reason" htmlFor="reason-text" help="The facilitator sees these words.">
        <Input
          id="reason-text"
          maxLength={200}
          value={text}
          autoFocus
          onChange={(event) => setText(event.target.value)}
        />
      </Field>
      <Field label="Section">
        <Listbox
          aria-label="Section"
          placeholder="Choose a section"
          value={section}
          onChange={(value) => {
            setSection(value);
            setFields([]);
          }}
          items={state.sections.map((item) => ({
            value: item.key,
            text: `${item.title} ${item.step}`,
            label: item.title === item.step ? item.title : `${item.title} (${item.step})`,
          }))}
        />
      </Field>
      {markable.length ? (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">
            Fields it marks <span className="font-normal text-muted-foreground">optional</span>
          </legend>
          <div className="grid gap-x-3 gap-y-1.5 border p-3 sm:grid-cols-2">
            {markable.map((field) => (
              <label key={field.path} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={fields.includes(field.path)}
                  onCheckedChange={(on) =>
                    setFields((current) => (on ? [...current, field.path] : current.filter((path) => path !== field.path)))
                  }
                />
                <span className="truncate">{field.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : section ? (
        <p className="text-sm text-muted-foreground">This section has no fields to mark. The reason alone goes back.</p>
      ) : null}
    </FormDialog>
  );
}

function RejectReasons({ state }: { state: ReviewSettings }) {
  const save = useSave();
  const [editing, setEditing] = useState<{ index: number | null } | null>(null);
  const reasons = state.reject_reasons;
  const titles = Object.fromEntries(state.sections.map((item) => [item.key, item.title]));
  const labels = Object.fromEntries(state.sections.flatMap((item) => item.fields.map((field) => [field.path, field.label])));

  const store = (next: RejectReason[], message: string, done?: () => void, fail?: (error: unknown) => void) =>
    save.mutate(
      { overdue_days: state.overdue_days, reject_reasons: next },
      {
        onSuccess: () => {
          toast.success(message);
          done?.();
        },
        onError: (error) => (fail ? fail(error) : toast.error(messageOf(error))),
      },
    );

  const move = (index: number, by: number) => {
    const next = [...reasons];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    store(next, "Order saved.");
  };

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-medium">Reject reasons</h2>
          <p className="text-sm text-muted-foreground">
            The ready-made reasons a reviewer can pick when sending a form back, in this order. Each one shows only to
            those whose steps cover its section.
          </p>
        </div>
        <Button variant="outline" onClick={() => setEditing({ index: null })}>
          <Plus /> Add reason
        </Button>
      </div>
      {reasons.length ? (
        <ul className="divide-y border">
          {reasons.map((reason, index) => (
            <li key={reason.text} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{reason.text}</p>
                <p className="text-xs text-muted-foreground">
                  {titles[reason.section] ?? reason.section}
                  {reason.fields.length
                    ? ` · marks ${reason.fields.map((path) => labels[path] ?? path).join(", ")}`
                    : " · marks no fields"}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Move "${reason.text}" up`}
                  disabled={index === 0 || save.isPending}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Move "${reason.text}" down`}
                  disabled={index === reasons.length - 1 || save.isPending}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Edit "${reason.text}"`}
                  onClick={() => setEditing({ index })}
                >
                  <Pencil />
                </Button>
                <Confirm
                  trigger={
                    <Button variant="ghost" size="icon" aria-label={`Delete "${reason.text}"`} disabled={save.isPending}>
                      <Trash2 />
                    </Button>
                  }
                  title="Delete this reason?"
                  description={`"${reason.text}" will no longer be offered. Forms already sent back keep their reason.`}
                  action="Delete"
                  onConfirm={() => store(reasons.filter((_, other) => other !== index), "Reason deleted.")}
                />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="No ready-made reasons"
          description="Reviewers will type every reason. Add the problems you see most often."
        />
      )}
      {editing ? (
        <ReasonDialog
          state={state}
          initial={editing.index === null ? null : reasons[editing.index]}
          onClose={() => setEditing(null)}
          onSave={(reason, done, fail) => {
            const next =
              editing.index === null
                ? [...reasons, reason]
                : reasons.map((item, index) => (index === editing.index ? reason : item));
            store(next, editing.index === null ? "Reason added." : "Reason saved.", done, fail);
          }}
        />
      ) : null}
    </Card>
  );
}

function ChecklistDialog({
  step,
  initial,
  onClose,
  onSave,
}: {
  step: ReviewSettings["steps"][number];
  initial: string[];
  onClose: () => void;
  onSave: (checks: string[], done: () => void, fail: (error: unknown) => void) => void;
}) {
  const [text, setText] = useState(initial.join("\n"));
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const lowered = lines.map((line) => line.toLowerCase());
  const problem =
    lines.length > MAX_CHECKS
      ? `Keep it to ${MAX_CHECKS} checks or fewer.`
      : lines.some((line) => line.length > 200)
        ? "Keep each check under 200 letters."
        : new Set(lowered).size !== lowered.length
          ? "Each check must be different."
          : null;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (problem) return;
    setPending(true);
    onSave(lines, onClose, (failure) => {
      setPending(false);
      setError(failure);
    });
  };

  return (
    <FormDialog
      title={`Checklist for step ${step.number}, ${step.title}`}
      description="The reviewer ticks every check before approving this step. The ticked checks are kept with the approval."
      onClose={onClose}
      onSubmit={submit}
      error={error}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" disabled={!!problem || pending}>
            {pending ? "Saving…" : "Save checklist"}
          </Button>
        </>
      }
    >
      <Field
        label="Checks"
        htmlFor="checklist-text"
        help={
          problem ? (
            <span className="text-destructive">{problem}</span>
          ) : (
            `One check per line, up to ${MAX_CHECKS}. Short and concrete: "Name matches the passbook". Leave it empty for no checklist.`
          )
        }
      >
        <Textarea
          id="checklist-text"
          rows={6}
          value={text}
          autoFocus
          aria-invalid={!!problem}
          onChange={(event) => setText(event.target.value)}
        />
      </Field>
      <p className="text-xs text-muted-foreground tabular-nums">
        {lines.length ? `${lines.length} ${lines.length === 1 ? "check" : "checks"}` : "No checklist"}
      </p>
    </FormDialog>
  );
}

function Checklists({ state }: { state: ReviewSettings }) {
  const save = useSave();
  const [editing, setEditing] = useState<string | null>(null);
  const step = state.steps.find((item) => item.key === editing) ?? null;

  return (
    <Card className="gap-4 p-5">
      <div>
        <h2 className="font-medium">Step checklists</h2>
        <p className="text-sm text-muted-foreground">
          What a reviewer must tick on each step before approving it. Every reviewer checks the same things, and the
          approval keeps what was ticked.
        </p>
      </div>
      <ul className="divide-y border">
        {state.steps.map((item) => {
          const checks = state.checks[item.key] ?? [];
          return (
            <li key={item.key} className="flex items-start gap-3 px-3 py-2.5">
              <span className="mt-0.5 w-5 shrink-0 text-sm text-muted-foreground tabular-nums">{item.number}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{item.title}</p>
                {checks.length ? (
                  <ul className="mt-1 space-y-0.5">
                    {checks.map((check) => (
                      <li key={check} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                        <ListChecks className="mt-px size-3.5 shrink-0" aria-hidden /> {check}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-muted-foreground">No checklist. The step is approved without one.</p>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Edit the checklist for ${item.title}`}
                onClick={() => setEditing(item.key)}
              >
                <Pencil />
              </Button>
            </li>
          );
        })}
      </ul>
      {step ? (
        <ChecklistDialog
          step={step}
          initial={state.checks[step.key] ?? []}
          onClose={() => setEditing(null)}
          onSave={(checks, done, fail) =>
            save.mutate(
              {
                overdue_days: state.overdue_days,
                reject_reasons: state.reject_reasons,
                checks: { ...state.checks, [step.key]: checks },
              },
              {
                onSuccess: () => {
                  toast.success(`Checklist for ${step.title} saved.`);
                  done();
                },
                onError: fail,
              },
            )
          }
        />
      ) : null}
    </Card>
  );
}

/** The late threshold, the reject reasons and the step checklists, all kept per organization. */
export function ReviewSettingsCards() {
  const state = useQuery({
    queryKey: ["review-settings"],
    queryFn: () => api<ReviewSettings>("settings/review"),
  });

  if (state.error) return <ErrorState error={state.error} onRetry={() => state.refetch()} />;
  if (!state.data) return <ListSkeleton rows={4} />;
  return (
    <>
      <LateThreshold key={`late-${state.data.overdue_days}`} state={state.data} />
      <Checklists state={state.data} />
      <RejectReasons state={state.data} />
    </>
  );
}
