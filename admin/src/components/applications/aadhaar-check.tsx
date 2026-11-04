"use client";

import {
  BadgeCheck,
  CircleAlert,
  Keyboard,
  QrCode,
  ShieldAlert,
} from "lucide-react";

import { Card } from "@/components/ui/card";
import type {
  AadhaarCheck,
  ApplicationDetail,
  ApplicationDocument,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const fileUrl = (id: string) => `/api/backend/documents/${id}/file`;

const GENDERS: Record<string, string> = {
  female: "Female",
  male: "Male",
  other: "Other",
};
const RELATIONS: Record<string, string> = {
  husband: "Husband",
  father: "Father",
  guardian: "Guardian",
};

function shown(field: string, value: string) {
  if (!value) return "—";
  if (field === "gender") return GENDERS[value] ?? value;
  if (field === "relation_type") return RELATIONS[value] ?? value;
  if (field === "date_of_birth" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-");
    return `${day}/${month}/${year}`;
  }
  return value;
}

function Headline({ check }: { check: AadhaarCheck | null }) {
  if (!check) {
    return (
      <p className="flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-400">
        <Keyboard className="size-4" /> Entered by hand: check the details
        against the Aadhaar photos.
      </p>
    );
  }
  if (check.status === "invalid") {
    return (
      <p className="flex items-center gap-2 text-sm font-medium text-destructive">
        <ShieldAlert className="size-4" /> The Aadhaar QR&apos;s signature is not
        UIDAI&apos;s. It may have been altered.
      </p>
    );
  }
  if (check.status === "unsigned") {
    return (
      <p className="flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-400">
        <QrCode className="size-4" /> Read from an older Aadhaar QR, which
        carries no signature: check by eye.
      </p>
    );
  }
  return (
    <p
      className={cn(
        "flex items-center gap-2 text-sm font-medium",
        check.full_match
          ? "text-emerald-700 dark:text-emerald-400"
          : "text-amber-700 dark:text-amber-400",
      )}
    >
      {check.full_match ? (
        <BadgeCheck className="size-4" />
      ) : (
        <CircleAlert className="size-4" />
      )}
      {check.full_match
        ? "Verified with UIDAI's signature, and every detail matches the Aadhaar."
        : "Verified with UIDAI's signature, but some details differ from the Aadhaar."}
    </p>
  );
}

/**
 * The member's Aadhaar QR beside what the form says, so step 1 is checked at a glance
 * instead of letter by letter. Fields that differ show in red.
 */
export function AadhaarCheckCard({
  application,
  documents,
}: {
  application: ApplicationDetail;
  documents: ApplicationDocument[];
}) {
  const check = application.aadhaar_check;
  const profile = documents.find(
    (document) => document.document_type === "photo",
  );
  return (
    <Card className="gap-4 p-5">
      <div className="space-y-1">
        <h3 className="text-sm font-semibold">Aadhaar check</h3>
        <Headline check={check} />
        {check ? (
          <p className="text-xs text-muted-foreground">
            {check.source === "scan"
              ? "Scanned"
              : "Read from the Aadhaar photo"}
            {check.checked_by_name ? ` by ${check.checked_by_name}` : ""}
            {check.consent ? ", with the member's consent" : ""}.
          </p>
        ) : null}
      </div>
      {check ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="overflow-x-auto border">
            <table className="w-full text-sm">
              <thead className="bg-muted text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-1.5 font-medium">Detail</th>
                  <th className="px-3 py-1.5 font-medium">In the form</th>
                  <th className="px-3 py-1.5 font-medium">On the Aadhaar</th>
                  <th className="w-10 px-3 py-1.5" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {check.fields.map((item) => (
                  <tr
                    key={item.field}
                    className={cn(
                      item.match === false &&
                        "bg-destructive/5 text-destructive",
                    )}
                  >
                    <td className="px-3 py-1.5 text-muted-foreground">
                      {item.label}
                    </td>
                    <td className="px-3 py-1.5">
                      {shown(item.field, item.form)}
                    </td>
                    <td className="px-3 py-1.5">
                      {shown(item.field, item.aadhaar)}
                    </td>
                    <td className="px-3 py-1.5 text-center">
                      {item.match === null ? (
                        <span
                          className="text-muted-foreground"
                          title="The Aadhaar does not say"
                        >
                          –
                        </span>
                      ) : item.match ? (
                        <BadgeCheck
                          className="inline size-4 text-emerald-600"
                          aria-label="Matches"
                        />
                      ) : (
                        <CircleAlert
                          className="inline size-4"
                          aria-label="Differs"
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {check.has_photo ? (
            <div className="flex gap-3">
              <figure className="space-y-1">
                {/* Private, authenticated files, so the image optimizer cannot fetch them. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/api/backend/applications/${application.id}/aadhaar-photo`}
                  alt="Photo on the Aadhaar"
                  className="h-32 w-24 border bg-muted object-cover"
                />
                <figcaption className="text-center text-xs text-muted-foreground">
                  On the Aadhaar
                </figcaption>
              </figure>
              {profile ? (
                <figure className="space-y-1">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={fileUrl(profile.id)}
                    alt="Profile photo"
                    className="h-32 w-24 border bg-muted object-cover"
                  />
                  <figcaption className="text-center text-xs text-muted-foreground">
                    Profile photo
                  </figcaption>
                </figure>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
