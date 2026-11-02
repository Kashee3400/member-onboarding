"use client";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function StatusTabs<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string; count?: number }[];
}) {
  return (
    // Many options scroll inside their own row instead of pushing the page wide.
    <Tabs
      value={value}
      onValueChange={(v) => onChange(v as T)}
      className="max-w-full min-w-0 overflow-x-auto overflow-y-hidden [scrollbar-width:thin]"
    >
      <TabsList className="shrink-0">
        {options.map((o) => (
          <TabsTrigger key={o.value} value={o.value}>
            {o.label}
            {o.count ? (
              <span className="ml-1.5 bg-muted px-1.5 text-[11px] font-semibold text-muted-foreground tabular-nums">
                {o.count}
              </span>
            ) : null}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
