"use client";

import { useState, type ReactElement, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/**
 * A confirmation that asks why. Staff actions are logged with their reason
 * (apps/rbac PrivilegedActionLog), so the reason is required unless `optional`.
 */
export function ReasonDialog({
  trigger,
  title,
  description,
  label = "Reason",
  placeholder,
  confirmLabel = "Confirm",
  destructive = false,
  optional = false,
  minLength = 3,
  extra,
  onConfirm,
}: {
  trigger: ReactElement;
  title: string;
  description?: ReactNode;
  label?: string;
  placeholder?: string;
  confirmLabel?: string;
  destructive?: boolean;
  optional?: boolean;
  minLength?: number;
  /** More fields above the reason (a select, a checkbox). */
  extra?: ReactNode;
  onConfirm: (reason: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const ok = optional || reason.trim().length >= minLength;

  const submit = async () => {
    setBusy(true);
    try {
      await onConfirm(reason.trim());
      setOpen(false);
      setReason("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={trigger} />
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <div className="space-y-4">
          {extra}
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="reason">{label}</Label>
            </div>
            <Textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={placeholder}
              rows={4}
              autoFocus
              onKeyDown={(e) => {
                // Ctrl/⌘ + Enter confirms, so a keyboard review never needs the mouse.
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && ok && !busy) {
                  e.preventDefault();
                  void submit();
                }
              }}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={submit} disabled={!ok || busy}>
            {busy ? "Working…" : confirmLabel}
            {!busy ? <span className="ml-1 hidden text-[10px] opacity-70 sm:inline">Ctrl+↵</span> : null}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
