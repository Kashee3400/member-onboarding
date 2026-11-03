"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, X } from "lucide-react";
import { createContext, useContext, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api/client";
import type { ApplicationDetail, FieldMark, RejectReason } from "@/lib/types";
import { cn } from "@/lib/utils";

const MAX_REASON = 300;

export const sectionOf = (path: string) => path.split(".")[0];

/** Markable parts of the form that are not fields of its schema. */
export const EXTRA_LABELS: Record<string, string> = {
  "applicant.aadhaar_number": "Aadhaar number",
  "bank.account_number": "Account number",
  family: "Household members",
};

/** The usual problems, as the organization set them under Review Steps. Shared with the reject dialog. */
export function useRejectReasons(enabled = true) {
  return useQuery({
    queryKey: ["reject-reasons"],
    queryFn: () => api<RejectReason[]>("applications/reject-reasons"),
    staleTime: 10 * 60_000,
    enabled,
  });
}

export type FieldMarks = {
  marks: FieldMark[];
  /** The sections of this person's own steps. Only their fields can be marked. */
  mySections: string[];
  canMark: (path: string) => boolean;
  save: (path: string, reason: string) => Promise<unknown>;
  remove: (mark: FieldMark) => Promise<unknown>;
  /** Shows the step a marked field is on. */
  open: (path: string) => void;
};

const Context = createContext<FieldMarks | null>(null);
export const FieldMarksProvider = Context.Provider;
export const useFieldMarkState = () => useContext(Context);

/**
 * Fields marked wrong on this submission, kept on the server so they outlast a reload
 * and everyone on the stage sees them. Each person changes only their own.
 */
export function useFieldMarks(
  application: ApplicationDetail | undefined,
  { visible, reviewing }: { visible: boolean; reviewing: boolean },
): Omit<FieldMarks, "open"> {
  const id = application?.id ?? "";
  const client = useQueryClient();
  const key = ["field-marks", id, application?.revision];
  const query = useQuery({
    queryKey: key,
    queryFn: () => api<FieldMark[]>(`applications/${id}/marks`),
    enabled: visible && !!id,
  });
  const done = (marks: FieldMark[]) => client.setQueryData(key, marks);
  const save = useMutation({
    mutationFn: ({ path, reason }: { path: string; reason: string }) =>
      api<FieldMark[]>(`applications/${id}/marks`, { method: "PUT", body: { path, reason } }),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: (mark: FieldMark) => api<FieldMark[]>(`applications/${id}/marks/${mark.id}`, { method: "DELETE" }),
    onSuccess: done,
    onError: (error) => toast.error(error instanceof ApiError ? error.summary : "The mark was not removed. Try again."),
  });
  const mySections = (application?.review_steps ?? []).filter((step) => step.mine).flatMap((step) => step.sections);
  return {
    marks: visible ? (query.data ?? []) : [],
    mySections,
    canMark: (path) => visible && reviewing && mySections.includes(sectionOf(path)),
    save: (path, reason) => save.mutateAsync({ path, reason }),
    remove: (mark) => remove.mutateAsync(mark),
  };
}

/** One row per field, with every reviewer's reason joined: what a rejection carries. */
export function carriedMarks(marks: FieldMark[], sections: string[]) {
  const rows = new Map<string, { path: string; label: string; reasons: string[] }>();
  for (const mark of marks) {
    if (!sections.includes(sectionOf(mark.path))) continue;
    const row = rows.get(mark.path) ?? { path: mark.path, label: mark.label, reasons: [] };
    if (!row.reasons.includes(mark.reason)) row.reasons.push(mark.reason);
    rows.set(mark.path, row);
  }
  return [...rows.values()].map((row) => ({ path: row.path, label: row.label, reason: row.reasons.join("; ") }));
}

/** The marks on one field. */
export function useMarksOn(path: string | undefined) {
  const state = useFieldMarkState();
  return path && state ? state.marks.filter((mark) => mark.path === path) : [];
}

/** Under a field: why it was marked, and by whom. */
export function MarkNotes({ marks, note }: { marks: FieldMark[]; note?: string }) {
  if (!marks.length && !note) return null;
  return (
    <ul className="space-y-0.5 text-xs text-destructive">
      {note ? (
        <li className="flex items-start gap-1">
          <X className="mt-0.5 size-3 shrink-0" /> {note}
        </li>
      ) : null}
      {marks.map((mark) => (
        <li key={mark.id} className="flex items-start gap-1">
          <X className="mt-0.5 size-3 shrink-0" />
          <span className="min-w-0 wrap-break-word">
            {mark.reason} <span className="text-muted-foreground">· {mark.mine ? "you" : mark.marked_by_name}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * The small ✗ at the end of a field box. It opens a box for the reason, with the
 * organization's ready-made reasons for this section to pick from.
 */
export function MarkButton({ path, label }: { path: string; label: string }) {
  const state = useFieldMarkState();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const reasons = useRejectReasons(open);
  if (!state?.canMark(path)) return null;

  const marks = state.marks.filter((mark) => mark.path === path);
  const mine = marks.find((mark) => mark.mine);
  const section = sectionOf(path);
  // Reasons that name this very field come first.
  const offered = (reasons.data ?? [])
    .filter((item) => item.section === section)
    .sort((a, b) => Number(b.fields.includes(path)) - Number(a.fields.includes(path)));
  const reason = text.trim();

  const run = async (work: () => Promise<unknown>, failed: string) => {
    setSaving(true);
    try {
      await work();
      setOpen(false);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.summary : failed);
    } finally {
      setSaving(false);
    }
  };
  const submit = () => reason && run(() => state.save(path, reason), "The mark was not saved. Try again.");

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (next) setText(mine?.reason ?? "");
        setOpen(next);
      }}
    >
      <PopoverTrigger
        aria-label={mine ? `Change why ${label} is wrong` : `Mark ${label} wrong`}
        title={mine ? "Change your mark" : "Mark wrong"}
        className={cn(
          "inline-flex size-6 shrink-0 items-center justify-center outline-none focus-visible:ring-2 focus-visible:ring-ring",
          mine
            ? "text-destructive hover:bg-destructive/10"
            : "text-muted-foreground/70 hover:bg-destructive/10 hover:text-destructive",
        )}
      >
        {mine ? <Pencil className="size-3.5" /> : <X className="size-4" />}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <PopoverHeader>
          <PopoverTitle>{label} is wrong</PopoverTitle>
          <PopoverDescription>The facilitator sees this reason next to the field.</PopoverDescription>
        </PopoverHeader>
        {offered.length ? (
          <div className="flex flex-wrap gap-1">
            {offered.map((item) => (
              <button
                key={item.text}
                type="button"
                aria-pressed={reason === item.text}
                onClick={() => setText(item.text)}
                className={cn(
                  "border px-1.5 py-0.5 text-left text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  reason === item.text
                    ? "border-destructive bg-destructive/10 text-destructive"
                    : "text-muted-foreground hover:border-foreground/30 hover:text-foreground",
                )}
              >
                {item.text}
              </button>
            ))}
          </div>
        ) : null}
        <Textarea
          autoFocus
          rows={2}
          maxLength={MAX_REASON}
          value={text}
          aria-label="Why it is wrong"
          placeholder="What is wrong with it?"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="flex items-center justify-end gap-2">
          {mine ? (
            <Button
              variant="ghost"
              size="sm"
              className="mr-auto text-muted-foreground"
              disabled={saving}
              onClick={() => run(() => state.remove(mine), "The mark was not removed. Try again.")}
            >
              Remove mark
            </Button>
          ) : null}
          <Button variant="destructive" size="sm" disabled={!reason || saving} onClick={submit}>
            {saving ? "Saving…" : mine ? "Save" : "Mark wrong"}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** In the bottom bar: what has been marked so far, and the way to send it back. */
export function MarkedSummary({ onReject }: { onReject: () => void }) {
  const state = useFieldMarkState();
  const rows = state ? carriedMarks(state.marks, state.mySections) : [];
  if (!state || !rows.length) return null;
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
      <span className="font-medium text-destructive">
        {rows.length === 1 ? "1 field marked" : `${rows.length} fields marked`}
      </span>
      {rows.map((row) => (
        <button
          key={row.path}
          type="button"
          title={row.reason}
          onClick={() => state.open(row.path)}
          className="max-w-40 truncate border border-destructive/30 bg-destructive/5 px-1.5 py-0.5 text-destructive outline-none hover:border-destructive/60 focus-visible:ring-2 focus-visible:ring-ring"
        >
          {row.label}
        </button>
      ))}
      <button
        type="button"
        onClick={onReject}
        className="font-medium text-destructive underline underline-offset-2 outline-none hover:no-underline focus-visible:ring-2 focus-visible:ring-ring"
      >
        Reject with these
      </button>
    </div>
  );
}
