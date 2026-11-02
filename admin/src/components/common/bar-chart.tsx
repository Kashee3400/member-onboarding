"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";

/**
 * A light bar chart for a daily series — no chart library. Hovering a bar shows
 * its day and value; long series thin out their date labels.
 */
export function BarChart({
  data,
  format = (v) => v.toLocaleString("en-IN"),
  height = 180,
  className,
}: {
  data: { label: string; value: number }[];
  format?: (v: number) => string;
  height?: number;
  className?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...data.map((d) => d.value), 0) || 1;
  const every = Math.max(1, Math.ceil(data.length / 8));
  const shown = hover !== null ? data[hover] : null;
  const total = data.reduce((n, d) => n + d.value, 0);

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-baseline justify-between text-xs text-muted-foreground">
        <span>{shown ? shown.label : `${data.length} days`}</span>
        <span className="font-medium text-foreground tabular-nums">
          {shown ? format(shown.value) : `Total ${format(total)}`}
        </span>
      </div>
      <div
        className="flex items-end gap-[2px] border-b"
        style={{ height }}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label={`Bar chart, total ${format(total)}`}
      >
        {data.map((d, i) => (
          <div key={d.label} className="group flex h-full min-w-0 flex-1 items-end" onMouseEnter={() => setHover(i)}>
            <div
              className={cn(
                "w-full rounded-t-sm bg-primary/70 transition-colors group-hover:bg-primary",
                hover !== null && hover !== i && "bg-primary/35",
              )}
              style={{ height: `${Math.max((d.value / max) * 100, d.value > 0 ? 2 : 0)}%` }}
            />
          </div>
        ))}
      </div>
      <div className="flex gap-[2px] text-[10px] text-muted-foreground">
        {data.map((d, i) => (
          <span key={d.label} className="min-w-0 flex-1 overflow-visible whitespace-nowrap">
            {i % every === 0 ? d.label.slice(5) : ""}
          </span>
        ))}
      </div>
    </div>
  );
}
