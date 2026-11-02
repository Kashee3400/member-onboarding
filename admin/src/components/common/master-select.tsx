"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { AsyncSelect, type FetchPage } from "@/components/common/async-select";
import { api, type Page } from "@/lib/api/client";

const PAGE_SIZE = 50;

type Master = { id: string; code: string; name: string };
export type MasterKind = "plants" | "mccs" | "bmcs" | "routes" | "mpps";

const WORDS: Record<MasterKind, { one: string; search: string }> = {
  plants: { one: "plant", search: "Search by code or name" },
  mccs: { one: "MCC", search: "Search by code or name" },
  bmcs: { one: "BMC", search: "Search by code or name" },
  routes: { one: "route", search: "Search by code or name" },
  mpps: { one: "MPP", search: "Search by ex code or name" },
};

export const masterLabel = (item: Pick<Master, "code" | "name">) => `${item.code} - ${item.name}`;

/**
 * A picker for a hierarchy master of any size: 50 at a time as you scroll, searched
 * on the server by code or name. Empty means none chosen, which a filter reads as all.
 */
export function MasterSelect({
  kind,
  value,
  onChange,
  filters,
  disabled,
  placeholder = "All",
  clearable = true,
  className,
}: {
  kind: MasterKind;
  /** The chosen item's id, or "". */
  value: string;
  onChange: (id: string) => void;
  /** API filters, such as `{ mcc }` for MPPs or `{ bmc__mcc: mcc }` for routes. */
  filters?: Record<string, string | undefined>;
  disabled?: boolean;
  placeholder?: string;
  clearable?: boolean;
  className?: string;
}) {
  const [picked, setPicked] = useState<Master | null>(null);
  // A value set from outside (a link, a record being edited) still shows its name.
  const known = useQuery({
    queryKey: ["hierarchy", kind, "one", value],
    queryFn: () => api<Master>(`hierarchy/${kind}/${value}`),
    enabled: !!value && picked?.id !== value,
    staleTime: 5 * 60_000,
  });
  const selected = !value ? null : picked?.id === value ? picked : (known.data ?? null);

  const fetchPage: FetchPage<Master> = async ({ search, cursor, signal }) => {
    const page = Number(cursor ?? 1);
    const data = await api<Page<Master>>(`hierarchy/${kind}`, {
      query: { ...filters, q: search, page, page_size: PAGE_SIZE, ordering: "code" },
      signal,
    });
    return { items: data.results, next: data.next ? String(page + 1) : null };
  };

  return (
    <AsyncSelect<Master>
      fetchPage={fetchPage}
      // Keys the cached pages, so one list is never mixed up with another.
      params={{ list: `hierarchy/${kind}`, ...filters }}
      value={selected}
      onChange={(item) => {
        setPicked(item);
        onChange(item?.id ?? "");
      }}
      getValue={(item) => item.id}
      getLabel={masterLabel}
      placeholder={placeholder}
      searchPlaceholder={WORDS[kind].search}
      emptyText={`No ${WORDS[kind].one} matches`}
      pageSize={PAGE_SIZE}
      clearable={clearable}
      disabled={disabled}
      className={className}
    />
  );
}
