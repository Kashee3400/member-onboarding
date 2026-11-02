"use client";

import { useState, type ReactNode } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

/**
 * Asks twice, for what can't be taken back. The first question explains; the second
 * is a separate moment, so that Enter pressed twice by habit is the only quick way through.
 */
export function DoubleConfirm({
  open,
  onOpenChange,
  title,
  description,
  body,
  canContinue = true,
  finalTitle,
  finalDescription,
  action,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  /** Anything to settle before going on, such as which steps were checked. */
  body?: ReactNode;
  canContinue?: boolean;
  finalTitle: string;
  finalDescription: ReactNode;
  action: string;
  onConfirm: () => void;
}) {
  const [sure, setSure] = useState(false);
  const change = (next: boolean) => {
    if (!next) setSure(false);
    onOpenChange(next);
  };

  return (
    <AlertDialog open={open} onOpenChange={change}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{sure ? finalTitle : title}</AlertDialogTitle>
          <AlertDialogDescription>{sure ? finalDescription : description}</AlertDialogDescription>
        </AlertDialogHeader>
        {sure ? null : body}
        <AlertDialogFooter>
          {sure ? (
            <>
              <Button variant="outline" onClick={() => setSure(false)}>
                Back
              </Button>
              <AlertDialogAction
                autoFocus
                onClick={() => {
                  change(false);
                  onConfirm();
                }}
              >
                {action}
              </AlertDialogAction>
            </>
          ) : (
            <>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <Button autoFocus disabled={!canContinue} onClick={() => setSure(true)}>
                Continue
              </Button>
            </>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
