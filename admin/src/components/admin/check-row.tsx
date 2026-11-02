"use client";

import type { ReactNode } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

/** A checkbox with room for what it means. The whole row is the target. */
export function CheckRow({
  label,
  hint,
  checked,
  disabled,
  onChange,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
}) {
  return (
    <label
      className={cn(
        "flex items-start gap-2.5 px-2 py-1.5 text-sm transition-colors",
        disabled ? "cursor-not-allowed opacity-70" : "cursor-pointer hover:bg-muted/60",
        className,
      )}
    >
      <Checkbox
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onChange(Boolean(value))}
        className="mt-0.5"
      />
      <span className="min-w-0">
        <span className="block">{label}</span>
        {hint ? <span className="block text-xs text-muted-foreground">{hint}</span> : null}
      </span>
    </label>
  );
}
