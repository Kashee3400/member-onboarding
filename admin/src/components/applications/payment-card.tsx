"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Upload } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";
import { toast } from "sonner";

import { DatePicker } from "@/components/common/date-picker";
import { Field } from "@/components/common/field";
import { Listbox } from "@/components/common/listbox";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCan } from "@/hooks/use-session";
import { ApiError, api } from "@/lib/api/client";
import { date, rupees } from "@/lib/format";
import type { ApplicationDetail } from "@/lib/types";

import { APPROVE_ALL } from "./constants";

const MODES: Record<string, string> = { cash: "Cash", dd: "DD", online: "Online" };

const message = (error: unknown) => (error instanceof ApiError ? error.summary : "Something went wrong. Try again.");

/** The joining payment. Finance records it; the Area Manager or Finance add the slip. */
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
  const canRecord = application.review_steps.some((step) => step.key === "fee" && step.can_approve);
  const canUpload =
    canRecord || (isFinance && atFinance) || (isAreaManager && application.status === "pending_am");
  const [depositedOn, setDepositedOn] = useState(paid.deposited_on ?? "");
  const [mode, setMode] = useState(paid.mode ?? "cash");
  const fee = application.fee;

  const save = useMutation({
    mutationFn: (body: object) => api(`applications/${id}/payment`, { method: "POST", body }),
    onSuccess: () => {
      toast.success("Payment saved.");
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
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    save.mutate({ ...fields, share_quantity: Number(fields.share_quantity), deposited_on: depositedOn, mode });
  }

  if (!canUpload && !paid.amount) return null;

  return (
    <Card id="section-payment" className="scroll-mt-28 gap-3 p-4">
      <h2 className="text-sm font-semibold">Member fee</h2>
      {canUpload || paid.amount ? (
        <dl className="grid gap-x-5 gap-y-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted-foreground">Admission fee</dt>
            <dd className="tabular-nums">{rupees(fee.admission_fee)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Share quantity</dt>
            <dd className="tabular-nums">{fee.share_quantity}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">SHG member</dt>
            <dd>{fee.is_shg_member ? "Yes" : "No"}</dd>
          </div>
        </dl>
      ) : null}
      {paid.amount ? (
        <p className="flex items-start gap-2 text-sm">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
          <span>
            {rupees(paid.amount)} received by {MODES[paid.mode ?? "cash"] ?? paid.mode}, at {paid.bank_name},{" "}
            {paid.branch_name}
            {paid.bank_address ? `, ${paid.bank_address}` : ""} on {date(paid.deposited_on)}
            {paid.reference ? `, reference ${paid.reference}` : ""}.{" "}
            <span className="text-muted-foreground">Recorded by {paid.recorded_by_name}.</span>
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
          <Button variant="outline" disabled={upload.isPending} onClick={() => file.current?.click()}>
            <Upload /> {upload.isPending ? "Uploading…" : hasProof ? "Replace payment slip" : "Upload payment slip"}
          </Button>
          <p className="text-xs text-muted-foreground">
            A photo or scan of the slip.{hasProof ? " It replaces the earlier one." : ""}
          </p>
        </div>
      ) : null}

      {canRecord ? (
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Field label="Cash / DD">
            <Listbox aria-label="Cash or DD" value={mode} onChange={setMode} items={MODES} />
          </Field>
          <Field label="Bank" htmlFor="pay-bank">
            <Input id="pay-bank" name="bank_name" required defaultValue={paid.bank_name} />
          </Field>
          <Field label="Branch" htmlFor="pay-branch">
            <Input id="pay-branch" name="branch_name" required defaultValue={paid.branch_name} />
          </Field>
          <Field label="Bank address" htmlFor="pay-address" optional>
            <Input id="pay-address" name="bank_address" defaultValue={paid.bank_address} />
          </Field>
          <Field label="Slip or UTR number" htmlFor="pay-reference" optional>
            <Input id="pay-reference" name="reference" defaultValue={paid.reference} />
          </Field>
          <Field label="Share quantity" htmlFor="pay-shares">
            <Input
              id="pay-shares"
              name="share_quantity"
              type="number"
              min={0}
              required
              defaultValue={fee.share_quantity}
            />
          </Field>
          <Field label="Amount (₹)" htmlFor="pay-amount">
            <Input id="pay-amount" name="amount" type="number" min={1} required defaultValue={paid.amount} />
          </Field>
          <Field label="Deposit date">
            <DatePicker value={depositedOn} onChange={setDepositedOn} aria-label="Deposit date" />
          </Field>
          <div className="flex items-end">
            <Button type="submit" variant="outline" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save payment"}
            </Button>
          </div>
        </form>
      ) : null}
    </Card>
  );
}
