"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ReasonDialog } from "@/components/common/reason-dialog";
import { DoubleConfirm } from "@/components/common/double-confirm";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";

/**
 * One action run on every selected row of a DataTable, one after another, with
 * a running count and a summary of what didn't work. Rows the action doesn't
 * apply to are skipped (`applies`). With `reason`, a single reason is asked once
 * and sent with every row — the audit log gets it for each.
 */
export function BulkAction<T>({
  rows,
  applies = () => true,
  label,
  icon: Icon,
  run,
  done,
  clear,
  reason,
  confirm,
  destructive = false,
}: {
  rows: T[];
  applies?: (row: T) => boolean;
  label: string;
  icon?: LucideIcon;
  run: (row: T, reason: string) => Promise<unknown>;
  /** e.g. "held" → "4 held". */
  done: string;
  clear: () => void;
  reason?: { title: string; description: string; placeholder?: string };
  /** Asks before running, for an action without a reason. */
  confirm?: { title: string; description: string };
  destructive?: boolean;
}) {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const targets = rows.filter(applies);
  if (!targets.length) return null;

  const go = async (why: string) => {
    setBusy(true);
    const id = toast.loading(`${label}: 0 of ${targets.length}…`);
    let ok = 0;
    const failed: string[] = [];
    for (const [i, row] of targets.entries()) {
      try {
        await run(row, why);
        ok += 1;
      } catch (e) {
        failed.push(e instanceof ApiError ? e.message : "didn't work");
      }
      toast.loading(`${label}: ${i + 1} of ${targets.length}…`, { id });
    }
    setBusy(false);
    client.invalidateQueries({ queryKey: ["queue"] });
    client.invalidateQueries({ queryKey: ["summary"] });
    if (failed.length) {
      toast.error(`${ok} ${done}, ${failed.length} didn't: ${[...new Set(failed)].slice(0, 2).join("; ")}`, { id });
    } else {
      toast.success(`${ok} ${done}`, { id });
    }
    if (ok) clear();
  };

  const text = `${label}${targets.length !== rows.length ? ` (${targets.length})` : ""}`;
  if (reason) {
    return (
      <ReasonDialog
        trigger={
          <Button size="sm" variant={destructive ? "destructive" : "outline"} disabled={busy}>
            {Icon ? <Icon /> : null} {text}
          </Button>
        }
        title={reason.title}
        description={`${reason.description} It applies to ${targets.length} selected.`}
        placeholder={reason.placeholder}
        confirmLabel={label}
        destructive={destructive}
        onConfirm={go}
      />
    );
  }
  if (confirm) {
    return (
      <>
        <Button size="sm" disabled={busy} onClick={() => setAsking(true)}>
          {Icon ? <Icon /> : null} {text}
        </Button>
        <DoubleConfirm
          open={asking}
          onOpenChange={setAsking}
          title={confirm.title}
          description={confirm.description}
          finalTitle="Are you sure?"
          finalDescription={`This can't be undone. It applies to ${targets.length} selected.`}
          action={`Yes, ${label.toLowerCase()}`}
          onConfirm={() => go("")}
        />
      </>
    );
  }
  return (
    <Button size="sm" variant={destructive ? "destructive" : "outline"} disabled={busy} onClick={() => go("")}>
      {Icon ? <Icon /> : null} {text}
    </Button>
  );
}
