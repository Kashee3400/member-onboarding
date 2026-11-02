"use client";

import { DatePicker, DateRangePicker } from "@/components/common/date-picker";

const clean = (v: string | undefined) => (v && v !== "__all" ? v : "");

/** A date filter for a table (`YYYY-MM-DD` in the URL; empty is no limit). */
export function DateFilter({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | undefined;
  onChange: (v: string | undefined) => void;
}) {
  return (
    <DatePicker
      size="sm"
      value={clean(value)}
      onChange={(v) => onChange(v || undefined)}
      placeholder={label}
      aria-label={label}
    />
  );
}

/**
 * The From–To filter of a table, as one box with quick picks. Writes the `from`
 * and `to` filters (or the keys given) together.
 */
export function DateRangeFilter({
  filters,
  setFilters,
  fromKey = "from",
  toKey = "to",
  placeholder = "Any date",
}: {
  filters: Record<string, string | undefined>;
  setFilters: (values: Record<string, string | undefined>) => void;
  fromKey?: string;
  toKey?: string;
  placeholder?: string;
}) {
  return (
    <DateRangePicker
      size="sm"
      from={clean(filters[fromKey])}
      to={clean(filters[toKey])}
      onChange={(r) => setFilters({ [fromKey]: r.from || undefined, [toKey]: r.to || undefined })}
      placeholder={placeholder}
      aria-label="Dates"
    />
  );
}
