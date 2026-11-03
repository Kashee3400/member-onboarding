"use client";

import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { DoubleConfirm } from "@/components/common/double-confirm";
import { Kbd } from "@/components/shell/shortcuts-help";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, type Page } from "@/lib/api/client";
import { isTyping } from "@/lib/shortcuts";
import type { ApplicationDetail, ApplicationSummary, FormSchema, ReviewStep } from "@/lib/types";

import { STAGE_LABEL, STAGE_QUEUE } from "./constants";
import { checksKey, unticked } from "./step-checklist";
import { MarkedSummary, carriedMarks, useFieldMarkState, useRejectReasons } from "./field-marks";

const message = (error: unknown) => (error instanceof ApiError ? error.summary : "Something went wrong. Try again.");

/**
 * The decision, always in reach at the foot of the screen. Approve works on the step
 * on screen, one at a time, and then the next open step shows. Once the stage is done
 * the next oldest form opens, so a queue never has to be gone back to. A and R work
 * from the keyboard, and D too, matching the queue.
 */
export function DecisionBar({
  application,
  schema,
  blocked,
  current,
  onApproved,
}: {
  application: ApplicationDetail;
  schema: FormSchema;
  /** Why approving can't happen yet. */
  blocked: string | null;
  /** The step on screen, when it is one of this person's. */
  current: ReviewStep | null;
  /** A step was approved and the form stays at this stage: show the next one. */
  onApproved: (step: string) => void;
}) {
  const id = application.id;
  const stage = STAGE_LABEL[application.status];
  const open = application.review_steps.filter((step) => step.can_approve);
  const left = application.review_steps.filter((step) => !step.approved_at).length;
  const router = useRouter();
  const params = useSearchParams();
  const client = useQueryClient();
  const [approving, setApproving] = useState(false);
  const [checked, setChecked] = useState(false);
  const [rejecting, setRejecting] = useState(params.get("reject") === "1");
  const target = current?.can_approve ? current : null;
  const saving = useIsMutating({ mutationKey: checksKey(id) }) > 0;
  const toTick = target ? unticked(target).length : 0;
  // The fee waits for its payment; any step with a checklist waits for every tick.
  const targetBlocked =
    (target?.key === "fee" ? blocked : null) ??
    (toTick
      ? `Tick every check of step ${target?.number} before approving: ${toTick} of ${target?.checks.length} left.`
      : saving
        ? "Saving your ticks…"
        : null);
  // The last step left on the whole form: approving it makes the member.
  const finishes = application.status === "pending_finance" && left === 1 && !!target;
  const mySections = application.review_steps.filter((step) => step.mine).flatMap((step) => step.sections);
  const markState = useFieldMarkState();
  // What was marked on the form goes with a rejection, each field with its reason.
  const carried = markState ? carriedMarks(markState.marks, mySections) : [];

  const decide = useMutation({
    mutationFn: (body: object) => api<ApplicationDetail>(`applications/${id}/decide`, { method: "POST", body }),
    onSuccess: async (result, body) => {
      const rejected = (body as { decision: string }).decision === "rejected";
      if (!rejected && result.status === application.status) {
        const done = (body as { steps: string[] }).steps[0];
        const step = application.review_steps.find((item) => item.key === done);
        toast.success(step ? `Step ${step.number}, ${step.title}, approved.` : "Step approved.");
        client.invalidateQueries({ queryKey: ["queue"] });
        client.invalidateQueries({ queryKey: ["application", id] });
        onApproved(done);
        return;
      }
      toast.success(
        rejected
          ? "Rejected. It has gone back to the facilitator."
          : result.tr_code
            ? `Approved. Member code ${result.tr_code}`
            : `All your steps are approved. The form moves on from ${stage}.`,
        { duration: result.tr_code ? 10_000 : 4000 },
      );
      client.invalidateQueries({ queryKey: ["queue"] });
      client.invalidateQueries({ queryKey: ["application", id] });
      const waiting = await api<Page<ApplicationSummary>>("applications", {
        query: { status: application.status, ordering: "waiting_since", page_size: 2 },
      }).catch(() => null);
      const next = waiting?.results.find((row) => row.id !== id);
      router.push(next ? `/applications/${next.id}` : STAGE_QUEUE[application.status]);
    },
    onError: (error, body) => {
      if ((body as { decision: string }).decision === "approved") toast.error(message(error));
    },
  });

  const askApproval = () => {
    if (!target) {
      if (open.length) onApproved(current?.key ?? "");
      else toast.error("None of your steps are open on this form.");
      return;
    }
    if (targetBlocked) {
      toast.error(targetBlocked);
      return;
    }
    setChecked(false);
    setApproving(true);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event) || event.metaKey || event.ctrlKey || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "a") {
        event.preventDefault();
        askApproval();
      } else if (key === "r" || key === "d") {
        event.preventDefault();
        setRejecting(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const yours = application.review_steps.filter((step) => step.mine);
  const doneOfYours = yours.filter((step) => step.approved_at).length;

  return (
    <>
      <div className="sticky bottom-0 z-20 md:bottom-10 -mx-4 -mb-4 border-t bg-background/90 px-4 py-2.5 backdrop-blur md:-mx-6 md:-mb-6 md:px-6">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="min-w-0 flex-1 text-sm">
            {targetBlocked ? (
              <span className="text-amber-700 dark:text-amber-300">{targetBlocked}</span>
            ) : target ? (
              <span>
                <span className="font-medium">
                  Step {target.number}: {target.title}
                </span>{" "}
                <span className="text-muted-foreground">
                  · {open.length === 1 ? "your last open step" : `${open.length} of your steps open`}
                </span>
              </span>
            ) : open.length ? (
              <span className="font-medium">
                This step is done. {open.length}{" "}
                {open.length === 1 ? "step is" : "steps are"} still yours to approve.
              </span>
            ) : (
              <span className="font-medium">Your steps are done.</span>
            )}
            {yours.length ? (
              <div className="mt-1 flex items-center gap-2" aria-hidden>
                <div className="h-1 w-32 bg-muted">
                  <div
                    className="h-full bg-emerald-500 transition-[width] duration-500"
                    style={{ width: `${(doneOfYours / yours.length) * 100}%` }}
                  />
                </div>
                <span className="text-[11px] text-muted-foreground tabular-nums">
                  {doneOfYours} of {yours.length} of your steps approved
                </span>
              </div>
            ) : null}
            <MarkedSummary onReject={() => setRejecting(true)} />
          </div>
          <div className="flex items-center gap-2 max-sm:w-full [&>*]:max-sm:flex-1">
            <Button
              variant="outline"
              className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={() => setRejecting(true)}
            >
              <X /> Reject <Kbd className="ml-1 hidden sm:inline-flex">R</Kbd>
            </Button>
            <Button onClick={askApproval} disabled={!open.length || !!targetBlocked}>
              {target ? (
                <>
                  <Check /> Approve step {target.number}
                </>
              ) : (
                <>
                  <ArrowRight /> Next open step
                </>
              )}
              <Kbd className="ml-1 hidden border-primary-foreground/30 bg-primary-foreground/15 text-primary-foreground sm:inline-flex">
                A
              </Kbd>
            </Button>
          </div>
        </div>
      </div>

      <DoubleConfirm
        open={approving}
        onOpenChange={setApproving}
        title={target ? `Approve step ${target.number}, ${target.title}?` : "Approve this step?"}
        description={
          target?.checks.length
            ? "What you ticked is kept with the approval, under your name."
            : "Approve only after checking it against the documents."
        }
        body={
          target?.checks.length ? (
            <ul className="space-y-1 border px-3 py-2.5 text-sm">
              {target.checks.map((check) => (
                <li key={check} className="flex items-start gap-2">
                  <Check className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden />
                  {check}
                </li>
              ))}
            </ul>
          ) : (
            <label className="flex items-start gap-3 border px-3 py-2.5 text-sm">
              <Checkbox className="mt-0.5" checked={checked} onCheckedChange={(on) => setChecked(!!on)} />
              <span>I checked every detail of this step against the documents and photos.</span>
            </label>
          )
        }
        canContinue={!!target?.checks.length || checked}
        finalTitle={finishes ? "Give final approval?" : "Are you sure?"}
        finalDescription={
          finishes
            ? `${application.applicant_name} becomes a member and gets a member code. This can't be undone.`
            : `You are approving step ${target?.number} of ${application.applicant_name}'s form under your name. This can't be undone.`
        }
        action={finishes ? "Create member" : "Yes, approve"}
        onConfirm={() => target && decide.mutate({ decision: "approved", steps: [target.key] })}
      />

      <RejectDialog
        // Opens filled with the latest marks; edits made in it start again when they change.
        key={carried.map((row) => `${row.path}:${row.reason}`).join("|")}
        open={rejecting}
        onOpenChange={setRejecting}
        schema={schema}
        // The step on screen, when it is one of theirs: its own fields and reasons only.
        mySections={current?.mine ? current.sections : mySections}
        step={current?.mine ? current : null}
        marks={carried}
        pending={decide.isPending}
        error={decide.isError && rejecting ? message(decide.error) : null}
        onReject={(reason, fields, notes) =>
          decide.mutate({ decision: "rejected", reason, rejected_fields: fields, field_notes: notes })
        }
      />
    </>
  );
}

function RejectDialog({
  open,
  onOpenChange,
  schema,
  mySections,
  step,
  marks,
  pending,
  error,
  onReject,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  schema: FormSchema;
  /** The sections being rejected: the step on screen, or all of this person's steps. */
  mySections: string[];
  /** The step on screen, named in the dialog so it is clear what is being sent back. */
  step: ReviewStep | null;
  /** Fields marked wrong on the form, each with its reason. */
  marks: { path: string; label: string; reason: string }[];
  pending: boolean;
  error: string | null;
  onReject: (reason: string, fields: string[], notes: Record<string, string>) => void;
}) {
  const [note, setNote] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>(() =>
    Object.fromEntries(marks.map((mark) => [mark.path, mark.reason])),
  );
  const noted = marks.filter((mark) => mark.path in notes);
  const [picked, setPicked] = useState<string[]>([]);
  const [marked, setMarked] = useState<string[]>([]);
  const box = useRef<HTMLTextAreaElement>(null);
  const known = new Set(schema.sections.flatMap((section) => section.fields.map((field) => `${section.key}.${field.key}`)));
  const offered = useRejectReasons();
  const reasons = (offered.data ?? []).filter((item) => mySections.includes(item.section));
  const chosen = reasons.filter((item) => picked.includes(item.text));
  const fields = [
    ...new Set([
      ...Object.keys(notes),
      ...marked,
      ...chosen.flatMap((item) => item.fields.filter((path) => known.has(path))),
    ]),
  ];
  const reason = [...chosen.map((item) => item.text), note.trim()].filter(Boolean).join(". ");
  // A reason, or at least one marked field: each mark says what is wrong with it.
  const ok = (reason.length > 0 || noted.length > 0) && !pending;
  const sections = schema.sections
    .filter((section) => mySections.includes(section.key))
    .map((section) => ({ ...section, fields: section.fields.filter((field) => field.required) }))
    .filter((section) => section.fields.length);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Header and buttons stay put; a long list of reasons and fields scrolls between them. */}
      <DialogContent
        className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] sm:max-w-lg"
        initialFocus={box}
      >
        <DialogHeader>
          <DialogTitle>{step ? `Reject at step ${step.number}: ${step.title}` : "Reject this form"}</DialogTitle>
          <DialogDescription>It goes straight back to the facilitator, and starts again from the Area Manager.</DialogDescription>
        </DialogHeader>
        <div className="-mx-4 min-w-0 space-y-4 overflow-y-auto px-4">
          {noted.length ? (
            <div className="space-y-2">
              <p className="text-sm font-medium">
                Marked on the form <span className="font-normal text-muted-foreground">{noted.length}</span>
              </p>
              <ul className="space-y-2">
                {noted.map((mark) => (
                  <li key={mark.path} className="space-y-1">
                    <Label htmlFor={`note-${mark.path}`} className="text-xs text-destructive">
                      {mark.label}
                    </Label>
                    <div className="flex items-center gap-1.5">
                      <Input
                        id={`note-${mark.path}`}
                        value={notes[mark.path]}
                        maxLength={300}
                        onChange={(event) => setNotes({ ...notes, [mark.path]: event.target.value })}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Leave out ${mark.label}`}
                        title="Leave out of this rejection"
                        onClick={() =>
                          setNotes(Object.fromEntries(Object.entries(notes).filter(([path]) => path !== mark.path)))
                        }
                      >
                        <X />
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {reasons.length ? (
            <div className="space-y-2">
              <p className="text-sm font-medium">What is wrong?</p>
              <div className="flex flex-wrap gap-1.5">
                {reasons.map((item) => {
                  const on = picked.includes(item.text);
                  return (
                    <button
                      key={item.text}
                      type="button"
                      aria-pressed={on}
                      onClick={() =>
                        setPicked((current) => (on ? current.filter((text) => text !== item.text) : [...current, item.text]))
                      }
                      className={
                        on
                          ? "border border-destructive bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          : "border px-2 py-1 text-xs text-muted-foreground outline-none hover:border-foreground/30 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
                      }
                    >
                      {item.text}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="reject-reason">
              {reasons.length || noted.length ? "Anything else" : "Reason"}
              {noted.length ? <span className="font-normal text-muted-foreground">(optional)</span> : null}
            </Label>
            <Textarea
              ref={box}
              id="reject-reason"
              rows={reasons.length ? 2 : 3}
              className="h-20 resize-none overflow-y-auto [field-sizing:fixed]"
              value={note}
              placeholder="What needs correcting? The facilitator sees this."
              onChange={(event) => setNote(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && ok) {
                  event.preventDefault();
                  onReject(reason, fields, notes);
                }
              }}
            />
          </div>
          <div className="space-y-2">
            <p className="text-sm font-medium">
              {reasons.length ? "Other fields to correct" : "Fields to correct"}{" "}
              <span className="font-normal text-muted-foreground">
                {fields.length ? `${fields.length} marked` : "optional"}
              </span>
            </p>
            <div className="max-h-56 space-y-3 overflow-y-auto border p-3">
              {sections.map((section) => (
                <fieldset key={section.key} className="space-y-1.5">
                  <legend className="text-xs font-medium text-muted-foreground">{section.title}</legend>
                  <div className="grid gap-x-3 gap-y-1.5 sm:grid-cols-2">
                    {section.fields.map((field) => {
                      const path = `${section.key}.${field.key}`;
                      return (
                        <label key={path} className="flex items-center gap-2 text-sm">
                          <Checkbox
                            disabled={!marked.includes(path) && fields.includes(path)}
                            checked={fields.includes(path)}
                            onCheckedChange={(checked) =>
                              setMarked(checked ? [...marked, path] : marked.filter((item) => item !== path))
                            }
                          />
                          <span className="truncate">{field.label}</span>
                        </label>
                      );
                    })}
                  </div>
                </fieldset>
              ))}
            </div>
          </div>
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancel
          </Button>
          <Button variant="destructive" disabled={!ok} onClick={() => onReject(reason, fields, notes)}>
            {pending ? "Rejecting…" : "Reject form"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
