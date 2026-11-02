"use client";

import { MasterSelect } from "@/components/common/master-select";

/** MPPs, searched by ex code or name, optionally only one MCC's or one route's. */
export function MppSelect({
  value,
  onChange,
  mcc,
  route,
  disabled,
  placeholder,
  className,
}: {
  value: string;
  onChange: (id: string) => void;
  mcc?: string;
  route?: string;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}) {
  return (
    <MasterSelect
      kind="mpps"
      value={value}
      onChange={onChange}
      filters={{ mcc, route }}
      disabled={disabled}
      placeholder={placeholder}
      className={className}
    />
  );
}
