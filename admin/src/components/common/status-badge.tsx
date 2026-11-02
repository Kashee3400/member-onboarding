import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";

const TONES: Record<string, keyof typeof TONE_CLASS> = {
  // waiting on someone
  pending_am: "warn",
  pending_cs: "warn",
  pending_finance: "warn",
  pending: "warn",
  processing: "warn",
  queued: "warn",
  invited: "warn",
  // fine
  approved: "good",
  active: "good",
  ready: "good",
  completed: "good",
  // stopped
  rejected: "bad",
  failed: "bad",
  inactive: "bad",
  // nothing to do
  draft: "muted",
  discarded: "muted",
};

const TONE_CLASS = {
  warn: "bg-amber-500/12 text-amber-700 ring-amber-500/25 dark:text-amber-300",
  good: "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:text-emerald-300",
  bad: "bg-red-500/12 text-red-700 ring-red-500/25 dark:text-red-300",
  muted: "bg-muted text-muted-foreground ring-border",
};

/** A status in the same colour on every page: amber waits, green is done, red stopped. */
export function StatusBadge({ status, label, className }: { status: string; label?: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
        TONE_CLASS[TONES[status] ?? "muted"],
        className,
      )}
    >
      {label ?? humanize(status)}
    </span>
  );
}
