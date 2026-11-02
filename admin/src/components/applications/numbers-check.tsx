"use client";

import { useQuery } from "@tanstack/react-query";

import { useCan } from "@/hooks/use-session";
import { api } from "@/lib/api/client";
import { date } from "@/lib/format";
import type { ApplicationDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

import { APPROVE_ALL } from "./constants";
import { CopyButton } from "./copy-button";

export type SensitiveNumbers = { aadhaar: string; account: string; full: boolean };

const inGroups = (number: string) => number.replace(/(\d{4})(?=\d)/g, "$1 ");

/** Approvers check these against the photos, so they get the whole numbers. Others, the last digits. */
export function useSensitiveNumbers(id: string, application: ApplicationDetail | undefined): SensitiveNumbers {
  const manager = useCan("applications.approve_am");
  const legal = useCan("applications.approve_cs");
  const finance = useCan("applications.approve_finance");
  const admin = useCan(APPROVE_ALL);
  const hasNumbers = !!(application?.aadhaar_last4 || application?.account_last4);

  const { data } = useQuery({
    queryKey: ["application-numbers", id],
    queryFn: () =>
      api<{ aadhaar_number: string; account_number: string }>(`applications/${id}/numbers`, { method: "POST" }),
    enabled: (manager || legal || finance || admin) && hasNumbers,
    // One look per opening: each is written to the audit log, and nothing stays in memory after.
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  });

  return {
    aadhaar: data?.aadhaar_number
      ? inGroups(data.aadhaar_number)
      : application?.aadhaar_last4
        ? `XXXX XXXX ${application.aadhaar_last4}`
        : "",
    account: data?.account_number || (application?.account_last4 ? `XXXXXX${application.account_last4}` : ""),
    full: !!data,
  };
}

/**
 * What to hold against a document, shown above it when enlarged: the name, date of
 * birth and number for an Aadhaar card, the holder, IFSC and number for a passbook.
 */
export function noteFor(
  documentType: string,
  numbers: SensitiveNumbers,
  application?: ApplicationDetail,
): string | undefined {
  const applicant = application?.data.applicant ?? {};
  const bank = application?.data.bank ?? {};
  const parts =
    documentType === "aadhaar_front" || documentType === "aadhaar_back"
      ? [applicant.full_name, applicant.date_of_birth && date(String(applicant.date_of_birth)), numbers.aadhaar]
      : documentType === "passbook"
        ? [bank.holder_name, bank.ifsc, numbers.account]
        : documentType === "photo" || documentType === "member_signature" || documentType === "member_thumbprint"
          ? [applicant.full_name]
          : [];
  return parts.filter(Boolean).join("  ·  ") || undefined;
}

export function NumbersCheck({ numbers, className }: { numbers: SensitiveNumbers; className?: string }) {
  if (!numbers.aadhaar && !numbers.account) return null;
  return (
    <dl className={cn("divide-y border bg-card text-sm", className)}>
      {(
        [
          ["Aadhaar", numbers.aadhaar],
          ["Bank account", numbers.account],
        ] as const
      ).map(([label, value]) =>
        value ? (
          <div key={label} className="flex items-center justify-between gap-2 px-2.5 py-1.5">
            <div className="min-w-0">
              <dt className="text-[11px] text-muted-foreground">{label}</dt>
              <dd className="truncate font-mono tabular-nums">{value}</dd>
            </div>
            {numbers.full ? <CopyButton value={value.replaceAll(" ", "")} label={`Copy ${label}`} /> : null}
          </div>
        ) : null,
      )}
    </dl>
  );
}
