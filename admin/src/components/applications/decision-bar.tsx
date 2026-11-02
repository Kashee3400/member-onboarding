"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { DoubleConfirm } from "@/components/common/double-confirm";
import { Kbd } from "@/components/shell/shortcuts-help";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import type { ApplicationDetail, ApplicationSummary, FormSchema } from "@/lib/types";

import { STAGE_LABEL, STAGE_QUEUE } from "./constants";

const message = (error: unknown) => (error instanceof ApiError ? error.summary : "Something went wrong. Try again.");

/**
 * The decision, always in reach at the foot of the screen. A and R work from the
 * keyboard, and D too, matching the queue. Afterwards the next oldest form opens,
 * so someone working through a queue never has to go back to it.
 */
export function DecisionBar({
  application,
  schema,
  blocked,
}: {
  application: ApplicationDetail;
  schema: FormSchema;
  /** Why approving can't happen yet. */
  blocked: string | null;
}) {
  const id = application.id;
  const stage = STAGE_LABEL[application.status];
  const open = application.review_steps.filter((step) => step.can_approve);
  const left = application.review_steps.filter((step) => !step.approved_at).length;
  const router = useRouter();
  const params = useSearchParams();
  const client = useQueryClient();
  const [approving, setApproving] = useState(false);
  const [checked, setChecked] = useState<string[]>([]);
  // Every step left on the form is one of these, so this approval makes the member.
  const finishes = application.status === "pending_finance" && checked.length === left;
  const [rejecting, setRejecting] = useState(params.get("reject") === "1");

  const decide = useMutation({
    mutationFn: (body: object) => api<ApplicationDetail>(`applications/${id}/decide`, { method: "POST", body }),
    onSuccess: async (result, body) => {
      const rejected = (body as { decision: string }).decision === "rejected";
      if (!rejected && result.status === application.status) {
        toast.success(checked.length === 1 ? "Step approved." : `${checked.length} steps approved.`);
        client.invalidateQueries({ queryKey: ["queue"] });
        client.invalidateQueries({ queryKey: ["application", id] });
        return;
      }
      toast.success(
        rejected
          ? "Rejected. It has gone back to the facilitator."
          : result.tr_code
            ? `Approved. Member code ${result.tr_code}`
            : `Approved as ${stage}.`,
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

  const canTick = (key: string) => key !== "fee" || !blocked;
  const askApproval = () => {
    const ready = open.filter((step) => canTick(step.key));
    if (!ready.length) {
      toast.error(blocked ?? "None of your steps are open on this form.");
      return;
    }
    setChecked([]);
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

  return (
    <>
      <div className="sticky bottom-0 z-20 md:bottom-10 -mx-4 -mb-4 border-t bg-background/90 px-4 py-2.5 backdrop-blur md:-mx-6 md:-mb-6 md:px-6">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <p className="min-w-0 flex-1 text-sm">
            {blocked ? (
              <span className="text-amber-700 dark:text-amber-300">{blocked}</span>
            ) : (
              <>
                <span className="font-medium">
                  {open.length
                    ? `${open.length} ${open.length === 1 ? "step" : "steps"} for you to approve.`
                    : "Your steps are done."}
                </span>{" "}
                <span className="hidden text-muted-foreground xl:inline">
                  {left} of {application.review_steps.length} steps left on this form.
                </span>
              </>
            )}
          </p>
          <div className="flex items-center gap-2 max-sm:w-full [&>*]:max-sm:flex-1">
            <Button
              variant="outline"
              className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={() => setRejecting(true)}
            >
              <X /> Reject <Kbd className="ml-1 hidden sm:inline-flex">R</Kbd>
            </Button>
            <Button onClick={askApproval} disabled={!open.length}>
              <Check /> Approve{" "}
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
        title="Which steps have you checked?"
        description="Tick each step you checked against the documents. The rest stay open for later."
        body={
          <ul className="divide-y border">
            {open.map((step) => (
              <li key={step.key}>
                <label className="flex items-start gap-3 px-3 py-2.5 text-sm">
                  <Checkbox
                    className="mt-0.5"
                    disabled={!canTick(step.key)}
                    checked={checked.includes(step.key)}
                    onCheckedChange={(on) =>
                      setChecked((current) =>
                        on ? [...current, step.key] : current.filter((key) => key !== step.key),
                      )
                    }
                  />
                  <span className="min-w-0">
                    <span className="block font-medium">
                      {step.number}. {step.title}
                    </span>
                    {canTick(step.key) ? null : (
                      <span className="block text-xs text-amber-700 dark:text-amber-300">{blocked}</span>
                    )}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        }
        canContinue={checked.length > 0}
        finalTitle={finishes ? "Give final approval?" : "Are you sure?"}
        finalDescription={
          finishes
            ? `${application.applicant_name} becomes a member and gets a member code. This can't be undone.`
            : `You are approving ${checked.length} ${checked.length === 1 ? "step" : "steps"} of ${application.applicant_name}'s form under your name. This can't be undone.`
        }
        action={finishes ? "Create member" : "Yes, approve"}
        onConfirm={() => decide.mutate({ decision: "approved", steps: checked })}
      />

      <RejectDialog
        open={rejecting}
        onOpenChange={setRejecting}
        schema={schema}
        mySections={application.review_steps.filter((step) => step.mine).flatMap((step) => step.sections)}
        pending={decide.isPending}
        error={decide.isError && rejecting ? message(decide.error) : null}
        onReject={(reason, fields) => decide.mutate({ decision: "rejected", reason, rejected_fields: fields })}
      />
    </>
  );
}

/** The usual problems, one press each. Each marks the fields the facilitator must fix. */
const REASONS: { text: string; section: string; fields: string[] }[] = [
  { text: "Name does not match the Aadhaar card", section: "applicant", fields: ["applicant.full_name"] },
  { text: "Date of birth does not match the Aadhaar card", section: "applicant", fields: ["applicant.date_of_birth"] },
  { text: "Father / husband name does not match the Aadhaar card", section: "applicant", fields: ["applicant.relation_name"] },
  { text: "Aadhaar photo is unclear or cut off", section: "applicant", fields: [] },
  { text: "Member photo is unclear", section: "applicant", fields: [] },
  { text: "Member signature is missing or unclear", section: "applicant", fields: [] },
  { text: "Mobile number is wrong", section: "address", fields: ["address.mobile"] },
  { text: "Address is incomplete", section: "address", fields: ["address.post_office", "address.pincode"] },
  { text: "Milk figures do not look right", section: "animals", fields: ["animals.production_lpd", "animals.consumption_lpd"] },
  { text: "Name does not match the passbook", section: "bank", fields: ["bank.holder_name"] },
  { text: "IFSC does not match the passbook", section: "bank", fields: ["bank.ifsc"] },
  { text: "Passbook photo is unclear", section: "bank", fields: [] },
  { text: "Household members are missing", section: "family", fields: [] },
  { text: "Nominee details are incomplete", section: "nominee", fields: ["nominee.name", "nominee.relation", "nominee.date_of_birth"] },
  { text: "Payment slip is missing or does not match", section: "payment", fields: [] },
];

function RejectDialog({
  open,
  onOpenChange,
  schema,
  mySections,
  pending,
  error,
  onReject,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  schema: FormSchema;
  /** The sections of this person's own steps: the problems they can send back. */
  mySections: string[];
  pending: boolean;
  error: string | null;
  onReject: (reason: string, fields: string[]) => void;
}) {
  const [note, setNote] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [marked, setMarked] = useState<string[]>([]);
  const box = useRef<HTMLTextAreaElement>(null);
  const known = new Set(schema.sections.flatMap((section) => section.fields.map((field) => `${section.key}.${field.key}`)));
  const reasons = REASONS.filter((item) => mySections.includes(item.section));
  const chosen = reasons.filter((item) => picked.includes(item.text));
  const fields = [...new Set([...marked, ...chosen.flatMap((item) => item.fields.filter((path) => known.has(path)))])];
  const reason = [...chosen.map((item) => item.text), note.trim()].filter(Boolean).join(". ");
  const ok = reason.length > 0 && !pending;
  const sections = schema.sections
    .map((section) => ({ ...section, fields: section.fields.filter((field) => field.required) }))
    .filter((section) => section.fields.length);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" initialFocus={box}>
        <DialogHeader>
          <DialogTitle>Reject this form</DialogTitle>
          <DialogDescription>It goes straight back to the facilitator, and starts again from the Area Manager.</DialogDescription>
        </DialogHeader>
        <div className="min-w-0 space-y-4">
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
            <Label htmlFor="reject-reason">{reasons.length ? "Anything else" : "Reason"}</Label>
            <Textarea
              ref={box}
              id="reject-reason"
              rows={reasons.length ? 2 : 3}
              value={note}
              placeholder="What needs correcting? The facilitator sees this."
              onChange={(event) => setNote(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && ok) {
                  event.preventDefault();
                  onReject(reason, fields);
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
          <Button variant="destructive" disabled={!ok} onClick={() => onReject(reason, fields)}>
            {pending ? "Rejecting…" : "Reject form"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
