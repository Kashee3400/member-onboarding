"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, TriangleAlert, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { DatePicker } from "@/components/common/date-picker";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useCan } from "@/hooks/use-session";
import { ApiError, api } from "@/lib/api/client";
import { date, rupees } from "@/lib/format";
import type { ApplicationDetail } from "@/lib/types";

import { APPROVE_ALL } from "./constants";

const message = (error: unknown) =>
  error instanceof ApiError
    ? error.summary
    : "Something went wrong. Try again.";

/**
 * The fee's deposit. Every fee goes into the organization's one collection account,
 * and the amount and mode are what the facilitator collected, so Finance says only
 * when it was deposited. The Area Manager or Finance add the slip.
 */
export function PaymentCard({
  application,
  hasProof,
  onChange,
}: {
  application: ApplicationDetail;
  hasProof: boolean;
  onChange: () => void;
}) {
  const id = application.id;
  const file = useRef<HTMLInputElement>(null);
  const paid = application.payment;
  const atFinance = application.status === "pending_finance";
  const actsOnAll = useCan(APPROVE_ALL);
  const isFinance = useCan("applications.approve_finance") || actsOnAll;
  const isAreaManager = useCan("applications.approve_am") || actsOnAll;
  const canRecord = application.review_steps.some(
    (step) => step.key === "fee" && step.can_approve,
  );
  const canUpload =
    canRecord ||
    (isFinance && atFinance) ||
    (isAreaManager && application.status === "pending_am");

  const upload = useMutation({
    mutationFn: (proof: File) => {
      const body = new FormData();
      body.append("document_type", "payment_proof");
      body.append("file", proof);
      return api(`applications/${id}/documents`, { method: "POST", body });
    },
    onSuccess: () => {
      toast.success("Payment slip uploaded.");
      onChange();
    },
    onError: (error) => toast.error(message(error)),
    onSettled: () => {
      if (file.current) file.current.value = "";
    },
  });

  if (!canUpload && !paid.amount) return null;

  return (
    <Card id="section-payment" className="scroll-mt-28 gap-3 p-4">
      <h2 className="text-sm font-semibold">Payment slip</h2>
      {paid.amount ? (
        <p className="flex items-start gap-2 text-sm">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
          <span>
            {rupees(paid.amount)} deposited on {date(paid.deposited_on)} into{" "}
            {paid.bank_name}, {paid.branch_name}.{" "}
            <span className="text-muted-foreground">
              Recorded by {paid.recorded_by_name}.
            </span>
          </span>
        </p>
      ) : null}

      {canUpload ? (
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={file}
            type="file"
            accept="image/jpeg,image/png"
            className="sr-only"
            aria-label="Payment slip"
            onChange={(event) => {
              const proof = event.target.files?.[0];
              if (proof) upload.mutate(proof);
            }}
          />
          <Button
            variant="outline"
            disabled={upload.isPending}
            onClick={() => file.current?.click()}
          >
            <Upload />{" "}
            {upload.isPending
              ? "Uploading…"
              : hasProof
                ? "Replace payment slip"
                : "Upload payment slip"}
          </Button>
          <p className="text-xs text-muted-foreground">
            A photo or scan of the slip.
            {hasProof ? " It replaces the earlier one." : ""}
          </p>
        </div>
      ) : null}
    </Card>
  );
}

/**
 * The deposit date, picked by Finance on the day the money reached the collection
 * account. Everything else about the fee is already known, so this is all they enter.
 */
export function DepositDate({
  application,
}: {
  application: ApplicationDetail;
}) {
  const client = useQueryClient();
  const paid = application.payment;
  const bank = application.fee.collection_bank;
  const canRecord = application.review_steps.some(
    (step) => step.key === "fee" && step.can_approve,
  );
  const [value, setValue] = useState(paid.deposited_on ?? "");
  const save = useMutation({
    mutationFn: () =>
      api(`applications/${application.id}/payment`, {
        method: "POST",
        body: { deposited_on: value },
      }),
    onSuccess: () => {
      toast.success("Deposit date saved.");
      client.invalidateQueries({ queryKey: ["application", application.id] });
      client.invalidateQueries({ queryKey: ["queue"] });
    },
    onError: (error) => toast.error(message(error)),
  });

  if (!canRecord) {
    return (
      <div className="space-y-1">
        <p className="text-sm font-medium">Deposit date</p>
        <p className="border bg-muted/40 px-3 py-2.5 text-sm">
          {paid.deposited_on ? date(paid.deposited_on) : "—"}
        </p>
        {paid.deposited_on ? null : (
          <p className="text-xs text-muted-foreground">
            Finance picks this at the Finance stage.
          </p>
        )}
      </div>
    );
  }
  if (!bank.bank_name) {
    return (
      <div className="space-y-1">
        <p className="text-sm font-medium">Deposit date</p>
        <p className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400">
          <TriangleAlert className="size-3.5" /> First set the collection bank
          under{" "}
          <Link
            href="/admin/member-code"
            className="underline underline-offset-2"
          >
            Member Code
          </Link>
          .
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <p className="text-sm font-medium">Deposit date</p>
      <div className="flex gap-2">
        <DatePicker
          value={value}
          onChange={setValue}
          aria-label="Deposit date"
        />
        <Button
          type="button"
          disabled={save.isPending || !value || value === paid.deposited_on}
          onClick={() => save.mutate()}
        >
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        The day the payment reached the account.
      </p>
    </div>
  );
}
