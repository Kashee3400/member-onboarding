"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, TriangleAlert, Upload } from "lucide-react";
import Link from "next/link";
import { type FormEvent, useRef, useState } from "react";
import { toast } from "sonner";

import { DatePicker } from "@/components/common/date-picker";
import { Field } from "@/components/common/field";
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
  const bank = application.fee.collection_bank;
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
  const [depositedOn, setDepositedOn] = useState(paid.deposited_on ?? "");

  const save = useMutation({
    mutationFn: (body: object) =>
      api(`applications/${id}/payment`, { method: "POST", body }),
    onSuccess: () => {
      toast.success("Deposit saved.");
      onChange();
    },
    onError: (error) => toast.error(message(error)),
  });
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

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!depositedOn) {
      toast.error("Choose the deposit date.");
      return;
    }
    save.mutate({ deposited_on: depositedOn });
  }

  if (!canUpload && !paid.amount) return null;

  return (
    <Card id="section-payment" className="scroll-mt-28 gap-3 p-4">
      <h2 className="text-sm font-semibold">Deposit</h2>
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

      {canRecord ? (
        bank.bank_name ? (
          <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
            <Field label="Deposit date">
              <DatePicker
                value={depositedOn}
                onChange={setDepositedOn}
                aria-label="Deposit date"
              />
            </Field>
            <Button type="submit" variant="outline" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save deposit"}
            </Button>
            <p className="basis-full text-xs text-muted-foreground">
              Into {bank.bank_name}, {bank.branch_name}
              {bank.bank_address ? `, ${bank.bank_address}` : ""}: the
              organization&apos;s collection account.
            </p>
          </form>
        ) : (
          <p className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
            <TriangleAlert className="size-4" /> Set the bank member fees are
            paid into, under{" "}
            <Link
              href="/admin/member-code"
              className="underline underline-offset-2"
            >
              Member Code
            </Link>
            , before recording a deposit.
          </p>
        )
      ) : null}
    </Card>
  );
}
