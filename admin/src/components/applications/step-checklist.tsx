"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, CircleCheck, ListChecks } from "lucide-react";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ApiError, api } from "@/lib/api/client";
import type { ApplicationDetail, ReviewStep } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Shared with the decision bar, which waits while a tick is still being saved. */
export const checksKey = (id: string) => ["checks", id];

/** The checks of a step this person has not ticked yet. */
export const unticked = (step: ReviewStep) =>
  step.checks.filter((check) => !step.ticked.includes(check));

/**
 * The step's checklist, ticked one line at a time. Each tick is saved at once, so a
 * reload keeps it, and the page shows it straight away while it saves.
 */
export function StepChecklist({
  application,
  step,
}: {
  application: ApplicationDetail;
  step: ReviewStep;
}) {
  const client = useQueryClient();
  const queryKey = ["application", application.id];
  const setTicked = (ticked: (current: string[]) => string[]) =>
    client.setQueryData<ApplicationDetail>(queryKey, (current) =>
      current
        ? {
            ...current,
            review_steps: current.review_steps.map((item) =>
              item.key === step.key
                ? { ...item, ticked: ticked(item.ticked) }
                : item,
            ),
          }
        : current,
    );

  const tick = useMutation({
    mutationKey: checksKey(application.id),
    mutationFn: (body: { text: string; ticked: boolean }) =>
      api<{ step: string; ticked: string[] }>(
        `applications/${application.id}/checks`,
        {
          method: "POST",
          body: { step: step.key, ...body },
        },
      ),
    onMutate: ({ text, ticked }) =>
      setTicked((current) =>
        ticked ? [...current, text] : current.filter((item) => item !== text),
      ),
    // Quick ticks in a row: only the last answer is the whole story.
    onSuccess: (saved) => {
      if (client.isMutating({ mutationKey: checksKey(application.id) }) <= 1)
        setTicked(() => saved.ticked);
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiError
          ? error.summary
          : "The tick was not saved. Try again.",
      );
      client.invalidateQueries({ queryKey });
    },
  });

  // Details proven by a UIDAI-signed Aadhaar QR need no line-by-line check: the list
  // ticks itself once, and the reviewer still looks and approves. Unticking stays.
  const proven =
    step.key === "member" && !!application.aadhaar_check?.full_match;
  const autoTicked = useRef(false);
  useEffect(() => {
    if (!proven || autoTicked.current || step.ticked.length) return;
    autoTicked.current = true;
    for (const check of step.checks) tick.mutate({ text: check, ticked: true });
    // Once per opening of the form; the ticks are saved, so a reload keeps them.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proven]);

  const left = unticked(step).length;
  const done = left === 0;
  return (
    <Card
      className={cn(
        "gap-2 p-4",
        done ? "border-emerald-500/40" : "border-amber-500/40",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          {done ? (
            <CircleCheck
              className="size-4 text-emerald-600 dark:text-emerald-400"
              aria-hidden
            />
          ) : (
            <ListChecks
              className="size-4 text-amber-600 dark:text-amber-400"
              aria-hidden
            />
          )}
          Checklist
        </h3>
        <span className="text-xs text-muted-foreground tabular-nums">
          {done
            ? "All checked. You can approve this step."
            : `${step.checks.length - left} of ${step.checks.length} ticked`}
        </span>
      </div>
      {proven ? (
        <p className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400">
          <BadgeCheck className="size-3.5" /> Ticked for you: every detail
          matches the UIDAI-signed Aadhaar QR.
        </p>
      ) : null}
      <ul className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
        {step.checks.map((check) => {
          const on = step.ticked.includes(check);
          return (
            <li key={check}>
              <label className="flex cursor-pointer items-start gap-2.5 py-0.5 text-sm">
                <Checkbox
                  className="mt-0.5"
                  checked={on}
                  onCheckedChange={(checked) =>
                    tick.mutate({ text: check, ticked: !!checked })
                  }
                />
                <span className={cn(on && "text-muted-foreground")}>
                  {check}
                </span>
              </label>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/** What the approver ticked, as the checks were worded then. */
export function CheckedList({ step }: { step: ReviewStep }) {
  if (!step.approved_checks.length) return null;
  return (
    <div className="border border-emerald-500/30 bg-emerald-500/8 px-4 py-2.5 text-sm">
      <p className="font-medium">Checked by {step.approved_by_name}</p>
      <ul className="mt-1 space-y-0.5">
        {step.approved_checks.map((check) => (
          <li
            key={check}
            className="flex items-start gap-2 text-muted-foreground"
          >
            <CircleCheck
              className="mt-0.5 size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400"
              aria-hidden
            />
            {check}
          </li>
        ))}
      </ul>
    </div>
  );
}
