"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { FormError } from "@/components/admin/feedback";
import { ReviewSettingsCards } from "@/components/admin/review-settings";
import { Field } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, ApiError } from "@/lib/api/client";

type State = {
  steps: { key: string; number: number; title: string; roles: string[] }[];
  roles: { code: string; name: string }[];
};

function Matrix({ state }: { state: State }) {
  const client = useQueryClient();
  const [chosen, setChosen] = useState(() =>
    Object.fromEntries(state.steps.map((step) => [step.key, step.roles])),
  );

  const toggle = (step: string, role: string) =>
    setChosen((current) => ({
      ...current,
      [step]: current[step].includes(role)
        ? current[step].filter((item) => item !== role)
        : [...current[step], role],
    }));

  const save = useMutation({
    mutationFn: () =>
      api("settings/review-steps", { method: "PUT", body: { steps: chosen } }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["review-steps"] });
      toast.success("Review steps saved.");
    },
  });

  const unassigned = state.steps.filter((step) => !chosen[step.key].length);
  const changed = state.steps.some(
    (step) =>
      [...chosen[step.key]].sort().join() !== [...step.roles].sort().join(),
  );

  return (
    <>
      <Card className="gap-0 p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Step</TableHead>
                {state.roles.map((role) => (
                  <TableHead key={role.code} className="text-center">
                    {role.name}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {state.steps.map((step) => (
                <TableRow key={step.key}>
                  <TableCell className="font-medium">
                    {step.number}. {step.title}
                  </TableCell>
                  {state.roles.map((role) => (
                    <TableCell key={role.code} className="text-center">
                      <Checkbox
                        aria-label={`${role.name} acts on ${step.title}`}
                        checked={chosen[step.key].includes(role.code)}
                        onCheckedChange={() => toggle(step.key, role.code)}
                      />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
      <FormError error={save.error} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {unassigned.length
            ? `Give a role to: ${unassigned.map((step) => step.title).join(", ")}.`
            : "Everyone can read every step. Each step is approved by its role, and a form moves on when its stage is complete."}
        </p>
        <Button
          disabled={!changed || unassigned.length > 0 || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
    </>
  );
}

type Signers = {
  stages: {
    stage: string;
    label: string;
    membership: string | null;
    candidates: { id: string; name: string; has_signature: boolean }[];
  }[];
};

/** The head whose signature the printed form carries, whoever on the team approved. */
function Signatories() {
  const client = useQueryClient();
  const state = useQuery({
    queryKey: ["signatories"],
    queryFn: () => api<Signers>("settings/signatories"),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, string>) =>
      api("settings/signatories", { method: "PUT", body }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["signatories"] });
      toast.success("Signatory saved.");
    },
    onError: (error) =>
      toast.error(
        error instanceof ApiError ? error.summary : "Could not save.",
      ),
  });

  return (
    <Card className="gap-4 p-5">
      <div>
        <h2 className="font-medium">Signatures on the printed form</h2>
        <p className="text-sm text-muted-foreground">
          Anyone on these teams can approve their steps. The form always carries
          the head&apos;s signature, and the history keeps who approved.
        </p>
      </div>
      {state.data ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {state.data.stages.map((stage) => (
            <Field key={stage.stage} label={`${stage.label} head`}>
              <Listbox
                aria-label={`${stage.label} head`}
                placeholder="Choose who signs"
                value={stage.membership ?? ""}
                onChange={(value) => save.mutate({ [stage.stage]: value })}
                items={stage.candidates.map((person) => ({
                  value: person.id,
                  label: person.has_signature
                    ? person.name
                    : `${person.name} (signature to add)`,
                }))}
              />
              {stage.candidates.some(
                (person) =>
                  person.id === stage.membership && !person.has_signature,
              ) ? (
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  Add their signature under Staff, or they add it under My
                  account. Forms wait at this stage until it is on file.
                </p>
              ) : null}
            </Field>
          ))}
        </div>
      ) : (
        <ListSkeleton />
      )}
    </Card>
  );
}

export default function ReviewStepsPage() {
  const state = useQuery({
    queryKey: ["review-steps"],
    queryFn: () => api<State>("settings/review-steps"),
  });

  return (
    <>
      <PageHeader
        title="Review Steps"
        description="Choose which role approves each step of a form, who signs it, what reviewers tick on each step, when a form counts as late, and the ready-made reject reasons."
      />
      {state.error ? (
        <ErrorState error={state.error} onRetry={() => state.refetch()} />
      ) : state.data ? (
        <Matrix key={state.dataUpdatedAt} state={state.data} />
      ) : (
        <ListSkeleton />
      )}
      <Signatories />
      <ReviewSettingsCards />
    </>
  );
}
