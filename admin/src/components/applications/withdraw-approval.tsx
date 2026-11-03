"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Undo2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api/client";
import type { ApplicationDetail, ReviewStep } from "@/lib/types";

/**
 * Takes back a step approved by mistake. Offered only while the form is still at the
 * stage it was approved in, to whoever approved it (and to the organization admin).
 */
export function WithdrawApproval({ application, step }: { application: ApplicationDetail; step: ReviewStep }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const withdraw = useMutation({
    mutationFn: () =>
      api<ApplicationDetail>(`applications/${application.id}/steps/${step.key}/withdraw`, { method: "POST" }),
    onSuccess: () => {
      setOpen(false);
      toast.success(`Approval of step ${step.number}, ${step.title}, withdrawn. The step is open again.`);
      client.invalidateQueries({ queryKey: ["application", application.id] });
      client.invalidateQueries({ queryKey: ["queue"] });
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.summary : "Something went wrong. Try again."),
  });

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Undo2 /> Withdraw approval
      </Button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Withdraw the approval of step {step.number}, {step.title}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Approved by {step.approved_by_name}. The step opens again and needs to be approved before the form can move
              on. This is written to the form&apos;s audit log.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={withdraw.isPending}>Keep it approved</AlertDialogCancel>
            <Button variant="destructive" disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>
              {withdraw.isPending ? "Withdrawing…" : "Withdraw approval"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
